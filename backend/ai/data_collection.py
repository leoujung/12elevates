"""12ELEVATE AI Network Building Intelligence - Task 4 data collection validators (synthetic-only).

Scope: validation of incoming records BEFORE they reach matching. No storage, no network.
Rules enforced (fail closed):
  - Engagement events: allowed types only; stable idempotency key required; raw assessment answers
    are refused outright (Task 4: store only approved derived features).
  - Matching consent: explicit boolean per purpose; never pre-checked; granted=True requires an
    approved notice_version. The notice version is NOT invented here: it must be supplied from a
    written legal record. Verbal approval is not accepted as a notice_version.
  - Matching gate: a prospect may enter matching only with an active, granted consent for that
    purpose and no withdrawal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

ENGAGEMENT_TYPES = {"WEBINAR_REGISTERED", "WEBINAR_ATTENDED", "EDUCATION_VIEWED", "EDUCATION_COMPLETED"}
CONSENT_PURPOSES = {"matching_customer", "matching_business", "marketing"}
FORBIDDEN_RAW_FIELDS = {"raw_answers", "answers", "assessment_answers", "answer_values"}


class RejectedRecord(Exception):
    pass


@dataclass
class EngagementEvent:
    event_id: str          # stable idempotency key (Blocker 1 must guarantee stability in browser)
    member_id: str
    prospect_id: str
    event_type: str
    occurred_at: str       # ISO timestamp string


def validate_engagement_event(payload: dict) -> EngagementEvent:
    bad_raw = FORBIDDEN_RAW_FIELDS & set(payload.keys())
    if bad_raw:
        raise RejectedRecord(f"raw assessment fields are not allowed: {sorted(bad_raw)}")
    for k in ("event_id", "member_id", "prospect_id", "event_type", "occurred_at"):
        if not payload.get(k):
            raise RejectedRecord(f"missing required field: {k}")
    if payload["event_type"] not in ENGAGEMENT_TYPES:
        raise RejectedRecord(f"event_type not allowed: {payload['event_type']}")
    return EngagementEvent(payload["event_id"], payload["member_id"], payload["prospect_id"],
                           payload["event_type"], payload["occurred_at"])


@dataclass
class MatchingConsent:
    purpose: str
    granted: bool
    notice_version: Optional[str]
    granted_at: Optional[str]
    withdrawn_at: Optional[str] = None


def validate_consent(payload: dict, approved_notice_versions: set[str]) -> MatchingConsent:
    purpose = payload.get("purpose")
    if purpose not in CONSENT_PURPOSES:
        raise RejectedRecord(f"unknown consent purpose: {purpose}")
    granted = payload.get("granted")
    if not isinstance(granted, bool):
        raise RejectedRecord("granted must be an explicit boolean (never pre-checked or inferred)")
    notice = payload.get("notice_version")
    if granted:
        if not notice or notice not in approved_notice_versions:
            raise RejectedRecord("granted=True requires a notice_version in the approved legal record")
        if not payload.get("granted_at"):
            raise RejectedRecord("granted=True requires granted_at timestamp")
    return MatchingConsent(purpose, granted, notice, payload.get("granted_at"), payload.get("withdrawn_at"))


def may_enter_matching(consent: Optional[MatchingConsent], purpose: str) -> bool:
    """Gate used before any matching run. Fails closed."""
    if consent is None or consent.purpose != purpose:
        return False
    if not consent.granted or consent.withdrawn_at:
        return False
    return True
