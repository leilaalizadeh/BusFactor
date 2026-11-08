"""Improve3 visual overhaul: the design system and Mission Control draw only real data, in both themes."""
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from busfactor import database as db
from busfactor import orchestrator as orc
from busfactor.ui import parts as ui
from busfactor.ui.theme import INK, TOKENS, palette, stylesheet

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def demo_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    db.set_db_path(tmp_path / "visual.db")
    orc.seed_demo_data()


def open_app(page="Mission Control", viewer="M04", **state):
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


# --- the hero instrument is drawn from real data
def test_orbit_has_one_segment_per_decision_and_honest_coverage():
    svg = ui.orbit_svg([("D01", "covered", 2), ("D02", "single_point_of_failure", 1), ("D03", "unconfirmed", 0)],
                       team=4, covered=1, assessed=2, confirmed=2, p=palette("dark"))
    assert svg.count('stroke-width="16"') == 3                       # one outer segment per decision
    assert "1/2" in svg and "50% of assessed decisions" in svg
    assert "1 of 2 assessed decisions are shared; 2 of 2 confirmed decisions are assessed" in svg  # aria summary
    assert 'stroke-dasharray="4 5"' in svg                          # unconfirmed decisions are drawn dashed


def test_orbit_with_nothing_assessed_claims_nothing():
    svg = ui.orbit_svg([], team=0, covered=0, assessed=0, confirmed=0, p=palette("dark"))
    assert "—" in svg and "nothing assessed yet" in svg and 'class="arc"' not in svg


# --- Mission Control composition
def test_mission_control_keeps_coverage_and_completeness_separate():
    page = text(open_app())
    assert "Verified coverage" in page and "Assessment completeness" in page
    assert "1/5<small>20%</small>" in page and ">5/5<" in page
    assert "Your project is finished." in page and "Is its knowledge shared?" in page
    assert "4 of 5 assessed decisions rest on one person, or nobody." in page


def test_pulse_shows_a_baseline_view_not_an_empty_chart():
    page = text(open_app())
    assert "Baseline · the start" in page and "no history is invented" in page
    assert "Resilience Pulse." not in page                          # no trend chart with a single observation


def test_pulse_draws_a_trend_once_coverage_has_changed():
    q = orc.start_check("M04", ["D04"])[0]
    orc.submit_answer(q.id, "A stratified split keeps the share of positives in each subset, so a small test set "
                            "is not left with few positives by chance.", "M04")
    m = {x.decision_id: x for x in orc.propose_missions()}["D03"]
    orc.accept_mission(m.id, "M02")
    orc.accept_mission(m.id, "M04")
    orc.start_retest(m.id, "M04")
    from demo_answers import GOOD
    orc.submit_retest(m.id, GOOD, "M04")
    page = text(open_app())
    assert "Resilience Pulse. Start: 1 of 5 covered; Change 1: 3 of 5 covered" in page


def test_vulnerability_explorer_lists_the_most_critical_first():
    at = open_app()
    keys = [b.key for b in at.button if (b.key or "").startswith("mc-spot-")]
    assert keys[0] == "mc-spot-D05"                                 # nobody can defend it: first
    assert ">05</div>" in text(at)                                  # decision numbering in the explorer


# --- themes
def test_dark_is_the_default_and_light_rethemes_the_whole_app():
    dark = open_app()
    assert f"--bf-canvas:{TOKENS['dark']['canvas']}" in text(dark)
    light = open_app(appearance="Light")
    css = text(light)
    assert f"--bf-canvas:{TOKENS['light']['canvas']}" in css
    # instrument surfaces keep the dark palette in light mode
    assert re.search(r'\[class\*="st-key-bfi-"\] \{ --bf-teal:' + re.escape(TOKENS["dark"]["teal"]), css)
    assert f"--bf-text:{INK['ink_text']}" in css


def test_the_light_query_parameter_opens_light_mode():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.query_params["theme"] = "light"
    at.run()
    assert not at.exception and at.session_state["appearance"] == "Light"


def test_stylesheet_is_valid_and_never_uses_tiny_type():
    for theme in ("dark", "light"):
        css = stylesheet(theme)
        assert "{{" not in css and "}}" not in css                   # no unrendered template braces
        sizes = [float(s) for s in re.findall(r"font(?:-size)?:[^;]*?\b(\d*\.?\d+)rem", css)]
        assert sizes and min(sizes) >= 0.75                          # 12px minimum for any rem-sized text


def test_brand_shows_the_orchestrators_synthetic_badge():
    assert "DEMO DATA — synthetic" in text(open_app())
    p = orc.create_project("Real team", "Course", [], ["Ada"])
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert at.selectbox(key="project").value == p.id and "DEMO DATA" not in text(at)
