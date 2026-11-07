# Shared contracts: EXACTLY brief section 5. Do not edit without telling the whole team.
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field


class ReviewStatus(str, Enum):
    proposed = "proposed"
    verified = "verified"
    unsupported = "unsupported"


class Importance(str, Enum):
    critical = "critical"
    normal = "normal"


class EvidenceStatus(str, Enum):
    demonstrated = "demonstrated"          # rubric_score == 2
    needs_practice = "needs_practice"      # rubric_score 0 or 1
    insufficient_evidence = "insufficient_evidence"  # cannot judge / no source


class QuestionType(str, Enum):
    why = "why"
    what_if = "what_if"
    transfer = "transfer"


class MissionStatus(str, Enum):
    proposed = "proposed"
    accepted = "accepted"
    completed = "completed"
    verified = "verified"
    fallback = "fallback"   # no mentor available -> course material / TA


class SourceRef(BaseModel):
    file: str
    page: Optional[int] = None
    section: Optional[str] = None
    quote: str = ""


class Project(BaseModel):
    id: str
    title: str
    course: str
    source_files: list[str] = []


class DecisionCard(BaseModel):
    id: str
    project_id: str
    title: str
    rationale: str
    alternatives: list[str] = []
    concept_ids: list[str] = []
    importance: Importance = Importance.critical
    owner_id: Optional[str] = None          # declared by the team, never inferred
    source_refs: list[SourceRef] = []
    review_status: ReviewStatus = ReviewStatus.proposed


class Member(BaseModel):
    id: str
    project_id: str
    display_name: str
    consent_assessment: bool = True
    consent_mentor: bool = True
    consent_learner: bool = True


class InterviewQuestion(BaseModel):
    id: str
    decision_id: str
    member_id: str
    prompt: str
    question_type: QuestionType
    rubric_expectations: list[str] = []      # points a score-2 answer must contain
    source_refs: list[SourceRef] = []
    mode: Literal["practice", "independent"] = "practice"


class AssessmentEvidence(BaseModel):
    id: str
    member_id: str
    decision_id: str
    question_id: str
    answer: str
    rubric_score: int = Field(ge=0, le=2)
    status: EvidenceStatus
    feedback: str = ""
    source_refs: list[SourceRef] = []
    assessment_version: str = "v1"
    visibility: Literal["private", "team"] = "private"
    is_synthetic: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TeachingMission(BaseModel):
    id: str
    decision_id: str
    mentor_id: Optional[str] = None
    learner_id: str
    objective: str
    steps: list[str] = []
    mentor_consent: bool = False
    learner_consent: bool = False
    status: MissionStatus = MissionStatus.proposed
    retest_question_id: Optional[str] = None
    fallback_message: Optional[str] = None


class DecisionCoverage(BaseModel):
    decision_id: str
    demonstrated_by: list[str] = []
    status: Literal["covered", "single_point_of_failure", "no_explainer", "not_assessed"]


class CoverageReport(BaseModel):
    numerator: int
    denominator: int
    score: Optional[float] = None            # None when denominator == 0 ("not measurable")
    per_decision: list[DecisionCoverage] = []
    spof_decision_ids: list[str] = []
    unknown_decision_ids: list[str] = []


class LogEvent(BaseModel):
    ts: datetime = Field(default_factory=datetime.utcnow)
    actor: str          # "agent" or member id
    action: str         # e.g. "evaluate_answer", "create_mission"
    detail: dict = {}
