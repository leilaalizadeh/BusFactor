"""The seven screens of the Intelligence Observatory. Every action calls the orchestrator; every number is real."""
from __future__ import annotations

from collections import Counter
from typing import Callable

import streamlit as st

from busfactor import orchestrator as orc
from busfactor.llm_provider import LLMUnavailable, llm_available
from busfactor.missions import explain_mission
from busfactor.models import MissionStatus, ReviewStatus
from busfactor.ui import parts as ui
from busfactor.ui.atlas import knowledge_constellation
from busfactor.ui.model import (
    FILTERS, KNOWLEDGE, Ctx, atlas_edges, atlas_nodes, coverage_of, decision_state, defense_queue, dlabel, explain,
    feed, matches, mission_for, mission_public_state, next_move, pulse_points, stages,
)
from busfactor.ui.theme import palette

NAV = ["Mission Control", "Knowledge Atlas", "Defense Studio", "Peer Missions", "Decision Library",
       "Project Setup", "Trust Center"]
NAV_HINTS = ["Where do we stand?", "Explore every decision", "Prepare your defense", "Teach each other",
             "Decisions and their evidence", "Start or manage a project", "Privacy, log and limits"]
FOCUS_KEYS = ("atlas_selected", "studio_focus", "library_focus", "studio_pick")
RISKY = ("single_point_of_failure", "no_explainer")


def show(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def go(page: str, **state) -> Callable[[], None]:
    """Button callback: switch screen and carry the focus along (runs before the next script run)."""
    def _go():
        st.session_state["nav"] = page
        for key, value in state.items():
            st.session_state[key] = value
    return _go


def need_viewer(ctx: Ctx) -> None:
    if ctx.viewer is None:
        show(ui.empty("This project has no members yet", "Add the team in Project Setup; each member then opts in "
                      "for themselves."))
        st.button("Open Project Setup", on_click=go("Project Setup"), key="to-setup", type="primary")
        st.stop()


def section(title: str, support: str = "", right: str = "") -> None:
    show(f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:6px">'
         f'<div><h3 class="bf-section">{ui.esc(title)}</h3>'
         + (f'<p class="bf-support" style="margin-top:4px">{ui.esc(support)}</p>' if support else "")
         + f"</div>{right}</div>")


def risky_ids(ctx: Ctx) -> list[str]:
    order = {"no_explainer": 0, "single_point_of_failure": 1}
    found = [did for did in sorted(ctx.cards) if decision_state(ctx, did) in RISKY]
    return sorted(found, key=lambda d: (order[decision_state(ctx, d)], d))


# ================================================================== A. Mission Control

def mission_control(ctx: Ctx) -> None:
    p, rep, pal = ctx.project, ctx.report, palette("dark")  # the hero is an instrument surface: dark palette
    confirmed = [d for d in ctx.cards.values() if d.review_status == ReviewStatus.verified]
    states = {did: decision_state(ctx, did) for did in sorted(ctx.cards)}
    counts = Counter(states.values())
    risky = risky_ids(ctx)
    team = len(ctx.members)

    # --- hero: the question, and an instrument drawn from real coverage
    with st.container(key="bfi-hero"):
        left, right = st.columns([1.2, 1], vertical_alignment="center", gap="large")
        with left:
            kind = "Synthetic demo" if ctx.demo else "Your project"
            if not ctx.cards:
                lede = "Add the project's key decisions, and BusFactor shows who can defend each one."
            elif rep.denominator == 0:
                lede = "Nothing is verified yet. Private checks reveal who can defend each decision."
            elif risky:
                shared = "is" if rep.numerator == 1 else "are"
                lede = (f"{len(risky)} of {rep.denominator} assessed decisions rest on one person, or nobody. "
                        f"{rep.numerator} {shared} shared by at least two members.")
            else:
                lede = f"Every assessed decision has at least two defenders ({rep.numerator} of {rep.denominator})."
            facts = "".join(ui.chip(f"{counts[s]} {KNOWLEDGE[s][0].lower()}", ui.TONE[s], KNOWLEDGE[s][2])
                            for s in KNOWLEDGE if counts[s])
            show(f'<div class="bf-reveal">{ui.label(f"Mission Control · {kind} · {p.title}")}'
                 '<h1 class="bf-display">Your project is finished.<br><span class="accent">Is its knowledge shared?'
                 f'</span></h1><p class="bf-lede" style="color:var(--bf-ink-muted)">{ui.esc(lede)}</p>'
                 f'<div class="bf-hero-facts">{facts}</div></div>')
            b1, b2, _ = st.columns([1, 1, 0.5])
            b1.button("Explore the Atlas", type="primary", key="hero-atlas", on_click=go("Knowledge Atlas"),
                      width="stretch")
            b2.button("Open Peer Missions", key="hero-missions", on_click=go("Peer Missions"), width="stretch")
        with right:
            show(ui.orbit_svg([(dlabel(did), s, len(coverage_of(ctx, did).demonstrated_by)
                                if coverage_of(ctx, did) and s != "unconfirmed" else 0) for did, s in states.items()],
                              team, rep.numerator, rep.denominator, len(confirmed), pal)
                 + '<p class="bf-support" style="text-align:center;color:var(--bf-ink-muted);margin-top:4px">'
                 "Outer ring: one segment per decision, dots = members who can explain it. Inner arcs: verified "
                 "coverage (teal) and assessment completeness (blue).</p>")

    # --- metrics: one grid row, equal heights, each with its own mini visualization
    assessed = [c for c in rep.per_decision if c.status != "not_assessed" and states[c.decision_id] != "unconfirmed"]
    mission_states = [mission_public_state(m, ctx.viewer) for m in ctx.missions if m.mentor_id]
    agreed = sum(s in ("accepted", "completed", "verified") for s in mission_states)
    pct = f"<small>{rep.numerator / rep.denominator:.0%}</small>" if rep.denominator else "<small>not measurable</small>"
    show('<section class="bf-metrics" aria-label="Key measures">' + "".join([
        ui.metric("Verified coverage", f"{rep.numerator}/{rep.denominator}{pct}",
                  "Assessed decisions that at least two members can explain.",
                  ui.segs([ui.TONE[c.status] for c in assessed], "One segment per assessed decision")
                  + '<div class="bf-legend"><span><b style="color:var(--bf-teal)">■</b> shared</span>'
                  '<span><b style="color:var(--bf-amber)">■</b> one person</span>'
                  '<span><b style="color:var(--bf-red)">■</b> nobody</span></div>'),
        ui.metric("Assessment completeness", f"{rep.denominator}/{len(confirmed)}",
                  "Confirmed decisions with at least one judged answer. Unassessed is unknown, never failed.",
                  ui.segs(["sky" if states[d.id] != "not_assessed" else "neutral" for d in confirmed],
                          "One segment per confirmed decision")),
        ui.metric("Single points of failure", str(len(rep.spof_decision_ids)),
                  "Decisions only one member can explain"
                  + (f"; {counts['no_explainer']} nobody can explain yet." if counts["no_explainer"] else "."),
                  ui.segs([ui.TONE[s] for s in states.values()], "One segment per decision")),
        ui.metric("Teaching missions", f"{agreed}<small>agreed</small>",
                  f"{mission_states.count('verified')} transfer(s) verified · "
                  f"{mission_states.count('proposed')} waiting for consent.",
                  ui.segs([{"proposed": "neutral", "verified": "teal"}.get(s, "violet") for s in mission_states],
                          "One segment per mission")),
    ]) + "</section>")

    # --- workspace
    with st.container(key="bfx-work"):
        left, right = st.columns([1.75, 1], gap="large")
    with left, st.container(key="bfc-vuln"):
        section("Vulnerability explorer", "Decisions that depend on one person or on nobody, most critical first.",
                ui.chip(f"{len(risky)} at risk", "amber" if risky else "teal", "◐" if risky else "◉"))
        if not ctx.cards:
            show(ui.empty("No decisions yet", "Add the project's key decisions in Project Setup."))
        elif not risky:
            show(ui.empty("No known single point of failure",
                          "Every assessed decision has two defenders, or nothing is assessed yet."))
        for did in risky:
            cov, state = coverage_of(ctx, did), states[did]
            why, _ = explain(ctx, did)
            mission = mission_for(ctx, did)
            with st.container(key=f"bfr-{did}"):
                c0, c1, c2, c3 = st.columns([0.7, 4.2, 1.8, 1.35], vertical_alignment="center")
                c0.markdown(f'<div class="bf-vrow-num">{ui.esc(dlabel(did)[1:])}</div>', unsafe_allow_html=True)
                with c1:
                    chips = ui.knowledge_chip(state) + (
                        " " + ui.mission_chip(mission_public_state(mission, ctx.viewer)) if mission else "")
                    show(f'<div class="bf-chips">{chips}</div><div class="bf-vrow-title">'
                         f'{ui.esc(ctx.cards[did].title)}</div><p class="bf-support">{ui.esc(why)}</p>')
                with c2:
                    n = len(cov.demonstrated_by) if cov else 0
                    show(ui.dots(n, team, ui.TONE[state])
                         + f'<p class="bf-support" style="margin-top:6px">{n} of {team} can explain</p>')
                c3.button("Spotlight", key=f"mc-spot-{did}", on_click=go("Knowledge Atlas", atlas_selected=did),
                          width="stretch")
    with right:
        move = next_move(ctx)
        with st.container(key="bfc-move"):
            show(ui.icon(move.page) + ui.label("Your next move")
                 + f'<p class="bf-card-title" style="font-size:1.2rem;margin:6px 0 6px">{ui.esc(move.title)}</p>'
                 f'<p class="bf-support">{ui.esc(move.why)}</p>')
            focus = {}
            if move.page == "Defense Studio" and move.focus:  # a queue task key, or a decision to check
                focus = {"studio_focus": move.focus} if ":" in move.focus else {"studio_pick": [move.focus]}
            elif move.page == "Decision Library" and move.focus:
                focus = {"library_focus": move.focus}
            st.button(move.cta, type="primary", on_click=go(move.page, **focus), key="next-move", width="stretch")
        points = pulse_points(ctx)
        with st.container(key="bfc-pulse"):
            section("Resilience Pulse", "Verified coverage at every stored change.")
            if len(points) >= 2:
                show(ui.pulse_svg(points, palette(ctx.theme)))  # a panel surface: follows the app theme
            elif points:
                _, num, den = points[0]
                show(f'<div style="display:flex;align-items:baseline;gap:14px;margin:8px 0 6px">'
                     f'<span class="bf-numeral">{num}/{den}</span>{ui.label("Baseline · the start")}</div>'
                     '<p class="bf-support">One observation so far. A trend appears after a verified retest changes '
                     "coverage; no history is invented.</p>"
                     + ui.segs(["teal"] * num + ["neutral"] * max(den - num, 0), f"{num} of {den} covered"))
        with st.container(key="bfc-feed"):
            section("Recent team progress", "Shared milestones only, never anyone's private steps.")
            show(ui.feed_html(feed(ctx, 5)))
    show('<p class="bf-support" style="margin-top:6px">'
         + ("All numbers come from the synthetic demo data and update live as you use the app."
            if ctx.demo else "All numbers come from this project's stored, consented evidence.") + "</p>")


# ================================================================== B. Knowledge Atlas

def spotlight(ctx: Ctx, did: str) -> None:
    card, cov = ctx.cards[did], coverage_of(ctx, did)
    state = decision_state(ctx, did)
    mission = mission_for(ctx, did)
    with st.container(key="bfc-focus-spotlight"):
        chips = ui.knowledge_chip(state)
        if mission:
            chips += " " + ui.mission_chip(mission_public_state(mission, ctx.viewer))
        explainers = (f"{len(cov.demonstrated_by)} of {len(ctx.members)} members can explain it"
                      if cov and state != "unconfirmed" else "Not counted until confirmed")
        why, step = explain(ctx, did)
        show(f'{ui.label(f"Decision spotlight · {dlabel(did)}")}<p class="bf-spot-title">'
             f'{ui.esc(card.title)}</p><div class="bf-chips">{chips}</div>'
             f'<p class="bf-support" style="margin-top:12px"><b style="color:var(--bf-text)">{ui.esc(explainers)}.</b> '
             f'{ui.esc(why)}</p><p style="margin-top:12px"><b>Why the team chose it.</b> {ui.esc(card.rationale)}</p>'
             + (f'{ui.label("Instead of")}{ui.alternatives(card.alternatives)}' if card.alternatives else "")
             + "".join(ui.quote(r) for r in card.source_refs)
             + f'<p class="bf-support"><b style="color:var(--bf-text)">Next:</b> {ui.esc(step)}</p>')
        me = ctx.members.get(ctx.viewer) if ctx.viewer else None
        if state == "unconfirmed":
            st.button("Review it in the Decision Library", key=f"sp-lib-{did}", type="primary",
                      on_click=go("Decision Library", library_focus=did))
        elif me and card.owner_id == ctx.viewer and did in orc.owner_check_decisions(ctx.viewer):
            st.button("Verify it as its owner", key=f"sp-own-{did}", type="primary",
                      on_click=go("Defense Studio", studio_focus=f"owner_start:{did}"))
        elif me and card.owner_id != ctx.viewer:
            st.button("Practise it in the Defense Studio", key=f"sp-check-{did}", type="primary",
                      on_click=go("Defense Studio", studio_pick=[did]))
        if mission or state in RISKY:
            st.button("Open Peer Missions", key=f"sp-mis-{did}", on_click=go("Peer Missions"))


def atlas(ctx: Ctx) -> None:
    rep = ctx.report
    show(ui.page_head("Knowledge Atlas · constellation", 'Every decision, <span class="accent">and who can defend it.</span>',
                      "Each star is a key decision. Its colour and glyph show whether the team can defend it, the arcs "
                      "around it count the members who can explain it, a violet orbit marks a teaching mission and a "
                      "double teal ring a verified transfer.",
                      [(f"{rep.numerator}/{rep.denominator}" if rep.denominator else "—", "verified"),
                       (str(len(risky_ids(ctx))), "at risk")]))
    if not ctx.cards:
        show(ui.empty("The sky is empty", "Add decisions in Project Setup and they will appear here."))
        return
    with st.container(key="bfx-atlas-filters"):
        f1, f2 = st.columns([2.2, 1], vertical_alignment="bottom")
    view = f1.segmented_control("Show", FILTERS, default="All", key="atlas_view") or "All"
    query = f2.text_input("Find a decision", key="atlas_query", placeholder="Search by title or D-number")
    nodes = atlas_nodes(ctx)
    dimmed = [n["id"] for n in nodes if not matches(n, view, query)]
    show(f'<p class="bf-support" role="status">{len(nodes) - len(dimmed)} of {len(nodes)} decisions match.</p>')
    selected = st.session_state.get("atlas_selected")
    if selected not in ctx.cards:
        selected = None
    with st.container(key="bfx-atlas"):
        left, right = st.columns([1.8, 1], gap="large")
    with left:
        with st.container(key="bfi-map"):
            picked = knowledge_constellation(nodes, atlas_edges(nodes), selected=selected, dimmed=dimmed,
                                             palette=palette(ctx.theme),
                                             core=(f"{rep.numerator}/{rep.denominator}" if rep.denominator else "—",
                                                   "VERIFIED" if rep.denominator else "NOT MEASURED"))
            if picked in ctx.cards and picked != selected:
                # the map above was drawn with the old selection: run once more so the chosen star shows as
                # selected (and gets keyboard focus back). `picked` is a one-shot trigger, so this cannot loop.
                st.session_state["atlas_selected"] = picked
                st.rerun()
        legend = " ".join(ui.knowledge_chip(s) for s in KNOWLEDGE) + " " + " ".join(
            ui.mission_chip(s) for s in ("accepted", "verified"))
        show(f'<div class="bf-chips" aria-label="Legend">{legend}</div>')
    with right:
        if selected:
            spotlight(ctx, selected)
        else:
            with st.container(key="bfc-hint"):
                show(ui.empty("Select a star", "Click a decision, or Tab to it and press Enter, to open its spotlight. "
                              "Arrow keys move between stars."))

    st.markdown("### All decisions")
    show('<p class="bf-support">The same information as the map, as an accessible list.</p>')
    with st.container(key="bfc-list"):
        for n in nodes:
            if n["id"] in dimmed:
                continue
            why, step = explain(ctx, n["id"])
            with st.container(key=f"bfr-atlas-{n['id']}"):
                a, b = st.columns([5, 1], vertical_alignment="center")
                a.markdown(f'<div class="bf-chips">{ui.knowledge_chip(n["state"])}</div>'
                           f'<div class="bf-vrow-title">{ui.esc(n["label"])} · {ui.esc(n["title"])}</div>'
                           f'<p class="bf-support">{ui.esc(why)} <b style="color:var(--bf-text)">Next:</b> '
                           f'{ui.esc(step)}</p>', unsafe_allow_html=True)
                b.button("Spotlight", key=f"spot-{n['id']}", on_click=go("Knowledge Atlas", atlas_selected=n["id"]),
                         width="stretch")


# ================================================================== C. Defense Studio

TASK_NAMES = {"retest_open": "Independent retest", "retest_start": "Independent retest",
              "owner_open": "Owner check", "owner_start": "Verify a decision you own", "practice_open": "Practice"}


def consent_panel(ctx: Ctx) -> None:
    me = ctx.members[ctx.viewer]
    with st.expander("My consent", expanded=not me.consent_assessment):
        st.caption("Only the selected member can change these (no login yet), and you can withdraw at any time. "
                   "Withdrawing removes your answers from the team's coverage."
                   + (" In the demo, consent is synthetic." if ctx.demo else ""))
        a = st.checkbox("I agree to be assessed (private questions and retests)", value=me.consent_assessment,
                        key="c-assess")
        m = st.checkbox("I am willing to mentor a teammate", value=me.consent_mentor, key="c-mentor")
        learn = st.checkbox("I am willing to learn from a teammate", value=me.consent_learner, key="c-learn")
        if st.button("Save my consent", key="c-save"):
            orc.update_consent(ctx.viewer, ctx.viewer, assessment=a, mentor=m, learner=learn)
            st.rerun()


def mode_banner(independent: bool, owner: bool = False) -> str:
    if independent:
        name = "Owner check · no hints" if owner else "Independent retest · no hints"
        return (f'{ui.chip(name, "violet", "◆")}<p class="bf-support" style="margin-top:8px">Independent: no hints or '
                "sources here. Answer from your own understanding; a partial answer is still useful evidence.</p>")
    return (f'{ui.chip("Practice · hints allowed", "teal", "◇")}<p class="bf-support" style="margin-top:8px">Practice: '
            "you may re-read the source first. Explain the reasoning in your own words.</p>")


def answer_form(ctx: Ctx, task, position: str) -> None:
    q = task.question
    independent = q.mode == "independent"
    show(f'<div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap">'
         f'{ui.label(f"{dlabel(q.decision_id)} · {task.title}")}{ui.label(position)}</div>'
         + mode_banner(independent, owner=task.kind == "owner_open")
         + f'<p class="bf-question">{ui.esc(q.prompt)}</p>')
    if not independent:
        with st.expander("Re-read the source"):
            for r in ctx.cards[q.decision_id].source_refs:
                show(ui.quote(r))
    with st.form(f"form-{q.id}"):
        answer = st.text_area("Your answer", key=f"a-{q.id}", height=160,
                              help="English or Italian. Length doesn't earn points; explained reasoning does.")
        if st.form_submit_button("Submit", type="primary"):
            res = orc.submit_answer(q.id, answer, ctx.viewer)
            if res.blocked:
                st.warning(res.message)
            else:
                st.session_state.pop("studio_focus", None)
                st.rerun()


def retest_panel(ctx: Ctx, task, position: str) -> None:
    m = task.mission
    show(f'<div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap">'
         f'{ui.label(f"{dlabel(m.decision_id)} · {task.title}")}{ui.label(position)}</div>' + mode_banner(True))
    if task.kind == "retest_start":
        show('<p class="bf-question">After the teach-back, show the knowledge moved: a new situation you have not '
             "seen, answered on your own.</p>")
        if st.button("Start a new independent question", key=f"rt-{m.id}", type="primary"):
            try:
                q = orc.start_retest(m.id, ctx.viewer)
                st.session_state["studio_focus"] = f"retest_open:{q.id}"
                st.rerun()
            except ValueError as err:  # every scenario was used: no pass-chasing loop
                st.warning(str(err))
        return
    q = task.question
    if q.scenario:
        show(f'<div class="bf-scenario" style="margin-top:10px">New situation · {ui.esc(q.scenario)}</div>')
    show(f'<p class="bf-question">{ui.esc(q.prompt)}</p>')
    with st.form(f"retest-{m.id}"):
        answer = st.text_area("Your answer", height=170,
                              help="No hints are available here. Explain your reasoning in your own words.")
        if st.form_submit_button("Submit", type="primary"):
            res = orc.submit_retest(m.id, answer, ctx.viewer)
            if res.blocked:
                st.error(res.message)
            else:
                cov = ui.coverage_text(res.coverage.numerator, res.coverage.denominator)
                if res.evidence.rubric_score == 2:
                    show(f'<div class="bf-reveal">{ui.chip("Transfer verified", "teal", "✓")}<p class="bf-card-title" '
                         f'style="margin-top:10px;font-size:1.2rem">New question passed. Team coverage is now '
                         f'{ui.esc(cov)}.</p></div>')
                else:
                    show(ui.evidence_chip(res.evidence.status.value))
                st.markdown(f"Result: {res.evidence.feedback}")
                st.markdown(f"Mission status: **{res.mission.status.value}** · team coverage now {cov}")


def studio(ctx: Ctx) -> None:
    need_viewer(ctx)
    name = ctx.names[ctx.viewer]
    queue = defense_queue(ctx) if ctx.members[ctx.viewer].consent_assessment else []
    show(ui.page_head(f"Defense Studio · {name}", 'Prepare like it\'s <span class="accent">the real defense.</span>',
                      "Questions about decisions you didn't make, owner checks and independent retests. Your answers "
                      "and feedback are shown only to you as the selected member; there is no login yet, so anyone "
                      "using this app can switch identity.",
                      [(str(len(queue)), "open"),
                       (str(sum(ev is not None for _, ev in orc.my_questions(ctx.viewer, ctx.viewer))), "answered")]))
    consent_panel(ctx)
    if not ctx.members[ctx.viewer].consent_assessment:
        st.warning("You have not agreed to be assessed, so BusFactor will not ask or score you.")
        return
    keys = [t.key for t in queue]
    focus = st.session_state.get("studio_focus")
    if focus not in keys:
        focus = keys[0] if keys else None
    with st.container(key="bfx-studio"):
        left, right = st.columns([1, 1.85], gap="large")
    with left:
        with st.container(key="bfc-queue"):
            section("Your defense queue", "Retests first, then open questions and owner checks.")
            if not queue:
                show(ui.empty("Nothing open", "Start a private check below."))
            for t in queue:
                st.button(f"{TASK_NAMES[t.kind]} · {dlabel(t.decision_id)} · {t.title}", key=f"task-{t.key}",
                          type="primary" if t.key == focus else "secondary", width="stretch",
                          on_click=go("Defense Studio", studio_focus=t.key))
        with st.container(key="bfc-start"):
            section("Start a private check", "Two decisions you didn't make. Only you see the result.")
            options = [d.id for d in ctx.cards.values() if d.owner_id != ctx.viewer]
            if "studio_pick" not in st.session_state:  # first visit: the suggested decisions
                st.session_state["studio_pick"] = orc.suggest_check_decisions(ctx.viewer)
            st.session_state["studio_pick"] = [d for d in st.session_state["studio_pick"] if d in options][:2]
            choice = st.multiselect("Decisions you didn't make (up to 2)", options, key="studio_pick",
                                    max_selections=2, format_func=lambda i: f"{dlabel(i)} · {ctx.cards[i].title}")
            if st.button("Get my questions", width="stretch"):
                made = orc.start_check(ctx.viewer, choice)
                if made:
                    st.session_state["studio_focus"] = f"practice_open:{made[0].id}"
                    st.rerun()
                st.info("No new questions for these decisions: they are not confirmed yet, or you already "
                        "answered both question types.")
    with right:
        task = next((t for t in queue if t.key == focus), None)
        position = f"Item {keys.index(focus) + 1} of {len(keys)}" if task else ""
        with st.container(key="bfc-focus-workspace"):
            if task is None:
                show(ui.empty("Your workspace is clear", "Pick a decision on the left to practise."))
            elif task.kind in ("practice_open", "owner_open"):
                answer_form(ctx, task, position)
            elif task.kind == "owner_start":
                show(f'<div style="display:flex;justify-content:space-between;gap:12px">'
                     f'{ui.label(f"{dlabel(task.decision_id)} · {task.title}")}{ui.label(position)}</div>'
                     f'{mode_banner(True, owner=True)}<p class="bf-question">Verify a decision you own</p>'
                     '<p class="bf-support">Owning a decision is not proof you can defend it: one independent '
                     "question, no hints. Only a full answer lets you mentor a teammate on it.</p>")
                if st.button("Start owner check", key="own-start", type="primary"):
                    try:
                        q = orc.start_owner_check(ctx.viewer, task.decision_id)
                        st.session_state["studio_focus"] = f"owner_open:{q.id}"
                        st.rerun()
                    except ValueError as err:
                        st.warning(str(err))
            else:
                retest_panel(ctx, task, position)
        with st.container(key="bfc-results"):
            section("Your recent results", "Private feedback, newest first.")
            done = sorted(((q, ev) for q, ev in orc.my_questions(ctx.viewer, ctx.viewer) if ev is not None),
                          key=lambda x: x[1].created_at, reverse=True)[:5]
            if not done:
                show('<p class="bf-support">Nothing answered yet.</p>')
            for q, ev in done:
                with st.container(key=f"bfr-done-{q.id}"):
                    show(f'<div class="bf-chips">{ui.evidence_chip(ev.status.value)}'
                         f'<span class="bf-label" style="align-self:center">{ui.esc(dlabel(q.decision_id))} · '
                         f'{ui.esc(q.question_type.value.replace("_", " "))}</span></div>'
                         f'<p class="bf-support" style="margin-top:8px">{ui.esc(q.prompt)}</p>'
                         f'<p class="bf-result">Result: {ui.esc(ev.feedback)}</p>')


# ================================================================== D. Peer Missions

def flow_html(ctx: Ctx, m) -> str:
    def person(mid: str, role: str, ok: bool) -> str:
        initial = ui.esc(ctx.names[mid].split()[-1][:1])
        tone = "teal" if ok else "neutral"
        return (f'<div style="display:flex;gap:10px;align-items:center"><span class="bf-chip bf-{tone}" '
                f'style="width:38px;height:38px;justify-content:center;padding:0;font-size:1rem">{initial}</span>'
                f'<div>{ui.label(role)}<div class="bf-card-title">{ui.esc(ctx.names[mid])}</div>'
                f'<span class="bf-support">{"agreed ✓" if ok else "not yet agreed"}</span></div></div>')
    return (f'<div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap;margin:14px 0">'
            f'{person(m.mentor_id, "Mentor", m.mentor_consent)}<div aria-hidden="true" '
            f'style="flex:1;min-width:30px;height:2px;background:linear-gradient(90deg,var(--bf-violet),var(--bf-teal))"></div>'
            f'{person(m.learner_id, "Learner", m.learner_consent)}</div>')


def missions_page(ctx: Ctx) -> None:
    need_viewer(ctx)
    states = [mission_public_state(m, ctx.viewer) for m in ctx.missions]
    show(ui.page_head("Peer Missions", 'Turn one defender into <span class="accent">two.</span>',
                      "For each decision only one person can explain, a teammate who can explain it teaches one who "
                      "wants to learn, only if both agree. A new independent question then verifies the transfer.",
                      [(str(states.count("accepted") + states.count("completed")), "agreed"),
                       (str(states.count("verified")), "verified")]))
    st.button("Find knowledge silos and propose missions", type="primary", on_click=orc.propose_missions)
    if not ctx.missions:
        show(ui.empty("No missions yet", "Missions appear for decisions that depend on one person or nobody."))
        return
    with st.container(key="bfx-grid-missions"):
        cols = st.columns(2, gap="medium")
    for i, (m, state) in enumerate(zip(ctx.missions, states)):
        involved = ctx.viewer in (m.mentor_id, m.learner_id)
        with cols[i % 2], st.container(key=f"bfc-mission-{m.id}"):
            show(f'<div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">'
                 f'{ui.label(f"Mission · {dlabel(m.decision_id)}")}{ui.mission_chip(state)}</div>'
                 f'<p class="bf-card-title" style="font-size:1.15rem;margin:10px 0 4px">'
                 f'{ui.esc(ctx.cards[m.decision_id].title)}</p><p class="bf-support"><b style="color:var(--bf-text)">'
                 f'Why it matters:</b> {ui.esc(explain(ctx, m.decision_id)[0])}</p>'
                 + ui.stepper(stages(m, ctx.viewer), "Mission journey"))
            if m.status == MissionStatus.fallback:
                st.write(m.fallback_message)
                if involved:
                    show(f'<p class="bf-support">{ui.esc(explain_mission(m, ctx.labels))}</p>')
                continue
            if not involved and m.status == MissionStatus.proposed:
                show('<p class="bf-support">The people in this mission are shown only to them until both accept.</p>')
                continue
            show(flow_html(ctx, m) + f'<p class="bf-support">{ui.esc(explain_mission(m, ctx.labels))}</p>')
            with st.expander("The four teaching steps"):
                st.markdown("\n".join(f"{n}. {step}" for n, step in enumerate(m.steps, 1)))
            if involved and m.status == MissionStatus.proposed:
                mine = m.mentor_consent if ctx.viewer == m.mentor_id else m.learner_consent
                role = "mentor" if ctx.viewer == m.mentor_id else "learner"
                if mine:
                    st.info("You agreed. Waiting for the other person.")
                elif st.button(f"I agree to take part as {role}", key=f"acc-{m.id}", type="primary"):
                    orc.accept_mission(m.id, ctx.viewer)
                    st.rerun()
            if ctx.viewer == m.learner_id and m.status in (MissionStatus.accepted, MissionStatus.completed):
                st.button("Go to my independent retest", key=f"to-rt-{m.id}", type="primary",
                          on_click=go("Defense Studio", studio_focus=f"retest_start:{m.id}"))


# ================================================================== E. Decision Library

REVIEW_VIEWS = {"All": None, "Needs review": ReviewStatus.proposed, "Confirmed": ReviewStatus.verified,
                "No source": ReviewStatus.unsupported}
REVIEW_CHIP = {"verified": ("Confirmed against its source", "teal", "✓"),
               "proposed": ("Proposed · needs review", "amber", "◇"),
               "unsupported": ("No verified source", "red", "×")}


def decision_card(ctx: Ctx, d, focused: bool = False) -> None:
    with st.container(key=f"bfc-{'focus-' if focused else ''}dec-{d.id}"):
        owner = ctx.names.get(d.owner_id, "not declared")
        show(f'{ui.label(f"{dlabel(d.id)} · {d.importance.value} · owner: {owner}")}'
             f'<p class="bf-card-title" style="font-size:1.2rem;margin:8px 0 10px">{ui.esc(d.title)}</p>'
             f'<div class="bf-chips">{ui.chip(*REVIEW_CHIP[d.review_status.value])}'
             # the knowledge chip only adds information once the card is confirmed
             + (f' {ui.knowledge_chip(decision_state(ctx, d.id))}' if d.review_status == ReviewStatus.verified else "")
             + f'</div><p style="margin-top:14px"><b>Why.</b> {ui.esc(d.rationale)}</p>'
             + (f'{ui.label("Instead of")}{ui.alternatives(d.alternatives)}' if d.alternatives else "")
             + "".join(ui.quote(r) for r in d.source_refs))
        if d.review_status == ReviewStatus.unsupported:
            st.warning("No verified source: the quote is not on the cited page, so this decision is never assessed.")
        if d.review_status == ReviewStatus.proposed:
            show('<p class="bf-support">Proposed: not assessed until a member checks the quote and confirms it.</p>')
            if ctx.viewer is None:
                show('<p class="bf-support">Add members first: only a member can confirm a decision.</p>')
            else:
                owner_pick = st.selectbox("Owner (who made this decision)", [None, *ctx.members], key=f"owner-{d.id}",
                                          format_func=lambda m: "not declared" if m is None else ctx.names[m])
                if st.button("Confirm card", key=f"confirm-{d.id}", type="primary"):
                    orc.confirm_decision(d.id, {"owner_id": owner_pick} if owner_pick else None, actor=ctx.viewer)
                    st.rerun()
        st.button("Spotlight in the Atlas", key=f"lib-spot-{d.id}",
                  on_click=go("Knowledge Atlas", atlas_selected=d.id))


def library(ctx: Ctx) -> None:
    by = Counter(d.review_status for d in ctx.cards.values())
    show(ui.page_head("Decision Library · evidence explorer",
                      'What the team decided, <span class="accent">and the page that proves it.</span>',
                      "Every key decision with its reasoning, the alternatives the team rejected and the exact quote it "
                      "rests on. A decision is assessed only after a member confirms it against its source.",
                      [(f"{by[ReviewStatus.verified]}/{len(ctx.cards)}", "confirmed"),
                       (str(by[ReviewStatus.proposed]), "to review")]))
    if not ctx.cards:
        show(ui.empty("No decisions yet", "Add them in Project Setup, by hand or with the live model."))
        return
    with st.container(key="bfx-lib-filters"):
        c1, c2 = st.columns([2.2, 1], vertical_alignment="bottom")
    view = c1.segmented_control("Review state", list(REVIEW_VIEWS), default="All", key="lib_view") or "All"
    query = c2.text_input("Search", key="lib_query", placeholder="Title, rationale or alternative").strip().casefold()
    focus = st.session_state.get("library_focus")
    shown = [d for d in ctx.cards.values()
             if (REVIEW_VIEWS[view] is None or d.review_status == REVIEW_VIEWS[view])
             and (not query or query in " ".join([d.title, d.rationale, *d.alternatives]).casefold())]
    shown.sort(key=lambda d: (d.id != focus, d.id))
    if not shown:
        show(ui.empty("No decision matches", "Change the filter or the search."))
    with st.container(key="bfx-grid-library"):
        cols = st.columns(2, gap="medium")
    for i, d in enumerate(shown):
        with cols[i % 2]:
            decision_card(ctx, d, focused=d.id == focus)


# ================================================================== F. Project Setup

def setup(ctx: Ctx) -> None:
    p = ctx.project
    by = {s: [d for d in ctx.cards.values() if d.review_status == s] for s in ReviewStatus}
    consenting = [m for m in ctx.members.values() if m.consent_assessment]
    show(ui.page_head("Project Setup · guided start", 'From a report to <span class="accent">a team that can defend it.</span>',
                      "Six steps, each checked against what is actually stored. The synthetic demo is fixed; create "
                      "your own project to use BusFactor for real. Choosing a name in the top bar is a demo identity "
                      "switch, not a login."))
    steps = [("Project", bool(p)), ("Team", bool(ctx.members)), ("Material", bool(p and p.source_files)),
             ("Decisions", bool(ctx.cards)), ("Confirm", bool(by[ReviewStatus.verified]) and not by[ReviewStatus.proposed]),
             ("Begin", bool(consenting))]
    first_open = next((i for i, (_, ok) in enumerate(steps) if not ok), None)
    with st.container(key="bfc-steps"):
        show(ui.stepper([(name, "done" if ok else ("now" if i == first_open else "todo"))
                         for i, (name, ok) in enumerate(steps)], "Setup progress"))
        if not ctx.members:
            next_step = "Add the team members below. Each member then opts in to assessment in the Defense Studio."
        elif not ctx.cards:
            next_step = "Add the project's key decisions: by hand (each quote is checked) or with the live model."
        elif by[ReviewStatus.proposed]:
            next_step = (f"Review {len(by[ReviewStatus.proposed])} proposed decision(s): check the quote, choose the "
                         "owner, confirm. Nothing is assessed before it is confirmed.")
        elif not consenting:
            next_step = "Decisions are confirmed. Each member now opts in for themselves in the Defense Studio."
        else:
            next_step = "Decisions are confirmed. Members can now take private checks and owners their owner checks."
        st.info(f"**Next step:** {next_step}")
        show(f'<p class="bf-support">{ui.esc(p.title)} · {ui.esc(p.course or "No course given")} · documents: '
             f'{ui.esc(", ".join(p.source_files) or "none yet")}</p>')

    with st.container(key="bfx-setup"):
        left, right = st.columns([1.35, 1], gap="large")
    with right:
        with st.container(key="bfc-new"):
            section("Start a new project", "Added next to the existing ones; nothing is deleted.")
            with st.expander("New project form", expanded=False):
                st.caption("Members start with every consent off. Only upload documents you are allowed to share.")
                with st.form("new-project"):
                    new_title = st.text_input("Project title")
                    new_course = st.text_input("Course")
                    new_doc = st.file_uploader("Project report (PDF, Markdown or text)", type=["pdf", "md", "txt"])
                    new_names = st.text_area("Team members, one name per line")
                    if st.form_submit_button("Create project", type="primary"):
                        try:
                            with st.spinner("Creating the project…"):
                                orc.create_project(new_title, new_course,
                                                   [(new_doc.name, new_doc.getvalue())] if new_doc else [],
                                                   new_names.splitlines(), actor=ctx.viewer or "agent")
                            for key in FOCUS_KEYS:
                                st.session_state.pop(key, None)
                            st.rerun()
                        except ValueError as err:
                            st.error(str(err))
        if not ctx.demo:
            with st.container(key="bfc-danger"):
                section("Danger zone", "Deleting removes this project's decisions, members, answers, missions, "
                        "documents and log. It cannot be undone; other projects are not affected.")
                with st.expander("Delete this project"):
                    typed = st.text_input("Type the project title to confirm", key="delete-title")
                    if st.button("Delete project", disabled=typed.strip() != p.title):
                        orc.delete_project(p.id, typed, actor=ctx.viewer or "agent")
                        for key in FOCUS_KEYS:
                            st.session_state.pop(key, None)
                        st.rerun()
    with left:
        if ctx.demo:
            with st.container(key="bfc-demo"):
                section("This is the synthetic demo", "Its fictional members and decisions are fixed. Explore it, or "
                        "start your own project on the right.")
                st.button("Open the Decision Library", key="setup-lib", on_click=go("Decision Library"))
        else:
            with st.container(key="bfc-team"):
                section(f"Step 2 · Team ({len(ctx.members)})", "Each member opts in for themselves in the Defense Studio.")
                show('<div class="bf-chips" style="margin:6px 0 4px">'
                     + ("".join(ui.chip(n, "neutral", "●") for n in ctx.names.values()) or
                        '<span class="bf-support">No members yet.</span>') + "</div>")
                with st.form("add-member", clear_on_submit=True):
                    new_member = st.text_input("Add a member (name)")
                    if st.form_submit_button("Add member"):
                        try:
                            orc.add_member(new_member, actor=ctx.viewer or "agent")
                            st.rerun()
                        except ValueError as err:
                            st.error(str(err))
            with st.container(key="bfc-decisions"):
                section("Steps 3–4 · Material and decisions", "Every quote is checked against the cited page.")
                if not p.source_files:
                    st.warning("This project has no document, so no decision can be source-checked. Start a new "
                               "project with its report.")
                else:
                    if not ctx.cards:
                        if st.button("Propose decisions with the live model", disabled=not llm_available()):
                            try:
                                with st.spinner("Reading the report and checking every quote…"):
                                    orc.extract_project_decisions(actor=ctx.viewer or "agent")
                                st.rerun()
                            except (LLMUnavailable, ValueError) as err:
                                st.error(str(err))
                        if not llm_available():
                            st.caption(orc.EXTRACTION_NEEDS_MODEL)
                    with st.form("add-decision", clear_on_submit=True):
                        st.caption("Copy the quote word for word from the document; it is checked against that page.")
                        d_title = st.text_input("Decision (what the team chose)")
                        d_why = st.text_area("Rationale (why, in the team's words)", height=80)
                        d_alts = st.text_input("Rejected alternatives (comma-separated)")
                        f1, f2 = st.columns([3, 1])
                        d_file = f1.selectbox("Document", p.source_files)
                        d_page = f2.number_input("Page", min_value=1, step=1)
                        d_quote = st.text_area("Exact quote from that page", height=80)
                        if st.form_submit_button("Add decision"):
                            try:
                                card = orc.add_decision(title=d_title, rationale=d_why, alternatives=d_alts.split(","),
                                                        source_file=d_file, page=int(d_page), quote=d_quote,
                                                        actor=ctx.viewer or "agent")
                                if card.review_status == ReviewStatus.unsupported:
                                    st.warning("Added, but the quote was not found on that page, so it can never be "
                                               "assessed. Check the page number and the exact wording.")
                                else:
                                    st.rerun()
                            except ValueError as err:
                                st.error(str(err))
            st.button("Open the Decision Library", key="setup-lib", on_click=go("Decision Library"))

    if by[ReviewStatus.proposed]:
        st.markdown("### Step 5 · Confirm source-backed decisions")
        with st.container(key="bfx-grid-review"):
            cols = st.columns(2, gap="medium")
        for i, d in enumerate(by[ReviewStatus.proposed]):
            with cols[i % 2]:
                decision_card(ctx, d)


# ================================================================== G. Trust Center

def trust(ctx: Ctx) -> None:
    need_viewer(ctx)
    show(ui.page_head("Trust Center", 'What BusFactor knows, <span class="accent">and what it can\'t promise.</span>',
                      "Where every decision comes from, what the agent did, and the limits of this prototype."))
    live = llm_available()
    show('<section class="bf-metrics" aria-label="Trust facts">' + "".join([
        ui.metric("Identity", "Demo switch", "Choosing a member is not a login. Anyone using the app can act as any "
                  "member.", "", ui.chip("not authentication", "amber", "!")),
        ui.metric("Grading", "Live model" if live else "Offline", orc.grading_mode(), ""),
        ui.metric("Privacy", "Counts only", "Team views never show names next to results, scores or answers; the log "
                  "below shows only shared steps and your own.", ""),
        ui.metric("Data", "Live API" if live else "This machine",
                  "Project text and answers are sent to the model API." if live
                  else "Answers, documents and the log stay in local files on this machine.", ""),
    ]) + "</section>")
    log = orc.team_log(ctx.viewer)  # team events + the viewer's own private steps, never other members'

    def log_rows(events):
        return [[e.ts.strftime("%H:%M:%S"), e.actor, e.action, str(e.detail)] for e in events]

    sources, actions, abstain, limits = st.tabs(["Evidence table", "Action log", "Abstentions & blocked", "Limits"])
    with sources:
        show(ui.table(["Decision", "Status", "Document", "Page", "Quote"],
                      [[dlabel(d.id), d.review_status.value, ", ".join(r.file for r in d.source_refs) or "none",
                        ", ".join(str(r.page) for r in d.source_refs), " / ".join(r.quote for r in d.source_refs)]
                       for d in ctx.cards.values()], mono=(0, 3)))
    with actions:
        st.caption("Shared project steps, plus your own private steps. Other members' checks, consents and retests "
                   "are never shown here, and answers and scores are never written to the log.")
        show(ui.table(["Time", "Actor", "Action", "Detail"], log_rows(log[::-1]), mono=(0, 2, 3)))
    with abstain:
        flagged = [e for e in log if any(k in e.action for k in ("abstain", "blocked", "answer_request", "flagged"))
                   or e.detail.get("abstained")]
        if flagged:
            show(ui.table(["Time", "Actor", "Action", "Detail"], log_rows(flagged), mono=(0, 2, 3)))
        else:
            show(ui.empty("Nothing blocked or abstained", "Requests for answers and unscorable answers appear here."))
    with limits:
        items = [
            ("No login", "The top bar picks a demo identity. Anyone using the app can act as any member."),
            ("Formative scores", "Scores are practice feedback, not grades. A score from the model can be wrong."),
            ("One day, one answer", "A correct answer shows someone explained one decision once, not that they'll "
             "remember it."),
            ("Prototype metric", "Decision Coverage is a prototype indicator, not a validated measure."),
            ("Demo rubric", "In the synthetic demo, answers are scored offline with a keyword rubric on made-up data. "
             "A score of 2 also needs explained reasoning and the scenario's own conclusion."),
            ("Human review", "Without the live model, your own projects are never scored automatically. With it, "
             "unsure or inconsistent grades also go to human review."),
            ("Instructions in answers", "Answers that try to instruct the grader are never scored. The app cannot stop "
             "anyone from using an outside AI tool."),
            ("Sources first", "No source means no assessment; a decision is assessed only after a member confirms it."),
            ("No invented mentors", "If nobody can explain a decision, the app points to the course material or the TA."),
            ("Small teams", "Even totals can identify people in a small team, so team views show only counts per "
             "decision."),
        ]
        show(ui.table(["Limit", "What it means"], [[k, v] for k, v in items]))


ROUTES: dict[str, Callable[[Ctx], None]] = dict(zip(NAV, [mission_control, atlas, studio, missions_page, library,
                                                          setup, trust]))
