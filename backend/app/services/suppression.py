"""Global suppression (UU PDP opt-out). Persistent, shared across instances.

Normalisation must match api/security-validator.js so both sides agree:
  digits-only for phone numbers, lowercase for emails.
"""
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

_EMAIL = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}")


def normalize(identifier):
    """Return the canonical form, or None if the input is not a usable identifier."""
    if not identifier or not isinstance(identifier, str):
        return None
    if "@" in identifier:
        clean = identifier.strip().lower()
        return clean if _EMAIL.fullmatch(clean) else None
    digits = re.sub(r"\D", "", identifier)
    return digits or None


def _kind(clean):
    return "email" if "@" in clean else "phone"


def add(db, *, identifier, source):
    """Idempotent insert. True if a new row was written; False if already present or invalid."""
    clean = normalize(identifier)
    if not clean:
        return False
    if db.execute(text("select 1 from suppression_list where identifier = :i"), {"i": clean}).first():
        return False
    try:
        db.execute(
            text("insert into suppression_list (id, identifier, kind, source, created_at) "
                 "values (:id, :i, :k, :s, :t)"),
            {"id": uuid.uuid4().hex, "i": clean, "k": _kind(clean), "s": source,
             "t": datetime.now(timezone.utc)},
        )
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def is_suppressed(db, identifier):
    """True if the identifier is on the list. Invalid input returns False here; callers decide how to treat it."""
    clean = normalize(identifier)
    if not clean:
        return False
    return db.execute(text("select 1 from suppression_list where identifier = :i"), {"i": clean}).first() is not None
