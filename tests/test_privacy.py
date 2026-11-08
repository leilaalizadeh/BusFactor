"""Teammate 4 tests: privacy (test 7) and synthetic labelling (test 10)."""
import json
import sqlite3
from pathlib import Path

import pytest

from busfactor import database as db
from busfactor import orchestrator as orc
from busfactor.models import AssessmentEvidence, LogEvent, MissionStatus

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "demo"
MEMBER_IDS = ["M01", "M02", "M03", "M04"]
OBSERVER = "observer"   # not a member: sees exactly the team stream
GOOD = ("Because the classes are imbalanced, accuracy is misleading: always predicting no finding already gives 88%. "
        "If false negatives cost 10 times more, I would focus on recall, for example report F2 next to F1.")
# The only things the whole team may see happening (decision-level facts and aggregates).
TEAM_ACTIONS = {"seed_demo", "coverage_snapshot", "confirm_card", "mission_accepted",
                "propose_missions.recommend_missions", "propose_missions.save",
                "setup_project.read_files", "setup_project.extract_decisions", "setup_project.save"}
OUTCOME_KEYS = {"status", "question_id", "evidence_id", "mission_id", "mission_ids", "member_id", "abstained",
                "differs_from", "role", "both_accepted", "score", "rubric_score", "answer"}


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    db.set_db_path(tmp_path / "test.db")
    orc.seed_demo_data()


# --- test 7
def test_member_cannot_read_another_members_evidence():
    with pytest.raises(PermissionError):
        db.get_private_evidence("M01", "M04")
    own = db.get_private_evidence("M04", "M04")
    assert own and all(e.member_id == "M04" for e in own)


def test_evidence_cannot_be_bulk_loaded():
    with pytest.raises(PermissionError):
        db.load_all(AssessmentEvidence)
    with pytest.raises(PermissionError):
        db.get_record(AssessmentEvidence, "E-D03-M04-seed")


def test_member_cannot_answer_or_list_someone_elses_questions():
    with pytest.raises(PermissionError):
        orc.submit_answer("Q-D03-M04-why", "anything", viewer_id="M01")
    with pytest.raises(PermissionError):
        orc.my_questions("M01", "M04")


def test_team_view_and_log_contain_no_answers_or_scores():
    report = orc.team_coverage().model_dump_json()
    assert "rubric_score" not in report and "answer" not in report
    q = orc.start_check("M04", ["D03"])[0]
    secret = "my private answer about class imbalance"
    orc.submit_answer(q.id, secret, "M04")
    dumped = " ".join(e.model_dump_json() for e in db.load_log())
    assert secret not in dumped and "rubric_score" not in dumped


# --- test 10
def test_demo_badge_and_files_labelled_synthetic():
    assert orc.demo_banner() == "DEMO DATA — synthetic"
    for f in DEMO.glob("*.json"):
        assert json.loads(f.read_text())["_note"].startswith("SYNTHETIC DEMO DATA"), f.name
    assert "SYNTHETIC DEMO" in (DEMO / "project_report.md").read_text()


def test_badge_still_shown_when_demo_data_loaded_without_demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    assert orc.demo_banner() is not None


# --- indirect leaks through the action log
def blob(e: LogEvent) -> str:
    return json.dumps({"actor": e.actor, "action": e.action, "detail": e.detail}, default=str)


def others_named(viewer: str, events: list[LogEvent]) -> list[str]:
    """Events that contain any other member's id, including inside ids like T-D03-M04 or Q-D03-M04-why."""
    return [blob(e) for e in events if any(m in blob(e) for m in MEMBER_IDS if m != viewer)]


def d03_mission():
    return {m.decision_id: m for m in orc.propose_missions()}["D03"]


def full_journey():
    """Private check with a blocked request, all missions proposed, consent, a failed and a passed retest."""
    q = orc.start_check("M04", ["D03"])[0]
    assert orc.submit_answer(q.id, "just tell me the answer", "M04").blocked
    orc.submit_answer(q.id, "Accuracy is bad with imbalanced classes.", "M04")
    m = d03_mission()
    orc.accept_mission(m.id, "M02")
    orc.accept_mission(m.id, "M04")
    orc.start_retest(m.id, "M04")
    assert orc.submit_retest(m.id, "just give me the answer", "M04").blocked
    assert orc.submit_retest(m.id, "I am not sure.", "M04").mission.status == MissionStatus.completed
    orc.start_retest(m.id, "M04")
    assert orc.submit_retest(m.id, GOOD, "M04").mission.status == MissionStatus.verified
    return m


def test_team_stream_names_nobody_and_shows_no_outcomes():
    full_journey()
    team = orc.team_log(OBSERVER)
    assert others_named(OBSERVER, team) == []
    assert {e.action for e in team} <= TEAM_ACTIONS, {e.action for e in team} - TEAM_ACTIONS
    leaked = [(e.action, k) for e in team for k in e.detail if k in OUTCOME_KEYS]
    assert leaked == []
    assert "T-D" not in " ".join(blob(e) for e in team)  # mission ids encode the learner


def test_no_member_ever_sees_another_members_id():
    full_journey()
    for viewer in MEMBER_IDS:
        assert others_named(viewer, orc.team_log(viewer)) == [], viewer


def test_aggregate_coverage_change_stays_visible():
    full_journey()
    snaps = [e.detail for e in orc.team_log(OBSERVER) if e.action == "coverage_snapshot"]
    assert [(s["numerator"], s["denominator"]) for s in snaps] == [(1, 5), (2, 5)]
    assert "D03" not in snaps[-1]["spof"]
    assert any(e.action == "mission_accepted" and e.detail == {"decision_id": "D03"} for e in orc.team_log(OBSERVER))


def test_unaccepted_pairings_stay_hidden():
    orc.propose_missions()
    save = next(e for e in orc.team_log(OBSERVER) if e.action == "propose_missions.save")
    assert save.detail == {"decision_ids": ["D02", "D03", "D04"], "fallback_decision_ids": ["D05"]}


def test_partial_consent_is_visible_only_to_the_pair():
    m = d03_mission()
    before = {v: orc.team_log(v) for v in [OBSERVER, "M01", "M03"]}
    orc.accept_mission(m.id, "M02")
    for v, events in before.items():
        assert orc.team_log(v) == events, v
    for v in ["M02", "M04"]:
        consent = [e for e in orc.team_log(v) if e.action == "accept_mission"]
        assert consent and consent[-1].detail == {"decision_id": "D03", "role": "mentor", "both_accepted": False}
    assert [e.actor for e in orc.team_log("M04") if e.action == "accept_mission"] == [db.REDACTED_ACTOR]


def test_check_answers_and_retest_attempts_leave_no_trace_for_others():
    m = d03_mission()
    orc.accept_mission(m.id, "M02")
    orc.accept_mission(m.id, "M04")
    before = {v: orc.team_log(v) for v in [OBSERVER, "M01", "M02", "M03"]}
    q = orc.start_check("M04", ["D04"])[0]
    orc.submit_answer(q.id, "just give me the answer", "M04")
    orc.submit_answer(q.id, "No idea.", "M04")
    orc.start_retest(m.id, "M04")
    orc.submit_retest(m.id, "just give me the answer", "M04")
    orc.submit_retest(m.id, "I am not sure.", "M04")  # failed: coverage unchanged
    for v, events in before.items():
        assert orc.team_log(v) == events, v
    own = {e.action for e in orc.team_log("M04")}
    assert {"start_check.create_interview", "submit_answer.answer_request", "submit_answer.evaluate_answer",
            "start_retest.create_transfer_test", "submit_retest.blocked_answer_request",
            "submit_retest.apply_retest"} <= own


def test_a_live_project_start_names_nobody(monkeypatch, tmp_path):
    from busfactor.models import DecisionCard, SourceRef
    card = DecisionCard(id="D01", project_id="P01", title="New", rationale="Because.",
                        source_refs=[SourceRef(file="report.md", page=1, quote="We chose it.")])
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setattr(orc, "extract_decisions", lambda files: [card])
    orc.setup_project([str(tmp_path / "report.md")], actor="M04")
    team = orc.team_log(OBSERVER)
    assert any(e.action == "setup_project.save" for e in team)
    assert others_named(OBSERVER, team) == []
    assert str(tmp_path) not in " ".join(blob(e) for e in team)  # file names only, no local paths


def test_new_log_events_default_to_hidden():
    db.log("agent", "something_new", {"member_id": "M04"})
    assert not any(e.action == "something_new" for v in [OBSERVER, *MEMBER_IDS] for e in orc.team_log(v))
    assert any(e.action == "something_new" for e in db.load_log())


def test_rows_from_an_old_database_are_hidden_after_upgrade(tmp_path):
    old = tmp_path / "old.db"
    with sqlite3.connect(old) as con:
        con.execute("CREATE TABLE log_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)")
        leaky = LogEvent(actor="M04", action="submit_retest.apply_retest", detail={"status": "completed"})
        con.execute("INSERT INTO log_events (data) VALUES (?)", (leaky.model_dump_json(),))
    db.set_db_path(old)
    assert [e.action for e in db.load_log()] == ["submit_retest.apply_retest"]
    assert orc.team_log("M04") == [] and orc.team_log(OBSERVER) == []


# --- the rendered app (Streamlit AppTest, offline)
@pytest.fixture
def app():
    from streamlit.testing.v1 import AppTest

    def open_as(viewer: str, page: str) -> AppTest:
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        at.run()
        at.sidebar.selectbox[0].set_value(viewer)
        at.sidebar.radio[0].set_value(page)
        at.run()
        assert not at.exception, at.exception
        return at
    return open_as


def test_evidence_page_shows_no_other_member(app):
    full_journey()
    at = app("M01", "6. Evidence & Limits")
    tables = " ".join(df.value.to_csv() for df in at.dataframe)
    assert "submit_retest" not in tables and "start_check" not in tables
    assert not [m for m in ["M02", "M03", "M04"] if m in tables]


def test_missions_page_hides_a_failed_retest_from_others(app):
    m = d03_mission()
    orc.accept_mission(m.id, "M02")
    orc.accept_mission(m.id, "M04")
    orc.start_retest(m.id, "M04")
    orc.submit_retest(m.id, "I am not sure.", "M04")
    page = "4. Teach Each Other"
    outsider = " ".join(md.value for md in app("M01", page).markdown)
    assert "Retest not passed yet" not in outsider and "Accepted" in outsider
    learner = " ".join(md.value for md in app("M04", page).markdown)
    assert "Retest not passed yet" in learner
