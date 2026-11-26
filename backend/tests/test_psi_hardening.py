"""PSI hardening tests: permission evidence, transaction integrity, secret lifecycle, and ingestion.

Synthetic data only. SQLite in-memory. No LLM, no network, no real secret values (test secrets are
generated in-memory and never printed).
"""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import psi_source, psi_ingest, psi_evidence, psi_secret  # noqa: F401  (register tables)
from app.models.core import AuditLog, Base, ConsentRecord, Member, Organization, Prospect
from app.models.psi_evidence import PspPermissionEvidence
from app.models.psi_ingest import PspIngestionEvent, PspProspectProvenance
from app.models.psi_secret import PspSourceSecret
from app.models.psi_source import PspSource, PspSourceAuditEvent, PspSourcePermissionProfile
from app.services import psi_evidence as evsvc
from app.services import psi_ingest as ingest_mod
from app.services import psi_secret as secsvc
from app.services import psi_source as svc
from app.services.psi_connector import InboundFormConnector
from app.services.psi_evidence_rules import ACTIVE, EvidenceRuleError, LEGAL_APPROVED, REVOKED
from app.services.psi_ingest import ACCEPTED, DUPLICATE, REJECTED, RECONCILE, receive_webhook
from app.services.psi_ingest_rules import IngestRefused, payload_hash, verify_with_keys, verify_signature
from app.services.psi_secret_rules import ACTIVE as K_ACTIVE, GRACE, PENDING as K_PENDING, RETIRED, REVOKED as K_REVOKED
from app.services.psi_secret_rules import SecretRow, SecretRuleError, plan_activation, plan_revoke, verification_kids, ingest_gate
from app.services.psi_source_rules import APPROVED, PENDING_REVIEW
from app.services.psi_evidence_rules import usable_reason

NOW = 1_800_000_000
NOW_DT = datetime.fromtimestamp(NOW, tz=timezone.utc)
ANDI = "member-andi"
BUDI = "member-budi"
ADMIN = "member-admin"
LEGAL = "member-legal"
CONN = InboundFormConnector()

# Synthetic in-memory key material. Mapped through a resolver, never printed or stored in the DB.
SYN_KEYS = {"env:PSI_TEST_K1": b"synthetic-key-one-not-real", "env:PSI_TEST_K2": b"synthetic-key-two-not-real"}


def resolve(ref):
    return SYN_KEYS.get(ref)


def _sign(body: bytes, *, ts: int = NOW, key: bytes = SYN_KEYS["env:PSI_TEST_K1"]) -> str:
    return hmac.new(key, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


# ---------- secret rules (pure) ----------

def _rows(*specs):
    return [SecretRow(kid=k, status=s, secret_ref="env:PSI_TEST_K1", retired_at=r) for k, s, r in specs]


def test_secret_ref_rejects_raw_value_shapes():
    from app.services.psi_secret_rules import validate_secret_ref
    for bad in ("supersecretvalue123", "sk_live_abc", "env:lowercase", "http://x", ""):
        with pytest.raises(SecretRuleError):
            validate_secret_ref(bad)
    validate_secret_ref("env:PSI_SRC_ABC_K1")
    validate_secret_ref("vault:psi/source-abc/k1")


def test_kid_format_enforced():
    from app.services.psi_secret_rules import validate_kid
    validate_kid("k2026-11")
    for bad in ("K1", "a", "bad kid", "x" * 40):
        with pytest.raises(SecretRuleError):
            validate_kid(bad)


def test_rotation_activation_retires_previous_with_grace():
    now = NOW_DT
    rows = _rows(("k1", K_ACTIVE, None), ("k2", K_PENDING, None))
    changes = plan_activation(rows, "k2", now)
    assert changes["k2"] == (K_ACTIVE, None)
    assert changes["k1"] == (RETIRED, now)


def test_verification_keys_grace_then_expire():
    now = NOW_DT
    rows = _rows(("k2", K_ACTIVE, None), ("k1", RETIRED, now - timedelta(hours=1)))
    assert [r.kid for r in verification_kids(rows, now)] == ["k2", "k1"]          # inside grace
    later = now + GRACE + timedelta(seconds=1)
    assert [r.kid for r in verification_kids(rows, later)] == ["k2"]              # grace over


def test_revoked_key_never_verifies():
    rows = _rows(("k1", K_REVOKED, None), ("k2", K_ACTIVE, None))
    assert [r.kid for r in verification_kids(rows, NOW_DT)] == ["k2"]


def test_revoke_is_immediate_and_terminal():
    rows = _rows(("k1", K_ACTIVE, None))
    status, at = plan_revoke(rows, "k1", NOW_DT)
    assert status == K_REVOKED and at == NOW_DT
    with pytest.raises(SecretRuleError):
        plan_revoke(_rows(("k1", K_REVOKED, None)), "k1", NOW_DT)


def test_rate_and_failure_policy():
    assert ingest_gate(requests_last_minute=10, failures_last_window=0) == "ALLOW"
    assert ingest_gate(requests_last_minute=61, failures_last_window=0) == "THROTTLE"
    assert ingest_gate(requests_last_minute=1, failures_last_window=10) == "BLOCK"
    from app.services.psi_secret_rules import should_alert
    assert should_alert(5) and not should_alert(4)


def test_multi_key_verification_accepts_either_kid_and_rejects_neither():
    body = b'{"x":1}'
    keys = [("k2", SYN_KEYS["env:PSI_TEST_K2"]), ("k1", SYN_KEYS["env:PSI_TEST_K1"])]
    sig_k1 = _sign(body, key=SYN_KEYS["env:PSI_TEST_K1"])
    assert verify_with_keys(keys, timestamp=str(NOW), raw_body=body, signature=sig_k1, now_epoch=NOW) == "k1"
    with pytest.raises(IngestRefused, match="mismatch"):
        verify_with_keys(keys, timestamp=str(NOW), raw_body=body, signature="0" * 64, now_epoch=NOW)
    with pytest.raises(IngestRefused, match="no_secret"):
        verify_with_keys([], timestamp=str(NOW), raw_body=body, signature=sig_k1, now_epoch=NOW)


def test_stale_timestamp_rejected_regardless_of_key():
    body = b"{}"
    with pytest.raises(IngestRefused, match="stale"):
        verify_with_keys([("k1", SYN_KEYS["env:PSI_TEST_K1"])], timestamp=str(NOW - 999),
                         raw_body=body, signature=_sign(body, ts=NOW - 999), now_epoch=NOW)


# ---------- evidence rules (pure) ----------

def _ev(**over):
    base = dict(purpose="INQUIRY_RESPONSE", lawful_basis="CONSENT", legal_review_status=LEGAL_APPROVED,
                legal_review_ref="LR-SYN-1", notice_version="NOTICE-SYN-1", collection_method="WEB_FORM",
                collected_at=NOW_DT - timedelta(days=1), valid_until=None, status=ACTIVE, recorded_by=ADMIN)
    base.update(over)
    return ev_rules_state(**base)


def ev_rules_state(**kw):
    from app.services.psi_evidence_rules import EvidenceState
    return EvidenceState(**kw)


def test_evidence_usable_when_all_match():
    assert usable_reason(_ev(), now=NOW_DT, purpose="INQUIRY_RESPONSE",
                                        notice_version="NOTICE-SYN-1") is None


@pytest.mark.parametrize("over,reason", [
    (dict(status="PENDING"), "evidence_pending"),
    (dict(status=REVOKED), "evidence_revoked"),
    (dict(legal_review_status="PENDING_LEGAL_REVIEW"), "evidence_legal_not_approved"),
    (dict(valid_until=NOW_DT - timedelta(minutes=1)), "evidence_expired"),
    (dict(collected_at=NOW_DT + timedelta(days=1)), "evidence_future_dated"),
])
def test_evidence_refusals(over, reason):
    assert usable_reason(_ev(**over), now=NOW_DT, purpose="INQUIRY_RESPONSE",
                                        notice_version="NOTICE-SYN-1") == reason


def test_evidence_purpose_and_notice_must_match():
    assert usable_reason(_ev(), now=NOW_DT, purpose="EVENT_FOLLOW_UP",
                                        notice_version="NOTICE-SYN-1") == "evidence_purpose_mismatch"
    assert usable_reason(_ev(), now=NOW_DT, purpose="INQUIRY_RESPONSE",
                                        notice_version="NOTICE-OTHER") == "evidence_notice_mismatch"


def test_lawful_basis_is_closed_and_not_assumed_consent():
    from app.services.psi_evidence_rules import LAWFUL_BASES, validate_new, EvidenceRuleError
    assert set(LAWFUL_BASES) == {"CONSENT", "CONTRACT", "LEGITIMATE_INTEREST", "LEGAL_OBLIGATION"}
    with pytest.raises(EvidenceRuleError, match="lawful_basis_unknown"):
        validate_new(purpose="INQUIRY_RESPONSE", lawful_basis="ASSUMED", notice_version="N1",
                     collection_method="WEB_FORM", collected_at=NOW_DT, valid_until=None)


def test_separation_of_duties_on_approval():
    from app.services.psi_evidence_rules import can_approve, EvidenceRuleError
    st = _ev(status="PENDING", legal_review_status="PENDING_LEGAL_REVIEW", recorded_by=ADMIN)
    with pytest.raises(EvidenceRuleError, match="separation"):
        can_approve(st, actor=ADMIN, legal_review_ref="LR-1")
    can_approve(st, actor=LEGAL, legal_review_ref="LR-1")


def test_third_party_upload_is_not_a_collection_method():
    from app.services.psi_evidence_rules import COLLECTION_METHODS
    assert "THIRD_PARTY_UPLOAD" not in COLLECTION_METHODS
    assert "REFERRAL_SELF_SUBMISSION" in COLLECTION_METHODS


# ---------- DB fixture ----------

@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    org = Organization(name="synthetic org")
    s.add(org)
    s.flush()
    for mid, em in [(ANDI, "andi@example.test"), (BUDI, "budi@example.test"), (ADMIN, "admin@example.test"),
                    (LEGAL, "legal@example.test")]:
        s.add(Member(id=mid, organization_id=org.id, email=em, display_name=mid))
    s.commit()
    yield s
    s.close()


def _source(db, *, owner=ANDI, category="INBOUND_LEADS", fields="name,whatsapp,email",
            purposes="INQUIRY_RESPONSE,EVENT_FOLLOW_UP", approved=True, profile_expires=None):
    src = svc.create_source(db, actor=ADMIN, category=category, name="syn", owner_member_id=owner)
    svc.set_profile(db, actor=ADMIN, source_id=src.id, data_sharing_scope="NONE",
                    permitted_fields=fields, permitted_purposes=purposes, terms_ref="T-SYN")
    if profile_expires is not None:
        prof = db.execute(select(PspSourcePermissionProfile)).scalar_one()
        prof.expires_at = profile_expires
        db.commit()
    if approved:
        svc.transition(db, actor=ADMIN, source_id=src.id, target=PENDING_REVIEW)
        svc.transition(db, actor=LEGAL, source_id=src.id, target=APPROVED, legal_record_ref="LR-SRC-SYN")
    return src


def _key(db, src, kid="k1", ref="env:PSI_TEST_K1", activate=True, now=NOW_DT):
    # All rotation timestamps use the test clock so grace-period logic is deterministic.
    secsvc.begin_rotation(db, actor=ADMIN, source_id=src.id, kid=kid, secret_ref=ref, now=now)
    if activate:
        secsvc.activate_rotation(db, actor=LEGAL, source_id=src.id, kid=kid, now=now)


def _evidence(db, src, *, approve=True, purpose="INQUIRY_RESPONSE", notice="NOTICE-SYN-1",
              valid_until=None, collected_at=NOW_DT - timedelta(days=1), basis="CONSENT"):
    row = evsvc.record_evidence(db, actor=ADMIN, source_id=src.id, purpose=purpose, lawful_basis=basis,
                                notice_version=notice, collection_method="WEB_FORM",
                                collected_at=collected_at, valid_until=valid_until)
    if approve:
        evsvc.approve_evidence(db, actor=LEGAL, evidence_id=row.id, legal_review_ref="LR-EV-SYN")
    return row.id


def _body(evidence_ref, **over):
    b = {"event_id": "evt_0000001", "purpose": "INQUIRY_RESPONSE", "consent": True,
         "notice_version": "NOTICE-SYN-1", "evidence_ref": evidence_ref,
         "lead": {"name": "Citra Synthetic", "whatsapp": "081200000001", "email": "citra@example.test"}}
    b.update(over)
    return b


def _post(db, src, evidence_ref, body=None, *, raw=None, sig=None, ts=NOW, key=SYN_KEYS["env:PSI_TEST_K1"]):
    raw = raw if raw is not None else json.dumps(body if body is not None else _body(evidence_ref),
                                                 separators=(",", ":")).encode()
    signature = sig if sig is not None else _sign(raw, ts=ts, key=key)
    return receive_webhook(db, source_id=src.id, connector=CONN, resolve_secret=resolve,
                           timestamp=str(ts), signature=signature, raw_body=raw, now_epoch=NOW)


# ---------- ingestion engine: permission evidence ----------

def test_accepted_requires_active_evidence_and_records_provenance(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    r = _post(db, src, eid)
    assert r.status == ACCEPTED and r.prospect_id
    prov = db.execute(select(PspProspectProvenance)).scalar_one()
    assert prov.evidence_id == eid and prov.lawful_basis == "CONSENT" and prov.notice_version == "NOTICE-SYN-1"


def test_payload_consent_true_without_evidence_is_refused(db):
    src = _source(db)
    _key(db, src)
    r = _post(db, src, "00000000-0000-4000-8000-000000000000")
    assert r.status == REJECTED and r.reason == "evidence_not_found"
    assert db.execute(select(Prospect)).scalars().all() == []


def test_pending_evidence_refused(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src, approve=False)
    r = _post(db, src, eid)
    assert r.status == REJECTED and r.reason == "evidence_pending"


def test_revoked_evidence_stops_ingestion(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    evsvc.revoke_evidence(db, actor=ADMIN, evidence_id=eid, reason_code="WITHDRAWN")
    r = _post(db, src, eid)
    assert r.status == REJECTED and r.reason == "evidence_revoked"


def test_expired_evidence_refused(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src, valid_until=NOW_DT - timedelta(seconds=1), collected_at=NOW_DT - timedelta(days=2))
    r = _post(db, src, eid)
    assert r.status == REJECTED and r.reason == "evidence_expired"


def test_evidence_belonging_to_other_source_refused(db):
    a = _source(db, owner=ANDI)
    b = _source(db, owner=BUDI)
    _key(db, a)
    eid_b = _evidence(db, b)
    r = _post(db, a, eid_b)
    assert r.status == REJECTED and r.reason == "evidence_not_found"


def test_evidence_purpose_mismatch_refused(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src, purpose="EVENT_FOLLOW_UP")
    r = _post(db, src, eid)  # payload says INQUIRY_RESPONSE
    assert r.status == REJECTED and r.reason == "evidence_purpose_mismatch"


def test_evidence_notice_mismatch_refused(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src, notice="NOTICE-OLD")
    r = _post(db, src, eid)
    assert r.status == REJECTED and r.reason == "evidence_notice_mismatch"


def test_separation_of_duties_in_evidence_approval(db):
    src = _source(db)
    eid = _evidence(db, src, approve=False)
    with pytest.raises(EvidenceRuleError, match="separation"):
        evsvc.approve_evidence(db, actor=ADMIN, evidence_id=eid, legal_review_ref="LR-X")


def test_refused_evidence_action_is_audited_without_pii(db):
    src = _source(db)
    eid = _evidence(db, src, approve=False)
    with pytest.raises(EvidenceRuleError):
        evsvc.approve_evidence(db, actor=ADMIN, evidence_id=eid, legal_review_ref="LR-X")
    ev = db.execute(select(PspSourceAuditEvent).where(PspSourceAuditEvent.action == "evidence.approve")).scalars().all()
    assert ev and ev[-1].outcome == "REFUSED" and ev[-1].detail == "separation_of_duties"


# ---------- transaction integrity ----------

def test_replayed_identical_webhook_is_duplicate(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    first = _post(db, src, eid)
    second = _post(db, src, eid)
    assert first.status == ACCEPTED and second.status == DUPLICATE and second.prospect_id == first.prospect_id
    assert len(db.execute(select(Prospect)).scalars().all()) == 1


def test_same_event_id_different_payload_is_conflict(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    _post(db, src, eid)
    changed = _body(eid, lead={"name": "Other Synthetic", "whatsapp": "081200000001", "email": "citra@example.test"})
    r = _post(db, src, eid, changed)
    assert r.status == REJECTED and r.reason == "idempotency_conflict"


def test_atomic_failure_in_prospect_creation_leaves_no_prospect_and_flags_reconcile(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    with mock.patch.object(ingest_mod, "ingest_prospect", side_effect=RuntimeError("simulated crash")):
        r = _post(db, src, eid)
    assert r.status == RECONCILE
    assert db.execute(select(Prospect)).scalars().all() == []
    assert db.execute(select(ConsentRecord)).scalars().all() == []
    assert db.execute(select(PspProspectProvenance)).scalars().all() == []
    claim = db.execute(select(PspIngestionEvent)).scalar_one()
    assert claim.status == "RECONCILE" and claim.prospect_id is None


def test_reconcile_is_never_auto_retried(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    with mock.patch.object(ingest_mod, "ingest_prospect", side_effect=RuntimeError("simulated crash")):
        _post(db, src, eid)
    # A later, healthy delivery of the same event must NOT create a prospect.
    r = _post(db, src, eid)
    assert r.status == RECONCILE
    assert db.execute(select(Prospect)).scalars().all() == []


def test_crash_after_claim_before_outcome_is_reconcile_not_retry(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    # Simulate a process that wrote RECEIVED and died: the claim exists, status RECEIVED.
    raw = json.dumps(_body(eid), separators=(",", ":")).encode()
    from app.services import psi_ingest as _ing
    from datetime import timedelta as _td
    db.add(PspIngestionEvent(source_id=src.id, idempotency_key="evt_0000001",
                             payload_hash=payload_hash(_body(eid)), status="RECEIVED",
                             received_at=_ing._now() - _td(hours=2)))  # stale -> writer crashed
    db.commit()
    r = _post(db, src, eid)
    assert r.status == RECONCILE
    assert db.execute(select(Prospect)).scalars().all() == []


def test_no_partial_prospect_without_provenance(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    _post(db, src, eid)
    prospects = db.execute(select(Prospect)).scalars().all()
    provs = db.execute(select(PspProspectProvenance)).scalars().all()
    assert len(prospects) == len(provs) == 1


# ---------- ingestion engine: sources, signatures, isolation ----------

def test_revoked_source_stops_ingestion(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    svc.transition(db, actor=ADMIN, source_id=src.id, target="REVOKED")
    r = _post(db, src, eid)
    assert r.status == REJECTED and r.reason == "source_not_approved"


def test_unapproved_source_refused(db):
    src = _source(db, approved=False)
    _key(db, src)
    eid = _evidence(db, src)
    assert _post(db, src, eid).reason == "source_not_approved"


def test_bad_signature_refused_and_audited(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    r = _post(db, src, eid, sig="0" * 64)
    assert r.status == REJECTED and r.reason == "signature:mismatch"
    assert any(e.detail == "signature:mismatch" for e in db.execute(select(PspSourceAuditEvent)).scalars())


def test_no_active_key_fails_closed(db):
    src = _source(db)
    eid = _evidence(db, src)  # no secret rotated at all
    r = _post(db, src, eid)
    assert r.status == REJECTED and r.reason == "signature:no_secret"


def test_key_rotation_old_key_valid_in_grace_new_key_valid(db):
    src = _source(db)
    _key(db, src, kid="k1", ref="env:PSI_TEST_K1")
    eid = _evidence(db, src)
    _key(db, src, kid="k2", ref="env:PSI_TEST_K2", now=NOW_DT)  # k1 becomes RETIRED with grace
    assert _post(db, src, eid, key=SYN_KEYS["env:PSI_TEST_K1"]).status == ACCEPTED  # old key in grace
    body2 = _body(eid, event_id="evt_0000002")
    assert _post(db, src, eid, body2, key=SYN_KEYS["env:PSI_TEST_K2"]).status == ACCEPTED


def test_revoked_key_signature_rejected_immediately(db):
    src = _source(db)
    _key(db, src, kid="k1", ref="env:PSI_TEST_K1")
    eid = _evidence(db, src)
    secsvc.revoke_secret(db, actor=LEGAL, source_id=src.id, kid="k1")
    r = _post(db, src, eid, key=SYN_KEYS["env:PSI_TEST_K1"])
    assert r.status == REJECTED and r.reason == "signature:no_secret"


def test_unresolvable_secret_fails_closed_and_is_audited(db):
    src = _source(db)
    _key(db, src, kid="k1", ref="env:PSI_MISSING_KEY")
    eid = _evidence(db, src)
    r = _post(db, src, eid)
    assert r.status == REJECTED and r.reason == "signature:no_secret"
    assert any(e.action == "secret.unresolvable" for e in db.execute(select(PspSourceAuditEvent)).scalars())


def test_replayed_old_signature_is_stale(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    raw = json.dumps(_body(eid), separators=(",", ":")).encode()
    r = receive_webhook(db, source_id=src.id, connector=CONN, resolve_secret=resolve,
                        timestamp=str(NOW - 1000), signature=_sign(raw, ts=NOW - 1000),
                        raw_body=raw, now_epoch=NOW)
    assert r.status == REJECTED and r.reason == "signature:stale"


def test_cross_member_isolation(db):
    src = _source(db, owner=ANDI)
    _key(db, src)
    eid = _evidence(db, src)
    r = _post(db, src, eid)
    from app.services.prospects import get_prospect_for_member
    assert get_prospect_for_member(db, member_id=BUDI, prospect_id=r.prospect_id or "") is None
    assert get_prospect_for_member(db, member_id=ANDI, prospect_id=r.prospect_id or "") is not None


# ---------- no secret or PII in audit / ledger ----------

def test_no_secret_value_or_pii_in_audit_or_ledger(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    _post(db, src, eid, _body(eid, consent=False))           # refusal
    _post(db, src, eid)                                       # acceptance
    blob = []
    for r in db.execute(select(PspSourceAuditEvent)).scalars():
        blob += [str(r.detail), str(r.action), str(r.outcome)]
    for r in db.execute(select(PspIngestionEvent)).scalars():
        blob += [str(r.reason), str(r.status), str(r.payload_hash)]
    for r in db.execute(select(PspSourceSecret)).scalars():
        blob += [str(r.kid), str(r.secret_ref)]
    text = " ".join(blob)
    assert "citra" not in text.lower() and "@example.test" not in text
    for value in SYN_KEYS.values():
        assert value.decode() not in text
    assert "env:PSI_TEST_K1" not in " ".join(str(r.detail) for r in db.execute(select(PspSourceAuditEvent)).scalars())


def test_secret_audit_records_kid_only(db):
    src = _source(db)
    _key(db, src, kid="k1", ref="env:PSI_TEST_K1")
    details = [e.detail for e in db.execute(select(PspSourceAuditEvent).where(
        PspSourceAuditEvent.action.like("secret.%"))).scalars()]
    assert details and all((d or "").startswith("kid=") for d in details)
    assert all("PSI_TEST" not in (d or "") for d in details)


def test_legacy_audit_logs_untouched_by_psi(db):
    before = len(db.execute(select(AuditLog)).scalars().all())
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    _post(db, src, eid)
    assert len(db.execute(select(AuditLog)).scalars().all()) == before + 1  # only the one prospect.created


def test_pending_source_refused_before_any_prospect(db):
    src = _source(db, approved=False)
    _key(db, src)
    eid = _evidence(db, src)
    r = _post(db, src, eid)
    assert r.status == REJECTED and r.reason == "source_not_approved"
    assert db.execute(select(Prospect)).scalars().all() == []


def test_central_source_refused_without_distribution(db):
    src = _source(db, owner=None)
    _key(db, src)
    eid = _evidence(db, src)
    r = _post(db, src, eid)
    assert r.status == REJECTED and r.reason == "central_source_requires_distribution"


def test_category_mismatch_refused(db):
    src = _source(db, category="REFERRAL_NETWORK")
    _key(db, src)
    eid = _evidence(db, src)
    r = _post(db, src, eid)
    assert r.status == REJECTED and r.reason == "category_mismatch"


def test_expired_profile_refused(db):
    src = _source(db, profile_expires=NOW_DT - timedelta(seconds=1))
    _key(db, src)
    eid = _evidence(db, src)
    r = _post(db, src, eid)
    assert r.status == REJECTED and r.reason == "profile_expired"


def test_profile_purpose_not_permitted_refused(db):
    src = _source(db, purposes="EVENT_FOLLOW_UP")  # INQUIRY_RESPONSE not in profile
    _key(db, src)
    eid = _evidence(db, src)
    r = _post(db, src, eid)
    assert r.status == REJECTED and r.reason == "purpose_not_permitted"


def test_profile_field_not_permitted_refused(db):
    src = _source(db, fields="name,email")  # whatsapp present in payload but not permitted
    _key(db, src)
    eid = _evidence(db, src)
    r = _post(db, src, eid)
    assert r.status == REJECTED and r.reason == "unpermitted_field:whatsapp"


def test_consent_false_refused_even_with_evidence(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    r = _post(db, src, eid, _body(eid, consent=False))
    assert r.status == REJECTED and r.reason == "consent_missing"


def test_commit_false_is_not_committed_inside_service(db):
    # Contract: ingest_prospect(commit=False) must not commit. A rollback after it must remove the prospect.
    from app.services.prospects import ingest_prospect
    p = ingest_prospect(db, owner_member_id=ANDI, name="Rollback Synthetic", source="INBOUND_LEADS",
                        consent_purpose="INQUIRY_RESPONSE", consent_granted=True, commit=False)
    assert p.id is not None
    db.rollback()
    assert db.execute(select(Prospect)).scalars().all() == []
    assert db.execute(select(ConsentRecord)).scalars().all() == []
    assert db.execute(select(AuditLog).where(AuditLog.action == "prospect.created")).scalars().all() == []


def test_commit_default_still_commits(db):
    # Existing callers (routes.py, tests) use the default commit=True and must keep behaving the same.
    from app.services.prospects import ingest_prospect
    p = ingest_prospect(db, owner_member_id=ANDI, name="Default Synthetic", source="webinar",
                        consent_purpose="FOLLOW_UP", consent_granted=True)
    db.rollback()
    assert db.execute(select(Prospect).where(Prospect.id == p.id)).scalar_one_or_none() is not None


def test_service_refusal_without_consent_is_rejected_not_reconciled(db):
    # Phase A already refuses missing consent, so the service's ConsentRequired is never reached
    # as a RECONCILE. Verify the ingestion result is REJECTED with a reason code, never RECONCILE.
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    r = _post(db, src, eid, _body(eid, consent=False))
    assert r.status == REJECTED and r.reason == "consent_missing"
    assert r.status != RECONCILE


def test_rollback_after_prospect_flushed_removes_every_row(db):
    # Genuine atomicity check: the prospect IS flushed (written inside the transaction), then a later
    # step fails. Everything from Phase C must disappear, not only the prospect.
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    with mock.patch.object(ingest_mod, "PspProspectProvenance", side_effect=RuntimeError("late failure")):
        r = _post(db, src, eid)
    assert r.status == RECONCILE
    assert db.execute(select(Prospect)).scalars().all() == [], "prospect survived rollback"
    assert db.execute(select(ConsentRecord)).scalars().all() == [], "consent survived rollback"
    assert db.execute(select(AuditLog).where(AuditLog.action == "prospect.created")).scalars().all() == [], \
        "legacy audit survived rollback"
    assert db.execute(select(PspProspectProvenance)).scalars().all() == [], "provenance survived rollback"
    claim = db.execute(select(PspIngestionEvent)).scalar_one()
    assert claim.status == "RECONCILE" and claim.prospect_id is None


# ---------- Director review A: lawful basis vs consent semantics ----------

@pytest.mark.parametrize("basis", ["CONTRACT", "LEGITIMATE_INTEREST", "LEGAL_OBLIGATION"])
def test_non_consent_basis_refused_fail_closed_with_clear_reason(db, basis):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src, basis=basis)
    r = _post(db, src, eid)
    assert r.status == REJECTED and r.reason == "evidence_basis_not_supported"
    assert db.execute(select(Prospect)).scalars().all() == []
    assert db.execute(select(ConsentRecord)).scalars().all() == [], "no consent may be fabricated for non-consent basis"


def test_non_consent_basis_never_creates_consent_record_even_if_payload_says_consent(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src, basis="CONTRACT")
    r = _post(db, src, eid)  # payload consent=True is irrelevant: evidence basis governs
    assert r.status != ACCEPTED
    assert db.execute(select(ConsentRecord)).scalars().all() == []


def test_consent_for_one_purpose_does_not_authorize_another(db):
    # Evidence recorded for INQUIRY_RESPONSE must not authorize a payload declaring EVENT_FOLLOW_UP.
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src, purpose="INQUIRY_RESPONSE")
    r = _post(db, src, eid, _body(eid, purpose="EVENT_FOLLOW_UP"))
    assert r.status == REJECTED and r.reason == "evidence_purpose_mismatch"
    assert db.execute(select(ConsentRecord)).scalars().all() == []


def test_consent_record_purpose_comes_from_evidence(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src, purpose="INQUIRY_RESPONSE")
    r = _post(db, src, eid)
    assert r.status == ACCEPTED
    cr = db.execute(select(ConsentRecord)).scalar_one()
    assert cr.purpose == "INQUIRY_RESPONSE" and cr.granted is True


def test_consent_record_and_legacy_audit_not_duplicated(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    r = _post(db, src, eid)
    assert r.status == ACCEPTED
    _post(db, src, eid)  # duplicate delivery
    assert len(db.execute(select(ConsentRecord)).scalars().all()) == 1
    assert len(db.execute(select(AuditLog).where(AuditLog.action == "prospect.created")).scalars().all()) == 1


def test_expired_revoked_pending_mismatch_still_refused_after_basis_gate(db):
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src, approve=False)
    assert _post(db, src, eid).reason == "evidence_pending"


def test_in_flight_claim_is_not_reconcile(db):
    # A duplicate that finds the first claim still RECEIVED (Phase C in progress elsewhere) must be
    # IN_PROGRESS, not RECONCILE. RECONCILE means a known-failed or unknown outcome, not a live race.
    from app.services import psi_ingest as ing_mod
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    body = _body(eid)
    from app.services.psi_ingest_rules import payload_hash
    ph = payload_hash(body)
    db.add(ing_mod.PspIngestionEvent(source_id=src.id, idempotency_key=body["event_id"], payload_hash=ph,
                                     status="RECEIVED", received_at=ing_mod._now()))
    db.commit()
    res = ing_mod._resolve_existing(db, src, body["event_id"], ph)
    assert res.status == ing_mod.IN_PROGRESS
    assert res.status != ing_mod.RECONCILE
    assert db.execute(select(Prospect)).scalars().all() == []


def test_reconcile_row_still_returns_reconcile_not_duplicate(db):
    from app.services import psi_ingest as ing_mod
    from app.services.psi_ingest_rules import payload_hash
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    body = _body(eid)
    ph = payload_hash(body)
    db.add(ing_mod.PspIngestionEvent(source_id=src.id, idempotency_key=body["event_id"], payload_hash=ph,
                                     status="RECONCILE", received_at=NOW_DT, reason="outcome_unknown"))
    db.commit()
    res = ing_mod._resolve_existing(db, src, body["event_id"], ph)
    assert res.status == ing_mod.RECONCILE


def test_stale_received_claim_is_reconcile_not_in_progress(db):
    from app.services import psi_ingest as ing_mod
    from app.services.psi_ingest_rules import payload_hash
    from datetime import timedelta as _td
    src = _source(db)
    _key(db, src)
    eid = _evidence(db, src)
    body = _body(eid)
    ph = payload_hash(body)
    db.add(ing_mod.PspIngestionEvent(source_id=src.id, idempotency_key=body["event_id"], payload_hash=ph,
                                     status="RECEIVED", received_at=ing_mod._now() - _td(seconds=ing_mod.IN_FLIGHT_WINDOW_S + 30)))
    db.commit()
    res = ing_mod._resolve_existing(db, src, body["event_id"], ph)
    assert res.status == ing_mod.RECONCILE
    assert res.status != ing_mod.IN_PROGRESS
