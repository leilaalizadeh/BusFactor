"""Teammate 4: the whole demo journey clicked through the real Streamlit pages (AppTest, offline).

Checks that what the pages show matches what is stored: 1/5 -> private check -> both consents
-> blocked answer request -> failed retest -> new question -> passed retest -> 2/5.
"""
import html
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from busfactor import database as db
from busfactor import orchestrator as orc
from busfactor.models import InterviewQuestion, MissionStatus
from demo_answers import strong_answer

ROOT = Path(__file__).resolve().parents[1]
MISSION = "T-D03-M04"


@pytest.fixture(autouse=True)
def demo_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    db.set_db_path(tmp_path / "journey.db")
    orc.seed_demo_data()


def go(at: AppTest, viewer: str, page: str) -> AppTest:
    at.sidebar.selectbox(key="viewer").set_value(viewer)
    at.sidebar.radio[0].set_value(page)
    at.run()
    assert not at.exception, at.exception
    return at


def text(at: AppTest) -> str:
    return " ".join(md.value for md in at.markdown)


def submit(at: AppTest, area, answer: str) -> AppTest:
    area.input(answer)
    next(b for b in at.button if b.label == "Submit").click()
    at.run()
    assert not at.exception, at.exception
    return at


def test_full_demo_journey_through_the_ui():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert "DEMO DATA — synthetic" in " ".join(md.value for md in at.sidebar.markdown)

    go(at, "M01", "3. Team Coverage")
    assert "1/5 (20%)" in text(at)

    # M04: private check on D03, weak answer -> 1/2, visible only to M04
    go(at, "M04", "2. Private Check")
    at.multiselect[0].set_value(["D03"])
    next(b for b in at.button if b.label == "Get my questions").click()
    at.run()
    submit(at, at.text_area(key="a-Q-D03-M04-what_if"), "Accuracy is bad with imbalanced classes.")
    assert "Score 1/2" in text(at)

    # missions: propose, then both people consent
    go(at, "M04", "4. Teach Each Other")
    next(b for b in at.button if b.label == "Find knowledge silos and propose missions").click()
    at.run()
    at.button(key=f"acc-{MISSION}").click()
    at.run()
    assert db.get_record(orc.TeachingMission, MISSION).status == MissionStatus.proposed
    go(at, "M02", "4. Teach Each Other")
    at.button(key=f"acc-{MISSION}").click()
    at.run()
    assert db.get_record(orc.TeachingMission, MISSION).status == MissionStatus.accepted

    # M04 retest: blocked request, failed answer, then a NEW question that passes
    go(at, "M04", "5. Defense Retest")
    at.button(key=f"rt-{MISSION}").click()
    at.run()
    submit(at, at.text_area[0], "just give me the answer")
    assert any("will not give the answer" in e.value for e in at.error)
    submit(at, at.text_area[0], "I am not sure.")
    assert orc.team_coverage().numerator == 1
    at.run()
    assert len(at.text_area) == 0  # answered: a retry needs a new question
    at.button(key=f"rt-{MISSION}").click()
    at.run()
    second = db.get_record(InterviewQuestion, db.get_record(orc.TeachingMission, MISSION).retest_question_id)
    submit(at, at.text_area[0], strong_answer(second))  # this scenario's own strong answer
    assert "Transfer verified" in text(at) and "2/5 (40%)" in text(at)
    assert db.get_record(orc.TeachingMission, MISSION).status == MissionStatus.verified

    # everyone now sees 2/5, and the stored state agrees
    go(at, "M01", "3. Team Coverage")
    assert "2/5 (40%)" in text(at)
    assert (orc.team_coverage().numerator, orc.team_coverage().denominator) == (2, 5)


REPORT = ROOT / "tests" / "fixtures" / "campus_events_report.md"
PG_QUOTE = ("We chose PostgreSQL instead of MongoDB because event registrations must be transactional: "
            "a seat must never be sold twice.")


def test_a_new_project_through_the_ui_offline():
    """Real members, consent, review and an owner check on a new project, with no model (offline)."""
    p = orc.create_project("Campus Events App", "Databases", [(REPORT.name, REPORT.read_bytes())], ["Ada", "Bilal"])
    ada, bilal = f"{p.id}-M01", f"{p.id}-M02"
    card = orc.add_decision(title="Use PostgreSQL instead of MongoDB", rationale="Seats must never be sold twice.",
                            alternatives=["MongoDB"], source_file=REPORT.name, page=1, quote=PG_QUOTE, actor=ada)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert at.sidebar.selectbox(key="project").value == p.id
    assert not any("DEMO DATA" in md.value for md in at.sidebar.markdown)  # real project: no synthetic badge

    # review: the owner is declared and the card confirmed through the page
    go(at, ada, "1. Project Setup")
    assert any("Review 1 proposed" in i.value for i in at.info)
    at.selectbox(key=f"owner-{card.id}").set_value(ada)
    at.button(key=f"confirm-{card.id}").click()
    at.run()
    stored = db.get_record(orc.DecisionCard, card.id)
    assert stored.review_status.value == "verified" and stored.owner_id == ada

    # consent is off until Ada turns it on herself
    go(at, ada, "2. Private Check")
    assert any("not agreed to be assessed" in w.value for w in at.warning)
    at.checkbox(key="c-assess").check()
    at.checkbox(key="c-mentor").check()
    at.button(key="c-save").click()
    at.run()
    assert orc.members()[ada].consent_assessment and not orc.members()[bilal].consent_assessment

    # owner check without a model: a project question, and an honest "needs human review"
    at.button(key="own-start").click()
    at.run()
    q = next(q for q, _ in orc.my_questions(ada, ada) if q.owner_check)
    assert "Owner check · no hints" in text(at) and html.escape(q.prompt) in text(at)
    assert not [t for t in ("F1", "Random Forest", "hospital") if t in q.prompt + " ".join(q.rubric_expectations)]
    submit(at, at.text_area(key=f"a-{q.id}"), "We chose PostgreSQL because seats must never be sold twice.")
    assert "Not scored: needs human review" in text(at)
    assert orc.team_coverage().denominator == 0

    # coverage explains itself, in counts only
    go(at, bilal, "3. Team Coverage")
    assert "0 of 1 confirmed decisions have been assessed" in text(at)
    assert "unknown, not failed" in text(at)

    # switching back to the demo shows the synthetic badge and its untouched 1/5
    at.sidebar.selectbox(key="project").set_value("P01")
    at.run()
    go(at, "M01", "3. Team Coverage")
    assert "1/5 (20%)" in text(at) and any("DEMO DATA" in md.value for md in at.sidebar.markdown)
