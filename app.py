"""BusFactor — the Intelligence Observatory. Run: python -m streamlit run app.py

This file is the shell only: theme, top bar (project, demo identity, navigation, display settings),
routing and the status bar. Screens live in src/busfactor/ui/pages.py and read real state through
the orchestrator.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import streamlit as st  # noqa: E402

from busfactor import orchestrator as orc  # noqa: E402
from busfactor.ui import parts as ui  # noqa: E402
from busfactor.ui.model import build_ctx  # noqa: E402
from busfactor.ui.pages import FOCUS_KEYS, NAV, ROUTES, show  # noqa: E402
from busfactor.ui.theme import stylesheet  # noqa: E402

st.set_page_config(page_title="BusFactor · Intelligence Observatory", page_icon=":material/hub:", layout="wide",
                   initial_sidebar_state="collapsed")
orc.ensure_seeded()
if "appearance" not in st.session_state and st.query_params.get("theme") == "light":  # e.g. ?theme=light
    st.session_state["appearance"] = "Light"
appearance = st.session_state.get("appearance", "Dark")  # read before drawing: the whole page follows it
theme_type = "light" if appearance == "Light" else "dark"
st.markdown(stylesheet(theme_type), unsafe_allow_html=True)


def reset_focus() -> None:
    """Changing project or identity must never leave the previous context's selections on screen."""
    for key in FOCUS_KEYS:
        st.session_state.pop(key, None)


def reset_demo() -> None:  # a callback, so it runs before the widgets of the next run exist
    orc.seed_demo_data()
    st.session_state["project"] = orc.DEMO_PROJECT_ID
    reset_focus()


projects = {p.id: p for p in orc.projects()}
active = orc.active_project_id()
if st.session_state.get("project") not in projects:
    st.session_state["project"] = active
qp_page, qp_as = st.query_params.get("page", ""), st.query_params.get("as", "")

with st.container(key="bf-topbar"):
    brand_col, project_col, who_col, more_col = st.columns([3.1, 2.7, 2.7, 1.5], vertical_alignment="bottom")
    with project_col:
        chosen = st.selectbox("Project", list(projects), key="project",
                              format_func=lambda pid: projects[pid].title
                              + (" (demo)" if pid == orc.DEMO_PROJECT_ID else ""))
    if chosen != active:
        orc.open_project(chosen)
    previous = st.session_state.get("_ctx_project")
    st.session_state["_ctx_project"] = chosen
    if previous is not None and previous != chosen:  # a real switch, not the first load (keeps deep links)
        reset_focus()
    with brand_col:
        show(ui.brand(orc.demo_banner()))

    members = orc.members()
    ids = list(members)
    if st.session_state.get("viewer") not in ids:
        st.session_state["viewer"] = qp_as if qp_as in ids else (ids[0] if ids else None)
    with who_col:
        viewer = st.selectbox("Demo identity · not a login", ids, key="viewer",
                              format_func=lambda m: members[m].display_name
                              + (f" · {m}" if orc.is_demo_project() else ""),
                              placeholder="No members yet")
    previous = st.session_state.get("_ctx_viewer")
    st.session_state["_ctx_viewer"] = viewer
    if previous is not None and previous != viewer:
        for key in ("studio_focus", "studio_pick"):  # personal selections belong to one member
            st.session_state.pop(key, None)
    with more_col:
        with st.popover("Display & demo", width="stretch"):
            st.radio("Appearance", ["Dark", "Light"], key="appearance", horizontal=True)
            st.caption("Reset restores the synthetic demo to its start (coverage 1/5). Everything done in the demo is "
                       "lost; your own projects are not touched.")
            st.button("Reset the demo now", key="reset-demo", type="primary", on_click=reset_demo)

qp_focus = st.query_params.get("focus", "")  # e.g. ?page=1&focus=D03 opens a decision's spotlight
if qp_focus and "atlas_selected" not in st.session_state and st.session_state.get("_qp_focus") != qp_focus:
    st.session_state["atlas_selected"] = st.session_state["_qp_focus"] = qp_focus
if st.session_state.get("nav") not in NAV:
    st.session_state["nav"] = (NAV[int(qp_page)] if qp_page.isdigit() and int(qp_page) < len(NAV)
                               else qp_page if qp_page in NAV else NAV[0])
page = st.radio("Navigate", NAV, key="nav", horizontal=True, label_visibility="collapsed")

ROUTES[page](build_ctx(viewer, theme_type))

show(ui.statusbar([
    orc.grading_mode(),
    f"Viewing as {members[viewer].display_name} · demo identity switch, not a login" if viewer
    else "No members yet",
    "Live model: project text and answers are sent to the model API" if orc.llm_available()
    else "Data stays on this machine",
]))
