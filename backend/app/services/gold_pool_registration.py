"""Admin-only: record a member's sponsor and how the signed registration form was delivered.

Rules:
- Admin only (require_admin). Members cannot set their own sponsor.
- registration_channel must be WA or EMAIL (no free text).
- Sponsor fields are stored on the member row and are NOT returned by /v1/me (not shown to the member).
- Every change is written to the audit log with before/after values.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.core import Member
from app.models.gold_pool import GpAuditLog

ALLOWED_CHANNELS = {"WA", "EMAIL"}


class RegistrationError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def set_member_registration(db, *, actor_id: str, member_email: str,
                            sponsor_name: str | None, sponsor_ref: str | None,
                            registration_channel: str | None, reason: str) -> Member:
    if not reason or not reason.strip():
        raise RegistrationError("REASON_REQUIRED")
    if registration_channel is not None and registration_channel not in ALLOWED_CHANNELS:
        raise RegistrationError("INVALID_CHANNEL")

    member = db.execute(select(Member).where(Member.email == member_email.lower())).scalar_one_or_none()
    if member is None:
        raise RegistrationError("MEMBER_NOT_FOUND")

    before = {"sponsor_name": member.sponsor_name, "sponsor_ref": member.sponsor_ref,
              "registration_channel": member.registration_channel}
    member.sponsor_name = (sponsor_name or "").strip() or None
    member.sponsor_ref = (sponsor_ref or "").strip() or None
    member.registration_channel = registration_channel
    after = {"sponsor_name": member.sponsor_name, "sponsor_ref": member.sponsor_ref,
             "registration_channel": member.registration_channel}

    db.add(GpAuditLog(action="MEMBER_REGISTRATION_SET", actor_id=actor_id,
                      entity_type="member", entity_id=member.id,
                      before_value=json.dumps(before, ensure_ascii=False),
                      after_value=json.dumps(after, ensure_ascii=False),
                      reason=reason.strip()[:300],
                      at=datetime.now(timezone.utc)))
    db.commit()
    return member
