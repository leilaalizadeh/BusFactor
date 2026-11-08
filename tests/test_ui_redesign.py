"""Improve3: the Knowledge Resilience Lab UI — view models, interactions, empty states, contrast."""
import json
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from busfactor import database as db
from busfactor import orchestrator as orc
from busfactor.ui import model as vm
from busfactor.ui.atlas import node_aria
from busfactor.ui.pages import NAV
from busfactor.ui.theme import TOKENS
from demo_answers import GOOD

ROOT = Path(__file__).resolve().parents[1]
MEMBER = re.compile(r"(?<![\w-])M0[1-4]\b")


@pytest.fixture(autouse=True)
def demo_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    db.set_db_path(tmp_path / "ui.db")
    orc.seed_demo_data()


def accepted_d03():
    m = {x.decision_id: x for x in orc.propose_missions()}["D03"]
    orc.accept_mission(m.id, "M02")
    orc.accept_mission(m.id, "M04")
    return m


def failed_retest():
    m = accepted_d03()
    orc.start_retest(m.id, "M04")
    orc.submit_retest(m.id, "I am not sure.", "M04")
    return m


def open_app(viewer="M01", page="Mission Control", **state):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    for key, value in state.items():
        at.session_state[key] = value
    at.run()
    at.selectbox(key="viewer").set_value(viewer)
    at.radio(key="nav").set_value(page)
    at.run()
    assert not at.exception, at.exception
    return at


def text(at) -> str:
    return " ".join(md.value for md in at.markdown)


# --- the Knowledge Constellation's data: counts only, no people, no private outcomes
def test_constellation_carries_counts_only():
    failed_retest()
    ctx = vm.build_ctx("M04")
    nodes = vm.atlas_nodes(ctx)
    blob = json.dumps([*nodes, *vm.atlas_edges(nodes)]) + " ".join(node_aria(n) for n in nodes)
    assert not MEMBER.search(blob) and not re.search(r'"(rubric_)?score"|"answer"|"feedback"', blob)
    by_id = {n["id"]: n for n in nodes}
    assert by_id["D03"]["state"] == "single_point_of_failure" and by_id["D03"]["explainers"] == 1
    assert by_id["D03"]["mission"] == "accepted"  # the failed retest is not visible on the shared map
    assert by_id["D01"]["state"] == "covered" and by_id["D01"]["explainers"] == 2
    assert by_id["D05"]["mission"] == "fallback"


def test_constellation_layout_is_deterministic_and_inside_the_canvas():
    a, b = vm.layout(5), vm.layout(5)
    assert a == b and len(set(a)) == 5
    assert all(0 < x < vm.VIEW_W and 0 < y < vm.VIEW_H for x, y in a)


def test_edges_come_only_from_shared_reviewed_concepts():
    nodes = [{"id": "A", "concepts": ["indexing", "sql"]}, {"id": "B", "concepts": ["sql"]}, {"id": "C", "concepts": []}]
    assert vm.atlas_edges(nodes) == [{"a": "A", "b": "B", "concepts": ["sql"]}]


@pytest.mark.parametrize("view,expected", [("All", 5), ("Vulnerable", 4), ("Verified", 1), ("Unassessed", 0),
                                           ("Needs review", 0), ("In a mission", 0)])
def test_filters_narrow_the_map(view, expected):
    nodes = vm.atlas_nodes(vm.build_ctx("M01"))
    assert sum(vm.matches(n, view) for n in nodes) == expected


def test_search_matches_title_or_label():
    nodes = vm.atlas_nodes(vm.build_ctx("M01"))
    assert [n["id"] for n in nodes if vm.matches(n, "All", "random forest")] == ["D02"]
    assert [n["id"] for n in nodes if vm.matches(n, "All", "d04")] == ["D04"]


# --- Resilience Pulse and team feed: real snapshots, team events only
def test_pulse_follows_stored_coverage_changes():
    assert vm.pulse_points(vm.build_ctx("M01")) == [("Start", 1, 5)]
    m = failed_retest()
    assert vm.pulse_points(vm.build_ctx("M01")) == [("Start", 1, 5)]  # a failed attempt changes nothing
    orc.start_retest(m.id, "M04")
    q = db.get_record(orc.InterviewQuestion, db.get_record(orc.TeachingMission, m.id).retest_question_id)
    from demo_answers import strong_answer
    orc.submit_retest(m.id, strong_answer(q), "M04")
    assert vm.pulse_points(vm.build_ctx("M01")) == [("Start", 1, 5), ("Change 1", 2, 5)]


def test_team_feed_names_nobody_and_hides_private_steps():
    failed_retest()
    items = vm.feed(vm.build_ctx("M01"), limit=50)
    words = " ".join(t for _, t in items)
    assert "Mission on D03 accepted by both people" in words and "Coverage 1/5 at the start" in words
    assert not MEMBER.search(words) and "retest" not in words.lower()


# --- the mission journey respects who may know what
def test_mission_journey_hides_a_failed_retest_from_outsiders():
    m = db.get_record(orc.TeachingMission, failed_retest().id)
    assert vm.mission_public_state(m, "M01") == "accepted" and vm.mission_public_state(m, None) == "accepted"
    assert vm.mission_public_state(m, "M04") == "completed"
    assert [s for _, s in vm.stages(m, "M01")] == ["done", "done", "now", "todo"]


# --- Your next move: the most useful permitted step, from real state
def test_next_move_follows_the_workflow():
    assert vm.next_move(vm.build_ctx("M01")).page == "Peer Missions"     # silos without missions
    orc.propose_missions()
    move = vm.next_move(vm.build_ctx("M01"))                             # M01 is invited to learn D02
    assert move.page == "Peer Missions" and "Respond to a teaching mission" in move.title
    accepted_d03()
    move = vm.next_move(vm.build_ctx("M04"))
    assert move.page == "Defense Studio" and move.title.startswith("Take your independent retest")
    assert move.focus == "retest_start:T-D03-M04"


def test_next_move_for_new_projects_and_missing_consent():
    p = orc.create_project("Empty team", "Course", [("r.md", b"We chose X.")], [])
    assert vm.next_move(vm.build_ctx(None)).title == "Add your team"
    ada = orc.add_member("Ada", project_id=p.id)
    assert vm.next_move(vm.build_ctx(ada.id)).title == "Decide on your consent"
    orc.update_consent(ada.id, ada.id, assessment=True, mentor=True, learner=True)
    orc.add_decision(title="X", rationale="Y", alternatives=[], source_file="r.md", page=1, quote="We chose X.",
                     actor=ada.id, project_id=p.id)
    move = vm.next_move(vm.build_ctx(ada.id))
    assert move.page == "Decision Library" and move.title.startswith("Review 1 proposed")


def test_defense_queue_is_personal():
    accepted_d03()
    assert [t.kind for t in vm.defense_queue(vm.build_ctx("M04"))] == ["retest_start", "owner_start"]
    assert vm.defense_queue(vm.build_ctx("M03")) == []  # nothing open for M03, and nothing of M04's


# --- every screen renders, in the demo and in an empty project
@pytest.mark.parametrize("page", NAV)
def test_every_screen_renders_in_the_demo(page):
    at = open_app("M04", page)
    assert "DEMO DATA" in " ".join(md.value for md in at.markdown)


@pytest.mark.parametrize("page", NAV)
def test_every_screen_has_an_empty_state_in_a_new_project(page):
    orc.create_project("Brand new", "Course", [], [])
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    at.radio(key="nav").set_value(page)
    at.run()
    assert not at.exception, at.exception
    assert 'role="status"' in text(at) or "Next step" in " ".join(i.value for i in at.info)


# --- interactions: spotlight, navigation with focus, stale context
def test_spotlight_opens_and_routes_to_the_right_workflow():
    at = open_app("M01", "Knowledge Atlas", atlas_selected="D03")
    page = text(at)
    assert "Decision spotlight · D03" in page and "1 of 4 members can explain it" in page
    at.button(key="sp-check-D03").click().run()
    assert not at.exception and at.session_state["nav"] == "Defense Studio"
    assert at.multiselect[0].value == ["D03"]


def test_next_move_button_navigates_with_focus():
    accepted_d03()
    at = open_app("M04", "Mission Control")
    at.button(key="next-move").click().run()
    assert at.session_state["nav"] == "Defense Studio"
    assert any(b.label == "Start a new independent question" for b in at.button)


def test_atlas_list_and_filters_are_driven_by_state():
    at = open_app("M01", "Knowledge Atlas")
    assert "5 of 5 decisions match" in text(at)
    at.text_input(key="atlas_query").input("random forest").run()
    assert "1 of 5 decisions match" in text(at)
    assert [b.key for b in at.button if (b.key or "").startswith("spot-")] == ["spot-D02"]


def test_switching_project_or_member_clears_stale_selections():
    p = orc.create_project("Another team", "Course", [], ["Zoe"])
    orc.open_project("P01")
    at = open_app("M01", "Defense Studio", studio_focus="owner_start:D01", studio_pick=["D03"])
    at.selectbox(key="viewer").set_value("M02").run()      # another member: personal focus is cleared
    assert not at.exception and at.session_state["studio_pick"] != ["D03"]
    at.session_state["atlas_selected"] = "D03"
    at.radio(key="nav").set_value("Knowledge Atlas").run()
    assert "Decision spotlight · D03" in text(at)
    at.selectbox(key="project").set_value(p.id).run()       # another project: every selection is cleared
    assert not at.exception and "atlas_selected" not in at.session_state
    assert "Decision spotlight" not in text(at) and at.selectbox(key="viewer").value == f"{p.id}-M01"


def test_the_studio_answer_flow_still_scores_privately():
    at = open_app("M04", "Defense Studio")
    at.multiselect[0].set_value(["D03"]).run()
    next(b for b in at.button if b.label == "Get my questions").click().run()
    at.text_area(key="a-Q-D03-M04-what_if").input(GOOD)
    next(b for b in at.button if b.label == "Submit").click().run()
    assert not at.exception and "Verified understanding" in text(at)
    other = open_app("M01", "Defense Studio")
    assert GOOD not in text(other)  # another member never sees it


# --- design tokens: text contrast (WCAG 2.x relative luminance)
def _lum(hex_colour: str) -> float:
    rgb = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_text_colours_meet_wcag_aa(theme):
    t = TOKENS[theme]
    for fg in ("text", "muted", "faint", "teal", "amber", "violet", "red", "neutral", "sky"):
        for bg in ("canvas", "panel", "raised"):  # the three surface levels
            assert contrast(t[fg], t[bg]) >= 4.5, (theme, fg, bg, round(contrast(t[fg], t[bg]), 2))
    assert contrast(t["on_teal"], t["teal"]) >= 4.5   # primary buttons
    assert contrast(t["focus"], t["canvas"]) >= 3.0   # focus ring (non-text contrast)


def test_instrument_surfaces_meet_wcag_aa():
    """Hero and map are always dark ('ink') in both themes, and use the dark palette's colours."""
    from busfactor.ui.theme import INK
    d = TOKENS["dark"]
    for fg in (INK["ink_text"], INK["ink_muted"], INK["ink_faint"], d["teal"], d["amber"], d["violet"], d["red"],
               d["neutral"], d["sky"]):
        for bg in (INK["ink"], INK["ink_2"]):
            assert contrast(fg, bg) >= 4.5, (fg, bg, round(contrast(fg, bg), 2))
