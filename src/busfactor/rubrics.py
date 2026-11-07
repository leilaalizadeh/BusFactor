"""Rubrics — 0/1/2 scoring, the no-answer guard and the independent-mode output filter (Teammate 2).

Guards enforced in CODE:
- is_answer_request(): "give me the answer" (EN/IT) is detected before any grading.
- evaluate_answer() refuses to grade an answer request in independent mode.
- filter_feedback(): in independent mode, feedback that repeats the rationale is replaced.
- No verified source -> insufficient_evidence; no score is invented.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from busfactor.interview import bank_entry, is_assessable
from busfactor.llm_provider import LLMUnavailable, complete_json, llm_available
from busfactor.models import AssessmentEvidence, DecisionCard, EvidenceStatus, InterviewQuestion

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
MIN_WORDS_FOR_2 = 12
GRADE_SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "integer"}, "feedback": {"type": "string"}},
    "required": ["score", "feedback"],
}

_ANSWER_REQUEST = [
    r"\bgive me (the|an|your) (answer|solution|correct answer)",
    r"\b(tell|show) me (the|what the) (answer|solution|right answer|correct answer)",
    r"\bwhat('?s| is) the (right |correct )?(answer|solution)\b",
    r"\bjust (tell|give|show) me\b",
    r"\b(answer|solve) (it|this|the question) for me\b",
    r"\bwhat should i (write|answer|say)\b",
    r"\b(dammi|dimmi) la (risposta|soluzione)\b",
    r"\bqual ?(e|è|'è) la (risposta|soluzione)\b",
]

REFUSAL = (
    "This is an independent check, so BusFactor will not give the answer or a hint. "
    "Answer in your own words; a partial answer is fine and still useful evidence."
)
INSUFFICIENT = "No verified source for this decision, so it cannot be assessed. Ask the team to review the card."


class AnswerRequestBlocked(PermissionError):
    """Raised when someone asks for the answer during an independent check."""


def is_answer_request(text: str) -> bool:
    t = (text or "").casefold()
    return any(re.search(p, t) for p in _ANSWER_REQUEST)


def practice_hint(decision: DecisionCard) -> str:
    """In practice mode we point to the source instead of giving the answer."""
    entry = bank_entry(decision.id)
    pages = ", ".join(f"{r.file} page {r.page}" for r in decision.source_refs)
    hint = entry["hint"] + " " if entry else ""
    return f"Practice hint: {hint}Re-read {pages}, then answer in your own words."


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9%]+", text.casefold()) if len(w) > 3}


def filter_feedback(feedback: str, decision: DecisionCard, mode: str) -> str:
    """Independent mode: if feedback contains >50% of the rationale's words, replace it."""
    if mode != "independent":
        return feedback
    rationale = _words(decision.rationale)
    if rationale and len(rationale & _words(feedback)) / len(rationale) > 0.5:
        return "Your answer was recorded. Discuss the decision again with your mentor before retrying."
    return feedback


def _status(score: int) -> EvidenceStatus:
    return EvidenceStatus.demonstrated if score == 2 else EvidenceStatus.needs_practice


def _demo_score(answer: str, decision: DecisionCard, mode: str) -> tuple[int, str] | None:
    """Deterministic keyword rubric for SYNTHETIC demo mode (stand-in for the LLM grader)."""
    entry = bank_entry(decision.id)
    if entry is None:
        return None
    text = answer.casefold()
    hit = [p for p in entry["rubric"] if any(k in text for k in p["keywords"])]
    missing = [p for p in entry["rubric"] if p not in hit]
    long_enough = len(answer.split()) >= MIN_WORDS_FOR_2
    score = 2 if len(hit) >= 2 and long_enough else (1 if hit else 0)
    if mode == "independent":
        return score, f"Score {score}/2: your answer covered {len(hit)} of {len(entry['rubric'])} expected points."
    if score == 2:
        return score, "Score 2/2: you explained " + "; ".join(p["point"] for p in hit) + "."
    if score == 1:
        reason = "Develop the reasoning further. " if len(hit) >= 2 else ""
        return score, f"Score 1/2: {reason}You covered: {hit[0]['point']}. Still missing: {missing[0]['point'] if missing else 'the key tradeoff'}."
    return score, "Score 0/2: the answer does not yet explain the decision. " + practice_hint(decision)


def _llm_score(question: InterviewQuestion, answer: str, decision: DecisionCard) -> tuple[int, str] | None:
    rule = ("You may name one missing point." if question.mode == "practice"
            else "Do NOT reveal the rationale or the expected points; only say how complete the answer was.")
    prompt = (PROMPTS / "grade.txt").read_text(encoding="utf-8").format(
        question=question.prompt, expectations="; ".join(question.rubric_expectations),
        rationale=decision.rationale, quote=" / ".join(r.quote for r in decision.source_refs),
        answer=answer, feedback_rule=rule,
    )
    try:
        data = complete_json(prompt, GRADE_SCHEMA)
    except LLMUnavailable:
        return None
    score = data.get("score")
    if not isinstance(score, int) or not 0 <= score <= 2:
        return None  # invalid model output -> abstain, never guess
    return score, str(data.get("feedback", ""))[:500]


def evaluate_answer(question: InterviewQuestion, answer: str, source: DecisionCard) -> AssessmentEvidence:
    """Score an answer 0/1/2 (private, formative). Never fabricates a score."""
    if question.mode == "independent" and is_answer_request(answer):
        raise AnswerRequestBlocked(REFUSAL)

    def evidence(score: int, status: EvidenceStatus, feedback: str, synthetic: bool) -> AssessmentEvidence:
        return AssessmentEvidence(
            id=f"E-{question.id}-{uuid.uuid4().hex[:6]}",
            member_id=question.member_id,
            decision_id=question.decision_id,
            question_id=question.id,
            answer=answer,
            rubric_score=score,  # contract requires an int; 0 + insufficient_evidence means "not judged"
            status=status,
            feedback=filter_feedback(feedback, source, question.mode),
            source_refs=source.source_refs,
            visibility="private",
            is_synthetic=synthetic,
        )

    if not is_assessable(source) or not question.rubric_expectations:
        return evidence(0, EvidenceStatus.insufficient_evidence, INSUFFICIENT, synthetic=False)
    if not answer.strip():
        return evidence(0, EvidenceStatus.needs_practice, "Score 0/2: no answer was given.", not llm_available())

    if llm_available():
        result, synthetic = _llm_score(question, answer, source), False
    else:
        result, synthetic = _demo_score(answer, source, question.mode), True
    if result is None:
        return evidence(0, EvidenceStatus.insufficient_evidence,
                        "Could not assess this answer automatically; it needs human review.", synthetic)
    score, feedback = result
    return evidence(score, _status(score), feedback, synthetic)
