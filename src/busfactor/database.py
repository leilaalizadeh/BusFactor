"""Database — SQLite persistence, privacy-gated evidence access and the action log (Teammate 4).

Each model is stored as JSON in a `data` column, with id + key columns for lookups.
Privacy is enforced HERE: evidence (answers and scores) can only be read by its owner
via get_private_evidence(); load_all() refuses evidence. The agent's coverage
computation uses evidence_for_coverage(), whose result must never be shown in the UI.

Projects are isolated: every record and every log event carries a project_id, and records
without one are refused. Several projects live side by side; creating a project never
deletes another one, and the demo reset touches only the demo project.

The action log has an audience per event: TEAM (shared project facts and aggregate
coverage), a list of member ids (private steps, visible only to them) or INTERNAL
(nobody). The UI reads it only through load_team_log(viewer_id, project_id); load_log()
is the full audit trail for the agent and tests and must never be displayed.

Schema versions (PRAGMA user_version): 1 = original, 2 = project_id columns, settings,
indexes. Older databases are migrated in place the first time they are opened.
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
    DEMO_PROJECT_ID, AssessmentEvidence, DecisionCard, InterviewQuestion, LogEvent, Member, Project, TeachingMission,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO_ROOT / "data" / "demo"
TABLES: dict[type, str] = {
    Project: "projects", DecisionCard: "decisions", Member: "members",
    InterviewQuestion: "questions", AssessmentEvidence: "evidence", TeachingMission: "missions",
}
SCHEMA_VERSION = 2
M = TypeVar("M", bound=BaseModel)
_db_path: Path = Path(os.getenv("BUSFACTOR_DB", REPO_ROOT / "busfactor.db"))

TEAM = "team"            # every member may see the event
INTERNAL = "internal"    # nobody sees it in the UI (default: fail closed)
REDACTED_ACTOR = "team member"
Audience = Union[str, Iterable[str]]   # TEAM, INTERNAL, or the member ids allowed to see it


def set_db_path(path: str | Path) -> None:
    global _db_path
    _db_path = Path(path)


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}


def _migrate(con: sqlite3.Connection) -> None:
    """Bring an older database up to SCHEMA_VERSION, keeping all its data."""
    for table in TABLES.values():
        if "project_id" not in _columns(con, table):
            con.execute(f"ALTER TABLE {table} ADD COLUMN project_id TEXT")
    if "audience" not in _columns(con, "log_events"):
        # rows from before the audience column become INTERNAL, so nothing old leaks into a team view
        con.execute(f"ALTER TABLE log_events ADD COLUMN audience TEXT NOT NULL DEFAULT '{INTERNAL}'")
    if "project_id" not in _columns(con, "log_events"):
        con.execute("ALTER TABLE log_events ADD COLUMN project_id TEXT")
    # backfill: projects own themselves; cards and members carry it; the rest follow their decision
    con.execute("UPDATE projects SET project_id = id WHERE project_id IS NULL")
    for table in ("decisions", "members"):
        for rid, data in con.execute(f"SELECT id, data FROM {table} WHERE project_id IS NULL").fetchall():
            con.execute(f"UPDATE {table} SET project_id = ? WHERE id = ?",
                        (json.loads(data).get("project_id") or DEMO_PROJECT_ID, rid))
    decision_project = dict(con.execute("SELECT id, project_id FROM decisions").fetchall())
    for table in ("questions", "evidence", "missions"):
        for rid, did, data in con.execute(f"SELECT id, decision_id, data FROM {table} WHERE project_id IS NULL"
                                          ).fetchall():
            record = json.loads(data)
            pid = record.get("project_id") or decision_project.get(did) or DEMO_PROJECT_ID
            record["project_id"] = pid
            con.execute(f"UPDATE {table} SET project_id = ?, data = ? WHERE id = ?", (pid, json.dumps(record), rid))
    for table in [*TABLES.values(), "log_events"]:
        con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_project ON {table} (project_id)")
    for table in ("questions", "evidence", "missions"):
        con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_member ON {table} (member_id)")
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


@contextmanager
def _connect():
    con = sqlite3.connect(_db_path, timeout=30)  # wait for a lock (e.g. antivirus scan on Windows) instead of failing
    try:
        for table in TABLES.values():
            con.execute(f"CREATE TABLE IF NOT EXISTS {table} "
                        "(id TEXT PRIMARY KEY, member_id TEXT, decision_id TEXT, data TEXT NOT NULL, project_id TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS log_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, "
                    f"data TEXT NOT NULL, audience TEXT NOT NULL DEFAULT '{INTERNAL}', project_id TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        if con.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
            _migrate(con)
        yield con
        con.commit()
    finally:
        con.close()


def _project_of(record: BaseModel) -> str:
    pid = record.id if isinstance(record, Project) else getattr(record, "project_id", None)
    if not pid:
        raise ValueError(f"{type(record).__name__} {getattr(record, 'id', '')} has no project_id; refusing to store "
                         "a record that does not belong to a project.")
    return pid


def _upsert(con: sqlite3.Connection, record: BaseModel) -> str:
    table = TABLES[type(record)]
    member = getattr(record, "member_id", None) or getattr(record, "learner_id", None)
    con.execute(f"INSERT OR REPLACE INTO {table} (id, member_id, decision_id, data, project_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (record.id, member, getattr(record, "decision_id", None), record.model_dump_json(),
                 _project_of(record)))
    return record.id


def save_record(record: BaseModel) -> str:
    """Upsert by id; returns the id (log events get their sequence number)."""
    if isinstance(record, LogEvent):
        with _connect() as con:
            cur = con.execute("INSERT INTO log_events (data) VALUES (?)", (record.model_dump_json(),))
            return str(cur.lastrowid)
    with _connect() as con:
        return _upsert(con, record)


def save_records(*records: BaseModel) -> list[str]:
    """Upsert several records in ONE transaction: all are written, or none (e.g. evidence + mission)."""
    with _connect() as con:  # commits on success; closing without commit rolls back on error
        return [_upsert(con, r) for r in records]


def _rows(model_cls: Type[M], where: str = "", args: tuple = ()) -> list[M]:
    with _connect() as con:
        rows = con.execute(f"SELECT data FROM {TABLES[model_cls]} {where} ORDER BY id", args).fetchall()
    return [model_cls.model_validate_json(r[0]) for r in rows]


def load_all(model_cls: Type[M], **filters) -> list[M]:
    """All records of a type, filtered on attributes. Evidence is private: use get_private_evidence."""
    if model_cls is AssessmentEvidence:
        raise PermissionError("Evidence is private: use get_private_evidence(viewer_id, member_id).")
    pid = filters.pop("project_id", None)
    rows = _rows(model_cls, "WHERE project_id = ?", (pid,)) if pid else _rows(model_cls)
    return [r for r in rows if all(getattr(r, k) == v for k, v in filters.items())]


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


def evidence_awaiting_review(project_id: str) -> list[AssessmentEvidence]:
    """Answers the model could not score (insufficient_evidence) in one project.

    For the human-review queue ONLY: the caller must have checked the reviewer's access and each
    member's consent_review (orchestrator.review_queue does). Never display this list otherwise.
    """
    from busfactor.models import EvidenceStatus
    return [e for e in _rows(AssessmentEvidence, "WHERE project_id = ?", (project_id,))
            if e.status == EvidenceStatus.insufficient_evidence]


def evidence_for_coverage(project_id: Optional[str] = None) -> list[AssessmentEvidence]:
    """Evidence of one project (all with None), for the agent's coverage/mission logic ONLY. Never display."""
    if project_id:
        return _rows(AssessmentEvidence, "WHERE project_id = ?", (project_id,))
    return _rows(AssessmentEvidence)


# ------------------------------------------------------------------ settings (e.g. the open project)

def get_setting(key: str) -> Optional[str]:
    with _connect() as con:
        row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_setting(key: str, value: Optional[str]) -> None:
    with _connect() as con:
        if value is None:
            con.execute("DELETE FROM settings WHERE key = ?", (key,))
        else:
            con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


# ------------------------------------------------------------------ action log

def _audience(audience: Audience) -> str:
    if audience in (TEAM, INTERNAL):
        return audience
    ids = sorted({audience} if isinstance(audience, str) else {a for a in audience if a})
    return json.dumps(ids) if ids else INTERNAL


def log(actor: str, action: str, detail: Optional[dict] = None, audience: Audience = INTERNAL,
        project_id: Optional[str] = None) -> LogEvent:
    """Append an event. `audience` decides who may see it in the UI (see module docstring)."""
    event = LogEvent(actor=actor, action=action, detail=detail or {})
    with _connect() as con:
        con.execute("INSERT INTO log_events (data, audience, project_id) VALUES (?, ?, ?)",
                    (event.model_dump_json(), _audience(audience), project_id))
    return event


def load_log(limit: Optional[int] = 500, project_id: Optional[str] = None) -> list[LogEvent]:
    """The audit trail (newest `limit` events, or all with None), for the agent and tests ONLY. Never display."""
    where, args = ("WHERE project_id = ?", (project_id,)) if project_id else ("", ())
    with _connect() as con:
        rows = con.execute(f"SELECT data FROM log_events {where} ORDER BY seq DESC LIMIT ?",
                           (*args, -1 if limit is None else limit)).fetchall()
    return [LogEvent.model_validate_json(r[0]) for r in rows][::-1]


def load_team_log(viewer_id: str, project_id: Optional[str] = None, limit: int = 500) -> list[LogEvent]:
    """What `viewer_id` may see in one project: TEAM events plus their own private events.

    Other members are never named: any actor that is not the agent or the viewer
    is shown as "team member".
    """
    scope, args = ("AND project_id = ?", (project_id,)) if project_id else ("", ())
    with _connect() as con:
        rows = con.execute(f"SELECT data FROM log_events WHERE (audience = ? OR instr(audience, ?) > 0) {scope} "
                           "ORDER BY seq DESC LIMIT ?", (TEAM, json.dumps(viewer_id), *args, limit)).fetchall()
    events = [LogEvent.model_validate_json(r[0]) for r in rows][::-1]
    return [e if e.actor in ("agent", viewer_id) else e.model_copy(update={"actor": REDACTED_ACTOR})
            for e in events]


# ------------------------------------------------------------------ lifecycle

def reset() -> None:
    """Delete EVERYTHING (tests only; the app never calls this)."""
    with _connect() as con:
        for table in [*TABLES.values(), "log_events", "settings"]:
            con.execute(f"DELETE FROM {table}")


def _delete_project(con: sqlite3.Connection, project_id: str) -> None:
    # access codes of the project's members and its reviewer code go with it
    con.execute("DELETE FROM settings WHERE key IN (SELECT 'cred:member:' || id FROM members WHERE project_id = ?)",
                (project_id,))
    con.execute("DELETE FROM settings WHERE key = ?", (f"cred:reviewer:{project_id}",))
    for table in [*TABLES.values(), "log_events"]:
        con.execute(f"DELETE FROM {table} WHERE project_id = ?", (project_id,))


def delete_project(project_id: str) -> None:
    """Delete one project and everything that belongs to it, in one transaction. Other projects stay."""
    with _connect() as con:
        _delete_project(con, project_id)


def seed_demo() -> None:
    """Reset ONLY the demo project to the SYNTHETIC data in data/demo/*.json; other projects are untouched."""
    sources = [("project.json", "project", Project), ("members.json", "members", Member),
               ("decisions.json", "decisions", DecisionCard), ("questions.json", "questions", InterviewQuestion),
               ("evidence.json", "evidence", AssessmentEvidence)]
    records = []
    for file, key, model_cls in sources:
        raw = json.loads((DEMO_DIR / file).read_text(encoding="utf-8"))[key]
        records += [model_cls.model_validate(item) for item in (raw if isinstance(raw, list) else [raw])]
    with _connect() as con:  # one transaction: the demo is fully reset or left as it was
        _delete_project(con, DEMO_PROJECT_ID)
        for record in records:
            _upsert(con, record)
    log("agent", "seed_demo", {"note": "SYNTHETIC DEMO DATA loaded", "files": [s[0] for s in sources]},
        audience=TEAM, project_id=DEMO_PROJECT_ID)
