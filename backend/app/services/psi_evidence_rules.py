"""PSI-2 hardening: permission evidence rules (pure, deterministic, no LLM).

Design principles:
- A payload claim of consent is NOT evidence. Authorization must reference a recorded evidence row.
- The lawful basis is recorded per evidence row, never inferred by code. Consent is one option among
  several and is never assumed as the default.
- Evidence cannot be used until a legal review is approved and recorded (status ACTIVE).
- Revocation and expiry are checked at ingestion time, not only at record time.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.psi_ingest_rules import ALLOWED_PURPOSES

# Closed sets. Adding a basis or method requires Director and legal review.
LAWFUL_BASES = ("CONSENT", "CONTRACT", "LEGITIMATE_INTEREST", "LEGAL_OBLIGATION")
COLLECTION_METHODS = (
    "WEB_FORM",
    "WEBINAR_REGISTRATION",
    "CONSULTATION_REQUEST",
    "EVENT_SIGNUP",
    "REFERRAL_SELF_SUBMISSION",  # the person themselves submits; third-party uploads are not a method
)

# Only CONSENT may authorize ingestion in PSI-2. See usable_reason().
CONSENT_BASIS = "CONSENT"

# Legal review status (who decided the lawful basis is a separate governance step).
LEGAL_PENDING = "PENDING_LEGAL_REVIEW"
LEGAL_APPROVED = "APPROVED"

# Stored evidence status. EXPIRED is derived at read time, never stored.
PENDING = "PENDING"
ACTIVE = "ACTIVE"
REVOKED = "REVOKED"
EXPIRED = "EXPIRED"


class EvidenceRuleError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class EvidenceState:
    purpose: str
    lawful_basis: str
    legal_review_status: str
    legal_review_ref: str | None
    notice_version: str
    collection_method: str
    collected_at: datetime
    valid_until: datetime | None
    status: str
    recorded_by: str | None


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def validate_new(*, purpose, lawful_basis, notice_version, collection_method, collected_at, valid_until) -> None:
    if purpose not in ALLOWED_PURPOSES:
        raise EvidenceRuleError("purpose_not_allowlisted")
    if lawful_basis not in LAWFUL_BASES:
        raise EvidenceRuleError("lawful_basis_unknown")
    if collection_method not in COLLECTION_METHODS:
        raise EvidenceRuleError("collection_method_unknown")
    if not isinstance(notice_version, str) or not 1 <= len(notice_version) <= 40:
        raise EvidenceRuleError("notice_missing")
    if collected_at is None:
        raise EvidenceRuleError("collected_at_missing")
    if valid_until is not None and _utc(valid_until) <= _utc(collected_at):
        raise EvidenceRuleError("valid_until_before_collection")


def can_approve(state: EvidenceState, *, actor: str | None, legal_review_ref: str | None) -> None:
    if state.status != PENDING:
        raise EvidenceRuleError("not_pending")
    if not actor:
        raise EvidenceRuleError("approver_missing")
    if not legal_review_ref:
        raise EvidenceRuleError("legal_review_ref_missing")
    if actor == state.recorded_by:
        raise EvidenceRuleError("separation_of_duties")


def can_revoke(state: EvidenceState) -> None:
    if state.status == REVOKED:
        raise EvidenceRuleError("already_revoked")


def effective_status(state: EvidenceState, now: datetime) -> str:
    if state.status == REVOKED:
        return REVOKED
    if state.valid_until is not None and now >= _utc(state.valid_until):
        return EXPIRED
    return state.status


def usable_reason(state: EvidenceState, *, now: datetime, purpose: str, notice_version: str) -> str | None:
    """Returns None when the evidence may authorize this ingestion, otherwise a stable reason code.

    PSI-2 scope: only lawful_basis == CONSENT may authorize ingestion. Any other basis is refused
    fail-closed. Supporting CONTRACT / LEGITIMATE_INTEREST / LEGAL_OBLIGATION requires a separately
    approved design (Director + legal) and must not be inferred by code.
    """
    if state.lawful_basis != CONSENT_BASIS:
        return "evidence_basis_not_supported"
    status = effective_status(state, now)
    if status != ACTIVE:
        return f"evidence_{status.lower()}"
    if state.legal_review_status != LEGAL_APPROVED:
        return "evidence_legal_not_approved"
    if state.purpose != purpose:
        return "evidence_purpose_mismatch"
    if state.notice_version != notice_version:
        return "evidence_notice_mismatch"
    if _utc(state.collected_at) > now:
        return "evidence_future_dated"
    return None
