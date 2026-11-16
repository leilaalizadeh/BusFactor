"""The new pages and controls, clicked through the real Streamlit app (AppTest, offline, synthetic data)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from busfactor import database as db
from busfactor import orchestrator as orc
from busfactor.i18n import IT, set_lang
from busfactor.models import AssessmentEvidence, EvidenceStatus, InterviewQuestion, Member, QuestionType

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def demo_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    db.set_db_path(tmp_path / "ui_features.db")
    orc.seed_demo_data()
    yield
    set_lang("en")


def open_app() -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def goto(at: AppTest, page: str) -> AppTest:
    at.sidebar.radio[0].set_value(page)
    at.run()
    assert not at.exception, at.exception
    return at


def page_text(at: AppTest) -> str:
    return " ".join(md.value for md in at.markdown)


def test_interface_switches_to_italian_and_back():
    at = open_app()
    at.sidebar.selectbox(key="lang").set_value("it")
    at.run()
    assert not at.exception, at.exception
    assert "DATI DEMO — sintetici" in " ".join(md.value for md in at.sidebar.markdown)
    goto(at, "3. Team Coverage")
    text = page_text(at)
    assert "Copertura del team" in text and "Punto singolo di fallimento" in text
    assert "1/5 (20%)" in text                      # numbers are language independent
    at.sidebar.selectbox(key="lang").set_value("en")
    at.run()
    assert "Team Coverage" in page_text(at)


def test_every_italian_entry_keeps_its_placeholders():
    import re
    for english, italian in IT.items():
        assert sorted(re.findall(r"\{\w+\}", english)) == sorted(re.findall(r"\{\w+\}", italian)), english


def test_coverage_page_offers_counts_only_downloads():
    at = open_app()
    goto(at, "3. Team Coverage")
    assert len(at.get("download_button")) == 2                  # Markdown report and CSV
    report = orc.export_team_report()
    assert "Member A" not in report and "M02" not in report


def test_protected_project_hides_answers_until_the_code_is_entered():
    p = orc.create_project("Campus Events App", "Databases", [("report.md", b"We chose PostgreSQL.")],
                           ["Ada", "Grace"])
    codes = orc.protect_project(p.id)
    ada = f"{p.id}-M01"
    orc.open_project(p.id)

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    at.sidebar.selectbox(key="project").set_value(p.id)
    at.run()
    at.sidebar.selectbox(key="viewer").set_value(ada)
    at.sidebar.radio[0].set_value("2. Private Check")
    at.run()
    assert not at.exception, at.exception
    assert any("access code" in i.value for i in at.info)       # locked: nothing private is shown
    assert not any(c.key == "c-assess" for c in at.checkbox)

    at.sidebar.text_input(key=f"code-{ada}").input("WRONG-CODE")
    at.sidebar.button(key=f"unlock-{ada}").click()
    at.run()
    assert any("does not match" in e.value for e in at.sidebar.error)

    at.sidebar.text_input(key=f"code-{ada}").input(codes["members"][ada])
    at.sidebar.button(key=f"unlock-{ada}").click()
    at.run()
    assert not at.exception, at.exception
    assert any(c.key == "c-assess" for c in at.checkbox)         # unlocked: the member's own page


def test_review_queue_tab_lets_a_reviewer_score_an_unscored_answer():
    q = InterviewQuestion(id="Q-ui-review", decision_id="D02", member_id="M04",
                          prompt="Why did the team pick a Random Forest baseline?", question_type=QuestionType.why,
                          rubric_expectations=["Names the alternative", "Explains the tradeoff"], project_id="P01")
    ev = AssessmentEvidence(id="E-ui-review", member_id="M04", decision_id="D02", question_id=q.id,
                            answer="It handles mixed features and needs little tuning, unlike logistic regression.",
                            rubric_score=0, status=EvidenceStatus.insufficient_evidence, project_id="P01")
    db.save_records(q, ev)
    member = db.get_record(Member, "M04")
    orc.update_consent("M04", "M04", assessment=member.consent_assessment, mentor=member.consent_mentor,
                       learner=member.consent_learner, review=True)

    at = open_app()
    at.sidebar.selectbox(key="viewer").set_value("M01")
    goto(at, "6. Evidence & Limits")
    assert "It handles mixed features" in page_text(at)
    assert "M04" not in page_text(at) and "Member D" not in page_text(at)   # the reviewer never sees who answered
    at.radio(key="rv-score-E-ui-review").set_value(2)
    next(b for b in at.get("form_submit_button") if b.label == "Save review").click()
    at.run()
    assert not at.exception, at.exception
    assert orc.review_queue("P01") == []
    assert {c.decision_id: c for c in orc.team_coverage("P01").per_decision}["D02"].status == "covered"
