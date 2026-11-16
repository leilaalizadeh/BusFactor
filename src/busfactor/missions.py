"""Missions — who teaches whom, with consent, and what a retest changes (Teammate 3).

Matching rule (deterministic):
- Only decisions that are a single point of failure or have no explainer get a mission.
- Mentor: demonstrated the decision (latest score 2) AND consent_mentor, max 2 missions each;
  fewest missions first, then alphabetical id.
- Learner: has not demonstrated it AND consent_learner AND consent_assessment (the retest assesses
  them); latest score 1 before 0 before not-assessed; ties -> alphabetical id.
- Mentor and learner must be members of the decision's own project.
- No eligible mentor -> a `fallback` mission pointing to course material / TA. Never a fake mentor.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from busfactor.coverage import compute_coverage, latest_by_member
from busfactor.models import (
    AssessmentEvidence, DecisionCard, EvidenceStatus, Member, MissionStatus, TeachingMission, utcnow,
)

MAX_MISSIONS_PER_MENTOR = 2
FALLBACK_MESSAGE = (
    "Nobody on the team has demonstrated this yet — review the course material for this topic or ask the TA."
)
STEPS = [
    "Mentor explains the decision and one rejected alternative in their own words",
    "Learner challenges it with one \"what if\" question",
    "Learner teaches it back without notes",
    "Learner takes the independent retest in the app",
]


def recommend_missions(
    decisions: list[DecisionCard], evidence: list[AssessmentEvidence], consent: dict[str, Member]
) -> list[TeachingMission]:
    report = compute_coverage(decisions, evidence)
    cards = {d.id: d for d in decisions}
    load: Counter[str] = Counter()
    missions: list[TeachingMission] = []

    for cov in report.per_decision:  # already sorted by decision id
        if cov.status not in ("single_point_of_failure", "no_explainer"):
            continue
        card = cards[cov.decision_id]
        team = {mid: m for mid, m in consent.items() if m.project_id == card.project_id}
        latest = latest_by_member(evidence, cov.decision_id)

        learners = sorted(
            (m for m in team.values()
             if m.consent_learner and m.consent_assessment and m.id not in cov.demonstrated_by),
            key=lambda m: (-(latest[m.id].rubric_score if m.id in latest else -1), m.id),
        )
        if not learners:
            continue
        learner = learners[0]

        mentors = sorted(
            (m for m in cov.demonstrated_by
             if m in team and team[m].consent_mentor and load[m] < MAX_MISSIONS_PER_MENTOR),
            key=lambda m: (load[m], m),
        )
        objective = f"{learner.id} can explain and defend {cov.decision_id}: {card.title}"
        if mentors:
            mentor = mentors[0]
            load[mentor] += 1
            missions.append(TeachingMission(
                id=f"T-{cov.decision_id}-{learner.id}", decision_id=cov.decision_id,
                mentor_id=mentor, learner_id=learner.id, objective=objective, steps=list(STEPS),
                project_id=card.project_id,
            ))
        else:
            missions.append(TeachingMission(
                id=f"T-{cov.decision_id}-{learner.id}", decision_id=cov.decision_id,
                mentor_id=None, learner_id=learner.id, objective=objective,
                status=MissionStatus.fallback, fallback_message=FALLBACK_MESSAGE, project_id=card.project_id,
            ))
    return missions


def set_consent(mission: TeachingMission, member_id: str) -> TeachingMission:
    """Record one participant's consent; both consents -> accepted."""
    if mission.status != MissionStatus.proposed:
        raise ValueError(f"Mission {mission.id} is {mission.status.value}; consent can only be given while proposed.")
    if member_id == mission.mentor_id:
        mission = mission.model_copy(update={"mentor_consent": True})
    elif member_id == mission.learner_id:
        mission = mission.model_copy(update={"learner_consent": True})
    else:
        raise PermissionError(f"{member_id} is not part of mission {mission.id}.")
    if mission.mentor_consent and mission.learner_consent:
        mission = mission.model_copy(update={"status": MissionStatus.accepted, "accepted_at": utcnow()})
    return mission


def apply_retest(mission: TeachingMission, retest_evidence: AssessmentEvidence) -> TeachingMission:
    """Score 2 on the linked transfer question -> verified; otherwise completed (can retry)."""
    if mission.status not in (MissionStatus.accepted, MissionStatus.completed):
        raise ValueError(f"Mission {mission.id} is {mission.status.value}; it must be accepted first.")
    if mission.retest_question_id is None or retest_evidence.question_id != mission.retest_question_id:
        raise ValueError("Evidence is not for this mission's retest question.")
    if retest_evidence.member_id != mission.learner_id or retest_evidence.decision_id != mission.decision_id:
        raise ValueError("Retest evidence must come from the learner on the mission's decision.")
    if mission.project_id and retest_evidence.project_id and mission.project_id != retest_evidence.project_id:
        raise ValueError("Retest evidence belongs to another project.")
    if retest_evidence.status == EvidenceStatus.insufficient_evidence:
        return mission  # not judged (needs human review): neither a pass nor a failed attempt
    passed = retest_evidence.rubric_score == 2 and retest_evidence.status == EvidenceStatus.demonstrated
    if passed:
        return mission.model_copy(update={"status": MissionStatus.verified, "verified_at": utcnow()})
    return mission.model_copy(update={"status": MissionStatus.completed})


def explain_mission(mission: TeachingMission, names: Optional[dict[str, str]] = None) -> str:
    """One sentence for judges and users. Mentions no scores (they are private).
    `names` maps member ids to display names (and may map decision ids to short labels)."""
    n = lambda key: (names or {}).get(key, key)  # noqa: E731
    d = n(mission.decision_id)
    if mission.mentor_id is None:
        return (f"Nobody has demonstrated {d} yet, so no mentor was invented; "
                f"{n(mission.learner_id)} is pointed to course material or the TA.")
    return (f"{n(mission.mentor_id)} was chosen because they demonstrated {d} and are willing to mentor; "
            f"{n(mission.learner_id)} has not demonstrated it yet and is willing to learn.")
