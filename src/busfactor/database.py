"""Database — SQLite persistence, privacy-gated evidence access and the action log (Teammate 4).

Each model is stored as JSON in a `data` column, with id + key columns for lookups.
Privacy is enforced HERE: evidence (answers and scores) can only be read by its owner
via get_private_evidence(); load_all() refuses evidence. The agent's coverage
computation uses evidence_for_coverage(), whose result must never be shown in the UI.

The action log has an audience per event: TEAM (shared project facts and aggregate
coverage), a list of member ids (private steps, visible only to them) or INTERNAL
(nobody). The UI reads it only through load_team_log(viewer_id); load_log() is the
full audit trail for the agent and tests and must never be displayed.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional, Type, TypeVar, Union

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

TEAM = "team"            # every member may see the event
INTERNAL = "internal"    # nobody sees it in the UI (default: fail closed)
REDACTED_ACTOR = "team member"
Audience = Union[str, Iterable[str]]   # TEAM, INTERNAL, or the member ids allowed to see it


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
        con.execute("CREATE TABLE IF NOT EXISTS log_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, "
                    f"data TEXT NOT NULL, audience TEXT NOT NULL DEFAULT '{INTERNAL}')")
        if "audience" not in {row[1] for row in con.execute("PRAGMA table_info(log_events)")}:
            # older databases: existing rows become INTERNAL, so nothing old leaks into the team view
            con.execute(f"ALTER TABLE log_events ADD COLUMN audience TEXT NOT NULL DEFAULT '{INTERNAL}'")
        yield con
        con.commit()
    finally:
        con.close()


def _upsert(con: sqlite3.Connection, record: BaseModel) -> str:
    table = TABLES[type(record)]
    member = getattr(record, "member_id", None) or getattr(record, "learner_id", None)
    con.execute(f"INSERT OR REPLACE INTO {table} (id, member_id, decision_id, data) VALUES (?, ?, ?, ?)",
                (record.id, member, getattr(record, "decision_id", None), record.model_dump_json()))
    return record.id


def save_record(record: BaseModel) -> str:
    """Upsert by id; returns the id (log events get their sequence number)."""
    if isinstance(record, LogEvent):
        with _connect() as con:
            cur = con.execute("INSERT INTO log_events (data) VALUES (?)", (record.model_dump_json(),))
            return str(cur.lastrowid)
    with _connect() as con:
        return _upsert(con, record)


def save_records(*records: BaseModel, replacing: tuple[type, ...] = ()) -> list[str]:
    """Upsert several records in ONE transaction: all are written, or none (e.g. evidence + mission).

    `replacing` first deletes every record of those types inside the same transaction, so a new
    project either fully replaces the old one or leaves it untouched.
    """
    with _connect() as con:  # commits on success; closing without commit rolls back on error
        for model_cls in replacing:
            con.execute(f"DELETE FROM {TABLES[model_cls]}")
        return [_upsert(con, r) for r in records]


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


def _audience(audience: Audience) -> str:
    if audience in (TEAM, INTERNAL):
        return audience
    ids = sorted({audience} if isinstance(audience, str) else {a for a in audience if a})
    return json.dumps(ids) if ids else INTERNAL


def log(actor: str, action: str, detail: Optional[dict] = None, audience: Audience = INTERNAL) -> LogEvent:
    """Append an event. `audience` decides who may see it in the UI (see module docstring)."""
    event = LogEvent(actor=actor, action=action, detail=detail or {})
    with _connect() as con:
        con.execute("INSERT INTO log_events (data, audience) VALUES (?, ?)",
                    (event.model_dump_json(), _audience(audience)))
    return event


def load_log(limit: Optional[int] = 500) -> list[LogEvent]:
    """The audit trail (newest `limit` events, or all with None), for the agent and tests ONLY. Never display."""
    with _connect() as con:
        rows = con.execute("SELECT data FROM log_events ORDER BY seq DESC LIMIT ?",
                           (-1 if limit is None else limit,)).fetchall()
    return [LogEvent.model_validate_json(r[0]) for r in rows][::-1]


def load_team_log(viewer_id: str, limit: int = 500) -> list[LogEvent]:
    """What `viewer_id` may see: TEAM events plus their own private events.

    Other members are never named: any actor that is not the agent or the viewer
    is shown as "team member".
    """
    with _connect() as con:
        rows = con.execute("SELECT data FROM log_events WHERE audience = ? OR instr(audience, ?) > 0 "
                           "ORDER BY seq DESC LIMIT ?", (TEAM, json.dumps(viewer_id), limit)).fetchall()
    events = [LogEvent.model_validate_json(r[0]) for r in rows][::-1]
    return [e if e.actor in ("agent", viewer_id) else e.model_copy(update={"actor": REDACTED_ACTOR})
            for e in events]


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
    log("agent", "seed_demo", {"note": "SYNTHETIC DEMO DATA loaded", "files": [s[0] for s in sources]},
        audience=TEAM)
