"""Teammate 4 tests: privacy (test 7) and synthetic labelling (test 10)."""
import json
from pathlib import Path

import pytest

from busfactor import database as db
from busfactor import orchestrator as orc
from busfactor.models import AssessmentEvidence

DEMO = Path(__file__).resolve().parents[1] / "data" / "demo"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    db.set_db_path(tmp_path / "test.db")
    orc.seed_demo_data()


# --- test 7
def test_member_cannot_read_another_members_evidence():
    with pytest.raises(PermissionError):
        db.get_private_evidence("M01", "M04")
    own = db.get_private_evidence("M04", "M04")
    assert own and all(e.member_id == "M04" for e in own)


def test_evidence_cannot_be_bulk_loaded():
    with pytest.raises(PermissionError):
        db.load_all(AssessmentEvidence)
    with pytest.raises(PermissionError):
        db.get_record(AssessmentEvidence, "E-D03-M04-seed")


def test_member_cannot_answer_or_list_someone_elses_questions():
    with pytest.raises(PermissionError):
        orc.submit_answer("Q-D03-M04-why", "anything", viewer_id="M01")
    with pytest.raises(PermissionError):
        orc.my_questions("M01", "M04")


def test_team_view_and_log_contain_no_answers_or_scores():
    report = orc.team_coverage().model_dump_json()
    assert "rubric_score" not in report and "answer" not in report
    q = orc.start_check("M04", ["D03"])[0]
    secret = "my private answer about class imbalance"
    orc.submit_answer(q.id, secret, "M04")
    dumped = " ".join(e.model_dump_json() for e in db.load_log())
    assert secret not in dumped and "rubric_score" not in dumped


# --- test 10
def test_demo_badge_and_files_labelled_synthetic():
    assert orc.demo_banner() == "DEMO DATA — synthetic"
    for f in DEMO.glob("*.json"):
        assert json.loads(f.read_text())["_note"].startswith("SYNTHETIC DEMO DATA"), f.name
    assert "SYNTHETIC DEMO" in (DEMO / "project_report.md").read_text()


def test_badge_still_shown_when_demo_data_loaded_without_demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    assert orc.demo_banner() is not None
