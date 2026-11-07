"""Database — SQLite persistence, privacy-gated evidence access and the action log (Teammate 4).

Each model is stored as JSON in a `data` column, with id + key columns for lookups.
Privacy is enforced HERE: evidence (answers and scores) can only be read by its owner
via get_private_evidence(); load_all() refuses evidence. The agent's coverage
computation uses evidence_for_coverage(), whose result must never be shown in the UI.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

from busfactor.models import (
    AssessmentEvidence, DecisionCard, InterviewQuestion, LogEvent, Member, Project, TeachingMission,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO_ROOT / "data" / "demo"
TABLES: dict[type, str] = {
    Project: "projects", DecisionCard: "decisions", Member: "members",
    InterviewQuestion: "questions", AssessmentEvidence: "evidence", TeachingMission: "missions",
}
M = TypeVar("M", bound=BaseModel)
_db_path: Path = Path(os.getenv("BUSFACTOR_DB", REPO_ROOT / "busfactor.db"))


def set_db_path(path: str | Path) -> None:
    global _db_path
    _db_path = Path(path)


@contextmanager
def _connect():
    con = sqlite3.connect(_db_path)
    try:
        for table in TABLES.values():
            con.execute(f"CREATE TABLE IF NOT EXISTS {table} "
                        "(id TEXT PRIMARY KEY, member_id TEXT, decision_id TEXT, data TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS log_events "
                    "(seq INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)")
        yield con
        con.commit()
    finally:
        con.close()


def save_record(record: BaseModel) -> str:
    """Upsert by id; returns the id (log events get their sequence number)."""
    if isinstance(record, LogEvent):
        with _connect() as con:
            cur = con.execute("INSERT INTO log_events (data) VALUES (?)", (record.model_dump_json(),))
            return str(cur.lastrowid)
    table = TABLES[type(record)]
    member = getattr(record, "member_id", None) or getattr(record, "learner_id", None)
    with _connect() as con:
        con.execute(f"INSERT OR REPLACE INTO {table} (id, member_id, decision_id, data) VALUES (?, ?, ?, ?)",
                    (record.id, member, getattr(record, "decision_id", None), record.model_dump_json()))
    return record.id


def _rows(model_cls: Type[M], where: str = "", args: tuple = ()) -> list[M]:
    with _connect() as con:
        rows = con.execute(f"SELECT data FROM {TABLES[model_cls]} {where} ORDER BY id", args).fetchall()
    return [model_cls.model_validate_json(r[0]) for r in rows]


def load_all(model_cls: Type[M], **filters) -> list[M]:
    """All records of a type, filtered on attributes. Evidence is private: use get_private_evidence."""
    if model_cls is AssessmentEvidence:
        raise PermissionError("Evidence is private: use get_private_evidence(viewer_id, member_id).")
    return [r for r in _rows(model_cls) if all(getattr(r, k) == v for k, v in filters.items())]


def get_record(model_cls: Type[M], record_id: str) -> Optional[M]:
    if model_cls is AssessmentEvidence:
        raise PermissionError("Evidence is private: use get_private_evidence(viewer_id, member_id).")
    found = _rows(model_cls, "WHERE id = ?", (record_id,))
    return found[0] if found else None


def get_private_evidence(viewer_id: str, member_id: str) -> list[AssessmentEvidence]:
    """A member can read only their own answers and scores (brief test 7)."""
    if viewer_id != member_id:
        raise PermissionError(f"{viewer_id} cannot read {member_id}'s private evidence.")
    return sorted(_rows(AssessmentEvidence, "WHERE member_id = ?", (member_id,)), key=lambda e: e.created_at)


def evidence_for_coverage() -> list[AssessmentEvidence]:
    """All evidence, for the agent's coverage/mission logic ONLY. Never display this."""
    return _rows(AssessmentEvidence)


def log(actor: str, action: str, detail: Optional[dict] = None) -> LogEvent:
    event = LogEvent(actor=actor, action=action, detail=detail or {})
    save_record(event)
    return event


def load_log(limit: int = 500) -> list[LogEvent]:
    with _connect() as con:
        rows = con.execute("SELECT data FROM log_events ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
    return [LogEvent.model_validate_json(r[0]) for r in rows][::-1]


def reset() -> None:
    with _connect() as con:
        for table in [*TABLES.values(), "log_events"]:
            con.execute(f"DELETE FROM {table}")


def seed_demo() -> None:
    """Replace everything with the SYNTHETIC demo data in data/demo/*.json."""
    reset()
    sources = [("project.json", "project", Project), ("members.json", "members", Member),
               ("decisions.json", "decisions", DecisionCard), ("questions.json", "questions", InterviewQuestion),
               ("evidence.json", "evidence", AssessmentEvidence)]
    for file, key, model_cls in sources:
        raw = json.loads((DEMO_DIR / file).read_text(encoding="utf-8"))[key]
        for item in raw if isinstance(raw, list) else [raw]:
            save_record(model_cls.model_validate(item))
    log("agent", "seed_demo", {"note": "SYNTHETIC DEMO DATA loaded", "files": [s[0] for s in sources]})
