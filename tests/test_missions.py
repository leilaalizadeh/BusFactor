"""Teammate 3 tests: coverage and missions (brief tests 2, 3, 4, 6)."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from busfactor.coverage import compute_coverage
from busfactor.knowledge import load_demo_decisions
from busfactor.missions import FALLBACK_MESSAGE, apply_retest, explain_mission, recommend_missions, set_consent
from busfactor.models import AssessmentEvidence, EvidenceStatus, Member, MissionStatus

DEMO = Path(__file__).resolve().parents[1] / "data" / "demo"


@pytest.fixture
def decisions():
    return load_demo_decisions()


@pytest.fixture
def evidence():
    return [AssessmentEvidence.model_validate(e) for e in json.loads((DEMO / "evidence.json").read_text())["evidence"]]


@pytest.fixture
def members():
    return {m["id"]: Member.model_validate(m) for m in json.loads((DEMO / "members.json").read_text())["members"]}


def retest(score, question_id="Q-retest"):
    return AssessmentEvidence(
        id=f"E-retest-{score}", member_id="M04", decision_id="D03", question_id=question_id, answer="...",
        rubric_score=score, status=EvidenceStatus.demonstrated if score == 2 else EvidenceStatus.needs_practice,
        created_at=datetime(2026, 11, 7, 12, 0),
    )


# --- test 2
def test_spof_flagged_and_baseline_one_of_five(decisions, evidence):
    r = compute_coverage(decisions, evidence)
    assert r.spof_decision_ids == ["D02", "D03", "D04"]
    assert {c.decision_id: c.status for c in r.per_decision}["D05"] == "no_explainer"
    assert (r.numerator, r.denominator, r.score) == (1, 5, 0.2)


def test_demo_missions_are_deterministic(decisions, evidence, members):
    ms = recommend_missions(decisions, evidence, members)
    assert [(m.decision_id, m.mentor_id, m.learner_id, m.status) for m in ms] == [
        ("D02", "M02", "M01", MissionStatus.proposed),
        ("D03", "M02", "M04", MissionStatus.proposed),   # the demo star
        ("D04", "M03", "M01", MissionStatus.proposed),
        ("D05", None, "M04", MissionStatus.fallback),
    ]
    assert ms == recommend_missions(decisions, evidence, members)
    assert all(not m.mentor_consent and not m.learner_consent for m in ms)


# --- test 3
def test_no_peer_mission_without_mentor_consent(decisions, evidence, members):
    members["M02"] = members["M02"].model_copy(update={"consent_mentor": False})
    d03 = next(m for m in recommend_missions(decisions, evidence, members) if m.decision_id == "D03")
    assert d03.mentor_id is None and d03.status == MissionStatus.fallback


def test_no_mission_for_learner_without_consent(decisions, evidence, members):
    for mid in members:
        members[mid] = members[mid].model_copy(update={"consent_learner": False})
    assert recommend_missions(decisions, evidence, members) == []


def test_accepted_only_when_both_consent(decisions, evidence, members):
    m = next(m for m in recommend_missions(decisions, evidence, members) if m.decision_id == "D03")
    m = set_consent(m, "M02")
    assert m.status == MissionStatus.proposed
    m = set_consent(m, "M04")
    assert m.status == MissionStatus.accepted
    with pytest.raises(PermissionError):
        set_consent(m.model_copy(update={"status": MissionStatus.proposed}), "M01")


# --- test 4
def test_no_explainer_returns_fallback_not_fake_mentor(decisions, evidence, members):
    d05 = next(m for m in recommend_missions(decisions, evidence, members) if m.decision_id == "D05")
    assert d05.mentor_id is None and d05.fallback_message == FALLBACK_MESSAGE
    assert "no mentor was invented" in explain_mission(d05)


# --- test 6
@pytest.mark.parametrize("score,after", [(2, (2, 5)), (1, (1, 5)), (0, (1, 5))])
def test_retest_updates_coverage_only_on_score_2(decisions, evidence, members, score, after):
    m = next(m for m in recommend_missions(decisions, evidence, members) if m.decision_id == "D03")
    m = set_consent(set_consent(m, "M02"), "M04").model_copy(update={"retest_question_id": "Q-retest"})
    ev = retest(score)
    m = apply_retest(m, ev)
    assert m.status == (MissionStatus.verified if score == 2 else MissionStatus.completed)
    r = compute_coverage(decisions, evidence + [ev])
    assert (r.numerator, r.denominator) == after


def test_retest_for_other_question_is_rejected(decisions, evidence, members):
    m = next(m for m in recommend_missions(decisions, evidence, members) if m.decision_id == "D03")
    m = set_consent(set_consent(m, "M02"), "M04").model_copy(update={"retest_question_id": "Q-retest"})
    with pytest.raises(ValueError):
        apply_retest(m, retest(2, question_id="Q-something-else"))


def test_not_assessed_excluded_and_zero_denominator(decisions, evidence):
    no_d04 = [e for e in evidence if e.decision_id != "D04"]
    r = compute_coverage(decisions, no_d04)
    assert r.unknown_decision_ids == ["D04"] and (r.numerator, r.denominator) == (1, 4)
    empty = compute_coverage(decisions, [])
    assert empty.denominator == 0 and empty.score is None


def test_insufficient_evidence_does_not_count_as_assessed(decisions):
    ev = AssessmentEvidence(id="E1", member_id="M01", decision_id="D01", question_id="Q", answer="x",
                            rubric_score=0, status=EvidenceStatus.insufficient_evidence)
    assert compute_coverage(decisions, [ev]).denominator == 0


def test_max_two_missions_per_mentor(decisions, members):
    ev = [AssessmentEvidence(id=f"E{d}", member_id="M02", decision_id=d, question_id="Q", answer="x",
                             rubric_score=2, status=EvidenceStatus.demonstrated) for d in ["D01", "D02", "D03", "D04"]]
    ms = recommend_missions(decisions, ev, members)
    assert sum(m.mentor_id == "M02" for m in ms) == 2


def test_explanation_mentions_no_scores(decisions, evidence, members):
    m = next(m for m in recommend_missions(decisions, evidence, members) if m.decision_id == "D03")
    text = explain_mission(m, {"M02": "Member B", "M04": "Member D"})
    assert "Member B" in text and "Member D" in text and "score" not in text.lower()
