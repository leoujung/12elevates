"""PSI-2 hardening: webhook secret rotation and verification rules (pure, no I/O).

Rotation: PENDING -> ACTIVE (new key), previous ACTIVE -> RETIRED with a 24h verification grace.
Revocation (suspected compromise): immediate, no grace. REVOKED is terminal.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

ACTIVE = "ACTIVE"
PENDING = "PENDING"
RETIRED = "RETIRED"
REVOKED = "REVOKED"

GRACE = timedelta(hours=24)

# Rate and failure policy (enforced by the future public route; decisions are pure here).
REQUESTS_PER_MINUTE = 60
FAILURE_WINDOW_MINUTES = 5
FAILURE_ALERT_THRESHOLD = 5
FAILURE_BLOCK_THRESHOLD = 10

_KID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
# Only references are accepted. Anything that looks like a raw secret value is refused.
_REF_RE = re.compile(r"^env:[A-Z][A-Z0-9_]{2,63}$|^vault:[a-z0-9][a-z0-9/_-]{2,119}$")


class SecretRuleError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SecretRow:
    kid: str
    status: str
    secret_ref: str
    retired_at: datetime | None


def validate_kid(kid: str) -> None:
    if not isinstance(kid, str) or not _KID_RE.match(kid):
        raise SecretRuleError("kid_invalid")


def validate_secret_ref(ref: str) -> None:
    if not isinstance(ref, str) or not _REF_RE.match(ref):
        raise SecretRuleError("secret_ref_invalid")


def check_begin(rows: list[SecretRow], kid: str, ref: str) -> None:
    validate_kid(kid)
    validate_secret_ref(ref)
    if any(r.kid == kid for r in rows):
        raise SecretRuleError("kid_exists")
    if any(r.status == PENDING for r in rows):
        raise SecretRuleError("rotation_in_progress")


def plan_activation(rows: list[SecretRow], kid: str, now: datetime) -> dict[str, tuple[str, datetime | None]]:
    """Returns {kid: (new_status, retired_at)} for every row whose status changes."""
    target = next((r for r in rows if r.kid == kid), None)
    if target is None:
        raise SecretRuleError("kid_not_found")
    if target.status != PENDING:
        raise SecretRuleError("not_pending")
    changes: dict[str, tuple[str, datetime | None]] = {kid: (ACTIVE, None)}
    for r in rows:
        if r.status == ACTIVE and r.kid != kid:
            changes[r.kid] = (RETIRED, now)
    return changes


def plan_revoke(rows: list[SecretRow], kid: str, now: datetime) -> tuple[str, datetime]:
    target = next((r for r in rows if r.kid == kid), None)
    if target is None:
        raise SecretRuleError("kid_not_found")
    if target.status == REVOKED:
        raise SecretRuleError("already_revoked")
    return REVOKED, now


def verification_kids(rows: list[SecretRow], now: datetime) -> list[SecretRow]:
    """Keys allowed to verify signatures right now. ACTIVE always; RETIRED only within grace; REVOKED never."""
    out = []
    for r in rows:
        if r.status == ACTIVE:
            out.append(r)
        elif r.status == RETIRED and r.retired_at is not None and now < r.retired_at + GRACE:
            out.append(r)
    return sorted(out, key=lambda r: (r.status != ACTIVE, r.kid))


def ingest_gate(requests_last_minute: int, failures_last_window: int) -> str:
    """Pure rate/abuse decision for a source's public endpoint: BLOCK | THROTTLE | ALLOW."""
    if failures_last_window >= FAILURE_BLOCK_THRESHOLD:
        return "BLOCK"
    if requests_last_minute > REQUESTS_PER_MINUTE:
        return "THROTTLE"
    return "ALLOW"


def should_alert(failures_last_window: int) -> bool:
    """Failed-signature monitoring: alert the operator before the block threshold is reached."""
    return failures_last_window >= FAILURE_ALERT_THRESHOLD
