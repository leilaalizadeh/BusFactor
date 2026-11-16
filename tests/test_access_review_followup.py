"""Access codes, human review queue, spaced follow-up and the team report export (offline, synthetic data)."""
from datetime import timedelta

import pytest

from busfactor import auth
from busfactor import database as db
from busfactor import orchestrator as orc
from busfactor.models import (
    AssessmentEvidence, EvidenceStatus, InterviewQuestion, Member, MissionStatus, QuestionType, utcnow,
)
from demo_answers import strong_answer

MISSION = "T-D03-M04"


@pytest.fixture(autouse=True)
def demo_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    db.set_db_path(tmp_path / "access.db")
    orc.seed_demo_data()


def verified_mission():
    """The demo flow up to a passed retest: M02 teaches M04 on D03."""
    orc.propose_missions()
    orc.accept_mission(MISSION, "M02")
    orc.accept_mission(MISSION, "M04")
    q = orc.start_retest(MISSION, "M04")
    res = orc.submit_retest(MISSION, strong_answer(q), "M04")
    assert res.mission.status == MissionStatus.verified and res.mission.verified_at is not None
    return res.mission


# ------------------------------------------------------------------ access codes

def live_project():
    return orc.create_project("Campus Events App", "Databases", [("report.md", b"We chose PostgreSQL.")],
                              ["Ada", "Grace"])


def test_codes_are_stored_hashed_and_verified():
    p = live_project()
    ids = sorted(orc.members(p.id))
    codes = orc.protect_project(p.id)
    assert set(codes["members"]) == set(ids) and orc.is_protected(p.id)
    ada = codes["members"][ids[0]]
    assert auth.verify_member(ids[0], ada) and auth.verify_member(ids[0], ada.lower().replace("-", " "))
    assert not auth.verify_member(ids[0], codes["members"][ids[1]])     # another member's code does not work
    assert not auth.verify_member(ids[0], "WRONG-CODE")
    stored = db.get_setting(f"cred:member:{ids[0]}")
    assert ada.replace("-", "") not in stored and "$" in stored          # only a salted hash is stored


def test_demo_and_codeless_projects_stay_open():
    assert not orc.is_protected("P01")
    with pytest.raises(ValueError):
        orc.protect_project("P01")
    p = live_project()
    assert not orc.is_protected(p.id) and not auth.has_member_code(f"{p.id}-M01")


def test_deleting_a_project_removes_its_codes():
    p = live_project()
    ids = sorted(orc.members(p.id))
    orc.protect_project(p.id)
    orc.delete_project(p.id, "Campus Events App")
    assert not auth.is_protected(p.id) and not any(auth.has_member_code(m) for m in ids)


# ------------------------------------------------------------------ human review queue

def unscored_answer(member_id: str = "M04", decision_id: str = "D02") -> AssessmentEvidence:
    q = InterviewQuestion(id="Q-review-1", decision_id=decision_id, member_id=member_id,
                          prompt="Why did the team pick a Random Forest baseline?", question_type=QuestionType.why,
                          rubric_expectations=["Names the alternative", "Explains the tradeoff"], project_id="P01")
    ev = AssessmentEvidence(id="E-review-1", member_id=member_id, decision_id=decision_id, question_id=q.id,
                            answer="Because it was easy.", rubric_score=0,
                            status=EvidenceStatus.insufficient_evidence, feedback="Needs human review.",
                            project_id="P01")
    db.save_records(q, ev)
    return ev


def set_review_consent(member_id: str, allowed: bool) -> None:
    m = db.get_record(Member, member_id)
    orc.update_consent(member_id, member_id, assessment=m.consent_assessment, mentor=m.consent_mentor,
                       learner=m.consent_learner, review=allowed)


def test_review_queue_only_shows_answers_of_members_who_consented_to_review():
    unscored_answer()
    assert orc.review_queue("P01") == []                      # consent_review is off by default
    set_review_consent("M04", True)
    [item] = orc.review_queue("P01")
    assert item.answer == "Because it was easy." and item.decision_id == "D02"
    assert "M04" not in repr(item)                            # the reviewer never sees who answered
    set_review_consent("M04", False)                          # withdrawing removes it again
    assert orc.review_queue("P01") == []


def test_reviewing_scores_the_answer_and_updates_coverage():
    unscored_answer()
    set_review_consent("M04", True)
    before = orc.team_coverage("P01")
    assert {c.decision_id: c for c in before.per_decision}["D02"].demonstrated_by == ["M02"]
    res = orc.apply_review("E-review-1", 2, "Names the alternative and the tradeoff.", "P01")
    assert res.evidence.status == EvidenceStatus.demonstrated and res.evidence.rubric_score == 2
    assert res.evidence.feedback.startswith("Reviewed by a human")
    assert orc.review_queue("P01") == []                      # gone from the queue
    after = {c.decision_id: c for c in orc.team_coverage("P01").per_decision}["D02"]
    assert after.demonstrated_by == ["M02", "M04"] and after.status == "covered"
    # the log says a review happened but never the answer or the score
    logged = " ".join(str(e.detail) for e in db.load_log(project_id="P01") if e.action == "human_review")
    assert "E-review-1" in logged and "Because it was easy" not in logged and "score" not in logged
    with pytest.raises(LookupError):
        orc.apply_review("E-review-1", 2, "", "P01")          # already reviewed


def test_review_score_must_be_0_1_or_2_and_a_reviewer_code_is_enforced():
    unscored_answer()
    set_review_consent("M04", True)
    with pytest.raises(ValueError):
        orc.apply_review("E-review-1", 3, "", "P01")
    p = live_project()
    codes = orc.protect_project(p.id)
    with pytest.raises(PermissionError):
        orc.review_queue(p.id)
    with pytest.raises(PermissionError):
        orc.review_queue(p.id, codes["members"][f"{p.id}-M01"])   # a member code is not a reviewer code
    assert orc.review_queue(p.id, codes["reviewer"]) == []


def test_a_reviewed_retest_can_verify_the_mission():
    orc.propose_missions()
    orc.accept_mission(MISSION, "M02")
    orc.accept_mission(MISSION, "M04")
    q = orc.start_retest(MISSION, "M04")
    ev = AssessmentEvidence(id="E-retest-1", member_id="M04", decision_id="D03", question_id=q.id,
                            answer=strong_answer(q), rubric_score=0, status=EvidenceStatus.insufficient_evidence,
                            feedback="Needs human review.", project_id="P01")
    db.save_records(ev)
    set_review_consent("M04", True)
    res = orc.apply_review("E-retest-1", 2, "", "P01")
    assert res.mission.status == MissionStatus.verified
    assert db.get_record(type(res.mission), MISSION).status == MissionStatus.verified


# ------------------------------------------------------------------ reminders and follow-up

def test_idle_accepted_mission_triggers_a_reminder_for_both_people():
    orc.propose_missions()
    orc.accept_mission(MISSION, "M02")
    orc.accept_mission(MISSION, "M04")
    assert orc.reminders("M04") == []                         # just accepted
    later = utcnow() + timedelta(days=orc.REMINDER_DAYS + 1)
    for who in ("M02", "M04"):
        [r] = orc.reminders(who, later)
        assert r["kind"] == "session" and r["decision_id"] == "D03" and r["days"] >= orc.REMINDER_DAYS
    assert orc.reminders("M01", later) == []                  # not part of the mission


def test_followup_opens_after_the_delay_and_only_for_the_learner():
    verified_mission()
    due = utcnow() + timedelta(days=orc.FOLLOWUP_DAYS, minutes=1)
    assert orc.reminders("M04") == []                         # not due yet
    with pytest.raises(ValueError, match="opens"):
        orc.start_followup(MISSION, "M04")
    assert [r["kind"] for r in orc.reminders("M04", due)] == ["followup"]
    assert orc.reminders("M02", due) == []                    # the mentor gets no follow-up
    with pytest.raises(PermissionError):
        orc.start_followup(MISSION, "M02", due)

    q = orc.start_followup(MISSION, "M04", due)
    mission = orc._mission(MISSION)
    assert mission.followup_done and mission.status == MissionStatus.accepted and mission.retest_question_id == q.id
    assert q.mode == "independent" and q.question_type == QuestionType.transfer
    with pytest.raises(ValueError, match="already started"):
        orc.start_followup(MISSION, "M04", due)


def test_a_followup_miss_lowers_coverage_and_retries_stay_bounded():
    verified_mission()
    due = utcnow() + timedelta(days=orc.FOLLOWUP_DAYS, minutes=1)
    covered_before = orc.team_coverage("P01").numerator
    orc.start_followup(MISSION, "M04", due)
    res = orc.submit_retest(MISSION, "I do not remember.", "M04")
    assert res.mission.status == MissionStatus.completed
    assert orc.team_coverage("P01").numerator == covered_before - 1   # retention failed: the evidence says so
    with pytest.raises(ValueError, match="No new independent question"):
        orc.start_retest(MISSION, "M04")        # the demo has two scenarios and both are used: no pass-chasing


def test_a_followup_pass_verifies_the_mission_again():
    verified_mission()
    due = utcnow() + timedelta(days=orc.FOLLOWUP_DAYS, minutes=1)
    covered_before = orc.team_coverage("P01").numerator
    q = orc.start_followup(MISSION, "M04", due)
    res = orc.submit_retest(MISSION, strong_answer(q), "M04")
    assert res.mission.status == MissionStatus.verified and res.mission.verified_at is not None
    assert res.mission.followup_done and orc.team_coverage("P01").numerator == covered_before
    assert orc.reminders("M04", due + timedelta(days=30)) == []       # no second follow-up


# ------------------------------------------------------------------ team report export

def test_exports_contain_counts_only():
    verified_mission()
    report, csv_text = orc.export_team_report("P01"), orc.export_decisions_csv("P01")
    assert "BusFactor team report" in report and "DEMO DATA, synthetic" in report
    assert "2/5 (40%)" in report and "Single points of failure" in report
    secret_words = ["Member A", "Member B", "Member C", "Member D", "M01", "M02", "M03", "M04",
                    strong_answer(db.get_record(InterviewQuestion, orc._mission(MISSION).retest_question_id))]
    for text in (report, csv_text):
        for word in secret_words:
            assert word not in text, word
    assert csv_text.splitlines()[0].startswith("decision,title,card_status")
    assert len(csv_text.splitlines()) == 6                    # header + 5 decisions
