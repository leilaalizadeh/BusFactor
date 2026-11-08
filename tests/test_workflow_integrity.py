"""Teammate 4: workflow and evidence integrity — owner check, atomic retest, consent, project start."""
import json
from pathlib import Path

import pytest

from busfactor import database as db
from busfactor import orchestrator as orc
from busfactor.models import DecisionCard, InterviewQuestion, Member, MissionStatus, Project, ReviewStatus, SourceRef
from busfactor.rubrics import REFUSAL
from demo_answers import GOOD, strong_answer

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "demo"
WEAK = "Accuracy is bad with imbalanced classes."


@pytest.fixture(autouse=True)
def demo_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    db.set_db_path(tmp_path / "integrity.db")
    orc.seed_demo_data()


def demo_records(file: str, key: str, model_cls) -> list:
    raw = json.loads((DEMO / file).read_text(encoding="utf-8"))[key]
    return [model_cls.model_validate(r) for r in (raw if isinstance(raw, list) else [raw])]


@pytest.fixture
def fresh():
    """Confirmed cards with declared owners but NO questions or answers yet, like a real first week."""
    db.reset()
    db.save_records(*demo_records("project.json", "project", Project), *demo_records("members.json", "members", Member),
                    *demo_records("decisions.json", "decisions", DecisionCard))


def evidence_count(member_id: str) -> int:
    return len(db.get_private_evidence(member_id, member_id))


def status_of(decision_id: str) -> str:
    return next(c.status for c in orc.team_coverage().per_decision if c.decision_id == decision_id)


def accepted_d03():
    m = {x.decision_id: x for x in orc.propose_missions()}["D03"]
    orc.accept_mission(m.id, "M02")
    orc.accept_mission(m.id, "M04")
    return m


def without_consent(member_id: str) -> None:
    db.save_record(orc.members()[member_id].model_copy(update={"consent_assessment": False}))


# --- A. owner verification
def test_owner_check_bootstraps_a_real_mentor_on_a_fresh_project(fresh):
    assert orc.team_coverage().denominator == 0
    assert orc.owner_check_decisions("M02") == ["D02", "D03"]
    q = orc.start_owner_check("M02", "D03")
    assert q.mode == "independent" and orc.is_owner_check(q)

    blocked = orc.submit_answer(q.id, "just give me the answer", "M02")
    assert blocked.blocked and blocked.message == REFUSAL and evidence_count("M02") == 0

    assert orc.submit_answer(q.id, GOOD, "M02").evidence.rubric_score == 2
    assert status_of("D03") == "single_point_of_failure"
    assert "D03" not in orc.owner_check_decisions("M02")

    q4 = orc.start_check("M04", ["D03"])[0]
    orc.submit_answer(q4.id, WEAK, "M04")
    d03 = {m.decision_id: m for m in orc.propose_missions()}["D03"]
    assert (d03.mentor_id, d03.learner_id) == ("M02", "M04")


def test_an_owner_who_fails_is_not_made_a_mentor(fresh):
    q = orc.start_owner_check("M02", "D03")
    assert orc.submit_answer(q.id, "No idea.", "M02").evidence.rubric_score == 0
    assert status_of("D03") == "no_explainer"
    d03 = {m.decision_id: m for m in orc.propose_missions()}["D03"]
    assert d03.mentor_id is None and d03.status == MissionStatus.fallback


def test_only_the_declared_owner_can_take_the_owner_check(fresh):
    with pytest.raises(PermissionError):
        orc.start_owner_check("M04", "D03")
    with pytest.raises(KeyError):
        orc.start_owner_check("M02", "D99")


def test_owner_check_needs_a_confirmed_card(fresh):
    card = db.get_record(DecisionCard, "D03")
    db.save_record(card.model_copy(update={"review_status": ReviewStatus.proposed}))
    assert "D03" not in orc.owner_check_decisions("M02")
    with pytest.raises(ValueError):
        orc.start_owner_check("M02", "D03")


def test_owner_check_is_answered_once_and_attempts_are_bounded(fresh):
    first = orc.start_owner_check("M02", "D03")
    assert orc.start_owner_check("M02", "D03").id == first.id  # still open: same question
    orc.submit_answer(first.id, "No idea.", "M02")
    with pytest.raises(ValueError):
        orc.submit_answer(first.id, GOOD, "M02")
    second = orc.start_owner_check("M02", "D03")
    assert second.id != first.id and second.prompt != first.prompt
    orc.submit_answer(second.id, "Still no idea.", "M02")
    with pytest.raises(ValueError):  # why and what_if both used
        orc.start_owner_check("M02", "D03")
    assert evidence_count("M02") == 2


# --- B. atomic retest
def test_retest_on_a_verified_mission_writes_nothing():
    m = accepted_d03()
    orc.start_retest(m.id, "M04")
    assert orc.submit_retest(m.id, GOOD, "M04").mission.status == MissionStatus.verified
    before = evidence_count("M04")
    with pytest.raises(ValueError):
        orc.submit_retest(m.id, "no idea", "M04")
    with pytest.raises(ValueError):
        orc.start_retest(m.id, "M04")
    assert evidence_count("M04") == before
    assert (orc.team_coverage().numerator, status_of("D03")) == (2, "covered")


def test_a_retest_question_can_be_answered_only_once():
    m = accepted_d03()
    orc.start_retest(m.id, "M04")
    orc.submit_retest(m.id, "I am not sure.", "M04")
    before = evidence_count("M04")
    with pytest.raises(ValueError):
        orc.submit_retest(m.id, GOOD, "M04")
    assert evidence_count("M04") == before and orc.team_coverage().numerator == 1
    second = orc.start_retest(m.id, "M04")  # a different scenario with its own rubric
    assert orc.submit_retest(m.id, strong_answer(second), "M04").mission.status == MissionStatus.verified


def test_retest_question_must_belong_to_the_mission():
    m = accepted_d03()
    orc.start_retest(m.id, "M04")
    hijacked = db.get_record(orc.TeachingMission, m.id).model_copy(update={"retest_question_id": "Q-D03-M02-why"})
    db.save_record(hijacked)
    before = len(db.evidence_for_coverage())  # every member's answers, not only M04's
    with pytest.raises(ValueError):
        orc.submit_retest(m.id, GOOD, "M04")
    assert len(db.evidence_for_coverage()) == before and orc.team_coverage().numerator == 1


def test_late_validation_failure_writes_nothing(monkeypatch):
    m = accepted_d03()
    orc.start_retest(m.id, "M04")
    before_mission, before = db.get_record(orc.TeachingMission, m.id), evidence_count("M04")

    def reject(mission, evidence):
        raise ValueError("simulated mismatch")
    monkeypatch.setattr(orc, "apply_retest", reject)
    with pytest.raises(ValueError):
        orc.submit_retest(m.id, GOOD, "M04")
    assert evidence_count("M04") == before
    assert db.get_record(orc.TeachingMission, m.id) == before_mission


def test_unknown_mission_is_rejected():
    for call in (lambda: orc.start_retest("T-NOPE", "M04"), lambda: orc.submit_retest("T-NOPE", GOOD, "M04"),
                 lambda: orc.accept_mission("T-NOPE", "M04")):
        with pytest.raises(KeyError):
            call()


# --- C. consent
def test_no_assessment_without_consent():
    m = accepted_d03()
    without_consent("M04")
    questions, before = len(db.load_all(InterviewQuestion, member_id="M04")), evidence_count("M04")
    with pytest.raises(PermissionError):
        orc.start_check("M04", ["D04"])
    with pytest.raises(PermissionError):
        orc.start_owner_check("M04", "D05")
    with pytest.raises(PermissionError):
        orc.submit_answer("Q-D03-M04-why", GOOD, "M04")
    with pytest.raises(PermissionError):
        orc.start_retest(m.id, "M04")
    assert len(db.load_all(InterviewQuestion, member_id="M04")) == questions and evidence_count("M04") == before


# --- D. project start
def test_demo_mode_refuses_to_process_an_upload():
    before = [d.title for d in orc.decisions()]
    with pytest.raises(ValueError, match="not processed"):
        orc.setup_project([str(DEMO / "README.md")])
    assert [d.title for d in orc.decisions()] == before


def new_card(card_id: str, title: str) -> DecisionCard:
    # deliberately claims the demo project: the orchestrator must re-scope it to the new project
    return DecisionCard(id=card_id, project_id="P01", title=title, rationale="Because the data required it.",
                        source_refs=[SourceRef(file="group_report.md", page=1, quote="We chose it.")])


@pytest.fixture
def live_model(monkeypatch):
    """Live mode with the extractor faked: no network, no real key."""
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-real")


def demo_state():
    return ([d.title for d in orc.decisions("P01")], len(db.evidence_for_coverage("P01")), orc.missions("P01"))


def test_a_live_project_is_created_next_to_the_demo(monkeypatch, tmp_path, live_model):
    m = accepted_d03()
    orc.start_retest(m.id, "M04")
    before = demo_state()
    monkeypatch.setattr(orc, "extract_decisions",
                        lambda files, **kw: [new_card("D01", "New A"), new_card("D02", "New B")])
    cards = orc.setup_project([str(tmp_path / "group_report.md")], actor="agent")
    pid = orc.active_project_id()

    assert pid != "P01" and [c.id for c in cards] == [f"{pid}-D01", f"{pid}-D02"]
    assert all(c.project_id == pid for c in orc.decisions())  # re-scoped, never the demo's id
    assert orc.missions() == [] and db.load_all(InterviewQuestion, project_id=pid) == []
    assert orc.members() == {} and orc.team_coverage().denominator == 0
    assert orc.project().title == "group_report" and orc.project().source_files == ["group_report.md"]
    assert orc.demo_banner() is None  # live data is not labelled synthetic
    assert [(s["numerator"], s["denominator"]) for s in orc.coverage_snapshots()] == [(0, 0)]
    assert demo_state() == before  # the demo project was not touched


def test_a_failed_extraction_leaves_no_half_project(monkeypatch, tmp_path, live_model):
    accepted_d03()
    before = demo_state()
    monkeypatch.setattr(orc, "extract_decisions",
                        lambda files, **kw: [new_card("D01", "New A"), new_card("D02", "New B")])
    real_upsert = db._upsert

    def crash_on_second_card(con, record):
        if getattr(record, "id", "").endswith("-D02"):
            raise RuntimeError("disk full")
        return real_upsert(con, record)
    monkeypatch.setattr(db, "_upsert", crash_on_second_card)
    with pytest.raises(RuntimeError):
        orc.setup_project([str(tmp_path / "group_report.md")])
    assert [p.id for p in orc.projects()] == ["P01"] and orc.active_project_id() == "P01"
    assert demo_state() == before


def test_a_long_session_keeps_the_badge_and_the_baseline(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    for i in range(600):  # more than load_log's default window of 500 events
        db.log("agent", "noise", {"i": i}, project_id="P01")
    assert orc.demo_banner() is not None
    assert orc.coverage_snapshots()[0]["label"] == "baseline"


def test_a_database_from_before_projects_is_migrated(tmp_path):
    """A busfactor.db written before Improve2 (no project_id anywhere) opens and keeps its data."""
    import sqlite3
    old = tmp_path / "before_improve2.db"
    decision = json.loads((DEMO / "decisions.json").read_text(encoding="utf-8"))["decisions"][2]
    question = json.loads((DEMO / "questions.json").read_text(encoding="utf-8"))["questions"][7]
    evidence = json.loads((DEMO / "evidence.json").read_text(encoding="utf-8"))["evidence"][7]
    for legacy in (question, evidence):
        legacy.pop("project_id")
    with sqlite3.connect(old) as con:
        for table in ("projects", "decisions", "members", "questions", "evidence", "missions"):
            con.execute(f"CREATE TABLE {table} (id TEXT PRIMARY KEY, member_id TEXT, decision_id TEXT, "
                        "data TEXT NOT NULL)")
        con.execute("CREATE TABLE log_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, "
                    "audience TEXT NOT NULL DEFAULT 'internal')")
        con.execute("INSERT INTO decisions VALUES (?, NULL, ?, ?)", (decision["id"], decision["id"], json.dumps(decision)))
        con.execute("INSERT INTO questions VALUES (?, ?, ?, ?)",
                    (question["id"], question["member_id"], question["decision_id"], json.dumps(question)))
        con.execute("INSERT INTO evidence VALUES (?, ?, ?, ?)",
                    (evidence["id"], evidence["member_id"], evidence["decision_id"], json.dumps(evidence)))
    db.set_db_path(old)
    [q] = db.load_all(InterviewQuestion)
    assert q.id == question["id"] and q.project_id == "P01"
    [ev] = db.evidence_for_coverage("P01")
    assert ev.id == evidence["id"] and ev.project_id == "P01" and ev.answer == evidence["answer"]
    with sqlite3.connect(old) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        indexes = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert {"idx_evidence_project", "idx_evidence_member", "idx_log_events_project"} <= indexes


def test_records_without_a_project_are_refused():
    stray = db.get_record(InterviewQuestion, "Q-D03-M04-why").model_copy(update={"id": "Q-stray", "project_id": None})
    with pytest.raises(ValueError, match="no project_id"):
        db.save_record(stray)


def test_an_upload_without_cards_creates_nothing(monkeypatch, tmp_path, live_model):
    monkeypatch.setattr(orc, "extract_decisions", lambda files, **kw: [])
    with pytest.raises(ValueError, match="nothing was changed"):
        orc.setup_project([str(tmp_path / "empty.md")])
    assert [p.id for p in orc.projects()] == ["P01"]
    assert len(orc.decisions()) == 5 and orc.demo_banner() is not None


# --- the rendered pages (Streamlit AppTest, offline)
def open_as(viewer: str, page: str):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    at.selectbox(key="viewer").set_value(viewer)
    at.radio(key="nav").set_value(page)
    at.run()
    assert not at.exception, at.exception
    return at


def test_offline_setup_never_pretends_to_extract(tmp_path):
    # the demo project offers no extraction at all
    at = open_as("M01", "Project Setup")
    assert not any(b.label == "Propose decisions with the live model" for b in at.button)
    # an offline live project: the model button is disabled and the page says why
    p = orc.create_project("Campus Events App", "Databases", [("report.md", b"We chose PostgreSQL.")], ["Ada"])
    at = open_as(f"{p.id}-M01", "Project Setup")
    extract = next(b for b in at.button if b.label == "Propose decisions with the live model")
    assert extract.disabled and any(orc.EXTRACTION_NEEDS_MODEL in c.value for c in at.caption)
    assert any("Next step" in i.value for i in at.info)


def test_retest_page_asks_for_a_new_question_after_an_answer():
    m = accepted_d03()
    orc.start_retest(m.id, "M04")
    orc.submit_retest(m.id, "I am not sure.", "M04")
    at = open_as("M04", "Defense Studio")
    assert len(at.text_area) == 0
    assert any(b.label == "Start a new independent question" for b in at.button)


def test_private_check_offers_the_owner_check(fresh):
    at = open_as("M02", "Defense Studio")
    assert any("Verify a decision you own" in md.value for md in at.markdown)
    at.button(key="own-start").click().run()
    assert not at.exception
    assert any("Owner check · no hints" in md.value for md in at.markdown)


def test_private_check_respects_missing_consent():
    without_consent("M04")
    at = open_as("M04", "Defense Studio")
    assert any("not agreed to be assessed" in w.value for w in at.warning)
    assert not any(b.label == "Get my questions" for b in at.button)
