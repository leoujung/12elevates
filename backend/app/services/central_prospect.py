"""Central Prospect inbound persistence (E1.2). STAGING branch only.

PostgreSQL (cp_* tables) is the source of truth. CRM sync is a queued export, never the primary store.
Owns: schema validation, event-type validation, consent-purpose validation, identifier normalization,
suppression check, idempotency, tenant-scoped dedup, transactional persistence, consent ledger, provenance,
and sync-queue creation AFTER a successful database commit.
n8n owns orchestration only; it must not re-implement these rules.
"""
import re
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app.services import suppression as sup

EVENT_TYPES = {"LEAD_SUBMITTED", "ASSESSMENT_COMPLETED", "WEBINAR_REGISTERED", "PARTNER_INQUIRY"}

# Which consent purpose each event REQUIRES (granted must be true) and which it may OPTIONALLY record.
# Do not assume one purpose covers all events.
REQUIRED_PURPOSE = {
    "LEAD_SUBMITTED": "registration_processing",
    "ASSESSMENT_COMPLETED": "assessment_processing",
    "WEBINAR_REGISTERED": "registration_processing",
    "PARTNER_INQUIRY": "partner_contact",
}
OPTIONAL_PURPOSES = {"marketing_optional"}
ALL_PURPOSES = {"registration_processing", "assessment_processing", "partner_contact", "marketing_optional"}

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ID_MAX = 100


class InboundError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code


def normalize_phone(raw):
    """Digits only, Indonesian country code 62. Returns None if not a plausible number."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    if not digits.startswith("62") or not (10 <= len(digits) <= 15):
        return None
    return digits


def normalize_email(raw):
    clean = (raw or "").strip().lower()
    return clean if _EMAIL.match(clean) else None


def _ref(value):
    """Optional business reference id. Stored only as an opaque id, never as PII."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value.strip()) > 100:
        raise InboundError("INVALID_REFERENCE_ID")
    return value.strip() or None


def validate_event(event):
    """Pure validation. Raises InboundError with a stable code. Returns normalized fields."""
    if not isinstance(event, dict):
        raise InboundError("INVALID_PAYLOAD", "payload must be an object")
    etype = event.get("event_type")
    if etype not in EVENT_TYPES:
        raise InboundError("UNKNOWN_EVENT_TYPE", f"unsupported event_type")
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not event_id.strip() or len(event_id) > _ID_MAX:
        raise InboundError("INVALID_EVENT_ID")
    member_id = event.get("member_id")
    if not isinstance(member_id, str) or not member_id.strip() or len(member_id) > 64:
        raise InboundError("INVALID_MEMBER")

    lead = event.get("lead") or {}
    phone = normalize_phone(lead.get("whatsapp")) if lead.get("whatsapp") else None
    email = normalize_email(lead.get("email")) if lead.get("email") else None
    if not phone and not email:
        raise InboundError("NO_VALID_IDENTIFIER", "need a valid whatsapp or email")

    consents = event.get("consents") or {}
    if not isinstance(consents, dict):
        raise InboundError("INVALID_CONSENTS")
    unknown = set(consents) - ALL_PURPOSES
    if unknown:
        raise InboundError("UNKNOWN_CONSENT_PURPOSE")
    for p, v in consents.items():
        if not isinstance(v, bool):
            raise InboundError("INVALID_CONSENT_VALUE")
    required = REQUIRED_PURPOSE[etype]
    if consents.get(required) is not True:
        raise InboundError("REJECTED_CONSENT", f"required purpose {required} not granted")

    notice_version = event.get("notice_version")
    if not isinstance(notice_version, str) or not notice_version.strip() or len(notice_version) > 40:
        raise InboundError("INVALID_NOTICE_VERSION")

    return {
        "event_id": event_id.strip(),
        "event_type": etype,
        "member_id": member_id.strip(),
        "phone": phone,
        "email": email,
        "consents": consents,
        "notice_version": notice_version.strip(),
        "source": str((event.get("attribution") or {}).get("source") or "direct")[:100],
        "campaign": (str((event.get("attribution") or {}).get("campaign") or "")[:100]) or None,
        "referral_code": (str((event.get("attribution") or {}).get("referral_code") or "")[:50]) or None,
        "source_page": (str((event.get("attribution") or {}).get("landing_page") or "")[:200]) or None,
        "name": (str(lead.get("name") or "").strip()[:200]) or None,
        "registration_id": _ref(event.get("registration_id")),
        "assessment_id": _ref(event.get("assessment_id")),
    }


def _find_prospect_id(db, member_id, identifiers):
    """Tenant-scoped dedup: an identifier that already exists for THIS member resolves to its prospect."""
    for kind, value in identifiers:
        row = db.execute(
            text("select prospect_id from cp_prospect_identifiers "
                 "where member_id = :m and kind = :k and value_normalized = :v"),
            {"m": member_id, "k": kind, "v": value},
        ).first()
        if row:
            return str(row[0])
    return None


def persist_inbound(db, raw_event, *, now=None):
    """Validate, check suppression, dedupe, and persist in ONE transaction. Returns a result dict.

    Result status values:
      PERSISTED, DUPLICATE_IGNORED, SUPPRESSED_NO_ACTION, REJECTED_* (validation/consent, nothing written).
    Failure of the database raises; the caller must NOT report success and must NOT enqueue CRM sync.
    """
    now = now or datetime.now(timezone.utc)
    ev = validate_event(raw_event)  # raises InboundError before any write

    # Suppression: a suppressed identity is never persisted as an active prospect.
    for value in [ev["phone"], ev["email"]]:
        if value and sup.is_suppressed(db, value):
            return {"status": "SUPPRESSED_NO_ACTION", "event_id": ev["event_id"]}

    try:
        # Idempotency: same event_id already processed -> no new rows.
        seen = db.execute(text("select status from cp_inbound_events where event_id = :e and member_id = :m"),
                          {"e": ev["event_id"], "m": ev["member_id"]}).first()
        if seen:
            return {"status": "DUPLICATE_IGNORED", "event_id": ev["event_id"]}

        # 3) registration_id / assessment_id dedup per tenant (stored as opaque ref in payload_minimal)
        for ref_kind in ("registration_id", "assessment_id"):
            if ev.get(ref_kind):
                dup = db.execute(
                    text("select 1 from cp_inbound_events where member_id = :m and payload_minimal like :pat"),
                    {"m": ev["member_id"], "pat": '%"' + ref_kind + '": "' + ev[ref_kind] + '"%'},
                ).first()
                if dup:
                    return {"status": "DUPLICATE_IGNORED", "event_id": ev["event_id"]}

        identifiers = [("phone", ev["phone"])] if ev["phone"] else []
        if ev["email"]:
            identifiers.append(("email", ev["email"]))

        prospect_id = _find_prospect_id(db, ev["member_id"], identifiers)
        if prospect_id is None:
            prospect_id = str(uuid.uuid4())
            db.execute(
                text("insert into cp_prospects (prospect_id, member_id, prospect_type, display_name, status, created_at, updated_at) "
                     "values (:p, :m, :t, :n, 'active', :now, :now)"),
                {"p": prospect_id, "m": ev["member_id"], "t": _prospect_type(ev["event_type"]),
                 "n": ev["name"], "now": now},
            )
            for kind, value in identifiers:
                db.execute(
                    text("insert into cp_prospect_identifiers (id, prospect_id, member_id, kind, value_normalized, created_at) "
                         "values (:i, :p, :m, :k, :v, :now)"),
                    {"i": str(uuid.uuid4()), "p": prospect_id, "m": ev["member_id"], "k": kind, "v": value, "now": now},
                )

        refs = {k: ev[k] for k in ("registration_id", "assessment_id") if ev.get(k)}
        db.execute(
            text("insert into cp_inbound_events (event_id, event_type, member_id, prospect_id, status, payload_minimal, received_at) "
                 "values (:e, :t, :m, :p, 'persisted', :refs, :now)"),
            {"e": ev["event_id"], "t": ev["event_type"], "m": ev["member_id"], "p": prospect_id,
             "refs": json.dumps(refs, sort_keys=True), "now": now},
        )

        for purpose, granted in ev["consents"].items():
            db.execute(
                text("insert into cp_consent_ledger (prospect_id, member_id, purpose, granted, notice_version, source, event_id, recorded_at) "
                     "values (:p, :m, :pu, :g, :nv, :s, :e, :now)"),
                {"p": prospect_id, "m": ev["member_id"], "pu": purpose, "g": granted,
                 "nv": ev["notice_version"], "s": ev["source"], "e": ev["event_id"], "now": now},
            )

        if not db.execute(text("select 1 from cp_provenance where prospect_id = :p"), {"p": prospect_id}).first():
            db.execute(
                text("insert into cp_provenance (prospect_id, member_id, source_page, campaign, referral_code, first_event_id, first_seen_at) "
                     "values (:p, :mm, :sp, :c, :r, :e, :now)"),
                {"p": prospect_id, "mm": ev["member_id"], "sp": ev["source_page"], "c": ev["campaign"], "r": ev["referral_code"],
                 "e": ev["event_id"], "now": now},
            )

        # CRM export is queued in the SAME transaction: it exists only if the DB rows exist.
        db.execute(
            text("insert into cp_sync_queue (prospect_id, member_id, event_id, destination, idempotency_key, status, attempts, next_attempt_at, created_at, updated_at) "
                 "values (:p, :mm, :e, 'google_sheets_staging', :k, 'pending', 0, :now, :now, :now)"),
            {"p": prospect_id, "mm": ev["member_id"], "e": ev["event_id"], "k": f"sheets:{ev['member_id']}:{ev['event_id']}", "now": now},
        )

        db.execute(
            text("insert into cp_audit_log (member_id, actor, action, target_id, reason, at) "
                 "values (:m, 'inbound', 'INBOUND_PERSISTED', :t, :r, :now)"),
            {"m": ev["member_id"], "t": ev["event_id"], "r": ev["event_type"], "now": now},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"status": "PERSISTED", "event_id": ev["event_id"], "prospect_id": prospect_id}


def _prospect_type(event_type):
    return {"PARTNER_INQUIRY": "partner", "LEAD_SUBMITTED": "lead"}.get(event_type, "customer")
