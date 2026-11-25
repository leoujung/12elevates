"""PSI-2 deterministic ingestion rules (no I/O, no LLM).

Closed allowlists, input normalization, and webhook signature verification with a replay window.
"""
import hashlib
import hmac
import json
import re

# Closed allowlist of prospect fields an ingestion event may carry.
# Health, free-text needs/goals, and any other field are NOT allowed (fail-closed).
ALLOWED_FIELDS = frozenset({"name", "whatsapp", "email"})

# Closed allowlist of processing purposes an ingestion event may declare.
# Matching purposes are intentionally absent: no ingestion purpose authorizes matching,
# and follow-up consent is never matching authorization.
ALLOWED_PURPOSES = frozenset({"INQUIRY_RESPONSE", "EVENT_FOLLOW_UP", "REFERRAL_INTRODUCTION"})

SIGNATURE_TOLERANCE_SECONDS = 300
_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")


class IngestRefused(Exception):
    """Refusal carrying a stable reason code. Reason codes never contain personal data."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def parse_scope(text: str | None, allowed: frozenset) -> frozenset:
    """Profile text (comma-separated) intersected with the closed allowlist.
    A profile can narrow permissions but can never widen them beyond the allowlist."""
    if not text:
        return frozenset()
    tokens = {t.strip() for t in text.split(",") if t.strip()}
    return frozenset(tokens & allowed)


def normalize_name(value) -> str:
    if not isinstance(value, str):
        raise IngestRefused("validation:name")
    s = " ".join(value.split())
    if not 2 <= len(s) <= 200:
        raise IngestRefused("validation:name")
    return s


def normalize_whatsapp(value) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise IngestRefused("validation:whatsapp")
    digits = re.sub(r"\D", "", value)
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    if not 9 <= len(digits) <= 15:
        raise IngestRefused("validation:whatsapp")
    return digits


def normalize_email(value) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise IngestRefused("validation:email")
    s = value.strip().lower()
    if len(s) > 320 or not _EMAIL_RE.match(s):
        raise IngestRefused("validation:email")
    return s


def validate_event_id(value) -> str:
    if not isinstance(value, str) or not _EVENT_ID_RE.match(value):
        raise IngestRefused("validation:event_id")
    return value


def payload_hash(body: dict) -> str:
    """Canonical hash of the decoded body. Key order does not change the hash."""
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def verify_signature(*, secret: bytes | None, timestamp: str, raw_body: bytes,
                     signature: str | None, now_epoch: int) -> None:
    """HMAC-SHA256 over '<timestamp>.<raw body>'. Fail-closed on every branch.

    The timestamp is signed, and must be within SIGNATURE_TOLERANCE_SECONDS of now,
    so a captured request cannot be replayed later.
    """
    if not secret:
        raise IngestRefused("signature:no_secret")
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        raise IngestRefused("signature:timestamp")
    if abs(now_epoch - ts) > SIGNATURE_TOLERANCE_SECONDS:
        raise IngestRefused("signature:stale")
    expected = hmac.new(secret, f"{ts}.".encode() + raw_body, hashlib.sha256).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(expected, signature.lower()):
        raise IngestRefused("signature:mismatch")


def verify_with_keys(keys, *, timestamp: str, raw_body: bytes, signature: str | None, now_epoch: int) -> str:
    """Try each allowed key (ACTIVE, or RETIRED within grace). Returns the matching kid.

    Timestamp and staleness failures are key-independent and raise immediately.
    Fail-closed: no keys -> refused.
    """
    if not keys:
        raise IngestRefused("signature:no_secret")
    for kid, secret in keys:
        try:
            verify_signature(secret=secret, timestamp=timestamp, raw_body=raw_body,
                             signature=signature, now_epoch=now_epoch)
            return kid
        except IngestRefused as refusal:
            if refusal.reason != "signature:mismatch":
                raise
    raise IngestRefused("signature:mismatch")
