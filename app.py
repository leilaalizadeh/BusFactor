"""BusFactor — Streamlit app (Teammate 4). Run: streamlit run app.py"""
from __future__ import annotations

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

STATUS_LABEL = {
    "covered": "🟢 covered (2+ explainers)",
    "single_point_of_failure": "🔴 single point of failure",
    "no_explainer": "⚫ no explainer yet",
    "not_assessed": "⚪ not assessed",
}
PAGES = ["1. Project Setup", "2. Private Check", "3. Team Coverage", "4. Teach Each Other",
         "5. Defense Retest", "6. Evidence & Limits"]

st.set_page_config(page_title="BusFactor", page_icon="🚌", layout="wide")
orc.ensure_seeded()
members = orc.members()
names = {m.id: m.display_name for m in members.values()}
cards = {d.id: d for d in orc.decisions()}

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("🚌 BusFactor")
    st.caption("Your grade is shared. Your understanding shouldn't be isolated.")
    badge = orc.demo_banner()
    if badge:
        st.error(f"### {badge}\nFictional project, members and answers.")
    viewer = st.selectbox("Who are you?", list(members), format_func=lambda m: f"{names[m]} ({m})")
    page = st.radio("Page", PAGES)
    st.caption("Grader: " + ("live LLM" if llm_available() else "demo keyword rubric (offline, synthetic)"))
    if st.button("Reset demo data"):
        orc.seed_demo_data()
        st.rerun()


def coverage_text(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "not measurable"
    return f"{numerator}/{denominator} ({numerator / denominator:.0%})"


# ------------------------------------------------------------------ 1. setup
if page == PAGES[0]:
    p = orc.project()
    st.header(f"Project Setup — {p.title if p else 'no project'}")
    if p:
        st.caption(f"{p.course} · sources: {', '.join(p.source_files)}")
    upload = st.file_uploader("Upload a permitted project file (PDF, Markdown or text)", type=["pdf", "md", "txt"])
    if upload and st.button("Extract decision cards"):
        dest = ROOT / "uploads" / Path(upload.name).name
        dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(upload.getvalue())
        try:
            orc.setup_project([str(dest)], actor=viewer)
            st.success("Cards extracted. Unsupported cards have no verified quote and cannot be confirmed.")
            st.rerun()
        except (LLMUnavailable, RuntimeError, ValueError) as err:
            st.error(f"Extraction failed: {err}")
    st.subheader("Decision cards")
    for d in cards.values():
        icon = {"verified": "✅", "proposed": "📝", "unsupported": "⚠️"}[d.review_status.value]
        with st.expander(f"{icon} {d.id} · {d.title} · {d.review_status.value}"):
            st.write(f"**Rationale:** {d.rationale}")
            if d.alternatives:
                st.write(f"**Rejected alternatives:** {', '.join(d.alternatives)}")
            st.write(f"**Owner (declared by team):** {names.get(d.owner_id, '—')}")
            for r in d.source_refs:
                st.markdown(f"**Source:** `{r.file}` page {r.page}" + (f" · {r.section}" if r.section else ""))
                st.markdown(f"> {r.quote}")
            if not d.source_refs:
                st.warning("No verified source: this decision will not be assessed (insufficient evidence).")
            if d.review_status == ReviewStatus.proposed and st.button("Confirm card", key=f"confirm-{d.id}"):
                orc.confirm_decision(d.id, actor=viewer)
                st.rerun()

# ------------------------------------------------------------------ 2. private check
elif page == PAGES[1]:
    st.header(f"Private Check — {names[viewer]}")
    st.info("🔒 Only you can see your answers and feedback. Scores are practice feedback, not grades. "
            "Answer in English or Italian; language and grammar never lower the score.")
    others = [d for d in cards.values() if d.owner_id != viewer]
    choice = st.multiselect("Decisions to be checked on (you don't own these)", [d.id for d in others],
                            default=orc.suggest_check_decisions(viewer), max_selections=2,
                            format_func=lambda i: f"{i} · {cards[i].title}")
    if st.button("Get my questions"):
        made = orc.start_check(viewer, choice)
        st.success(f"{len(made)} new question(s)." if made else "No new questions for these decisions.")
    for q, ev in sorted(orc.my_questions(viewer, viewer), key=lambda x: (x[1] is not None, x[0].id)):
        if q.mode == "independent":
            continue  # retests live on page 5
        st.markdown(f"**{q.decision_id} · {q.question_type.value}** — {q.prompt}")
        if ev:
            st.caption(f"Your answer: {ev.answer}")
            st.write(f"Result: **{ev.status.value.replace('_', ' ')}** — {ev.feedback}")
        else:
            with st.form(f"form-{q.id}"):
                answer = st.text_area("Your answer", key=f"a-{q.id}")
                if st.form_submit_button("Submit"):
                    res = orc.submit_answer(q.id, answer, viewer)
                    if res.blocked:
                        st.warning(res.message)
                    else:
                        st.rerun()
        st.divider()

# ------------------------------------------------------------------ 3. coverage
elif page == PAGES[2]:
    st.header("Team Coverage")
    report = orc.team_coverage()
    snaps = orc.coverage_snapshots()
    c1, c2, c3 = st.columns(3)
    if snaps:
        c1.metric("Before (baseline)", coverage_text(snaps[0]["numerator"], snaps[0]["denominator"]))
    c2.metric("Now", coverage_text(report.numerator, report.denominator))
    c3.metric("Single points of failure", len(report.spof_decision_ids))
    st.caption("Decision Coverage = critical decisions demonstrated by ≥2 members ÷ critical decisions with "
               "assessment evidence. A prototype indicator, not a validated metric. "
               "No individual scores or rankings are shown here.")
    st.dataframe(pd.DataFrame([{
        "Decision": c.decision_id, "Title": cards[c.decision_id].title,
        "Status": STATUS_LABEL[c.status], "Members who can explain it": len(c.demonstrated_by),
    } for c in report.per_decision]), hide_index=True, width="stretch")

# ------------------------------------------------------------------ 4. missions
elif page == PAGES[3]:
    st.header("Teach Each Other")
    st.caption("BusFactor coordinates teaching between people; it does not replace your teammate as the teacher.")
    if st.button("Find knowledge silos and propose missions"):
        orc.propose_missions()
        st.rerun()
    for m in orc.missions():
        title = cards[m.decision_id].title
        involved = viewer in (m.mentor_id, m.learner_id)
        public = m.status in (MissionStatus.accepted, MissionStatus.completed, MissionStatus.verified)
        st.subheader(f"{m.decision_id} · {title}")
        st.caption(f"Status: {m.status.value}")
        if m.status == MissionStatus.fallback:
            st.warning(m.fallback_message)
            if involved:
                st.write(explain_mission(m, names))
        elif involved or public:
            st.write(explain_mission(m, names))
            st.write("**Objective:** " + m.objective.replace(m.learner_id, names[m.learner_id], 1))
            for i, step in enumerate(m.steps, 1):
                st.write(f"{i}. {step}")
            if involved and m.status == MissionStatus.proposed:
                mine = m.mentor_consent if viewer == m.mentor_id else m.learner_consent
                role = "mentor" if viewer == m.mentor_id else "learner"
                if mine:
                    st.info("You accepted. Waiting for the other participant.")
                elif st.button(f"I agree to take part as {role}", key=f"acc-{m.id}"):
                    orc.accept_mission(m.id, viewer)
                    st.rerun()
        else:
            st.write("Participants are shown only to them until both accept.")
        st.divider()

# ------------------------------------------------------------------ 5. retest
elif page == PAGES[4]:
    st.header(f"Defense Retest — {names[viewer]}")
    mine = [m for m in orc.missions() if m.learner_id == viewer and m.mentor_id]
    if not mine:
        st.info("You have no teaching mission as a learner.")
    for m in mine:
        st.subheader(f"{m.decision_id} · {cards[m.decision_id].title}")
        if m.status == MissionStatus.proposed:
            st.info("Both participants must accept the mission before the retest.")
            continue
        if m.status == MissionStatus.verified:
            st.success("Transfer verified: you explained this decision on a new question. 🎉")
            continue
        if st.button("Start a new independent question", key=f"rt-{m.id}"):
            orc.start_retest(m.id, viewer)
            st.rerun()
        m = next(x for x in orc.missions() if x.id == m.id)
        if m.retest_question_id:
            q = next(q for q, _ in orc.my_questions(viewer, viewer) if q.id == m.retest_question_id)
            st.warning("Independent check: no hints and no answers are available here.")
            st.markdown(f"**{q.prompt}**")
            with st.form(f"retest-{m.id}"):
                answer = st.text_area("Your answer")
                if st.form_submit_button("Submit"):
                    res = orc.submit_retest(m.id, answer, viewer)
                    if res.blocked:
                        st.error(res.message)
                    else:
                        st.write(f"Result: **{res.evidence.status.value.replace('_', ' ')}** — {res.evidence.feedback}")
                        st.write(f"Mission status: **{res.mission.status.value}** · team coverage now "
                                 f"{coverage_text(res.coverage.numerator, res.coverage.denominator)}")

# ------------------------------------------------------------------ 6. evidence & limits
else:
    st.header("Evidence & Limits")
    st.subheader("Sources behind each decision")
    st.dataframe(pd.DataFrame([{
        "Decision": d.id, "Status": d.review_status.value,
        "File": ", ".join(r.file for r in d.source_refs) or "— none —",
        "Page": ", ".join(str(r.page) for r in d.source_refs), "Quote": " / ".join(r.quote for r in d.source_refs),
    } for d in cards.values()]), hide_index=True, width="stretch")
    log = orc.db.load_log()
    st.subheader("Abstentions and blocked requests")
    flagged = [e for e in log if any(k in e.action for k in ("abstain", "blocked", "answer_request"))
               or e.detail.get("abstained")]
    if flagged:
        st.dataframe(pd.DataFrame([{"time": e.ts, "actor": e.actor, "action": e.action, "detail": str(e.detail)}
                                   for e in flagged]), hide_index=True, width="stretch")
    else:
        st.write("None yet.")
    st.subheader("Action log")
    st.dataframe(pd.DataFrame([{"time": e.ts, "actor": e.actor, "action": e.action, "detail": str(e.detail)}
                               for e in log[::-1]]), hide_index=True, width="stretch")
    st.subheader("Limits")
    st.markdown(
        "- Scores are formative practice feedback, not grades, and a model's score is provisional.\n"
        "- One good answer is evidence for one decision at one time, not proof of lasting mastery.\n"
        "- Decision Coverage is a prototype indicator, not a validated metric.\n"
        "- In demo mode, grading is a keyword rubric on synthetic data, standing in for the LLM grader.\n"
        "- No source → no assessment (`insufficient_evidence`); no qualified teammate → course material / TA.\n"
        "- Small teams: even aggregates can identify people, so the team view shows only counts per decision."
    )
