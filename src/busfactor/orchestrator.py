"""Orchestrator — the deterministic backbone of the loop (Teammate 4).

check -> silo -> mission -> retest -> coverage. Every step is written to the action log,
and each action has a budget of 6 steps. Logs never contain answers or scores
(they are private); they contain ids, counts and statuses that are already team-visible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from busfactor import database as db
from busfactor.coverage import compute_coverage
from busfactor.interview import UnsupportedDecision, create_interview, create_transfer_test, is_assessable
from busfactor.knowledge import confirm_card, extract_decisions
from busfactor.llm_provider import demo_mode
from busfactor.missions import apply_retest, recommend_missions, set_consent
from busfactor.models import (
    AssessmentEvidence, CoverageReport, DecisionCard, EvidenceStatus, InterviewQuestion, Member, MissionStatus,
    Project, QuestionType, TeachingMission,
)
from busfactor.rubrics import REFUSAL, evaluate_answer, is_answer_request, practice_hint

STEP_BUDGET = 6
DEMO_BADGE = "DEMO DATA — synthetic"


class _Steps:
    """Counts and logs the steps of one action; refuses to exceed the budget."""

    def __init__(self, actor: str, action: str):
        self.actor, self.action, self.n = actor, action, 0

    def __call__(self, step: str, **detail) -> None:
        self.n += 1
        if self.n > STEP_BUDGET:
            raise RuntimeError(f"{self.action} exceeded its step budget of {STEP_BUDGET}")
        db.log(self.actor, f"{self.action}.{step}", detail)


@dataclass
class Result:
    blocked: bool = False
    message: str = ""
    evidence: Optional[AssessmentEvidence] = None   # private: show only to its owner
    mission: Optional[TeachingMission] = None
    coverage: Optional[CoverageReport] = None
    extra: dict = field(default_factory=dict)


# ------------------------------------------------------------------ setup

def seed_demo_data() -> None:
    db.seed_demo()
    _snapshot("baseline")


def ensure_seeded() -> None:
    if not db.load_all(Member):
        seed_demo_data()


def demo_banner() -> Optional[str]:
    """Badge text when demo mode is on or synthetic demo data is loaded (brief test 10)."""
    seeded = any(e.action == "seed_demo" for e in db.load_log())
    return DEMO_BADGE if demo_mode() or seeded else None


def project() -> Optional[Project]:
    found = db.load_all(Project)
    return found[0] if found else None


def members() -> dict[str, Member]:
    return {m.id: m for m in db.load_all(Member)}


def decisions() -> list[DecisionCard]:
    return db.load_all(DecisionCard)


def setup_project(files: list[str], actor: str = "agent") -> list[DecisionCard]:
    s = _Steps(actor, "setup_project")
    s("read_files", files=[str(f) for f in files])
    cards = extract_decisions(files)
    s("extract_decisions", proposed=[c.id for c in cards if c.review_status.value == "proposed"],
      unsupported=[c.id for c in cards if c.review_status.value == "unsupported"],
      verified_demo=[c.id for c in cards if c.review_status.value == "verified"])
    for card in cards:
        db.save_record(card)
    s("save", count=len(cards))
    return cards


def confirm_decision(decision_id: str, edits: Optional[dict] = None, actor: str = "agent") -> DecisionCard:
    card = confirm_card(db.get_record(DecisionCard, decision_id), edits)
    db.save_record(card)
    db.log(actor, "confirm_card", {"decision_id": decision_id, "edited": sorted((edits or {}).keys())})
    return card


# ------------------------------------------------------------------ private check

def my_questions(viewer_id: str, member_id: str) -> list[tuple[InterviewQuestion, Optional[AssessmentEvidence]]]:
    """A member's own questions with their latest evidence. Only the member may call this."""
    evidence = db.get_private_evidence(viewer_id, member_id)  # raises for anyone else
    latest = {e.question_id: e for e in evidence}
    return [(q, latest.get(q.id)) for q in db.load_all(InterviewQuestion, member_id=member_id)]


def suggest_check_decisions(member_id: str) -> list[str]:
    """2 decisions the member does not own and has not demonstrated, with a question type left."""
    own = db.get_private_evidence(member_id, member_id)
    demonstrated = {e.decision_id for e in own if e.rubric_score == 2}
    asked = db.load_all(InterviewQuestion, member_id=member_id)
    picks = []
    for d in decisions():
        types = {q.question_type for q in asked if q.decision_id == d.id}
        if (d.owner_id != member_id and is_assessable(d) and d.id not in demonstrated
                and not {QuestionType.why, QuestionType.what_if} <= types):
            picks.append(d.id)
    return picks[:2]


def start_check(member_id: str, decision_ids: Optional[list[str]] = None) -> list[InterviewQuestion]:
    s = _Steps("agent", "start_check")
    chosen = decision_ids or suggest_check_decisions(member_id)
    s("select_decisions", member_id=member_id, decision_ids=chosen)
    cards = {d.id: d for d in decisions()}
    created = []
    for did in chosen[:2]:
        prior = db.load_all(InterviewQuestion, member_id=member_id)
        try:
            q = create_interview(cards[did], member_id, prior)
        except UnsupportedDecision:
            s("abstain", decision_id=did, reason="no verified source -> insufficient_evidence")
            continue
        except ValueError as err:
            s("skip", decision_id=did, reason=str(err))
            continue
        db.save_record(q)
        created.append(q)
        s("create_interview", decision_id=did, question_id=q.id, question_type=q.question_type.value)
    return created


def submit_answer(question_id: str, answer: str, viewer_id: str) -> Result:
    q = db.get_record(InterviewQuestion, question_id)
    if q is None:
        raise KeyError(question_id)
    if viewer_id != q.member_id:
        raise PermissionError("You can only answer your own questions.")
    if q.mode == "independent":
        raise ValueError("Independent questions are answered through submit_retest.")
    s = _Steps(viewer_id, "submit_answer")
    decision = db.get_record(DecisionCard, q.decision_id)
    if is_answer_request(answer):
        s("answer_request", question_id=q.id, mode=q.mode)
        return Result(blocked=True, message=practice_hint(decision))
    ev = evaluate_answer(q, answer, decision)
    db.save_record(ev)
    s("evaluate_answer", question_id=q.id, evidence_id=ev.id,
      abstained=ev.status == EvidenceStatus.insufficient_evidence)
    return Result(evidence=ev)


# ------------------------------------------------------------------ coverage and missions

def team_coverage() -> CoverageReport:
    return compute_coverage(decisions(), db.evidence_for_coverage())


def _snapshot(label: str) -> CoverageReport:
    report = team_coverage()
    db.log("agent", "coverage_snapshot", {"label": label, "numerator": report.numerator,
                                          "denominator": report.denominator, "spof": report.spof_decision_ids})
    return report


def coverage_snapshots() -> list[dict]:
    return [e.detail for e in db.load_log() if e.action == "coverage_snapshot"]


def propose_missions() -> list[TeachingMission]:
    s = _Steps("agent", "propose_missions")
    recs = recommend_missions(decisions(), db.evidence_for_coverage(), members())
    s("recommend_missions", count=len(recs))
    existing = {m.id: m for m in db.load_all(TeachingMission)}
    for m in recs:
        old = existing.get(m.id)
        if old is None or (old.status == MissionStatus.proposed and not (old.mentor_consent or old.learner_consent)):
            db.save_record(m)
    s("save", mission_ids=[m.id for m in recs])
    return db.load_all(TeachingMission)


def missions() -> list[TeachingMission]:
    return db.load_all(TeachingMission)


def accept_mission(mission_id: str, member_id: str) -> TeachingMission:
    mission = set_consent(db.get_record(TeachingMission, mission_id), member_id)
    db.save_record(mission)
    db.log(member_id, "accept_mission", {"mission_id": mission_id, "status": mission.status.value})
    return mission


def start_retest(mission_id: str, viewer_id: str) -> InterviewQuestion:
    mission = db.get_record(TeachingMission, mission_id)
    if viewer_id != mission.learner_id:
        raise PermissionError("Only the learner takes the retest.")
    if mission.status not in (MissionStatus.accepted, MissionStatus.completed):
        raise ValueError("Both mentor and learner must accept the mission first.")
    s = _Steps("agent", "start_retest")
    decision = db.get_record(DecisionCard, mission.decision_id)
    prior_qs = [q for q in db.load_all(InterviewQuestion, member_id=mission.learner_id)
                if q.decision_id == mission.decision_id]
    current = db.get_record(InterviewQuestion, mission.retest_question_id) if mission.retest_question_id else None
    prior = current or (prior_qs[-1] if prior_qs else create_interview(decision, mission.learner_id, []))
    q = create_transfer_test(decision, prior)
    db.save_record(q)
    db.save_record(mission.model_copy(update={"retest_question_id": q.id}))
    s("create_transfer_test", mission_id=mission_id, question_id=q.id, differs_from=prior.id)
    return q


def submit_retest(mission_id: str, answer: str, viewer_id: str) -> Result:
    mission = db.get_record(TeachingMission, mission_id)
    if viewer_id != mission.learner_id:
        raise PermissionError("Only the learner answers the retest.")
    if mission.retest_question_id is None:
        raise ValueError("Start the retest first.")
    s = _Steps(viewer_id, "submit_retest")
    if is_answer_request(answer):  # independent mode: blocked in code
        s("blocked_answer_request", mission_id=mission_id)
        return Result(blocked=True, message=REFUSAL)
    q = db.get_record(InterviewQuestion, mission.retest_question_id)
    ev = evaluate_answer(q, answer, db.get_record(DecisionCard, mission.decision_id))
    db.save_record(ev)
    s("evaluate_answer", question_id=q.id, evidence_id=ev.id)
    mission = apply_retest(mission, ev)
    db.save_record(mission)
    s("apply_retest", mission_id=mission_id, status=mission.status.value)
    report = _snapshot(f"after retest {mission_id}")
    return Result(evidence=ev, mission=mission, coverage=report)
