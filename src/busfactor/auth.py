"""Access codes — a light-weight sign-in for live projects.

The demo has no sign-in (it is a fictional team). A live project can turn on access codes:
- every member gets a personal code; the app only shows a member's answers after the code is entered;
- the project gets one reviewer code, needed to read the review queue (see orchestrator.review_queue).

Codes are shown once when they are issued and only a salted PBKDF2 hash is stored (in the settings
table, so no schema change). This is a prototype safeguard, not a full account system: there is no
password reset, no email and the attempt limit is per browser session.

A project is "protected" once its reviewer code exists. Projects without codes keep the old
behaviour (identity is a dropdown), which is what the demo and the automated tests use.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional

from busfactor import database as db

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I: codes are read out loud and typed by hand
CODE_LENGTH = 8
ITERATIONS = 200_000


def _member_key(member_id: str) -> str:
    return f"cred:member:{member_id}"


def _reviewer_key(project_id: str) -> str:
    return f"cred:reviewer:{project_id}"


def _normalise(code: str) -> str:
    return "".join(str(code).split()).replace("-", "").upper()


def _hash(code: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", _normalise(code).encode(), salt, ITERATIONS).hex()


def _store(key: str, code: str) -> None:
    salt = secrets.token_bytes(16)
    db.set_setting(key, f"{salt.hex()}${_hash(code, salt)}")


def _check(key: str, code: str) -> bool:
    stored = db.get_setting(key)
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    return hmac.compare_digest(_hash(code, bytes.fromhex(salt)), digest)


def new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    return f"{raw[:4]}-{raw[4:]}"


def issue_member_code(member_id: str) -> str:
    """Create (or replace) a member's code. Returns the plain code: show it once, it is not stored."""
    code = new_code()
    _store(_member_key(member_id), code)
    return code


def issue_reviewer_code(project_id: str) -> str:
    code = new_code()
    _store(_reviewer_key(project_id), code)
    return code


def issue_all(project_id: str, member_ids: list[str]) -> dict:
    """Protect a project: a code for every member plus the reviewer code. Replaces any earlier codes."""
    return {"members": {m: issue_member_code(m) for m in member_ids}, "reviewer": issue_reviewer_code(project_id)}


def is_protected(project_id: str) -> bool:
    return db.get_setting(_reviewer_key(project_id)) is not None


def has_member_code(member_id: str) -> bool:
    return db.get_setting(_member_key(member_id)) is not None


def verify_member(member_id: str, code: str) -> bool:
    return _check(_member_key(member_id), code)


def verify_reviewer(project_id: str, code: Optional[str]) -> bool:
    return bool(code) and _check(_reviewer_key(project_id), code)
