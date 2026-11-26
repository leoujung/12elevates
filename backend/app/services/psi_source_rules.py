"""PSI-1 source lifecycle and fail-closed permission rules (deterministic, no AI, no I/O).

State machine:
    DRAFT -> PENDING_REVIEW -> APPROVED -> REVOKED   (REVOKED is terminal)
    PENDING_REVIEW -> DRAFT                          (returned for correction)

Activation (-> APPROVED) is fail-closed: it requires approver, legal record reference,
and a permission profile. Missing anything -> refused, no state change.
"""
from dataclasses import dataclass

CATEGORIES = (
    "INBOUND_LEADS",
    "REFERRAL_NETWORK",
    "EVENTS_COMMUNITIES",
    "AUTHORIZED_BUSINESS_PARTNERSHIPS",
    "BUSINESS_DIRECTORIES_PUBLIC_SOURCES",
    "ADVERTISING_PLATFORMS",
)

DRAFT = "DRAFT"
PENDING_REVIEW = "PENDING_REVIEW"
APPROVED = "APPROVED"
REVOKED = "REVOKED"
STATUSES = (DRAFT, PENDING_REVIEW, APPROVED, REVOKED)

_TRANSITIONS = {
    DRAFT: {PENDING_REVIEW},
    PENDING_REVIEW: {APPROVED, DRAFT},
    APPROVED: {REVOKED},
    REVOKED: set(),
}


class SourceRuleError(Exception):
    """Raised when a source operation is refused. Refusals are also audited by the caller."""


@dataclass(frozen=True)
class SourceState:
    category: str
    status: str
    owner_member_id: str | None
    approved_by: str | None
    legal_record_ref: str | None
    has_permission_profile: bool


def validate_category(category: str) -> str:
    if category not in CATEGORIES:
        raise SourceRuleError(f"unknown category: {category!r}")
    return category


def can_transition(current: str, target: str) -> bool:
    return target in _TRANSITIONS.get(current, set())


def check_transition(state: SourceState, target: str, actor_member_id: str | None) -> None:
    """Raises SourceRuleError if the transition is not allowed. Pure function."""
    if target not in STATUSES:
        raise SourceRuleError(f"unknown status: {target!r}")
    if not can_transition(state.status, target):
        raise SourceRuleError(f"transition {state.status} -> {target} not allowed")
    if target == APPROVED:
        if not actor_member_id:
            raise SourceRuleError("approval requires an approver")
        if not state.legal_record_ref:
            raise SourceRuleError("approval requires legal_record_ref")
        if not state.has_permission_profile:
            raise SourceRuleError("approval requires a source permission profile")
        if actor_member_id == state.owner_member_id:
            raise SourceRuleError("owner cannot approve own source (separation of duties)")


def can_ingest(state: SourceState) -> bool:
    """Fail-closed: only APPROVED sources may accept ingestion. Revoked stops new ingestion."""
    return state.status == APPROVED


def can_member_view(state: SourceState, member_id: str) -> bool:
    """Member isolation: a member sees only their own sources (never central or others')."""
    return state.owner_member_id is not None and state.owner_member_id == member_id
