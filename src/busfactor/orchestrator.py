"""Orchestrator — the deterministic backbone of the loop (Teammate 4).

check -> silo -> mission -> retest -> coverage. Every step is written to the action log,
and each action has a budget of 6 steps. Logs never contain answers or scores.

Projects: several projects live side by side; one is "open" (a persisted setting). Team-level
functions take an optional project_id (default: the open project). Member-level functions derive
the project from the member and refuse anything (decision, question, mission) of another project.

Every event has an audience (see database.py):
- TEAM: shared project facts (cards, members joining, seeding), which decisions got a mission,
  a mission accepted by both people, and aggregate coverage when it changes. No member ids.
- the member(s) concerned: checks, answers, retests and attempts (the member only);
  consent steps (mentor + learner only). Other members never see these.

Integrity rules enforced here: nobody is assessed without consent_assessment (opt-in); every
action checks project membership; a retest is fully validated before anything is written, and
its evidence + mission are saved in one transaction; an owner can verify their own decision
through an independent check (ownership alone never makes someone a mentor); answers that try
to instruct the grader are never scored; demo mode never pretends to process an uploaded file;
creating a project never deletes another one, and deleting one needs its exact title.
"""
from __future__ import annotations

import csv
import io
import os
import re
import shutil
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from busfactor import auth
from busfactor import database as db
from busfactor.coverage import compute_coverage, explain_status
from busfactor.ingestion import load_pages
from busfactor.interview import UnsupportedDecision, create_interview, create_transfer_test, is_assessable
from busfactor.knowledge import add_manual_card, confirm_card, decision_id, extract_decisions
from busfactor.llm_provider import demo_mode, llm_available
from busfactor.missions import apply_retest, recommend_missions, set_consent
from busfactor.models import (
    DEMO_PROJECT_ID, AssessmentEvidence, CoverageReport, DecisionCard, EvidenceStatus, InterviewQuestion, LogEvent,
    Member, MissionStatus, Project, QuestionType, ReviewStatus, TeachingMission, utcnow,
)
from busfactor.rubrics import INJECTION_FLAGGED, REFUSAL, detect_injection, evaluate_answer, is_answer_request, practice_hint

STEP_BUDGET = 6
REMINDER_DAYS = int(os.getenv("BUSFACTOR_REMINDER_DAYS", "2"))    # an accepted mission with no retest yet
FOLLOWUP_DAYS = int(os.getenv("BUSFACTOR_FOLLOWUP_DAYS", "3"))    # spaced follow-up after a passed retest
MAX_DECISIONS = 10
DEMO_BADGE = "DEMO DATA — synthetic"
ACTIVE_PROJECT = "active_project"
OWNER_TAG = "-owner-"   # legacy owner-check ids: Q-<decision>-<member>-owner-<type>
UPLOADS = Path(os.getenv("BUSFACTOR_UPLOADS", db.REPO_ROOT / "uploads"))
DEMO_UPLOAD_REFUSED = ("Demo mode uses the synthetic demo project, so uploaded files are not processed. "
                       "Set DEMO_MODE=false and LLM_API_KEY to analyse your own file.")
EXTRACTION_NEEDS_MODEL = ("Automatic extraction needs the live model (DEMO_MODE=false and LLM_API_KEY). "
                          "You can still add decisions by hand: each quote is checked against your document.")
NO_CARDS = "No decisions with a checkable source were found, so nothing was changed."
DEMO_IS_FIXED = "The synthetic demo has fixed fictional members and decisions; create your own project instead."


class _Steps:
    """Counts and logs the steps of one action; refuses to exceed the budget."""

    def __init__(self, actor: str, action: str, audience: db.Audience = db.INTERNAL,
                 project_id: Optional[str] = None):
        self.actor, self.action, self.audience, self.project_id, self.n = actor, action, audience, project_id, 0

    def __call__(self, step: str, **detail) -> None:
        self.n += 1
        if self.n > STEP_BUDGET:
            raise RuntimeError(f"{self.action} exceeded its step budget of {STEP_BUDGET}")
        db.log(self.actor, f"{self.action}.{step}", detail, audience=self.audience, project_id=self.project_id)


@dataclass
class Result:
    blocked: bool = False
    message: str = ""
    evidence: Optional[AssessmentEvidence] = None   # private: show only to its owner
    mission: Optional[TeachingMission] = None
    coverage: Optional[CoverageReport] = None
    extra: dict = field(default_factory=dict)


# ------------------------------------------------------------------ projects

def set_uploads_dir(path: str | Path) -> None:
    global UPLOADS
    UPLOADS = Path(path)


def projects() -> list[Project]:
    return db.load_all(Project)


def active_project_id() -> Optional[str]:
    pid = db.get_setting(ACTIVE_PROJECT)
    if pid and db.get_record(Project, pid):
        return pid
    found = projects()
    return found[0].id if found else None


def open_project(project_id: str) -> Project:
    found = db.get_record(Project, project_id)
    if found is None:
        raise KeyError(f"Unknown project {project_id}")
    db.set_setting(ACTIVE_PROJECT, project_id)
    return found


def _pid(project_id: Optional[str] = None) -> str:
    pid = project_id or active_project_id()
    if pid is None:
        raise LookupError("No project is open.")
    return pid


def is_demo_project(project_id: Optional[str] = None) -> bool:
    return _pid(project_id) == DEMO_PROJECT_ID


def seed_demo_data() -> None:
    """Reset the synthetic demo project (only it) and open it."""
    db.seed_demo()
    _snapshot("baseline", DEMO_PROJECT_ID)
    open_project(DEMO_PROJECT_ID)


def ensure_seeded() -> None:
    if db.get_record(Project, DEMO_PROJECT_ID) is None:
        seed_demo_data()


def demo_banner(project_id: Optional[str] = None) -> Optional[str]:
    """Badge text whenever the open project is the synthetic demo (brief test 10)."""
    return DEMO_BADGE if is_demo_project(project_id) else None


def grading_mode(project_id: Optional[str] = None) -> str:
    """One honest line about how answers in this project are scored."""
    if llm_available():
        return "Live model grading: formative feedback that can be wrong, never an official grade."
    if is_demo_project(project_id):
        return "Offline demo keyword rubric on synthetic data: a stand-in, not a validated grader."
    return "Offline: questions come from templates and answers wait for human review, with no automatic scores."


def project(project_id: Optional[str] = None) -> Optional[Project]:
    pid = project_id or active_project_id()
    return db.get_record(Project, pid) if pid else None


def members(project_id: Optional[str] = None) -> dict[str, Member]:
    pid = project_id or active_project_id()
    return {m.id: m for m in db.load_all(Member, project_id=pid)} if pid else {}


def decisions(project_id: Optional[str] = None) -> list[DecisionCard]:
    pid = project_id or active_project_id()
    return db.load_all(DecisionCard, project_id=pid) if pid else []


def team_log(viewer_id: str, project_id: Optional[str] = None) -> list[LogEvent]:
    """The action log of one project as `viewer_id` may see it: team events plus their own private steps."""
    return db.load_team_log(viewer_id, _pid(project_id))


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    return cleaned or "document"


def project_file(project_id: str, name: str) -> Path:
    found = project(project_id)
    if found is None or name not in found.source_files:
        raise KeyError(f"{name} is not a document of this project.")
    return UPLOADS / project_id / name


def create_project(title: str, course: str = "", files: list[tuple[str, bytes]] = (),
                   member_names: list[str] = (), actor: str = "agent") -> Project:
    """Create a NEW project next to the existing ones (nothing is deleted) and open it.

    Uploaded documents are stored as text sources for quote checks; they are only read, never run.
    Members start with every consent OFF: each member opts in for themselves.
    """
    title = title.strip()
    if not title:
        raise ValueError("Give the project a title.")
    people = [" ".join(n.split()) for n in member_names if n.strip()]
    if len({p.casefold() for p in people}) != len(people):
        raise ValueError("The member list contains the same name twice.")  # checked BEFORE anything is written
    pid = f"P{uuid.uuid4().hex[:6]}"
    names, folder = [], UPLOADS / pid
    team = [Member(id=f"{pid}-M{i:02d}", project_id=pid, display_name=n, consent_assessment=False,
                   consent_mentor=False, consent_learner=False) for i, n in enumerate(people, 1)]
    try:
        for name, content in files:
            safe = _safe_name(name)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / safe).write_bytes(content)
            names.append(safe)
        # one transaction: the project and its members exist together, or not at all
        db.save_records(Project(id=pid, title=title, course=course.strip(), source_files=names), *team)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    db.log(actor, "create_project", {"title": title, "documents": names}, audience=db.TEAM, project_id=pid)
    if team:
        db.log(actor, "add_member", {"members": len(team)}, audience=db.TEAM, project_id=pid)
    _snapshot("baseline", pid)
    open_project(pid)
    return db.get_record(Project, pid)


def _readable(path: Path) -> None:
    """Fail with a clear message (not a crash) when a document has no readable text."""
    try:
        load_pages(path)
    except Exception as err:  # e.g. a damaged or scanned PDF: pdfminer raises its own exception types
        raise ValueError(f"Could not read text from {path.name}. Upload a text-based PDF, Markdown or text "
                         "file.") from err


def delete_project(project_id: str, confirm_title: str, actor: str = "agent") -> None:
    """Delete a live project and all its records. Needs the exact title; the demo is reset instead."""
    if project_id == DEMO_PROJECT_ID:
        raise ValueError("The demo cannot be deleted; use Reset demo instead.")
    found = project(project_id)
    if found is None:
        raise KeyError(f"Unknown project {project_id}")
    if confirm_title.strip() != found.title:
        raise ValueError("Type the project title exactly to delete it.")
    db.delete_project(project_id)
    shutil.rmtree(UPLOADS / project_id, ignore_errors=True)
    if db.get_setting(ACTIVE_PROJECT) == project_id:
        db.set_setting(ACTIVE_PROJECT, DEMO_PROJECT_ID if db.get_record(Project, DEMO_PROJECT_ID) else None)


def add_member(display_name: str, actor: str = "agent", project_id: Optional[str] = None) -> Member:
    """A real project member. Every consent starts OFF until the member opts in."""
    pid = _pid(project_id)
    if pid == DEMO_PROJECT_ID:
        raise ValueError(DEMO_IS_FIXED)
    name = " ".join(display_name.split())
    if not name:
        raise ValueError("A member needs a name.")
    team = members(pid)
    if any(m.display_name.casefold() == name.casefold() for m in team.values()):
        raise ValueError(f"{name} is already a member of this project.")
    n = len(team) + 1
    while f"{pid}-M{n:02d}" in team:
        n += 1
    member = Member(id=f"{pid}-M{n:02d}", project_id=pid, display_name=name,
                    consent_assessment=False, consent_mentor=False, consent_learner=False)
    db.save_records(member)
    db.log(actor, "add_member", {"members": len(team) + 1}, audience=db.TEAM, project_id=pid)
    return member


def update_consent(member_id: str, viewer_id: str, *, assessment: bool, mentor: bool, learner: bool,
                   review: Optional[bool] = None) -> Member:
    """Only the member can give or withdraw their own consent. `review=None` keeps the current choice."""
    if viewer_id != member_id:
        raise PermissionError("Only the member can change their own consent.")
    current = _member(member_id)
    member = current.model_copy(update={
        "consent_assessment": bool(assessment), "consent_mentor": bool(mentor), "consent_learner": bool(learner),
        "consent_review": current.consent_review if review is None else bool(review)})
    db.save_records(member)
    db.log(member_id, "update_consent", {"assessment": member.consent_assessment, "mentor": member.consent_mentor,
                                         "learner": member.consent_learner, "review": member.consent_review},
           audience=[member_id], project_id=member.project_id)
    return member


def _with_display_file(card: DecisionCard, name: str) -> DecisionCard:
    """Store the document's name, never the local path, in the card's source references."""
    return card.model_copy(update={"source_refs": [r.model_copy(update={"file": name}) for r in card.source_refs]})


def extract_project_decisions(actor: str = "agent", project_id: Optional[str] = None) -> list[DecisionCard]:
    """Propose up to 5 source-checked cards from the project's documents with the live model."""
    pid = _pid(project_id)
    if pid == DEMO_PROJECT_ID:
        raise ValueError(DEMO_IS_FIXED)
    if demo_mode() or not llm_available():
        raise ValueError(EXTRACTION_NEEDS_MODEL)
    if decisions(pid):
        raise ValueError("This project already has decisions; add more by hand.")
    names = project(pid).source_files
    if not names:
        raise ValueError("Upload the project document first.")
    s = _Steps(actor, "extract_decisions", audience=db.TEAM, project_id=pid)
    s("read_files", files=names)
    cards = []
    for name in names:
        _readable(project_file(pid, name))
        found = extract_decisions([str(project_file(pid, name))], project_id=pid)
        cards += [_with_display_file(c, name) for c in found]
    cards = [c.model_copy(update={"id": decision_id(pid, i), "project_id": pid, "owner_id": None})
             for i, c in enumerate(cards[:5], 1)]
    s("extract", proposed=[c.id for c in cards if c.review_status == ReviewStatus.proposed],
      unsupported=[c.id for c in cards if c.review_status == ReviewStatus.unsupported])
    if not cards:
        raise ValueError(NO_CARDS)
    db.save_records(*cards)
    s("save", count=len(cards))
    return cards


def add_decision(*, title: str, rationale: str, alternatives: list[str], source_file: str, page: int,
                 quote: str, actor: str = "agent", project_id: Optional[str] = None) -> DecisionCard:
    """A decision typed in by the team. It is `proposed` only if the quote is on that page of the document."""
    pid = _pid(project_id)
    if pid == DEMO_PROJECT_ID:
        raise ValueError(DEMO_IS_FIXED)
    existing = {d.id for d in decisions(pid)}
    if len(existing) >= MAX_DECISIONS:
        raise ValueError(f"A project can have at most {MAX_DECISIONS} key decisions.")
    n = len(existing) + 1
    while decision_id(pid, n) in existing:
        n += 1
    _readable(project_file(pid, source_file))
    card = add_manual_card(pid, decision_id(pid, n), title=title.strip(), rationale=rationale.strip(),
                           alternatives=[a.strip() for a in alternatives if a.strip()],
                           file=str(project_file(pid, source_file)), page=page, quote=quote.strip())
    card = _with_display_file(card, source_file)
    db.save_records(card)
    db.log(actor, "add_decision", {"decision_id": card.id, "review_status": card.review_status.value},
           audience=db.TEAM, project_id=pid)
    return card


def setup_project(files: list[str], actor: str = "agent") -> list[DecisionCard]:
    """Create a NEW live project from document paths and extract its decisions (live model only).

    The open project and every other project are kept; if extraction fails, the new project is removed.
    """
    if demo_mode():
        raise ValueError(DEMO_UPLOAD_REFUSED)  # never present fixture cards as an analysis of the upload
    previous = active_project_id()
    uploads = [(Path(f).name, Path(f).read_bytes() if Path(f).is_file() else b"") for f in files]
    new = create_project(Path(files[0]).stem, "Uploaded project", uploads, actor=actor)
    try:
        return extract_project_decisions(actor, new.id)
    except Exception:
        db.delete_project(new.id)
        shutil.rmtree(UPLOADS / new.id, ignore_errors=True)
        db.set_setting(ACTIVE_PROJECT, previous)
        raise


def confirm_decision(decision_id: str, edits: Optional[dict] = None, actor: str = "agent") -> DecisionCard:
    card = db.get_record(DecisionCard, decision_id)
    if card is None:
        raise KeyError(f"Unknown decision {decision_id}")
    team = members(card.project_id)
    if actor != "agent" and actor not in team:
        raise PermissionError("Only members of this project can confirm its decisions.")
    owner = (edits or {}).get("owner_id")
    if owner is not None and owner not in team:
        raise ValueError("The owner must be a member of this project.")
    card = confirm_card(card, edits)
    db.save_records(card)
    db.log(actor, "confirm_card", {"decision_id": decision_id, "edited": sorted((edits or {}).keys())},
           audience=db.TEAM, project_id=card.project_id)
    return card


# ------------------------------------------------------------------ private check

def _member(member_id: str) -> Member:
    member = db.get_record(Member, member_id)
    if member is None:
        raise KeyError(f"Unknown member {member_id}")
    return member


def _require_assessment_consent(member_id: str) -> Member:
    member = _member(member_id)
    if not member.consent_assessment:
        raise PermissionError("You have not agreed to be assessed, so BusFactor will not ask or score you.")
    return member


def _require_same_project(member: Member, project_id: Optional[str]) -> None:
    if project_id != member.project_id:
        raise PermissionError("That belongs to another project.")


def _answered(member_id: str, question_id: str) -> bool:
    return any(e.question_id == question_id for e in db.get_private_evidence(member_id, member_id))


def is_owner_check(question: InterviewQuestion) -> bool:
    return question.owner_check or OWNER_TAG in question.id


def my_questions(viewer_id: str, member_id: str) -> list[tuple[InterviewQuestion, Optional[AssessmentEvidence]]]:
    """A member's own questions with their latest evidence. Only the member may call this."""
    evidence = db.get_private_evidence(viewer_id, member_id)  # raises for anyone else
    latest = {e.question_id: e for e in evidence}
    return [(q, latest.get(q.id)) for q in db.load_all(InterviewQuestion, member_id=member_id)]


def suggest_check_decisions(member_id: str) -> list[str]:
    """2 confirmed decisions of the member's project they do not own and have not demonstrated."""
    member = _member(member_id)
    own = db.get_private_evidence(member_id, member_id)
    demonstrated = {e.decision_id for e in own if e.rubric_score == 2}
    asked = db.load_all(InterviewQuestion, member_id=member_id)
    picks = []
    for d in decisions(member.project_id):
        types = {q.question_type for q in asked if q.decision_id == d.id and not is_owner_check(q)}
        if (d.owner_id != member_id and is_assessable(d) and d.id not in demonstrated
                and not {QuestionType.why, QuestionType.what_if} <= types):
            picks.append(d.id)
    return picks[:2]


def owner_check_decisions(member_id: str) -> list[str]:
    """Confirmed decisions the member is the declared owner of and has not yet demonstrated."""
    member = _member(member_id)
    demonstrated = {e.decision_id for e in db.get_private_evidence(member_id, member_id) if e.rubric_score == 2}
    return [d.id for d in decisions(member.project_id)
            if d.owner_id == member_id and is_assessable(d) and d.id not in demonstrated]


def start_owner_check(member_id: str, decision_id: str) -> InterviewQuestion:
    """An independent (no-hint) question for a decision's declared owner.

    Owning a decision is not proof of understanding it: only a score of 2 on this check
    counts as evidence, and only that can make the owner an eligible mentor.
    """
    member = _require_assessment_consent(member_id)
    decision = db.get_record(DecisionCard, decision_id)
    if decision is None:
        raise KeyError(f"Unknown decision {decision_id}")
    _require_same_project(member, decision.project_id)
    if decision.owner_id != member_id:
        raise PermissionError("Only the declared owner can take the owner check for this decision.")
    if decision.review_status != ReviewStatus.verified:
        raise ValueError("The team must confirm this decision card before anyone is checked on it.")
    asked = [q for q in db.load_all(InterviewQuestion, member_id=member_id) if q.decision_id == decision_id]
    open_check = next((q for q in asked if is_owner_check(q) and not _answered(member_id, q.id)), None)
    if open_check:
        return open_check  # one open owner check at a time
    s = _Steps("agent", "start_owner_check", audience=[member_id], project_id=member.project_id)
    q = create_interview(decision, member_id, asked)  # raises once why and what_if were both used
    q = q.model_copy(update={"id": f"Q-{decision_id}-{member_id}{OWNER_TAG}{q.question_type.value}",
                             "mode": "independent", "owner_check": True})
    db.save_records(q)
    s("create_interview", decision_id=decision_id, question_id=q.id, question_type=q.question_type.value)
    return q


def start_check(member_id: str, decision_ids: Optional[list[str]] = None) -> list[InterviewQuestion]:
    member = _require_assessment_consent(member_id)
    cards = {d.id: d for d in decisions(member.project_id)}
    chosen = decision_ids or suggest_check_decisions(member_id)
    if any(did not in cards for did in chosen):
        raise PermissionError("You can only be checked on decisions of your own project.")
    s = _Steps("agent", "start_check", audience=[member_id], project_id=member.project_id)  # private
    s("select_decisions", member_id=member_id, decision_ids=chosen)
    created = []
    for did in chosen[:2]:
        prior = db.load_all(InterviewQuestion, member_id=member_id)
        try:
            q = create_interview(cards[did], member_id, [p for p in prior if not is_owner_check(p)])
        except UnsupportedDecision:
            s("abstain", decision_id=did, reason="not confirmed or no verified source -> not assessed")
            continue
        except ValueError as err:
            s("skip", decision_id=did, reason=str(err))
            continue
        db.save_records(q)
        created.append(q)
        s("create_interview", decision_id=did, question_id=q.id, question_type=q.question_type.value)
    return created


def submit_answer(question_id: str, answer: str, viewer_id: str) -> Result:
    q = db.get_record(InterviewQuestion, question_id)
    if q is None:
        raise KeyError(question_id)
    if viewer_id != q.member_id:
        raise PermissionError("You can only answer your own questions.")
    member = _require_assessment_consent(viewer_id)
    _require_same_project(member, q.project_id)
    owner_check = is_owner_check(q)
    if q.mode == "independent" and not owner_check:
        raise ValueError("Independent questions are answered through submit_retest.")
    if owner_check and _answered(viewer_id, q.id):
        raise ValueError("This owner check was already answered; start a new one.")
    s = _Steps(viewer_id, "submit_answer", audience=[viewer_id], project_id=member.project_id)
    decision = db.get_record(DecisionCard, q.decision_id)
    if is_answer_request(answer):
        s("answer_request", question_id=q.id, mode=q.mode)
        # practice: point to the source; independent owner check: no hint at all
        return Result(blocked=True, message=REFUSAL if q.mode == "independent" else practice_hint(decision))
    if detect_injection(answer):  # never sent to the grader, never stored as evidence
        s("flagged_instructions", question_id=q.id)
        return Result(blocked=True, message=INJECTION_FLAGGED)
    ev = evaluate_answer(q, answer, decision)
    db.save_records(ev)
    s("evaluate_answer", question_id=q.id, evidence_id=ev.id,
      abstained=ev.status == EvidenceStatus.insufficient_evidence)
    return Result(evidence=ev)


# ------------------------------------------------------------------ coverage and missions

def _team_evidence(pid: str) -> list[AssessmentEvidence]:
    """Evidence that may count: this project's, from members who (still) consent to assessment."""
    consenting = {m.id for m in members(pid).values() if m.consent_assessment}
    return [e for e in db.evidence_for_coverage(pid) if e.member_id in consenting]


def team_coverage(project_id: Optional[str] = None) -> CoverageReport:
    pid = _pid(project_id)
    return compute_coverage(decisions(pid), _team_evidence(pid))


def _snapshot(label: str, project_id: Optional[str] = None, only_if_changed: bool = False) -> CoverageReport:
    """Log aggregate coverage for the team. With only_if_changed, an unchanged report is not
    logged, so a failed attempt leaves no team-visible trace."""
    pid = _pid(project_id)
    report = team_coverage(pid)
    detail = {"label": label, "numerator": report.numerator,
              "denominator": report.denominator, "spof": report.spof_decision_ids}
    snaps = coverage_snapshots(pid)
    unchanged = bool(snaps) and all(snaps[-1].get(k) == detail[k] for k in ("numerator", "denominator", "spof"))
    if not (only_if_changed and unchanged):
        db.log("agent", "coverage_snapshot", detail, audience=db.TEAM, project_id=pid)
    return report


def coverage_snapshots(project_id: Optional[str] = None) -> list[dict]:
    """Coverage snapshots of one project (the first one is its baseline)."""
    return [e.detail for e in db.load_log(limit=None, project_id=_pid(project_id))
            if e.action == "coverage_snapshot"]


def propose_missions(project_id: Optional[str] = None) -> list[TeachingMission]:
    pid = _pid(project_id)
    # Team-visible: which decisions got a mission. Mission ids name the learner, so they stay out.
    s = _Steps("agent", "propose_missions", audience=db.TEAM, project_id=pid)
    recs = recommend_missions(decisions(pid), _team_evidence(pid), members(pid))
    s("recommend_missions", count=len(recs))
    existing = {m.id: m for m in missions(pid)}
    fresh = [m for m in recs if existing.get(m.id) is None or (
        existing[m.id].status == MissionStatus.proposed
        and not (existing[m.id].mentor_consent or existing[m.id].learner_consent))]
    if fresh:
        db.save_records(*fresh)
    s("save", decision_ids=sorted({m.decision_id for m in recs if m.mentor_id}),
      fallback_decision_ids=sorted({m.decision_id for m in recs if m.mentor_id is None}))
    return missions(pid)


def missions(project_id: Optional[str] = None) -> list[TeachingMission]:
    pid = project_id or active_project_id()
    return db.load_all(TeachingMission, project_id=pid) if pid else []


def _mission(mission_id: str) -> TeachingMission:
    mission = db.get_record(TeachingMission, mission_id)
    if mission is None:
        raise KeyError(f"Unknown mission {mission_id}")
    return mission


def _check_retest_allowed(mission: TeachingMission, viewer_id: str) -> Member:
    if viewer_id != mission.learner_id:
        raise PermissionError("Only the learner takes the retest.")
    if mission.status == MissionStatus.verified:
        raise ValueError("This mission is already verified; there is nothing left to retest.")
    if mission.status not in (MissionStatus.accepted, MissionStatus.completed):
        raise ValueError("Both mentor and learner must accept the mission first.")
    member = _require_assessment_consent(viewer_id)
    _require_same_project(member, mission.project_id)
    return member


def accept_mission(mission_id: str, member_id: str) -> TeachingMission:
    mission = _mission(mission_id)
    _require_same_project(_member(member_id), mission.project_id)
    mission = set_consent(mission, member_id)
    db.save_records(mission)
    both = mission.status == MissionStatus.accepted
    role = "mentor" if member_id == mission.mentor_id else "learner"
    # one person's consent is visible only to the two people in the mission
    db.log(member_id, "accept_mission", {"decision_id": mission.decision_id, "role": role, "both_accepted": both},
           audience=[mission.mentor_id, mission.learner_id], project_id=mission.project_id)
    if both:  # the pairing becomes public only once both agreed (matches the Missions page)
        db.log("agent", "mission_accepted", {"decision_id": mission.decision_id}, audience=db.TEAM,
               project_id=mission.project_id)
    return mission


def start_retest(mission_id: str, viewer_id: str) -> InterviewQuestion:
    """A new independent scenario for the learner. Each scenario is used once; raises when none is left."""
    mission = _mission(mission_id)
    member = _check_retest_allowed(mission, viewer_id)
    decision = db.get_record(DecisionCard, mission.decision_id)
    mine = [q for q in db.load_all(InterviewQuestion, member_id=mission.learner_id)
            if q.decision_id == mission.decision_id]
    used = [q.prompt for q in mine if q.question_type == QuestionType.transfer]
    answered_at = {e.question_id: e.created_at for e in db.get_private_evidence(viewer_id, viewer_id)}
    current = db.get_record(InterviewQuestion, mission.retest_question_id) if mission.retest_question_id else None
    practice = sorted((q for q in mine if q.mode == "practice"), key=lambda q: (q.id in answered_at,
                                                                                answered_at.get(q.id), q.id))
    prior = current or (practice[-1] if practice else create_interview(decision, mission.learner_id, []))
    q = create_transfer_test(decision, prior, used)   # raises ValueError when no new scenario is left
    s = _Steps("agent", "start_retest", audience=[mission.learner_id], project_id=member.project_id)
    db.save_records(q, mission.model_copy(update={"retest_question_id": q.id}))
    s("create_transfer_test", mission_id=mission_id, question_id=q.id, differs_from=prior.id)
    return q


def submit_retest(mission_id: str, answer: str, viewer_id: str) -> Result:
    """Score the learner's answer to the mission's current transfer question.

    Everything is validated BEFORE any write; the evidence and the updated mission are then
    saved in one transaction, so a rejected call can never change coverage.
    """
    mission = _mission(mission_id)
    member = _check_retest_allowed(mission, viewer_id)
    if mission.retest_question_id is None:
        raise ValueError("Start the retest first.")
    q = db.get_record(InterviewQuestion, mission.retest_question_id)
    if (q is None or q.mode != "independent" or q.member_id != mission.learner_id
            or q.decision_id != mission.decision_id or q.project_id != mission.project_id):
        raise ValueError("The retest question does not belong to this mission; start a new one.")
    if _answered(viewer_id, q.id):
        raise ValueError("This question was already answered; start a new independent question.")
    s = _Steps(viewer_id, "submit_retest", audience=[viewer_id], project_id=member.project_id)
    if is_answer_request(answer):  # independent mode: blocked in code, nothing is stored
        s("blocked_answer_request", mission_id=mission_id)
        return Result(blocked=True, message=REFUSAL)
    if detect_injection(answer):  # never sent to the grader, never stored, coverage untouched
        s("flagged_instructions", mission_id=mission_id)
        return Result(blocked=True, message=INJECTION_FLAGGED)
    ev = evaluate_answer(q, answer, db.get_record(DecisionCard, mission.decision_id))
    mission = apply_retest(mission, ev)   # raises on any mismatch, before anything is written
    db.save_records(ev, mission)
    s("evaluate_answer", question_id=q.id, evidence_id=ev.id)
    s("apply_retest", mission_id=mission_id, status=mission.status.value)
    report = _snapshot("coverage changed", member.project_id, only_if_changed=True)
    return Result(evidence=ev, mission=mission, coverage=report)


# ------------------------------------------------------------------ access codes

def is_protected(project_id: Optional[str] = None) -> bool:
    """True once the project uses access codes (see auth.py). The demo never does."""
    pid = _pid(project_id)
    return pid != DEMO_PROJECT_ID and auth.is_protected(pid)


def protect_project(project_id: Optional[str] = None, actor: str = "agent") -> dict:
    """Issue a personal code for every member and a reviewer code. Returns the plain codes: show them once."""
    pid = _pid(project_id)
    if pid == DEMO_PROJECT_ID:
        raise ValueError(DEMO_IS_FIXED)
    codes = auth.issue_all(pid, sorted(members(pid)))
    db.log(actor, "access_codes_issued", {"members": len(codes["members"])}, audience=db.TEAM, project_id=pid)
    return codes


# ------------------------------------------------------------------ reminders and spaced follow-up

def _days_since(moment: Optional[datetime], now: datetime) -> Optional[int]:
    return None if moment is None else (now - moment).days


def followup_due(mission: TeachingMission, now: Optional[datetime] = None) -> bool:
    """A verified mission whose learner has not yet taken the spaced follow-up and FOLLOWUP_DAYS have passed."""
    now = now or utcnow()
    return (mission.status == MissionStatus.verified and not mission.followup_done and mission.verified_at is not None
            and now - mission.verified_at >= timedelta(days=FOLLOWUP_DAYS))


def reminders(member_id: str, now: Optional[datetime] = None) -> list[dict]:
    """Nudges for one member: an accepted mission still waiting for its teaching session or retest, and a due
    follow-up check for the learner. Counts days only: no answers or scores."""
    member = _member(member_id)
    now = now or utcnow()
    found = []
    for m in missions(member.project_id):
        if member_id not in (m.mentor_id, m.learner_id):
            continue
        if m.status == MissionStatus.accepted and not m.followup_done:
            idle = _days_since(m.accepted_at, now)
            if idle is not None and idle >= REMINDER_DAYS:
                found.append({"kind": "session", "mission_id": m.id, "decision_id": m.decision_id, "days": idle})
        if member_id == m.learner_id and followup_due(m, now):
            found.append({"kind": "followup", "mission_id": m.id, "decision_id": m.decision_id,
                          "days": _days_since(m.verified_at, now)})
    return found


def start_followup(mission_id: str, viewer_id: str, now: Optional[datetime] = None) -> InterviewQuestion:
    """Spaced follow-up: after FOLLOWUP_DAYS the learner gets one more NEW independent question on the decision.

    The mission goes back to `accepted` with that question, so the normal retest flow scores it. A pass verifies
    the mission again; a miss leaves it `completed` and the learner's latest evidence (and so coverage) shows it.
    """
    mission = _mission(mission_id)
    if viewer_id != mission.learner_id:
        raise PermissionError("Only the learner takes the follow-up check.")
    member = _require_assessment_consent(viewer_id)
    _require_same_project(member, mission.project_id)
    if mission.followup_done:
        raise ValueError("The follow-up check for this mission was already started.")
    if mission.status != MissionStatus.verified:
        raise ValueError("A follow-up check comes after a verified retest.")
    if not followup_due(mission, now):
        raise ValueError(f"The follow-up check opens {FOLLOWUP_DAYS} days after the retest was passed.")
    decision = db.get_record(DecisionCard, mission.decision_id)
    mine = [q for q in db.load_all(InterviewQuestion, member_id=viewer_id) if q.decision_id == mission.decision_id]
    used = [q.prompt for q in mine if q.question_type == QuestionType.transfer]
    prior = (db.get_record(InterviewQuestion, mission.retest_question_id) if mission.retest_question_id else None) \
        or create_interview(decision, viewer_id, [])
    q = create_transfer_test(decision, prior, used)   # raises ValueError when no unused scenario is left
    db.save_records(q, mission.model_copy(update={"status": MissionStatus.accepted, "followup_done": True,
                                                  "retest_question_id": q.id, "verified_at": None}))
    db.log(viewer_id, "start_followup", {"mission_id": mission_id, "question_id": q.id}, audience=[viewer_id],
           project_id=member.project_id)
    return q


# ------------------------------------------------------------------ human review queue

@dataclass
class ReviewItem:
    """One answer the model could not score. No member identity: the reviewer sees the answer, not the person."""
    evidence_id: str
    decision_id: str
    decision_title: str
    question_type: str
    prompt: str
    rubric_expectations: list[str]
    answer: str
    source_quotes: list[str]
    note: str


def _require_reviewer(pid: str, reviewer_code: Optional[str]) -> None:
    if auth.is_protected(pid) and not auth.verify_reviewer(pid, reviewer_code):
        raise PermissionError("A valid reviewer code is needed to open the review queue.")


def _reviewable(pid: str) -> list[AssessmentEvidence]:
    """Unscored answers of members who consented to assessment AND to human review."""
    team = members(pid)
    return sorted((e for e in db.evidence_awaiting_review(pid)
                   if e.member_id in team and team[e.member_id].consent_assessment
                   and team[e.member_id].consent_review), key=lambda e: e.created_at)


def review_queue(project_id: Optional[str] = None, reviewer_code: Optional[str] = None) -> list[ReviewItem]:
    pid = _pid(project_id)
    _require_reviewer(pid, reviewer_code)
    items = []
    for e in _reviewable(pid):
        question, card = db.get_record(InterviewQuestion, e.question_id), db.get_record(DecisionCard, e.decision_id)
        if question is None or card is None:
            continue
        items.append(ReviewItem(
            evidence_id=e.id, decision_id=card.id, decision_title=card.title,
            question_type=question.question_type.value, prompt=question.prompt,
            rubric_expectations=list(question.rubric_expectations), answer=e.answer,
            source_quotes=[r.quote for r in card.source_refs if r.quote], note=e.feedback))
    return items


def apply_review(evidence_id: str, score: int, feedback: str = "", project_id: Optional[str] = None,
                 reviewer_code: Optional[str] = None) -> Result:
    """A human reviewer scores an answer the model abstained on. 0/1/2 as in the rubric.

    The member's evidence is replaced in place (same id), so it is no longer in the queue. If the answer was
    a mission's retest, the mission is updated in the same transaction, exactly as for an automatic score.
    The log records that a review happened, never the answer or the score.
    """
    pid = _pid(project_id)
    _require_reviewer(pid, reviewer_code)
    if score not in (0, 1, 2):
        raise ValueError("A review score is 0, 1 or 2.")
    ev = next((e for e in _reviewable(pid) if e.id == evidence_id), None)
    if ev is None:
        raise LookupError("That answer is not waiting for review (or the member has not agreed to human review).")
    note = " ".join(feedback.split())
    reviewed = ev.model_copy(update={
        "rubric_score": score,
        "status": EvidenceStatus.demonstrated if score == 2 else EvidenceStatus.needs_practice,
        "feedback": "Reviewed by a human" + (f": {note}" if note else "."),
        "assessment_version": "human-review-v1", "created_at": utcnow()})
    mission = next((m for m in missions(pid) if m.retest_question_id == ev.question_id
                    and m.status in (MissionStatus.accepted, MissionStatus.completed)), None)
    if mission is not None:
        mission = apply_retest(mission, reviewed)
        db.save_records(reviewed, mission)
    else:
        db.save_records(reviewed)
    db.log("reviewer", "human_review", {"evidence_id": ev.id}, audience=[ev.member_id], project_id=pid)
    return Result(evidence=reviewed, mission=mission, coverage=_snapshot("coverage changed", pid, only_if_changed=True))


# ------------------------------------------------------------------ team report export (counts only)

STATUS_WORDS = {"covered": "Covered (2+ people can explain it)", "single_point_of_failure": "Single point of failure",
                "no_explainer": "No explainer yet", "not_assessed": "Not assessed"}


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def export_team_report(project_id: Optional[str] = None, now: Optional[datetime] = None) -> str:
    """Markdown report for the team (and, if they choose, their TA). Only counts: never a name, answer or score."""
    pid = _pid(project_id)
    p, report, snaps = project(pid), team_coverage(pid), coverage_snapshots(pid)
    cards = {d.id: d for d in decisions(pid)}
    stamp = (now or utcnow()).strftime("%Y-%m-%d %H:%M UTC")
    pct = f" ({report.numerator / report.denominator:.0%})" if report.denominator else ""
    lines = [f"# BusFactor team report: {p.title}", "",
             f"{p.course or 'No course given'} · generated {stamp}"
             + (" · **DEMO DATA, synthetic**" if pid == DEMO_PROJECT_ID else ""), "",
             "## Decision coverage", "",
             f"- **Now:** {report.numerator}/{report.denominator}{pct}" if report.denominator
             else "- **Now:** not measurable yet (no assessed decisions)"]
    if snaps:
        lines.append(f"- **At the start:** {snaps[0]['numerator']}/{snaps[0]['denominator']}")
    lines += [f"- **Single points of failure:** {len(report.spof_decision_ids)}", "",
              "## Decisions", "", "| ID | Decision | Status | Can explain it | Source | Next step |",
              "|---|---|---|---|---|---|"]
    for c in report.per_decision:
        card = cards[c.decision_id]
        if card.review_status != ReviewStatus.verified:
            status, step = "Not confirmed (not counted)", "Review the card in Project Setup."
        else:
            status, step = STATUS_WORDS[c.status], explain_status(c)[1]
        src = "; ".join(f"{r.file} p.{r.page}" for r in card.source_refs) or "none"
        lines.append(f"| {_cell(c.decision_id.rsplit('-', 1)[-1])} | {_cell(card.title)} | {status} | "
                     f"{len(c.demonstrated_by)} | {_cell(src)} | {_cell(step)} |")
    counts = Counter(m.status.value for m in missions(pid))
    lines += ["", "## Teaching missions", ""]
    lines += ([f"- {name.replace('_', ' ').title()}: {n}" for name, n in sorted(counts.items())]
              or ["- None proposed yet."])
    lines += ["", "## How to read this", "",
              "- Decision Coverage = critical decisions that 2 or more members can explain, divided by critical "
              "decisions that have been assessed. It is a prototype indicator, not a validated metric.",
              "- Scores are practice feedback, not grades, and are never part of this report.",
              '- "Not assessed" is never counted as failed.', ""]
    return "\n".join(lines)


def export_decisions_csv(project_id: Optional[str] = None) -> str:
    """One row per decision: status and number of explainers, never who they are."""
    pid = _pid(project_id)
    cards, report = {d.id: d for d in decisions(pid)}, team_coverage(pid)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["decision", "title", "card_status", "coverage_status", "people_who_can_explain",
                     "source_file", "source_page"])
    for c in report.per_decision:
        card = cards[c.decision_id]
        ref = card.source_refs[0] if card.source_refs else None
        writer.writerow([c.decision_id.rsplit("-", 1)[-1], card.title, card.review_status.value, c.status,
                         len(c.demonstrated_by), ref.file if ref else "", ref.page if ref else ""])
    return out.getvalue()
