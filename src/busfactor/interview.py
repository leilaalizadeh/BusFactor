"""Interview — private Why?/What-if? questions and independent transfer retests (Teammate 2).

Questions come from the live model when available, otherwise from the SYNTHETIC demo
question bank, otherwise from a deterministic template. The rubric is always derived
from the verified decision card (never invented by the model).
"""
from __future__ import annotations

import difflib
import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Optional

from busfactor.llm_provider import LLMUnavailable, complete_json, llm_available
from busfactor.models import DecisionCard, InterviewQuestion, QuestionType, ReviewStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
BANK_PATH = REPO_ROOT / "data" / "demo" / "question_bank.json"
PROMPTS = REPO_ROOT / "prompts"
MAX_SIMILARITY = 0.8
PROMPT_SCHEMA = {"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"]}


class UnsupportedDecision(ValueError):
    """The decision has no verified source or rationale: we do not ask about it."""


@lru_cache(maxsize=1)
def load_bank() -> dict:
    if not BANK_PATH.exists():
        return {}
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))["decisions"]


def bank_entry(decision_id: str) -> Optional[dict]:
    return load_bank().get(decision_id)


def is_assessable(decision: DecisionCard) -> bool:
    return (
        decision.review_status != ReviewStatus.unsupported
        and bool(decision.rationale.strip())
        and bool(decision.source_refs)
    )


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.casefold().strip(), b.casefold().strip()).ratio()


def rubric_for(decision: DecisionCard) -> list[str]:
    """2-3 points a score-2 answer must contain: from the bank, else from the card itself."""
    entry = bank_entry(decision.id)
    if entry:
        return [p["point"] for p in entry["rubric"]]
    points = [decision.rationale]
    if decision.alternatives:
        points.append(f"Explains the tradeoff versus: {', '.join(decision.alternatives)}")
    return points


def _source_text(decision: DecisionCard) -> str:
    return "; ".join(f"{r.file} p.{r.page}: \"{r.quote}\"" for r in decision.source_refs)


def _llm_prompt(template: str, **values) -> Optional[str]:
    if not llm_available():
        return None
    try:
        text = (PROMPTS / template).read_text(encoding="utf-8").format(**values)
        return str(complete_json(text, PROMPT_SCHEMA)["prompt"]).strip() or None
    except (LLMUnavailable, KeyError, OSError):
        return None  # fall back to bank/template; never block the interview on the model


def create_interview(
    decision: DecisionCard, member_id: str, prior: list[InterviewQuestion]
) -> InterviewQuestion:
    """Next question for this member: `why` first, then `what_if`; types already asked are skipped."""
    if not is_assessable(decision):
        raise UnsupportedDecision(f"{decision.id} has no verified source or rationale; not asking.")

    asked = {q.question_type for q in prior if q.decision_id == decision.id and q.member_id == member_id}
    qtype = next((t for t in (QuestionType.why, QuestionType.what_if) if t not in asked), None)
    if qtype is None:
        raise ValueError(f"{member_id} already answered why and what_if for {decision.id}.")

    alternatives = ", ".join(decision.alternatives) or "the obvious alternative"
    entry = bank_entry(decision.id)
    prompt = (
        _llm_prompt("question.txt", question_type=qtype.value, title=decision.title,
                    rationale=decision.rationale, alternatives=alternatives, source=_source_text(decision))
        or (entry or {}).get(qtype.value)
        or (f"Why did the team decide: \"{decision.title}\" instead of {alternatives}?"
            if qtype == QuestionType.why else
            f"What if one key condition of the project changed? Would \"{decision.title}\" still be "
            f"the right choice over {alternatives}? Explain using the project's data.")
    )
    return InterviewQuestion(
        id=f"Q-{decision.id}-{member_id}-{qtype.value}",
        decision_id=decision.id,
        member_id=member_id,
        prompt=prompt,
        question_type=qtype,
        rubric_expectations=rubric_for(decision),
        source_refs=decision.source_refs,
        mode="practice",
    )


def create_transfer_test(decision: DecisionCard, prior_question: InterviewQuestion) -> InterviewQuestion:
    """A NEW independent what-if question (no hints). Raises if it cannot be made different enough."""
    if not is_assessable(decision):
        raise UnsupportedDecision(f"{decision.id} has no verified source or rationale; no retest.")

    def different(text: str) -> bool:
        return bool(text) and similarity(text, prior_question.prompt) <= MAX_SIMILARITY

    alternatives = ", ".join(decision.alternatives) or "the alternative"
    candidates: list[str] = []
    if llm_available():
        for _ in range(2):  # generate, check, regenerate once
            text = _llm_prompt("transfer.txt", title=decision.title, rationale=decision.rationale,
                               alternatives=alternatives, prior=prior_question.prompt)
            if text and different(text):
                candidates.append(text)
                break
    candidates += (bank_entry(decision.id) or {}).get("transfer", [])
    candidates.append(
        f"Imagine an examiner proposes {alternatives} instead of \"{decision.title}\" for a new dataset "
        f"from a different source. What would you answer, and would anything change?"
    )
    prompt = next((c for c in candidates if different(c)), None)
    if prompt is None:
        raise ValueError("Could not create a transfer question different from the previous one.")

    return InterviewQuestion(
        id=f"Q-{decision.id}-{prior_question.member_id}-transfer-{uuid.uuid4().hex[:6]}",
        decision_id=decision.id,
        member_id=prior_question.member_id,
        prompt=prompt,
        question_type=QuestionType.transfer,
        rubric_expectations=rubric_for(decision),
        source_refs=decision.source_refs,
        mode="independent",
    )
