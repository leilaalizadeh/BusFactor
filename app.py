"""BusFactor — Streamlit app (Teammate 4). Run: streamlit run app.py"""
from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402  (ships with streamlit)
import streamlit as st  # noqa: E402

from busfactor import orchestrator as orc  # noqa: E402
from busfactor.llm_provider import LLMUnavailable, llm_available  # noqa: E402
from busfactor.missions import explain_mission  # noqa: E402
from busfactor.models import MissionStatus, ReviewStatus  # noqa: E402

PAGES = ["1. Project Setup", "2. Private Check", "3. Team Coverage", "4. Teach Each Other",
         "5. Defense Retest", "6. Evidence & Limits"]
PAGE_HINTS = ["Key decisions and sources", "Your own questions", "Who can explain what",
              "Peer-teaching missions", "New question, no hints", "Sources, log, limits"]

COVERAGE_PILL = {
    "covered": ("Covered", "green"),
    "single_point_of_failure": ("Single point of failure", "red"),
    "no_explainer": ("No explainer yet", "dark"),
    "not_assessed": ("Not assessed", "gray"),
}
CARD_PILL = {"verified": ("Verified", "green"), "proposed": ("Needs review", "amber"),
             "unsupported": ("No source", "red")}
MISSION_PILL = {"proposed": ("Waiting for consent", "amber"), "accepted": ("Accepted", "blue"),
                "completed": ("Retest not passed yet", "gray"), "verified": ("Transfer verified", "green"),
                "fallback": ("Ask the TA", "dark")}
EVIDENCE_PILL = {"demonstrated": ("Demonstrated", "green"), "needs_practice": ("Needs practice", "amber"),
                 "insufficient_evidence": ("Not assessed: no source", "gray")}

CSS = """
<style>
.block-container {padding-top: 4rem; max-width: 1100px;}
h1, h2, h3 {letter-spacing: -0.01em;}
h1 {font-size: 2.3rem !important;}
div.bf-muted {padding-bottom: 0.35rem;}
.bf-pill {display:inline-block; padding:2px 10px; border-radius:999px; font-size:0.78rem;
          font-weight:600; white-space:nowrap;}
.bf-green {background:#E6F4EA; color:#1E7B3A;}
.bf-red   {background:#FDECEC; color:#B42318;}
.bf-amber {background:#FFF4E0; color:#9A5B00;}
.bf-blue  {background:#E8EEFF; color:#2F4AC0;}
.bf-gray  {background:#EEF0F4; color:#4A5160;}
.bf-dark  {background:#2B2F38; color:#FFFFFF;}
.bf-step  {color:#6B7280; font-size:0.8rem; font-weight:700; text-transform:uppercase;
           letter-spacing:0.07em; margin-bottom:-0.6rem;}
.bf-sub   {color:#5B6270; margin-top:-0.4rem; margin-bottom:1.2rem;}
.bf-quote {border-left:3px solid #3B5BDB; background:#F4F6FA; padding:0.6rem 0.9rem;
           border-radius:6px; font-size:0.92rem; margin:0.4rem 0;}
.bf-muted {color:#6B7280; font-size:0.86rem;}
.bf-badge {background:#FFF4E0; color:#9A5B00; border:1px solid #F5C77E; border-radius:8px;
           padding:0.55rem 0.75rem; font-weight:700; font-size:0.85rem; margin:0.3rem 0 0.8rem;}
.bf-dots  {font-size:1.15rem; letter-spacing:0.18em; color:#3B5BDB;}
.bf-question {background:#F4F6FA; border-radius:10px; padding:1rem 1.2rem; font-size:1.05rem;
              font-weight:500; margin:0.4rem 0 0.8rem;}
.bf-title {font-weight:600; font-size:1.02rem;}
</style>
"""

st.set_page_config(page_title="BusFactor", page_icon="🚌", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
orc.ensure_seeded()
members = orc.members()
names = {m.id: m.display_name for m in members.values()}
cards = {d.id: d for d in orc.decisions()}


# ------------------------------------------------------------------ small UI helpers
def esc(text: object) -> str:
    return html.escape(str(text))


def pill(label: str, kind: str) -> str:
    return f'<span class="bf-pill bf-{kind}">{esc(label)}</span>'


def show(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def page_header(index: int, title: str, subtitle: str) -> None:
    show(f'<div class="bf-step">Step {index} of 6</div>')
    st.title(title)
    show(f'<div class="bf-sub">{esc(subtitle)}</div>')


def coverage_text(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "not measurable"
    return f"{numerator}/{denominator} ({numerator / denominator:.0%})"


def quote_block(ref) -> str:
    where = f"{esc(ref.file)} · page {ref.page}" + (f" · {esc(ref.section)}" if ref.section else "")
    return f'<div class="bf-quote">“{esc(ref.quote)}”<br><span class="bf-muted">{where}</span></div>'


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("## 🚌 BusFactor")
    st.caption("Your grade is shared. Your understanding shouldn't be isolated.")
    badge = orc.demo_banner()
    if badge:
        show(f'<div class="bf-badge">{esc(badge)}<br>'
             '<span style="font-weight:500">Fictional project, members and answers.</span></div>')
    # Optional deep links for demos and screenshots, e.g. ?page=3&as=M04
    qp_page, qp_as = st.query_params.get("page", ""), st.query_params.get("as", "")
    start_page = int(qp_page) - 1 if qp_page.isdigit() and 1 <= int(qp_page) <= len(PAGES) else 0
    member_ids = list(members)
    viewer = st.selectbox("Who are you?", member_ids, format_func=lambda m: f"{names[m]} ({m})",
                          index=member_ids.index(qp_as) if qp_as in member_ids else 0)
    page = st.radio("Go to", PAGES, captions=PAGE_HINTS, index=start_page)
    st.divider()
    st.caption("Grader: " + ("live model" if llm_available() else "demo keyword rubric (offline)"))
    if st.button("Reset demo data", use_container_width=True):
        orc.seed_demo_data()
        st.rerun()


# ------------------------------------------------------------------ 1. setup
if page == PAGES[0]:
    p = orc.project()
    page_header(1, p.title if p else "Project Setup",
                "The key decisions of the project. Each one is linked to the exact page it comes from.")
    if p:
        show(f'<div class="bf-muted">{esc(p.course)} · source: {esc(", ".join(p.source_files))}</div>')

    with st.expander("Upload a different project file"):
        upload = st.file_uploader("PDF, Markdown or text. Only upload files you are allowed to share.",
                                  type=["pdf", "md", "txt"])
        if upload and st.button("Extract decision cards", type="primary"):
            dest = ROOT / "uploads" / Path(upload.name).name
            dest.parent.mkdir(exist_ok=True)
            dest.write_bytes(upload.getvalue())
            try:
                orc.setup_project([str(dest)], actor=viewer)
                st.success("Cards extracted. Cards without a verified quote can't be confirmed.")
                st.rerun()
            except (LLMUnavailable, RuntimeError, ValueError) as err:
                st.error(f"Extraction failed: {err}")

    verified = sum(d.review_status == ReviewStatus.verified for d in cards.values())
    c1, c2, c3 = st.columns(3)
    c1.metric("Decisions", len(cards))
    c2.metric("Verified", verified)
    c3.metric("Without a source", sum(not d.source_refs for d in cards.values()))

    for d in cards.values():
        with st.container(border=True):
            label, kind = CARD_PILL[d.review_status.value]
            left, right = st.columns([5, 1.4])
            left.markdown(f"**{d.id} · {d.title}**")
            with right:
                show(pill(label, kind))
            st.write(d.rationale)
            info = []
            if d.alternatives:
                info.append(f"Rejected: {esc(', '.join(d.alternatives))}")
            info.append(f"Owner: {esc(names.get(d.owner_id, 'not declared'))}")
            show(f'<div class="bf-muted">{" · ".join(info)}</div>')
            for r in d.source_refs:
                show(quote_block(r))
            if not d.source_refs:
                st.warning("No verified source, so this decision will not be assessed.")
            if d.review_status == ReviewStatus.proposed and st.button("Confirm card", key=f"confirm-{d.id}"):
                orc.confirm_decision(d.id, actor=viewer)
                st.rerun()

# ------------------------------------------------------------------ 2. private check
elif page == PAGES[1]:
    page_header(2, f"Private Check · {names[viewer]}",
                "Questions about decisions you didn't make. Only you can see your answers and feedback.")
    st.info("Scores are practice feedback, not grades. You can answer in English or Italian; "
            "grammar and language never lower the score.", icon="🔒")

    with st.container(border=True):
        others = [d for d in cards.values() if d.owner_id != viewer]
        choice = st.multiselect("Choose up to 2 decisions to be checked on",
                                [d.id for d in others], default=orc.suggest_check_decisions(viewer),
                                max_selections=2, format_func=lambda i: f"{i} · {cards[i].title}")
        if st.button("Get my questions", type="primary"):
            made = orc.start_check(viewer, choice)
            st.success(f"{len(made)} new question(s) below." if made else "No new questions for these decisions.")

    pairs = [(q, ev) for q, ev in orc.my_questions(viewer, viewer) if q.mode != "independent"]
    open_qs = [(q, ev) for q, ev in pairs if ev is None]
    done_qs = [(q, ev) for q, ev in pairs if ev is not None]

    st.subheader(f"To answer ({len(open_qs)})")
    if not open_qs:
        show('<div class="bf-muted">Nothing open. Get new questions above.</div>')
    for q, _ in sorted(open_qs, key=lambda x: x[0].id):
        with st.container(border=True):
            show(f'{pill(q.question_type.value.replace("_", " ").title(), "blue")} '
                 f'<span class="bf-muted">{esc(q.decision_id)} · {esc(cards[q.decision_id].title)}</span>')
            show(f'<div class="bf-question">{esc(q.prompt)}</div>')
            with st.form(f"form-{q.id}"):
                answer = st.text_area("Your answer", key=f"a-{q.id}", height=110)
                if st.form_submit_button("Submit", type="primary"):
                    res = orc.submit_answer(q.id, answer, viewer)
                    if res.blocked:
                        st.warning(res.message)
                    else:
                        st.rerun()

    st.subheader(f"Answered ({len(done_qs)})")
    for q, ev in sorted(done_qs, key=lambda x: x[0].id):
        with st.container(border=True):
            label, kind = EVIDENCE_PILL[ev.status.value]
            show(f'{pill(label, kind)} <span class="bf-muted">{esc(q.decision_id)} · '
                 f'{esc(q.question_type.value.replace("_", " "))}</span>')
            show(f'<div class="bf-title" style="margin:0.4rem 0">{esc(q.prompt)}</div>')
            show(f'<div class="bf-muted">Your answer: {esc(ev.answer)}</div>')
            st.markdown(f"Result: {ev.feedback}")

# ------------------------------------------------------------------ 3. coverage
elif page == PAGES[2]:
    page_header(3, "Team Coverage",
                "How many decisions at least two of you can explain. Only counts are shown, never names or scores.")
    report = orc.team_coverage()
    snaps = orc.coverage_snapshots()
    base = snaps[0] if snaps else None

    c1, c2, c3 = st.columns(3)
    if base:
        c1.metric("Before (baseline)", coverage_text(base["numerator"], base["denominator"]))
    gained = report.numerator - base["numerator"] if base else 0
    c2.metric("Now", coverage_text(report.numerator, report.denominator),
              delta=f"+{gained} decision{'s' if gained != 1 else ''}" if gained > 0 else None)
    c3.metric("Single points of failure", len(report.spof_decision_ids))
    if report.denominator:
        st.progress(report.numerator / report.denominator)

    st.subheader("Decisions")
    team_size = len(members)
    for c in report.per_decision:
        with st.container(border=True):
            label, kind = COVERAGE_PILL[c.status]
            n = len(c.demonstrated_by)
            left, mid, right = st.columns([4.5, 1.6, 1.8])
            left.markdown(f"**{c.decision_id} · {cards[c.decision_id].title}**")
            with mid:
                show(f'<span class="bf-dots" title="{n} of {team_size}">{"●" * n}{"○" * (team_size - n)}</span>'
                     f'<br><span class="bf-muted">{n} can explain it</span>')
            with right:
                show(pill(label, kind))

    show('<div class="bf-muted" style="margin-top:0.8rem">Decision Coverage = critical decisions that 2 or more '
         'members can explain ÷ critical decisions that have been assessed. This is a prototype indicator, '
         'not a validated metric. "Not assessed" is never counted as failed.</div>')

# ------------------------------------------------------------------ 4. missions
elif page == PAGES[3]:
    page_header(4, "Teach Each Other",
                "For each decision only one person can explain, a teammate who understands it teaches one who doesn't.")
    if st.button("Find knowledge silos and propose missions", type="primary"):
        orc.propose_missions()
        st.rerun()

    all_missions = orc.missions()
    if not all_missions:
        show('<div class="bf-muted">No missions yet. Press the button above.</div>')
    for m in all_missions:
        involved = viewer in (m.mentor_id, m.learner_id)
        public = m.status in (MissionStatus.accepted, MissionStatus.completed, MissionStatus.verified)
        with st.container(border=True):
            label, kind = MISSION_PILL[m.status.value]
            left, right = st.columns([5, 1.8])
            left.markdown(f"**{m.decision_id} · {cards[m.decision_id].title}**")
            with right:
                show(pill(label, kind))

            if m.status == MissionStatus.fallback:
                st.write(m.fallback_message)
                if involved:
                    show(f'<div class="bf-muted">{esc(explain_mission(m, names))}</div>')
                continue
            if not (involved or public):
                show('<div class="bf-muted">The people in this mission are shown only to them until both accept.</div>')
                continue

            a, b = st.columns(2)
            a.markdown(f"**Mentor:** {names[m.mentor_id]}" + (" ✓" if m.mentor_consent else ""))
            b.markdown(f"**Learner:** {names[m.learner_id]}" + (" ✓" if m.learner_consent else ""))
            show(f'<div class="bf-muted">{esc(explain_mission(m, names))}</div>')
            st.markdown("\n".join(f"{i}. {step}" for i, step in enumerate(m.steps, 1)))

            if involved and m.status == MissionStatus.proposed:
                mine = m.mentor_consent if viewer == m.mentor_id else m.learner_consent
                role = "mentor" if viewer == m.mentor_id else "learner"
                if mine:
                    st.info("You accepted. Waiting for the other person.")
                elif st.button(f"I agree to take part as {role}", key=f"acc-{m.id}", type="primary"):
                    orc.accept_mission(m.id, viewer)
                    st.rerun()

# ------------------------------------------------------------------ 5. retest
elif page == PAGES[4]:
    page_header(5, f"Defense Retest · {names[viewer]}",
                "After the teaching session, answer a new question on your own. No hints are available here.")
    mine = [m for m in orc.missions() if m.learner_id == viewer and m.mentor_id]
    if not mine:
        st.info("You have no teaching mission as a learner.")
    for m in mine:
        with st.container(border=True):
            label, kind = MISSION_PILL[m.status.value]
            left, right = st.columns([5, 1.8])
            left.markdown(f"**{m.decision_id} · {cards[m.decision_id].title}**")
            with right:
                show(pill(label, kind))

            if m.status == MissionStatus.proposed:
                st.write("Both people must accept the mission before the retest.")
                continue
            if m.status == MissionStatus.verified:
                st.success("You explained this decision on a new question. Coverage went up.")
                continue
            if st.button("Start a new independent question", key=f"rt-{m.id}"):
                orc.start_retest(m.id, viewer)
                st.rerun()

            m = next(x for x in orc.missions() if x.id == m.id)
            if m.retest_question_id:
                q = next(q for q, _ in orc.my_questions(viewer, viewer) if q.id == m.retest_question_id)
                show(f'<div class="bf-question">{esc(q.prompt)}</div>')
                with st.form(f"retest-{m.id}"):
                    answer = st.text_area("Your answer", height=130)
                    if st.form_submit_button("Submit", type="primary"):
                        res = orc.submit_retest(m.id, answer, viewer)
                        if res.blocked:
                            st.error(res.message)
                        else:
                            label, kind = EVIDENCE_PILL[res.evidence.status.value]
                            show(pill(label, kind))
                            st.markdown(f"Result: {res.evidence.feedback}")
                            st.markdown(f"Mission status: **{res.mission.status.value}** · team coverage now "
                                        f"{coverage_text(res.coverage.numerator, res.coverage.denominator)}")

# ------------------------------------------------------------------ 6. evidence & limits
else:
    page_header(6, "Evidence & Limits", "Where every decision comes from, what the agent did, and what it can't do.")
    log = orc.db.load_log()

    def log_table(events):
        return pd.DataFrame([{"time": e.ts.strftime("%H:%M:%S"), "actor": e.actor, "action": e.action,
                              "detail": str(e.detail)} for e in events])

    sources, actions, abstain, limits = st.tabs(["Sources", "Action log", "Abstentions & blocked", "Limits"])
    with sources:
        st.dataframe(pd.DataFrame([{
            "Decision": d.id, "Status": d.review_status.value,
            "File": ", ".join(r.file for r in d.source_refs) or "none",
            "Page": ", ".join(str(r.page) for r in d.source_refs),
            "Quote": " / ".join(r.quote for r in d.source_refs),
        } for d in cards.values()]), hide_index=True, width="stretch")
    with actions:
        st.caption("Every step the agent takes. Answers and scores are never written here.")
        st.dataframe(log_table(log[::-1]), hide_index=True, width="stretch")
    with abstain:
        flagged = [e for e in log if any(k in e.action for k in ("abstain", "blocked", "answer_request"))
                   or e.detail.get("abstained")]
        if flagged:
            st.dataframe(log_table(flagged), hide_index=True, width="stretch")
        else:
            st.write("None yet.")
    with limits:
        st.markdown(
            "- Scores are practice feedback, not grades. A score from the model can be wrong.\n"
            "- One correct answer shows someone explained one decision on one day, not that they'll remember it.\n"
            "- Decision Coverage is a prototype indicator, not a validated metric.\n"
            "- In demo mode, answers are scored with a keyword list on made-up data, as a stand-in for the model.\n"
            "- No source means no assessment. If nobody can explain a decision, the app points to the TA.\n"
            "- In a small team even totals can identify people, so the team view shows only counts per decision."
        )
