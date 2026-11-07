"""Coverage — which critical decisions can at least two members explain? (Teammate 3)

Deterministic, no LLM. Evidence is the single source of truth:
- only critical decisions count; a decision that is not `verified` cannot be assessed;
- per member, their LATEST judged evidence on a decision counts (insufficient_evidence is ignored);
- `not_assessed` is never treated as failed and is left out of the denominator.
"""
from __future__ import annotations

from busfactor.models import (
    AssessmentEvidence, CoverageReport, DecisionCard, DecisionCoverage, EvidenceStatus, Importance, ReviewStatus,
)


def latest_by_member(evidence: list[AssessmentEvidence], decision_id: str) -> dict[str, AssessmentEvidence]:
    """member_id -> their most recent judged evidence for this decision."""
    latest: dict[str, AssessmentEvidence] = {}
    judged = [e for e in evidence if e.decision_id == decision_id and e.status != EvidenceStatus.insufficient_evidence]
    for e in sorted(judged, key=lambda e: e.created_at):  # stable: later records win
        latest[e.member_id] = e
    return latest


def decision_status(decision: DecisionCard, evidence: list[AssessmentEvidence]) -> DecisionCoverage:
    latest = latest_by_member(evidence, decision.id) if decision.review_status == ReviewStatus.verified else {}
    demonstrated = sorted(m for m, e in latest.items() if e.rubric_score == 2)
    if not latest:
        status = "not_assessed"
    elif len(demonstrated) >= 2:
        status = "covered"
    elif len(demonstrated) == 1:
        status = "single_point_of_failure"
    else:
        status = "no_explainer"
    return DecisionCoverage(decision_id=decision.id, demonstrated_by=demonstrated, status=status)


def compute_coverage(decisions: list[DecisionCard], evidence: list[AssessmentEvidence]) -> CoverageReport:
    critical = sorted((d for d in decisions if d.importance == Importance.critical), key=lambda d: d.id)
    per_decision = [decision_status(d, evidence) for d in critical]
    assessed = [c for c in per_decision if c.status != "not_assessed"]
    numerator = sum(c.status == "covered" for c in assessed)
    denominator = len(assessed)
    return CoverageReport(
        numerator=numerator,
        denominator=denominator,
        score=numerator / denominator if denominator else None,  # None = "not measurable"
        per_decision=per_decision,
        spof_decision_ids=[c.decision_id for c in per_decision if c.status == "single_point_of_failure"],
        unknown_decision_ids=[c.decision_id for c in per_decision if c.status == "not_assessed"],
    )
