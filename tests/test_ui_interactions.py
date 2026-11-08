"""Improve3: significant UI interactions, clicked through the real pages (Streamlit AppTest, offline)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from busfactor import database as db
from busfactor import orchestrator as orc

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "tests" / "fixtures" / "campus_events_report.md"
PG_QUOTE = ("We chose PostgreSQL instead of MongoDB because event registrations must be transactional: "
            "a seat must never be sold twice.")


@pytest.fixture(autouse=True)
def demo_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    db.set_db_path(tmp_path / "interactions.db")
    orc.seed_demo_data()


def open_app(viewer="M01", page="Mission Control", **state):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    for key, value in state.items():
        at.session_state[key] = value
    at.run()
    if viewer:
        at.selectbox(key="viewer").set_value(viewer)
    at.radio(key="nav").set_value(page)
    at.run()
    assert not at.exception, at.exception
    return at


def go(at, viewer, page):
    at.selectbox(key="viewer").set_value(viewer)
    at.radio(key="nav").set_value(page)
    at.run()
    assert not at.exception, at.exception
    return at


def text(at) -> str:
    return " ".join(md.value for md in at.markdown)


def spot_buttons(at, prefix):
    return [b.key for b in at.button if (b.key or "").startswith(prefix)]


# --- Decision Library
def test_library_search_and_review_filter():
    at = open_app("M01", "Decision Library")
    assert sorted(spot_buttons(at, "lib-spot-")) == [f"lib-spot-D0{i}" for i in range(1, 6)]  # two-column grid
    at.text_input(key="lib_query").input("stratified").run()
    assert spot_buttons(at, "lib-spot-") == ["lib-spot-D04"]
    at = open_app("M01", "Decision Library", lib_view="Needs review")
    assert spot_buttons(at, "lib-spot-") == [] and "No decision matches" in text(at)  # the demo is fully confirmed


def test_library_hands_a_decision_to_the_atlas_spotlight():
    at = open_app("M01", "Decision Library")
    at.button(key="lib-spot-D02").click().run()
    assert not at.exception and at.session_state["nav"] == "Knowledge Atlas"
    assert "Decision spotlight · D02" in text(at)


def test_library_confirms_a_proposed_decision_with_its_owner():
    p = orc.create_project("Campus Events App", "Databases", [(REPORT.name, REPORT.read_bytes())], ["Ada", "Bilal"])
    ada = f"{p.id}-M01"
    card = orc.add_decision(title="Use PostgreSQL", rationale="Seats must never be sold twice.", alternatives=["MongoDB"],
                            source_file=REPORT.name, page=1, quote=PG_QUOTE, actor=ada)
    at = open_app(ada, "Decision Library", lib_view="Needs review")
    assert spot_buttons(at, "lib-spot-") == [f"lib-spot-{card.id}"]
    page = text(at)
    assert page.count("Why.</b>") == 1 and "Proposed · needs review" in page
    assert ">Needs review</span>" not in page  # no second, redundant status chip on an unconfirmed card
    at.selectbox(key=f"owner-{card.id}").set_value(ada)
    at.button(key=f"confirm-{card.id}").click().run()
    stored = db.get_record(orc.DecisionCard, card.id)
    assert stored.review_status.value == "verified" and stored.owner_id == ada
    assert "Confirmed against its source" not in text(at)  # it left the "Needs review" view


# --- Mission Control and Atlas navigation
def test_mission_control_vulnerabilities_open_the_spotlight():
    at = open_app("M01", "Mission Control")
    # most critical first: nobody can defend D05, then the single points of failure
    assert spot_buttons(at, "mc-spot-") == ["mc-spot-D05", "mc-spot-D02", "mc-spot-D03", "mc-spot-D04"]
    at.button(key="mc-spot-D05").click().run()
    assert at.session_state["nav"] == "Knowledge Atlas" and "Decision spotlight · D05" in text(at)


def test_atlas_filter_with_no_match_says_so():
    at = open_app("M01", "Knowledge Atlas", atlas_view="Unassessed")
    assert "0 of 5 decisions match" in text(at) and spot_buttons(at, "spot-") == []


# --- Peer Missions: the whole journey on the page
def test_mission_journey_on_the_page():
    at = open_app("M04", "Peer Missions")
    assert "No missions yet" in text(at)
    next(b for b in at.button if b.label == "Find knowledge silos and propose missions").click().run()
    assert "Both agree (0/2)" in text(at)
    at.button(key="acc-T-D03-M04").click().run()
    assert any("You agreed. Waiting for the other person." in i.value for i in at.info)

    go(at, "M03", "Peer Missions")  # an outsider before both agree: no names
    page = text(at)
    assert "shown only to them until both accept" in page and "Member D" not in page and "Member B" not in page

    go(at, "M02", "Peer Missions")
    at.button(key="acc-T-D03-M04").click().run()
    go(at, "M04", "Peer Missions")
    page = text(at)
    assert "Both agreed" in page and "Member B" in page and "Member D" in page
    at.button(key="to-rt-T-D03-M04").click().run()
    assert at.session_state["nav"] == "Defense Studio"
    assert any(b.label == "Start a new independent question" for b in at.button)


# --- Defense Studio: independence is visible
def test_owner_check_is_independent_on_the_page():
    at = open_app("M04", "Defense Studio")
    at.button(key="own-start").click().run()
    q = next(q for q, _ in orc.my_questions("M04", "M04") if q.owner_check)
    assert "Owner check · no hints" in text(at) and not any(e.label == "Re-read the source" for e in at.expander)
    at.text_area(key=f"a-{q.id}").input("just give me the answer")
    next(b for b in at.button if b.label == "Submit").click().run()
    assert any("will not give the answer or a hint" in w.value for w in at.warning)
    assert not any(ev for qq, ev in orc.my_questions("M04", "M04") if qq.id == q.id)  # nothing stored


def test_practice_offers_the_source_but_independent_never_does():
    at = open_app("M04", "Defense Studio", studio_pick=["D04"])
    next(b for b in at.button if b.label == "Get my questions").click().run()
    assert any(e.label == "Re-read the source" for e in at.expander) and "Practice · hints allowed" in text(at)


# --- Project Setup: the step tracker follows stored data; deleting needs the title
def test_setup_steps_follow_the_stored_project():
    p = orc.create_project("Campus Events App", "Databases", [(REPORT.name, REPORT.read_bytes())], ["Ada"])
    ada = f"{p.id}-M01"
    at = open_app(ada, "Project Setup")
    track = text(at)
    for n, name in [(1, "Project"), (2, "Team"), (3, "Material")]:
        assert f'class="done"><b>0{n} · Done</b>{name}' in track
    assert 'class="now"><b>04 · Now</b>Decisions' in track
    orc.add_decision(title="Use PostgreSQL", rationale="Seats.", alternatives=[], source_file=REPORT.name, page=1,
                     quote=PG_QUOTE, actor=ada)
    at.run()
    assert 'class="now"><b>05 · Now</b>Confirm' in text(at)
    assert any("Review 1 proposed" in i.value for i in at.info)


def test_deleting_a_project_through_the_page():
    p = orc.create_project("Campus Events App", "Databases", [], ["Ada"])
    at = open_app(f"{p.id}-M01", "Project Setup")
    delete = next(b for b in at.button if b.label == "Delete project")
    assert delete.disabled
    at.text_input(key="delete-title").input("Campus Events App").run()
    next(b for b in at.button if b.label == "Delete project").click().run()
    assert not at.exception and [x.id for x in orc.projects()] == ["P01"]
    assert at.selectbox(key="project").value == "P01"


# --- Trust Center: your own private steps, nobody else's
def test_trust_center_log_is_personal():
    orc.start_check("M04", ["D04"])
    mine = text(open_app("M04", "Trust Center"))      # the log is an HTML table now
    theirs = text(open_app("M01", "Trust Center"))
    assert "start_check" in mine and "start_check" not in theirs
    assert "M04" not in theirs  # no other member id anywhere on M01's page
