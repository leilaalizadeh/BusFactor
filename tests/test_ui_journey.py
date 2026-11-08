"""Teammate 4: the whole demo journey clicked through the real Streamlit pages (AppTest, offline).

Checks that what the pages show matches what is stored: 1/5 -> private check -> both consents
-> blocked answer request -> failed retest -> new question -> passed retest -> 2/5.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from busfactor import database as db
from busfactor import orchestrator as orc
from busfactor.models import MissionStatus

ROOT = Path(__file__).resolve().parents[1]
GOOD = ("Because the classes are imbalanced, accuracy is misleading: always predicting no finding already gives 88%. "
        "If false negatives cost 10 times more, I would focus on recall, for example report F2 next to F1.")
MISSION = "T-D03-M04"


@pytest.fixture(autouse=True)
def demo_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    db.set_db_path(tmp_path / "journey.db")
    orc.seed_demo_data()


def go(at: AppTest, viewer: str, page: str) -> AppTest:
    at.sidebar.selectbox[0].set_value(viewer)
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
    submit(at, at.text_area[0], GOOD)
    assert "Transfer verified" in text(at) and "2/5 (40%)" in text(at)
    assert db.get_record(orc.TeachingMission, MISSION).status == MissionStatus.verified

    # everyone now sees 2/5, and the stored state agrees
    go(at, "M01", "3. Team Coverage")
    assert "2/5 (40%)" in text(at)
    assert (orc.team_coverage().numerator, orc.team_coverage().denominator) == (2, 5)
