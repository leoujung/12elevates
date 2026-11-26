"""Member referral codes: issue (by the member themself) and resolve (for intake).

- Codes are random (secrets.token_urlsafe), never derived from personal data.
- A member can only request a code for themselves (token -> member_id).
- Intake resolves a code to exactly one active (not revoked) member.
"""
import secrets
from datetime import datetime, timezone

from sqlalchemy import text


def _now():
    return datetime.now(timezone.utc)


def issue_code(db, member_id: str) -> str:
    # One active code per member: revoke old, issue new.
    db.execute(text("update member_referral_codes set revoked_at = :t "
                    "where member_id = :m and revoked_at is null"), {"m": member_id, "t": _now()})
    code = secrets.token_urlsafe(8)
    db.execute(text("insert into member_referral_codes (code, member_id) values (:c, :m)"),
               {"c": code, "m": member_id})
    return code


def resolve_code(db, code: str):
    if not code or len(code) > 100:
        return None
    row = db.execute(text("select member_id from member_referral_codes "
                          "where code = :c and revoked_at is null limit 1"),
                     {"c": code.strip()}).first()
    return str(row[0]) if row else None
