"""Pure PSI-2 ingestion rules: allowlists, normalisation, event id, payload hash, connector parsing.

Carried over from the PSI-2 baseline (7b45fc7). Engine-bound tests were superseded by
tests/test_psi_hardening.py. No database, no LLM, synthetic data only.
"""
import hashlib
import hmac
import pytest

from app.services.psi_ingest_rules import (
    ALLOWED_FIELDS, ALLOWED_PURPOSES, IngestRefused, normalize_email, normalize_name,
    normalize_whatsapp, parse_scope, payload_hash, validate_event_id, verify_signature,
)
from app.services.psi_connector import InboundFormConnector

NOW = 1_800_000_000
SECRET = b"synthetic-test-secret-not-real"

CONN = InboundFormConnector()
EVIDENCE_REF = "11111111-2222-4333-8444-555555555555"


def _body(**over):
    b = {"event_id": "evt_0000001", "purpose": "INQUIRY_RESPONSE", "consent": True,
         "notice_version": "NOTICE-SYN-1", "evidence_ref": EVIDENCE_REF,
         "lead": {"name": "Citra Synthetic", "whatsapp": "081200000001", "email": "citra@example.test"}}
    b.update(over)
    return b

def test_allowlists_are_closed_and_exact():
    assert ALLOWED_FIELDS == frozenset({"name", "whatsapp", "email"})
    assert ALLOWED_PURPOSES == frozenset({"INQUIRY_RESPONSE", "EVENT_FOLLOW_UP", "REFERRAL_INTRODUCTION"})
    # Matching and follow-up-authorization purposes must never be ingestible.
    for bad in ("MATCHING", "CUSTOMER_MATCHING", "FOLLOW_UP", "AI_MATCHING", "MARKETING"):
        assert bad not in ALLOWED_PURPOSES


def test_profile_cannot_widen_beyond_allowlist():
    assert parse_scope("name,health,ssn", ALLOWED_FIELDS) == frozenset({"name"})
    assert parse_scope("", ALLOWED_FIELDS) == frozenset()
    assert parse_scope(None, ALLOWED_FIELDS) == frozenset()


def test_normalize_whatsapp_and_email_and_name():
    assert normalize_whatsapp("0812-3456-7890") == "6281234567890"
    assert normalize_email("  Andi@Example.TEST ") == "andi@example.test"
    assert normalize_name("  Budi   Santoso ") == "Budi Santoso"
    for fn, bad in [(normalize_whatsapp, "12"), (normalize_email, "not-an-email"), (normalize_name, "A")]:
        with pytest.raises(IngestRefused):
            fn(bad)


def test_event_id_validation():
    assert validate_event_id("evt_ABC12345") == "evt_ABC12345"
    with pytest.raises(IngestRefused):
        validate_event_id("x")
    with pytest.raises(IngestRefused):
        validate_event_id("bad id with spaces!")


def _sign(body: bytes, ts: int = NOW, secret: bytes = SECRET) -> str:
    return hmac.new(secret, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


def test_signature_valid_accepted():
    body = b'{"a":1}'
    verify_signature(secret=SECRET, timestamp=str(NOW), raw_body=body, signature=_sign(body), now_epoch=NOW)


def test_signature_wrong_secret_rejected():
    body = b'{"a":1}'
    with pytest.raises(IngestRefused, match="mismatch"):
        verify_signature(secret=SECRET, timestamp=str(NOW), raw_body=body,
                         signature=_sign(body, secret=b"other"), now_epoch=NOW)


def test_signature_tampered_body_rejected():
    with pytest.raises(IngestRefused, match="mismatch"):
        verify_signature(secret=SECRET, timestamp=str(NOW), raw_body=b'{"a":2}',
                         signature=_sign(b'{"a":1}'), now_epoch=NOW)


def test_signature_replay_outside_window_rejected():
    body = b'{"a":1}'
    old = NOW - 301
    with pytest.raises(IngestRefused, match="stale"):
        verify_signature(secret=SECRET, timestamp=str(old), raw_body=body,
                         signature=_sign(body, ts=old), now_epoch=NOW)


def test_signature_fail_closed_without_secret_or_header():
    body = b"{}"
    with pytest.raises(IngestRefused, match="no_secret"):
        verify_signature(secret=None, timestamp=str(NOW), raw_body=body, signature=_sign(body), now_epoch=NOW)
    with pytest.raises(IngestRefused, match="mismatch"):
        verify_signature(secret=SECRET, timestamp=str(NOW), raw_body=body, signature=None, now_epoch=NOW)
    with pytest.raises(IngestRefused, match="timestamp"):
        verify_signature(secret=SECRET, timestamp="abc", raw_body=body, signature=_sign(body), now_epoch=NOW)


def test_payload_hash_is_canonical():
    assert payload_hash({"a": 1, "b": 2}) == payload_hash({"b": 2, "a": 1})
    assert payload_hash({"a": 1}) != payload_hash({"a": 2})


# ---------- connector ----------

def test_connector_accepts_valid_synthetic_body():
    ev = CONN.parse(_body())
    assert ev.purpose == "INQUIRY_RESPONSE" and ev.consent_granted and ev.whatsapp == "6281200000001"
    assert set(ev.fields_present) == {"name", "whatsapp", "email"}


def test_connector_rejects_unknown_top_level_and_lead_fields():
    with pytest.raises(IngestRefused, match="unknown_field"):
        CONN.parse(_body(health_notes="synthetic"))
    with pytest.raises(IngestRefused, match="unknown_field"):
        CONN.parse(_body(lead={"name": "Citra Synthetic", "medical": "x"}))


def test_connector_rejects_non_allowlisted_purpose():
    with pytest.raises(IngestRefused, match="purpose_not_allowlisted"):
        CONN.parse(_body(purpose="CUSTOMER_MATCHING"))


# ---------- DB-backed engine ----------
