"""Teammate 2 tests: questions, rubric, guards (brief tests 5, 8, 9)."""
import json
from pathlib import Path

import pytest

from busfactor.interview import UnsupportedDecision, create_interview, create_transfer_test, similarity
from busfactor.knowledge import load_demo_decisions
from busfactor.models import EvidenceStatus, InterviewQuestion, QuestionType, ReviewStatus
from busfactor.rubrics import AnswerRequestBlocked, evaluate_answer, filter_feedback, is_answer_request

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def demo(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")


@pytest.fixture
def cards():
    return {c.id: c for c in load_demo_decisions()}


def test_why_first_then_what_if_then_none(cards):
    q1 = create_interview(cards["D03"], "M04", [])
    q2 = create_interview(cards["D03"], "M04", [q1])
    assert (q1.question_type, q2.question_type) == (QuestionType.why, QuestionType.what_if)
    assert q1.source_refs == cards["D03"].source_refs and len(q1.rubric_expectations) == 3
    with pytest.raises(ValueError):
        create_interview(cards["D03"], "M04", [q1, q2])


# --- test 5
@pytest.mark.parametrize("did", ["D01", "D02", "D03", "D04", "D05"])
def test_transfer_question_is_new_and_independent(cards, did):
    for prior in [create_interview(cards[did], "M04", [])]:
        t = create_transfer_test(cards[did], prior)
        assert t.prompt != prior.prompt and similarity(t.prompt, prior.prompt) <= 0.8
        assert t.question_type == QuestionType.transfer and t.mode == "independent"
        t2 = create_transfer_test(cards[did], t)  # a retake gets yet another question
        assert t2.prompt != t.prompt


# --- test 8
def test_unsupported_decision_gives_insufficient_evidence(cards):
    bad = cards["D03"].model_copy(update={"review_status": ReviewStatus.unsupported, "source_refs": []})
    with pytest.raises(UnsupportedDecision):
        create_interview(bad, "M04", [])
    q = create_interview(cards["D03"], "M04", [])
    ev = evaluate_answer(q, "Because of class imbalance, accuracy is misleading at 88%.", bad)
    assert ev.status == EvidenceStatus.insufficient_evidence and ev.rubric_score == 0
    assert ev.visibility == "private"


# --- test 9
@pytest.mark.parametrize("text", ["just give me the answer", "Can you tell me the answer?",
                                  "what's the correct answer", "dammi la risposta per favore"])
def test_answer_request_blocked_in_independent_mode(cards, text):
    assert is_answer_request(text)
    t = create_transfer_test(cards["D03"], create_interview(cards["D03"], "M04", []))
    with pytest.raises(AnswerRequestBlocked):
        evaluate_answer(t, text, cards["D03"])


def test_real_answers_are_not_flagged():
    assert not is_answer_request("My answer is that the classes are imbalanced, so accuracy misleads.")


# --- 6 sample D03 answers, 2 per level
D03_ANSWERS = [
    (2, "Only 12% of images show a finding, so a model that always predicts no finding gets 88% accuracy. "
        "F1 looks at precision and recall on the positive class, so it is not fooled."),
    (2, "Le classi sono sbilanciate: the data is imbalanced, and accuracy is misleading because the majority class "
        "dominates; F1 balances precision and recall for the rare findings."),
    (1, "Because the classes were imbalanced."),
    (1, "Accuracy can be misleading so F1 is better."),
    (0, "F1 is a newer metric than accuracy."),
    (0, ""),
]


@pytest.mark.parametrize("expected,answer", D03_ANSWERS)
def test_d03_sample_answers(cards, expected, answer):
    q = create_interview(cards["D03"], "M04", [])
    ev = evaluate_answer(q, answer, cards["D03"])
    assert ev.rubric_score == expected, ev.feedback
    assert ev.status == (EvidenceStatus.demonstrated if expected == 2 else EvidenceStatus.needs_practice)
    assert ev.is_synthetic


def test_independent_feedback_never_reveals_rationale(cards):
    d = cards["D03"]
    assert filter_feedback(d.rationale, d, "independent") != d.rationale
    assert filter_feedback(d.rationale, d, "practice") == d.rationale
    t = create_transfer_test(d, create_interview(d, "M04", []))
    ev = evaluate_answer(t, "Because of imbalance.", d)
    assert "precision" not in ev.feedback.lower() and "88" not in ev.feedback


def test_seed_evidence_matches_brief_table():
    ev = json.loads((ROOT / "data/demo/evidence.json").read_text())["evidence"]
    twos = {}
    for e in ev:
        assert e["is_synthetic"]
        if e["rubric_score"] == 2:
            twos.setdefault(e["decision_id"], set()).add(e["member_id"])
    assert twos == {"D01": {"M01", "M03"}, "D02": {"M02"}, "D03": {"M02"}, "D04": {"M03"}}
    assert {(e["decision_id"], e["member_id"], e["rubric_score"]) for e in ev} >= {("D03", "M04", 1), ("D05", "M04", 1)}
