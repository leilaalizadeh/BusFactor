"""Orchestrator — the deterministic backbone of the loop (Teammate 4).

check -> silo -> mission -> retest -> coverage. Every step is written to the action log,
and each action has a budget of 6 steps. Logs never contain answers or scores.

Every event has an audience (see database.py):
- TEAM: shared project facts (cards, seeding), which decisions got a mission, a mission
  accepted by both people, and aggregate coverage when it changes. No member ids.
- the member(s) concerned: checks, answers, retests and attempts (the member only);
  consent steps (mentor + learner only). Other members never see these.

Integrity rules enforced here: nobody is assessed without consent_assessment; a retest
is fully validated before anything is written, and its evidence + mission are saved in
one transaction; an owner can verify their own decision through an independent check
(ownership alone never makes someone a mentor); demo mode never pretends to process
an uploaded file, and a new live project never inherits the old project's records.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from busfactor import database as db
from busfactor.coverage import compute_coverage
from busfactor.interview import UnsupportedDecision, create_interview, create_transfer_test, is_assessable
from busfactor.knowledge import confirm_card, extract_decisions
from busfactor.llm_provider import demo_mode
from busfactor.missions import apply_retest, recommend_missions, set_consent
from busfactor.models import (
    AssessmentEvidence, CoverageReport, DecisionCard, EvidenceStatus, InterviewQuestion, LogEvent, Member,
    MissionStatus, Project, QuestionType, ReviewStatus, TeachingMission,
)
from busfactor.rubrics import REFUSAL, evaluate_answer, is_answer_request, practice_hint

STEP_BUDGET = 6
DEMO_BADGE = "DEMO DATA — synthetic"
PROJECT_START_ACTIONS = ("seed_demo", "setup_project.save")   # each starts a new project in the log
OWNER_TAG = "-owner-"   # question ids of owner checks: Q-<decision>-<member>-owner-<type>
DEMO_UPLOAD_REFUSED = ("Demo mode uses the synthetic demo project, so uploaded files are not processed. "
                       "Set DEMO_MODE=false and LLM_API_KEY to analyse your own file.")
NO_CARDS = "No decisions with a checkable source were found, so the current project was kept."


class _Steps:
    """Counts and logs the steps of one action; refuses to exceed the budget."""

    def __init__(self, actor: str, action: str, audience: db.Audience = db.INTERNAL):
        self.actor, self.action, self.audience, self.n = actor, action, audience, 0

    def __call__(self, step: str, **detail) -> None:
        self.n += 1
        if self.n > STEP_BUDGET:
            raise RuntimeError(f"{self.action} exceeded its step budget of {STEP_BUDGET}")
        db.log(self.actor, f"{self.action}.{step}", detail, audience=self.audience)


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


def _current_project_log() -> list[LogEvent]:
    """Log events since the most recent project start (demo seeding or a live upload)."""
    events = db.load_log(limit=None)  # a long session must not push the project start out of view
    starts = [i for i, e in enumerate(events) if e.action in PROJECT_START_ACTIONS]
    return events[starts[-1]:] if starts else events


def demo_banner() -> Optional[str]:
    """Badge text when demo mode is on or the CURRENT project is the synthetic demo (brief test 10)."""
    current = _current_project_log()
    seeded = bool(current) and current[0].action == "seed_demo"
    return DEMO_BADGE if demo_mode() or seeded else None


def project() -> Optional[Project]:
    found = db.load_all(Project)
    return found[0] if found else None


def members() -> dict[str, Member]:
    return {m.id: m for m in db.load_all(Member)}


def decisions() -> list[DecisionCard]:
    return db.load_all(DecisionCard)


def team_log(viewer_id: str) -> list[LogEvent]:
    """The action log as `viewer_id` may see it: team events plus their own private steps."""
    return db.load_team_log(viewer_id)


def setup_project(files: list[str], actor: str = "agent") -> list[DecisionCard]:
    """Start a NEW live project from uploaded files. It replaces the current project: its decisions,
    questions, evidence and missions are deleted, so nothing stale is reused under the same ids."""
    if demo_mode():
        raise ValueError(DEMO_UPLOAD_REFUSED)  # never present fixture cards as an analysis of the upload
    s = _Steps(actor, "setup_project", audience=db.TEAM)
    s("read_files", files=[Path(f).name for f in files])
    cards = extract_decisions(files)
    s("extract_decisions", proposed=[c.id for c in cards if c.review_status.value == "proposed"],
      unsupported=[c.id for c in cards if c.review_status.value == "unsupported"])
    if not cards:
        raise ValueError(NO_CARDS)
    db.save_records(  # one transaction: the old project is fully replaced, or kept if anything fails
        Project(id=cards[0].project_id, title=Path(files[0]).stem, course="Uploaded project",
                source_files=[Path(f).name for f in files]),
        *cards,
        replacing=(Project, DecisionCard, InterviewQuestion, AssessmentEvidence, TeachingMission),
    )
    s("save", count=len(cards), note="new project: previous decisions, questions, answers and missions removed")
    _snapshot("baseline")
    return cards


def confirm_decision(decision_id: str, edits: Optional[dict] = None, actor: str = "agent") -> DecisionCard:
    card = confirm_card(db.get_record(DecisionCard, decision_id), edits)
    db.save_record(card)
    db.log(actor, "confirm_card", {"decision_id": decision_id, "edited": sorted((edits or {}).keys())},
           audience=db.TEAM)
    return card


# ------------------------------------------------------------------ private check

def _member(member_id: str) -> Member:
    member = members().get(member_id)
    if member is None:
        raise KeyError(f"Unknown member {member_id}")
    return member


def _require_assessment_consent(member_id: str) -> None:
    if not _member(member_id).consent_assessment:
        raise PermissionError("You have not agreed to be assessed, so BusFactor will not ask or score you.")


def _answered(member_id: str, question_id: str) -> bool:
    return any(e.question_id == question_id for e in db.get_private_evidence(member_id, member_id))


def is_owner_check(question: InterviewQuestion) -> bool:
    return OWNER_TAG in question.id


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


def owner_check_decisions(member_id: str) -> list[str]:
    """Decisions the member is the declared owner of, verified, and not yet demonstrated by them."""
    demonstrated = {e.decision_id for e in db.get_private_evidence(member_id, member_id) if e.rubric_score == 2}
    return [d.id for d in decisions() if d.owner_id == member_id and d.review_status == ReviewStatus.verified
            and is_assessable(d) and d.id not in demonstrated]


def start_owner_check(member_id: str, decision_id: str) -> InterviewQuestion:
    """An independent (no-hint) question for a decision's declared owner.

    Owning a decision is not proof of understanding it: only a score of 2 on this check
    counts as evidence, and only that can make the owner an eligible mentor.
    """
    _require_assessment_consent(member_id)
    decision = next((d for d in decisions() if d.id == decision_id), None)
    if decision is None:
        raise KeyError(f"Unknown decision {decision_id}")
    if decision.owner_id != member_id:
        raise PermissionError("Only the declared owner can take the owner check for this decision.")
    if decision.review_status != ReviewStatus.verified:
        raise ValueError("The team must confirm this decision card before anyone is checked on it.")
    asked = [q for q in db.load_all(InterviewQuestion, member_id=member_id) if q.decision_id == decision_id]
    open_check = next((q for q in asked if is_owner_check(q) and not _answered(member_id, q.id)), None)
    if open_check:
        return open_check  # one open owner check at a time
    s = _Steps("agent", "start_owner_check", audience=[member_id])
    q = create_interview(decision, member_id, asked)  # raises once why and what_if were both used
    q = q.model_copy(update={"id": f"Q-{decision_id}-{member_id}{OWNER_TAG}{q.question_type.value}",
                             "mode": "independent"})
    db.save_record(q)
    s("create_interview", decision_id=decision_id, question_id=q.id, question_type=q.question_type.value)
    return q


def start_check(member_id: str, decision_ids: Optional[list[str]] = None) -> list[InterviewQuestion]:
    _require_assessment_consent(member_id)
    s = _Steps("agent", "start_check", audience=[member_id])  # what you are checked on is private
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
    owner_check = is_owner_check(q)
    if q.mode == "independent" and not owner_check:
        raise ValueError("Independent questions are answered through submit_retest.")
    _require_assessment_consent(viewer_id)
    if owner_check and _answered(viewer_id, q.id):
        raise ValueError("This owner check was already answered; start a new one.")
    s = _Steps(viewer_id, "submit_answer", audience=[viewer_id])
    decision = db.get_record(DecisionCard, q.decision_id)
    if is_answer_request(answer):
        s("answer_request", question_id=q.id, mode=q.mode)
        # practice: point to the source; independent owner check: no hint at all
        return Result(blocked=True, message=REFUSAL if q.mode == "independent" else practice_hint(decision))
    ev = evaluate_answer(q, answer, decision)
    db.save_record(ev)
    s("evaluate_answer", question_id=q.id, evidence_id=ev.id,
      abstained=ev.status == EvidenceStatus.insufficient_evidence)
    return Result(evidence=ev)


# ------------------------------------------------------------------ coverage and missions

def team_coverage() -> CoverageReport:
    return compute_coverage(decisions(), db.evidence_for_coverage())


def _snapshot(label: str, only_if_changed: bool = False) -> CoverageReport:
    """Log aggregate coverage for the team. With only_if_changed, an unchanged report is not
    logged, so a failed attempt leaves no team-visible trace."""
    report = team_coverage()
    detail = {"label": label, "numerator": report.numerator,
              "denominator": report.denominator, "spof": report.spof_decision_ids}
    snaps = coverage_snapshots()
    unchanged = bool(snaps) and all(snaps[-1].get(k) == detail[k] for k in ("numerator", "denominator", "spof"))
    if not (only_if_changed and unchanged):
        db.log("agent", "coverage_snapshot", detail, audience=db.TEAM)
    return report


def coverage_snapshots() -> list[dict]:
    """Coverage snapshots of the current project only (the first one is its baseline)."""
    return [e.detail for e in _current_project_log() if e.action == "coverage_snapshot"]


def propose_missions() -> list[TeachingMission]:
    # Team-visible: which decisions got a mission. Mission ids name the learner, so they stay out.
    s = _Steps("agent", "propose_missions", audience=db.TEAM)
    recs = recommend_missions(decisions(), db.evidence_for_coverage(), members())
    s("recommend_missions", count=len(recs))
    existing = {m.id: m for m in db.load_all(TeachingMission)}
    for m in recs:
        old = existing.get(m.id)
        if old is None or (old.status == MissionStatus.proposed and not (old.mentor_consent or old.learner_consent)):
            db.save_record(m)
    s("save", decision_ids=sorted({m.decision_id for m in recs if m.mentor_id}),
      fallback_decision_ids=sorted({m.decision_id for m in recs if m.mentor_id is None}))
    return db.load_all(TeachingMission)


def missions() -> list[TeachingMission]:
    return db.load_all(TeachingMission)


def _mission(mission_id: str) -> TeachingMission:
    mission = db.get_record(TeachingMission, mission_id)
    if mission is None:
        raise KeyError(f"Unknown mission {mission_id}")
    return mission


def _check_retest_allowed(mission: TeachingMission, viewer_id: str) -> None:
    if viewer_id != mission.learner_id:
        raise PermissionError("Only the learner takes the retest.")
    if mission.status == MissionStatus.verified:
        raise ValueError("This mission is already verified; there is nothing left to retest.")
    if mission.status not in (MissionStatus.accepted, MissionStatus.completed):
        raise ValueError("Both mentor and learner must accept the mission first.")
    _require_assessment_consent(viewer_id)


def accept_mission(mission_id: str, member_id: str) -> TeachingMission:
    mission = set_consent(_mission(mission_id), member_id)
    db.save_record(mission)
    both = mission.status == MissionStatus.accepted
    role = "mentor" if member_id == mission.mentor_id else "learner"
    # one person's consent is visible only to the two people in the mission
    db.log(member_id, "accept_mission", {"decision_id": mission.decision_id, "role": role, "both_accepted": both},
           audience=[mission.mentor_id, mission.learner_id])
    if both:  # the pairing becomes public only once both agreed (matches the Missions page)
        db.log("agent", "mission_accepted", {"decision_id": mission.decision_id}, audience=db.TEAM)
    return mission


def start_retest(mission_id: str, viewer_id: str) -> InterviewQuestion:
    mission = _mission(mission_id)
    _check_retest_allowed(mission, viewer_id)
    s = _Steps("agent", "start_retest", audience=[mission.learner_id])  # attempts are private
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
    """Score the learner's answer to the mission's current transfer question.

    Everything is validated BEFORE any write; the evidence and the updated mission are then
    saved in one transaction, so a rejected call can never change coverage.
    """
    mission = _mission(mission_id)
    _check_retest_allowed(mission, viewer_id)
    if mission.retest_question_id is None:
        raise ValueError("Start the retest first.")
    q = db.get_record(InterviewQuestion, mission.retest_question_id)
    if (q is None or q.mode != "independent" or q.member_id != mission.learner_id
            or q.decision_id != mission.decision_id):
        raise ValueError("The retest question does not belong to this mission; start a new one.")
    if _answered(viewer_id, q.id):
        raise ValueError("This question was already answered; start a new independent question.")
    s = _Steps(viewer_id, "submit_retest", audience=[viewer_id])
    if is_answer_request(answer):  # independent mode: blocked in code, nothing is stored
        s("blocked_answer_request", mission_id=mission_id)
        return Result(blocked=True, message=REFUSAL)
    ev = evaluate_answer(q, answer, db.get_record(DecisionCard, mission.decision_id))
    mission = apply_retest(mission, ev)   # raises on any mismatch, before anything is written
    db.save_records(ev, mission)
    s("evaluate_answer", question_id=q.id, evidence_id=ev.id)
    s("apply_retest", mission_id=mission_id, status=mission.status.value)
    report = _snapshot("coverage changed", only_if_changed=True)
    return Result(evidence=ev, mission=mission, coverage=report)
