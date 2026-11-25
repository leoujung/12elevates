"""PSI-3 reconciliation tests. Synthetic data only. Runs on SQLite and PostgreSQL (same fixtures)."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models.core import ConsentRecord, Prospect, AuditLog
from app.models.psi_ingest import PspIngestionEvent, PspProspectProvenance
from app.models.psi_source import PspSourceAuditEvent
from app.services import psi_reconcile as rec
from app.services.psi_ingest import IN_FLIGHT_WINDOW_S
from app.services.psi_ingest_rules import payload_hash


import pytest as _pt
from sqlalchemy import create_engine as _ce
from sqlalchemy.orm import sessionmaker as _sm
from app.models.core import Base as _Base, Member as _Member, Organization as _Org


@_pt.fixture()
def db():
    """Synthetic SQLite fixture local to PSI-3 tests (no Gold Pool conftest dependency)."""
    engine = _ce("sqlite:///:memory:")
    _Base.metadata.create_all(engine)
    s = _sm(bind=engine)()
    org = _Org(name="synthetic org")
    s.add(org)
    s.flush()
    s.add(_Member(id="member-andi", organization_id=org.id, email="andi@example.test", display_name="Andi"))
    s.commit()
    yield s
    s.close()
from tests.test_psi_hardening import (ANDI, _body, _evidence, _key, _source, _post, ACCEPTED, RECONCILE as ING_RECONCILE)

OLD = timedelta(seconds=IN_FLIGHT_WINDOW_S + 300)


def _claim(db, src, *, status, age, key="evt_recon_01", ph="a" * 64, prospect_id=None, reason=None):
    now = rec._now()
    ev = PspIngestionEvent(source_id=src.id, idempotency_key=key, payload_hash=ph, status=status,
                           reason=reason, prospect_id=prospect_id, received_at=now - age)
    db.add(ev)
    db.commit()
    return ev


def _provenance_for(db, src, ev, prospect_id):
    db.add(PspProspectProvenance(prospect_id=prospect_id, source_id=src.id, ingestion_event_id=ev.id,
                                 category=src.category, collected_at=rec._now(), notice_version="NOTICE-SYN-1",
                                 purpose="INQUIRY_RESPONSE", evidence_id=None, lawful_basis="CONSENT"))
    db.commit()


def _prospect(db):
    p = Prospect(owner_member_id=ANDI, name="Synthetic Recon", source="INBOUND_LEADS")
    db.add(p)
    db.commit()
    return p


# ---- listing ----

def test_list_excludes_fresh_in_flight_claims(db):
    src = _source(db)
    _claim(db, src, status="RECEIVED", age=timedelta(seconds=5), key="fresh01")
    stale = _claim(db, src, status="RECEIVED", age=OLD, key="stale01")
    ids = [e.id for e in rec.list_stuck(db)]
    assert stale.id in ids
    assert all(e.idempotency_key != "fresh01" for e in rec.list_stuck(db))


def test_list_includes_reconcile_rows(db):
    src = _source(db)
    ev = _claim(db, src, status="RECONCILE", age=timedelta(seconds=1), key="rc01", reason="outcome_unknown")
    assert ev.id in [e.id for e in rec.list_stuck(db)]


# ---- resolve: guards ----

def test_fresh_in_flight_claim_cannot_be_resolved(db):
    src = _source(db)
    ev = _claim(db, src, status="RECEIVED", age=timedelta(seconds=5), key="fresh02")
    with pytest.raises(rec.ReconcileRefused) as e:
        rec.resolve(db, event_id=ev.id, decision=rec.CLOSE_NO_PROSPECT, operator="op1")
    assert e.value.reason == "claim_in_flight"
    db.refresh(ev)
    assert ev.status == "RECEIVED"


def test_unknown_decision_refused(db):
    src = _source(db)
    ev = _claim(db, src, status="RECONCILE", age=timedelta(0), key="bad01")
    with pytest.raises(rec.ReconcileRefused) as e:
        rec.resolve(db, event_id=ev.id, decision="RETRY_INGEST", operator="op1")
    assert e.value.reason == "unknown_decision"


def test_final_status_cannot_be_changed(db):
    src = _source(db)
    ev = _claim(db, src, status="ACCEPTED", age=OLD, key="final01")
    with pytest.raises(rec.ReconcileRefused) as e:
        rec.resolve(db, event_id=ev.id, decision=rec.CLOSE_NO_PROSPECT, operator="op1")
    assert e.value.reason == "already_final"


def test_rejected_is_also_final(db):
    src = _source(db)
    ev = _claim(db, src, status="REJECTED", age=OLD, key="final02", reason="consent_missing")
    with pytest.raises(rec.ReconcileRefused):
        rec.resolve(db, event_id=ev.id, decision=rec.ACCEPT_LINKED, operator="op1")


def test_missing_event_refused(db):
    with pytest.raises(rec.ReconcileRefused) as e:
        rec.resolve(db, event_id="does-not-exist", decision=rec.CLOSE_NO_PROSPECT, operator="op1")
    assert e.value.reason == "event_not_found"


# ---- resolve: decisions ----

def test_accept_linked_requires_provenance(db):
    src = _source(db)
    ev = _claim(db, src, status="RECONCILE", age=OLD, key="acc_noprov", reason="outcome_unknown")
    with pytest.raises(rec.ReconcileRefused) as e:
        rec.resolve(db, event_id=ev.id, decision=rec.ACCEPT_LINKED, operator="op1")
    assert e.value.reason == "no_provenance_for_accept"
    db.refresh(ev)
    assert ev.status == "RECONCILE" and ev.prospect_id is None


def test_accept_linked_with_provenance_becomes_accepted(db):
    src = _source(db)
    p = _prospect(db)
    ev = _claim(db, src, status="RECONCILE", age=OLD, key="acc_prov", reason="outcome_unknown")
    _provenance_for(db, src, ev, p.id)
    final = rec.resolve(db, event_id=ev.id, decision=rec.ACCEPT_LINKED, operator="op1")
    assert final == "ACCEPTED"
    db.refresh(ev)
    assert ev.status == "ACCEPTED" and ev.prospect_id == p.id and ev.reason is None


def test_close_no_prospect_refused_when_provenance_exists(db):
    src = _source(db)
    p = _prospect(db)
    ev = _claim(db, src, status="RECONCILE", age=OLD, key="close_prov", reason="outcome_unknown")
    _provenance_for(db, src, ev, p.id)
    with pytest.raises(rec.ReconcileRefused) as e:
        rec.resolve(db, event_id=ev.id, decision=rec.CLOSE_NO_PROSPECT, operator="op1")
    assert e.value.reason == "provenance_exists_cannot_close"
    db.refresh(ev)
    assert ev.status == "RECONCILE"


def test_close_no_prospect_without_provenance_becomes_rejected(db):
    src = _source(db)
    ev = _claim(db, src, status="RECONCILE", age=OLD, key="close_ok", reason="outcome_unknown")
    final = rec.resolve(db, event_id=ev.id, decision=rec.CLOSE_NO_PROSPECT, operator="op1")
    assert final == "REJECTED"
    db.refresh(ev)
    assert ev.status == "REJECTED" and ev.reason == "reconciled_no_prospect" and ev.prospect_id is None


def test_stale_received_can_be_closed(db):
    src = _source(db)
    ev = _claim(db, src, status="RECEIVED", age=OLD, key="stale_close")
    assert rec.resolve(db, event_id=ev.id, decision=rec.CLOSE_NO_PROSPECT, operator="op1") == "REJECTED"


# ---- no retry, no ingestion, no prospect writes ----

def test_resolve_never_creates_prospect_or_consent(db):
    src = _source(db)
    ev = _claim(db, src, status="RECONCILE", age=OLD, key="noprosp", reason="outcome_unknown")
    rec.resolve(db, event_id=ev.id, decision=rec.CLOSE_NO_PROSPECT, operator="op1")
    assert db.execute(select(Prospect)).scalars().all() == []
    assert db.execute(select(ConsentRecord)).scalars().all() == []


def test_resolve_does_not_call_ingestion(db, monkeypatch):
    import app.services.psi_ingest as ing
    called = []
    monkeypatch.setattr(ing, "receive_webhook", lambda *a, **k: called.append(1))
    monkeypatch.setattr(ing, "ingest_prospect", lambda *a, **k: called.append(1), raising=False)
    src = _source(db)
    ev = _claim(db, src, status="RECONCILE", age=OLD, key="noingest", reason="outcome_unknown")
    rec.resolve(db, event_id=ev.id, decision=rec.CLOSE_NO_PROSPECT, operator="op1")
    assert called == []


# ---- audit ----

def test_resolve_is_audited_without_personal_data(db):
    src = _source(db)
    ev = _claim(db, src, status="RECONCILE", age=OLD, key="audit1", reason="outcome_unknown")
    rec.resolve(db, event_id=ev.id, decision=rec.CLOSE_NO_PROSPECT, operator="op1@example.test")
    rows = db.execute(select(PspSourceAuditEvent).where(
        PspSourceAuditEvent.action == "reconcile.close_no_prospect")).scalars().all()
    assert len(rows) == 1
    detail = rows[0].detail or ""
    assert ev.id in detail
    assert "@" not in detail, "operator identifier must not leak an email address into audit"
    assert "Synthetic" not in detail and "whatsapp" not in detail.lower()


def test_refused_resolve_writes_no_audit(db):
    src = _source(db)
    ev = _claim(db, src, status="RECEIVED", age=timedelta(seconds=2), key="noaudit")
    before = len(db.execute(select(PspSourceAuditEvent)).scalars().all())
    with pytest.raises(rec.ReconcileRefused):
        rec.resolve(db, event_id=ev.id, decision=rec.CLOSE_NO_PROSPECT, operator="op1")
    after = len(db.execute(select(PspSourceAuditEvent)).scalars().all())
    assert before == after
