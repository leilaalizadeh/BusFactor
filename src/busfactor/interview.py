"""Interview — private Why?/What-if? questions and independent transfer retests (Teammate 2).

Questions come from the live model when available, otherwise from the SYNTHETIC demo
question bank (demo project only), otherwise from a deterministic template.

Rules enforced in code:
- Only `verified` (human-confirmed, source-backed) decisions are assessed.
- The demo bank is used ONLY for cards of the demo project, so a live project's "D03"
  can never receive demo questions, rubrics or hints.
- A transfer question carries a SCENARIO-SPECIFIC rubric: when the changed condition changes
  the right reasoning, the expected points change with it. Each scenario is used once per learner.
"""
from __future__ import annotations

import difflib
import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from busfactor import llm_provider
from busfactor.llm_provider import LLMUnavailable
from busfactor.models import DEMO_PROJECT_ID, DecisionCard, InterviewQuestion, QuestionType, ReviewStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
BANK_PATH = REPO_ROOT / "data" / "demo" / "question_bank.json"
PROMPTS = REPO_ROOT / "prompts"
MAX_SIMILARITY = 0.8
PROMPT_SCHEMA = {"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"]}
TRANSFER_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string"},
        "changed_condition": {"type": "string"},
        "expected_points": {"type": "array", "items": {"type": "string"}},
        "conclusion_changes": {"type": "boolean"},
    },
    "required": ["prompt", "changed_condition", "expected_points", "conclusion_changes"],
}


class UnsupportedDecision(ValueError):
    """The decision is not verified, or has no source or rationale: we do not ask about it."""


@lru_cache(maxsize=1)
def load_bank() -> dict:
    if not BANK_PATH.exists():
        return {}
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def bank_entry(decision: DecisionCard) -> Optional[dict]:
    """The demo bank entry for a DEMO-project decision; None for every other project."""
    bank = load_bank()
    if decision.project_id != bank.get("project_id", DEMO_PROJECT_ID):
        return None
    return bank.get("decisions", {}).get(decision.id)


def bank_rubric(decision: DecisionCard, question: InterviewQuestion) -> Optional[list[dict]]:
    """Keyword rubric for a demo question: the scenario's own rubric for transfer questions."""
    entry = bank_entry(decision)
    if entry is None:
        return None
    if question.question_type == QuestionType.transfer:
        scenario = next((t for t in entry.get("transfer", []) if t["prompt"] == question.prompt), None)
        return scenario["rubric"] if scenario else None
    return entry["rubric"]


def is_assessable(decision: DecisionCard) -> bool:
    return (
        decision.review_status == ReviewStatus.verified
        and bool(decision.rationale.strip())
        and bool(decision.source_refs)
    )


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.casefold().strip(), b.casefold().strip()).ratio()


def rubric_for(decision: DecisionCard) -> list[str]:
    """2-3 points a score-2 answer must contain: from the demo bank, else from the reviewed card itself."""
    entry = bank_entry(decision)
    if entry:
        return [p["point"] for p in entry["rubric"]]
    points = [f"Explains the reason: {decision.rationale}"]
    if decision.alternatives:
        points.append(f"Explains the tradeoff versus: {', '.join(decision.alternatives)}")
    return points


def _source_text(decision: DecisionCard) -> str:
    return "; ".join(f"{r.file} p.{r.page}: \"{r.quote}\"" for r in decision.source_refs)


def _llm_json(template: str, schema: dict, **values) -> Optional[dict]:
    if not llm_provider.llm_available():
        return None
    try:
        text = (PROMPTS / template).read_text(encoding="utf-8").format(**values)
        return llm_provider.complete_json(text, schema)
    except (LLMUnavailable, KeyError, OSError):
        return None  # fall back to bank/template; never block the interview on the model


def _require_assessable(decision: DecisionCard, what: str) -> None:
    if not is_assessable(decision):
        state = decision.review_status.value
        raise UnsupportedDecision(f"{decision.id} is {state} (needs a confirmed card with a source); no {what}.")


def create_interview(
    decision: DecisionCard, member_id: str, prior: list[InterviewQuestion]
) -> InterviewQuestion:
    """Next question for this member: `why` first, then `what_if`; types already asked are skipped."""
    _require_assessable(decision, "question")

    asked = {q.question_type for q in prior if q.decision_id == decision.id and q.member_id == member_id}
    qtype = next((t for t in (QuestionType.why, QuestionType.what_if) if t not in asked), None)
    if qtype is None:
        raise ValueError(f"{member_id} already answered why and what_if for {decision.id}.")

    alternatives = ", ".join(decision.alternatives) or "the obvious alternative"
    entry = bank_entry(decision)
    generated = _llm_json("question.txt", PROMPT_SCHEMA, question_type=qtype.value, title=decision.title,
                          rationale=decision.rationale, alternatives=alternatives, source=_source_text(decision))
    prompt = (
        (str(generated.get("prompt", "")).strip() if generated else "")
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
        project_id=decision.project_id,
    )


def _valid_scenario(data: Optional[dict]) -> Optional[tuple[str, str, list[str]]]:
    """Validate the model's transfer question: a stated changed condition and 2-4 concrete points."""
    if not data:
        return None
    prompt = str(data.get("prompt") or "").strip()
    condition = str(data.get("changed_condition") or "").strip()
    points = [str(p).strip() for p in data.get("expected_points") or [] if str(p).strip()]
    if not prompt or not condition or not 2 <= len(points) <= 4:
        return None
    return prompt, condition, points


def create_transfer_test(
    decision: DecisionCard, prior_question: InterviewQuestion, used_prompts: Iterable[str] = ()
) -> InterviewQuestion:
    """A NEW independent what-if question (no hints) with a rubric for ITS scenario.

    Raises ValueError when no scenario is left that differs from the previous question and
    from every scenario this learner already used (bounded attempts, no pass-chasing loop).
    """
    _require_assessable(decision, "retest")
    used = [p for p in used_prompts if p] + [prior_question.prompt]

    def different(text: str) -> bool:
        return bool(text) and all(similarity(text, u) <= MAX_SIMILARITY for u in used)

    alternatives = ", ".join(decision.alternatives) or "the alternative"
    candidates: list[tuple[str, Optional[str], list[str]]] = []
    if llm_provider.llm_available():
        for _ in range(2):  # generate, check, regenerate once
            scenario = _valid_scenario(_llm_json("transfer.txt", TRANSFER_SCHEMA, title=decision.title,
                                                 rationale=decision.rationale, alternatives=alternatives,
                                                 prior="\n".join(used)))
            if scenario and different(scenario[0]):
                candidates.append(scenario)
                break
    for t in (bank_entry(decision) or {}).get("transfer", []):
        candidates.append((t["prompt"], t["scenario"], [p["point"] for p in t["rubric"]]))
    if not candidates:  # no model, no bank: a template whose rubric asks for the scenario-specific judgement
        candidates.append((
            f"Imagine an examiner proposes {alternatives} instead of \"{decision.title}\" for a new dataset "
            f"from a different source. What would you answer, and would anything change?",
            "The data comes from a different source and an examiner proposes the alternative.",
            [f"States whether \"{decision.title}\" still holds for the new data, with a reason",
             f"Compares it with {alternatives} using the project's tradeoff",
             "Names what evidence would be needed to be sure"],
        ))
    chosen = next((c for c in candidates if different(c[0])), None)
    if chosen is None:
        raise ValueError("No new independent question is left for this decision. Review it with your mentor "
                         "or the course material, then ask the team to add a scenario.")
    prompt, condition, points = chosen
    return InterviewQuestion(
        id=f"Q-{decision.id}-{prior_question.member_id}-transfer-{uuid.uuid4().hex[:6]}",
        decision_id=decision.id,
        member_id=prior_question.member_id,
        prompt=prompt,
        question_type=QuestionType.transfer,
        rubric_expectations=points,
        source_refs=decision.source_refs,
        mode="independent",
        project_id=decision.project_id,
        scenario=condition,
    )
