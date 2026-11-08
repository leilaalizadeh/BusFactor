"""View models: real orchestrator state turned into what one viewer may see. Pure, testable, no Streamlit.

Privacy rules applied here (on top of the orchestrator's):
- team-level views carry counts only, never member ids, scores or answers;
- a failed retest is shown as "accepted" to everyone except the mission's two members;
- personal views (next move, defense queue) are built only for the selected member, from their own data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from busfactor import orchestrator as orc
from busfactor.coverage import explain_status
from busfactor.models import (
    CoverageReport, DecisionCard, InterviewQuestion, Member, MissionStatus, Project, ReviewStatus, TeachingMission,
)

# label, tone, glyph — every status is shown with text and a glyph, never colour alone
KNOWLEDGE = {
    "covered": ("Shared · verified", "teal", "◉"),
    "single_point_of_failure": ("Single point of failure", "amber", "◐"),
    "no_explainer": ("Nobody can defend it yet", "red", "!"),
    "not_assessed": ("Unassessed", "neutral", "○"),
    "unconfirmed": ("Needs review", "neutral", "◇"),
}
MISSION = {
    "proposed": ("Mission proposed", "violet", "◌"),
    "accepted": ("Mission accepted", "violet", "◍"),
    "completed": ("Retest not passed yet", "amber", "↻"),
    "verified": ("Transfer verified", "teal", "✓"),
    "fallback": ("No mentor yet · course material or TA", "neutral", "?"),
}
EVIDENCE = {
    "demonstrated": ("Verified understanding", "teal", "✓"),
    "needs_practice": ("Needs practice", "amber", "◐"),
    "insufficient_evidence": ("Not scored: needs human review", "neutral", "…"),
}
FILTERS = ["All", "Vulnerable", "Verified", "Unassessed", "In a mission", "Needs review"]
VIEW_W, VIEW_H = 820, 560


def dlabel(decision_id: str) -> str:
    """Short decision label: live ids are <project>-D01, the demo uses D01."""
    return decision_id.rsplit("-", 1)[-1]


@dataclass
class Ctx:
    project: Optional[Project]
    demo: bool
    members: dict[str, Member]
    cards: dict[str, DecisionCard]
    viewer: Optional[str]
    report: Optional[CoverageReport]
    missions: list[TeachingMission]
    theme: str = "dark"
    names: dict[str, str] = field(default_factory=dict)

    @property
    def labels(self) -> dict[str, str]:  # for explain_mission: people and decisions
        return {**self.names, **{did: dlabel(did) for did in self.cards}}


def build_ctx(viewer: Optional[str], theme: Optional[str] = None) -> Ctx:
    project = orc.project()
    members = orc.members()
    viewer = viewer if viewer in members else (next(iter(members)) if members else None)
    return Ctx(project=project, demo=orc.is_demo_project() if project else False, members=members,
               cards={d.id: d for d in orc.decisions()}, viewer=viewer,
               report=orc.team_coverage() if project else None, missions=orc.missions(),
               theme=theme or "dark", names={m.id: m.display_name for m in members.values()})


# ------------------------------------------------------------------ decisions and missions

def coverage_of(ctx: Ctx, decision_id: str):
    return next((c for c in ctx.report.per_decision if c.decision_id == decision_id), None) if ctx.report else None


def decision_state(ctx: Ctx, decision_id: str) -> str:
    if ctx.cards[decision_id].review_status != ReviewStatus.verified:
        return "unconfirmed"
    cov = coverage_of(ctx, decision_id)
    return cov.status if cov else "not_assessed"


def explain(ctx: Ctx, decision_id: str) -> tuple[str, str]:
    """(why it has this status, the next useful step), counts only."""
    if decision_state(ctx, decision_id) == "unconfirmed":
        card = ctx.cards[decision_id]
        if card.review_status == ReviewStatus.unsupported:
            return ("Its quote was not found on the cited page, so it is never assessed.",
                    "Check the page and wording in the Decision Library.")
        return ("It is proposed but not confirmed, so it is not counted yet.",
                "A member checks the quote and confirms it in the Decision Library.")
    return explain_status(coverage_of(ctx, decision_id))


def mission_public_state(mission: TeachingMission, viewer: Optional[str]) -> str:
    """What `viewer` may know about a mission's state (a failed attempt is the learner's own business)."""
    if mission.status == MissionStatus.fallback:
        return "fallback"
    involved = viewer is not None and viewer in (mission.mentor_id, mission.learner_id)
    if mission.status == MissionStatus.completed and not involved:
        return "accepted"
    return mission.status.value


def mission_for(ctx: Ctx, decision_id: str) -> Optional[TeachingMission]:
    found = [m for m in ctx.missions if m.decision_id == decision_id]
    return next((m for m in found if m.mentor_id), found[0] if found else None)


def stages(mission: TeachingMission, viewer: Optional[str]) -> list[tuple[str, str]]:
    """Mission journey as (stage label, done|now|todo) for this viewer. Only real, stored states."""
    if mission.status == MissionStatus.fallback:
        return [("No mentor available", "now"), ("Course material or TA", "todo")]
    state = mission_public_state(mission, viewer)
    at = ["proposed", "accepted", "completed", "verified"].index(state)
    consents = int(mission.mentor_consent) + int(mission.learner_consent)
    agree = f"Both agree ({consents}/2)" if at == 0 else "Both agreed"
    return [("Proposed", "done"),
            (agree, "done" if at >= 1 else "now"),
            ("Teach-back & independent retest", "done" if at == 3 else ("now" if at >= 1 else "todo")),
            ("Transfer verified", "done" if at == 3 else "todo")]


# ------------------------------------------------------------------ the Knowledge Constellation

def layout(n: int) -> list[tuple[float, float]]:
    """Deterministic positions on an ellipse around the team core, starting at the top."""
    if n == 0:
        return []
    cx, cy, rx, ry = VIEW_W / 2, VIEW_H / 2 + 6, 300, 190
    if n == 1:
        return [(cx, cy - ry)]
    return [(round(cx + rx * math.sin(2 * math.pi * i / n), 1), round(cy - ry * math.cos(2 * math.pi * i / n), 1))
            for i in range(n)]


def atlas_nodes(ctx: Ctx) -> list[dict]:
    """One node per decision. Team-level, counts only: never member ids, scores or answers."""
    ids = sorted(ctx.cards)
    nodes = []
    for (x, y), did in zip(layout(len(ids)), ids):
        card, cov = ctx.cards[did], coverage_of(ctx, did)
        mission = mission_for(ctx, did)
        nodes.append({
            "id": did, "label": dlabel(did), "title": card.title, "x": x, "y": y,
            "state": decision_state(ctx, did), "critical": card.importance.value == "critical",
            "explainers": len(cov.demonstrated_by) if cov and decision_state(ctx, did) != "unconfirmed" else 0,
            "team": len(ctx.members),
            "mission": mission_public_state(mission, None) if mission else "none",
            "concepts": sorted(card.concept_ids),
        })
    return nodes


def atlas_edges(nodes: list[dict]) -> list[dict]:
    """Decisions that share a course concept (from the reviewed cards) are linked."""
    edges = []
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            shared = sorted(set(a["concepts"]) & set(b["concepts"]))
            if shared:
                edges.append({"a": a["id"], "b": b["id"], "concepts": shared})
    return edges


def matches(node: dict, view: str, query: str = "") -> bool:
    q = query.strip().casefold()
    if q and q not in node["title"].casefold() and q not in node["label"].casefold():
        return False
    return {
        "All": True,
        "Vulnerable": node["state"] in ("single_point_of_failure", "no_explainer"),
        "Verified": node["state"] == "covered",
        "Unassessed": node["state"] == "not_assessed",
        "In a mission": node["mission"] in ("proposed", "accepted", "verified"),
        "Needs review": node["state"] == "unconfirmed",
    }[view]


# ------------------------------------------------------------------ team progress

def pulse_points(ctx: Ctx) -> list[tuple[str, int, int]]:
    """Coverage over time: every stored team snapshot, plus 'now' if it differs from the last one."""
    if not ctx.project:
        return []
    points = [("Start" if i == 0 else f"Change {i}", s["numerator"], s["denominator"])
              for i, s in enumerate(orc.coverage_snapshots())]
    now = ("Now", ctx.report.numerator, ctx.report.denominator)
    if not points or points[-1][1:] != now[1:]:
        points.append(now)
    return points


def feed(ctx: Ctx, limit: int = 7) -> list[tuple[str, str]]:
    """Recent shared progress, in words. Team events only; nobody's private steps."""
    items = []
    for e in orc.team_events():
        d = e.detail
        text = {
            "seed_demo": ("neutral", "Synthetic demo project loaded"),
            "create_project": ("neutral", f"Project created: {d.get('title', '')}"),
            "add_member": ("neutral", f"The team now has {d.get('members', '?')} member(s)"),
            "add_decision": ("neutral", f"Decision {dlabel(d.get('decision_id', ''))} added"),
            "extract_decisions.save": ("neutral", f"{d.get('count', 0)} decisions proposed from the report"),
            "confirm_card": ("teal", f"Decision {dlabel(d.get('decision_id', ''))} confirmed against its source"),
            "propose_missions.save": ("violet", "Teaching missions proposed for "
                                      + (", ".join(dlabel(x) for x in d.get("decision_ids", [])) or "no decision")),
            "mission_accepted": ("violet", f"Mission on {dlabel(d.get('decision_id', ''))} accepted by both people"),
            "coverage_snapshot": ("teal", f"Coverage {d.get('numerator')}/{d.get('denominator')}"
                                  + (" at the start" if d.get("label") == "baseline" else "")),
        }.get(e.action)
        if text:
            items.append(text)
    return items[-limit:][::-1]


# ------------------------------------------------------------------ the selected member

@dataclass
class Task:
    kind: str                 # owner_open | practice_open | retest_open | retest_start | owner_start
    decision_id: str
    title: str
    question: Optional[InterviewQuestion] = None
    mission: Optional[TeachingMission] = None

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.question.id if self.question else (self.mission.id if self.mission else self.decision_id)}"

    @property
    def independent(self) -> bool:
        return self.kind != "practice_open"


def defense_queue(ctx: Ctx) -> list[Task]:
    """The selected member's own open work, most important first. Built only from their own records."""
    v = ctx.viewer
    if not v or not ctx.members[v].consent_assessment:
        return []
    tasks: list[Task] = []
    mine = orc.my_questions(v, v)
    for m in ctx.missions:
        if m.learner_id == v and m.mentor_id and m.status in (MissionStatus.accepted, MissionStatus.completed):
            q, ev = next(((q, ev) for q, ev in mine if q.id == m.retest_question_id), (None, None))
            title = ctx.cards[m.decision_id].title
            tasks.append(Task("retest_open", m.decision_id, title, q, m) if q and ev is None
                         else Task("retest_start", m.decision_id, title, None, m))
    for q, ev in mine:
        if ev is None and q.decision_id in ctx.cards and (q.mode == "practice" or orc.is_owner_check(q)):
            tasks.append(Task("owner_open" if orc.is_owner_check(q) else "practice_open", q.decision_id,
                              ctx.cards[q.decision_id].title, q))
    open_owner = {t.decision_id for t in tasks if t.kind == "owner_open"}
    for did in orc.owner_check_decisions(v):
        if did not in open_owner:
            tasks.append(Task("owner_start", did, ctx.cards[did].title))
    return tasks


@dataclass
class Move:
    title: str
    why: str
    page: str
    cta: str
    focus: Optional[str] = None   # a defense-queue task key or decision id to open


def next_move(ctx: Ctx) -> Move:
    """The single most useful permitted step for the selected member, from real state."""
    if not ctx.members or not ctx.viewer:
        return Move("Add your team", "BusFactor needs the people who will defend the project.", "Project Setup",
                    "Open Project Setup")
    me = ctx.members[ctx.viewer]
    if not me.consent_assessment:
        return Move("Decide on your consent", "You are not assessed until you opt in. It is your choice.",
                    "Defense Studio", "Review my consent")
    proposed = [d for d in ctx.cards.values() if d.review_status == ReviewStatus.proposed]
    if proposed:
        return Move(f"Review {len(proposed)} proposed decision(s)", "Nothing is assessed until a member checks its "
                    "source and confirms it.", "Decision Library", "Review decisions", proposed[0].id)
    if not any(d.review_status == ReviewStatus.verified for d in ctx.cards.values()):
        return Move("Add the project's key decisions", "Each one needs an exact quote from the report.",
                    "Project Setup", "Add decisions")
    queue = defense_queue(ctx)
    for kind, title, why, cta in [
        ("retest_open", "Finish your independent retest", "A new situation, no hints: this is what verifies "
         "the transfer.", "Continue the retest"),
        ("retest_start", "Take your independent retest", "Your teaching mission is agreed. Show the knowledge "
         "moved.", "Start the retest"),
    ]:
        task = next((t for t in queue if t.kind == kind), None)
        if task:
            return Move(f"{title} on {dlabel(task.decision_id)}", why, "Defense Studio", cta, task.key)
    waiting = [m for m in ctx.missions if m.status == MissionStatus.proposed and (
        (m.mentor_id == ctx.viewer and not m.mentor_consent) or (m.learner_id == ctx.viewer and not m.learner_consent))]
    if waiting:
        return Move(f"Respond to a teaching mission on {dlabel(waiting[0].decision_id)}",
                    "A teammate is waiting for your answer. Taking part is voluntary.", "Peer Missions",
                    "Open the mission", waiting[0].decision_id)
    task = next((t for t in queue if t.kind in ("owner_open", "practice_open")), None)
    if task:
        return Move(f"Answer your open question on {dlabel(task.decision_id)}", "Only you see your answer and "
                    "feedback.", "Defense Studio", "Answer it", task.key)
    task = next((t for t in queue if t.kind == "owner_start"), None)
    if task:
        return Move(f"Verify the decision you own: {dlabel(task.decision_id)}", "Owning a decision is not proof "
                    "you can defend it. One independent question settles it.", "Defense Studio",
                    "Start the owner check", task.key)
    covered_by_mission = {m.decision_id for m in ctx.missions}
    risky = [c.decision_id for c in ctx.report.per_decision
             if c.status in ("single_point_of_failure", "no_explainer") and c.decision_id not in covered_by_mission]
    if risky:
        return Move(f"{len(risky)} decision(s) depend on one person or nobody", "A teaching mission pairs someone "
                    "who can explain it with someone who wants to learn.", "Peer Missions", "Find teaching missions")
    suggested = orc.suggest_check_decisions(ctx.viewer)
    if suggested:
        return Move(f"Take a private check on {dlabel(suggested[0])}", "Explain a decision you did not make. "
                    "Only you see the result.", "Defense Studio", "Start a private check", suggested[0])
    return Move("You're defense-ready on everything you can do now", "Explore the constellation and rehearse a "
                "'what if' with a teammate.", "Knowledge Atlas", "Open the Atlas")
