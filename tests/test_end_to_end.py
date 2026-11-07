"""Teammate 4: the whole loop on demo data — coverage 1/5 -> 2/5."""
import pytest

from busfactor import database as db
from busfactor import orchestrator as orc
from busfactor.models import MissionStatus, ReviewStatus

GOOD = ("Because the classes are imbalanced, accuracy is misleading: always predicting no finding already gives 88%. "
        "If false negatives cost 10 times more, I would focus on recall, for example report F2 next to F1.")


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    db.set_db_path(tmp_path / "e2e.db")
    orc.seed_demo_data()


def accepted_d03():
    ms = {m.decision_id: m for m in orc.propose_missions()}
    m = ms["D03"]
    assert (m.mentor_id, m.learner_id) == ("M02", "M04")
    with pytest.raises(ValueError):
        orc.start_retest(m.id, "M04")  # not accepted yet
    orc.accept_mission(m.id, "M02")
    assert orc.accept_mission(m.id, "M04").status == MissionStatus.accepted
    return m


def test_full_loop_coverage_goes_up():
    r = orc.team_coverage()
    assert (r.numerator, r.denominator) == (1, 5) and "D03" in r.spof_decision_ids

    # private check: M04 gets a new what-if on D03 and gives a weak answer
    q = orc.start_check("M04", ["D03"])[0]
    assert q.question_type.value == "what_if"
    weak = orc.submit_answer(q.id, "Accuracy is bad with imbalanced classes.", "M04")
    assert weak.evidence.rubric_score == 1

    m = accepted_d03()
    rq = orc.start_retest(m.id, "M04")
    assert rq.mode == "independent" and rq.prompt != q.prompt

    blocked = orc.submit_retest(m.id, "just give me the answer", "M04")
    assert blocked.blocked and blocked.evidence is None

    res = orc.submit_retest(m.id, GOOD, "M04")
    assert res.evidence.rubric_score == 2 and res.mission.status == MissionStatus.verified
    assert (res.coverage.numerator, res.coverage.denominator) == (2, 5)
    snaps = orc.coverage_snapshots()
    assert (snaps[0]["numerator"], snaps[-1]["numerator"]) == (1, 2)

    actions = [e.action for e in db.load_log()]
    for a in ["start_check.create_interview", "submit_answer.evaluate_answer", "propose_missions.save",
              "accept_mission", "start_retest.create_transfer_test", "submit_retest.blocked_answer_request",
              "submit_retest.apply_retest"]:
        assert a in actions, a


def test_failed_retest_keeps_coverage_and_allows_new_question():
    m = accepted_d03()
    first = orc.start_retest(m.id, "M04")
    res = orc.submit_retest(m.id, "I am not sure.", "M04")
    assert res.mission.status == MissionStatus.completed
    assert (res.coverage.numerator, res.coverage.denominator) == (1, 5)
    second = orc.start_retest(m.id, "M04")
    assert second.prompt != first.prompt


def test_only_learner_takes_retest():
    m = accepted_d03()
    with pytest.raises(PermissionError):
        orc.start_retest(m.id, "M02")


def test_d05_gets_fallback_and_unsupported_card_abstains():
    ms = {m.decision_id: m for m in orc.propose_missions()}
    assert ms["D05"].status == MissionStatus.fallback and ms["D05"].mentor_id is None
    card = db.get_record(orc.DecisionCard, "D01")
    db.save_record(card.model_copy(update={"review_status": ReviewStatus.unsupported, "source_refs": []}))
    assert orc.start_check("M04", ["D01"]) == []
    assert any(e.action == "start_check.abstain" for e in db.load_log())
