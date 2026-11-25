"""PSI-2 shared ingestion engine (hardened). Deterministic, no LLM, no AI provider dependency.

Transaction design:
  Phase A  validate. Refusals are committed as REJECTED audit only (no prospect written).
  Phase B  commit a RECEIVED claim on (source_id, event_id). This is the single claim on the event.
  Phase C  ONE transaction: prospect + consent + provenance + ledger=ACCEPTED + audit. All or nothing.
           A failure in C rolls back everything and marks the claim RECONCILE.

RECEIVED or RECONCILE is NEVER retried automatically: the prospect may or may not exist.
Reason codes only in audit and ledger. No personal data, no secret values.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.core import Prospect
from app.models.psi_evidence import PspPermissionEvidence
from app.models.psi_ingest import PspIngestionEvent, PspProspectProvenance
from app.models.psi_source import PspSource, PspSourceAuditEvent, PspSourcePermissionProfile
from app.services import psi_evidence_rules as ev_rules
from app.services.prospects import ingest_prospect
from app.services.psi_connector import SourceConnector
from app.services.psi_ingest_rules import (
    ALLOWED_FIELDS,
    ALLOWED_PURPOSES,
    IngestRefused,
    parse_scope,
    payload_hash,
    verify_with_keys,
)
from app.services.psi_secret import load_verification_keys
from app.services.psi_source import source_state
from app.services.psi_source_rules import can_ingest

ACCEPTED = "ACCEPTED"
DUPLICATE = "DUPLICATE"
REJECTED = "REJECTED"
RECONCILE = "RECONCILE"
IN_PROGRESS = "IN_PROGRESS"  # duplicate arrived while the first claim is still in Phase C
# A RECEIVED claim younger than this is treated as in-flight; older is treated as a crashed writer.
IN_FLIGHT_WINDOW_S = 60


@dataclass(frozen=True)
class IngestResult:
    status: str
    reason: str | None = None
    prospect_id: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _from_epoch(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _audit(db: Session, *, source_id: str | None, action: str, outcome: str, detail: str | None = None) -> None:
    db.add(PspSourceAuditEvent(source_id=source_id, actor_member_id=None, action=action, outcome=outcome,
                               detail=(detail or "")[:300] or None, at=_now()))


def _reject(db: Session, *, source_id: str | None, reason: str) -> IngestResult:
    _audit(db, source_id=source_id, action="ingest.rejected", outcome="REFUSED", detail=reason)
    db.commit()
    return IngestResult(REJECTED, reason)


def _decode(raw_body: bytes) -> dict:
    try:
        body = json.loads(raw_body)
    except (UnicodeDecodeError, ValueError):
        raise IngestRefused("validation:body")
    if not isinstance(body, dict):
        raise IngestRefused("validation:body")
    return body


def _state_of(row: PspPermissionEvidence) -> ev_rules.EvidenceState:
    return ev_rules.EvidenceState(
        purpose=row.purpose, lawful_basis=row.lawful_basis,
        legal_review_status=row.legal_review_status, legal_review_ref=row.legal_review_ref,
        notice_version=row.notice_version, collection_method=row.collection_method,
        collected_at=row.collected_at, valid_until=row.valid_until,
        status=row.status, recorded_by=row.recorded_by,
    )


def receive_webhook(db: Session, *, source_id: str, connector: SourceConnector, resolve_secret,
                    timestamp: str, signature: str | None, raw_body: bytes, now_epoch: int) -> IngestResult:
    src = db.get(PspSource, source_id)
    if src is None:
        return _reject(db, source_id=source_id, reason="source_not_found")
    if not can_ingest(source_state(db, src)):
        return _reject(db, source_id=src.id, reason="source_not_approved")
    if src.owner_member_id is None:
        return _reject(db, source_id=src.id, reason="central_source_requires_distribution")
    if connector.category != src.category:
        return _reject(db, source_id=src.id, reason="category_mismatch")

    now = _from_epoch(now_epoch)
    # Phase A: validation. Nothing is written to prospects here.
    try:
        keys = load_verification_keys(db, source_id=src.id, now=now, resolve=resolve_secret)
        verify_with_keys(keys, timestamp=timestamp, raw_body=raw_body, signature=signature, now_epoch=now_epoch)
        body = _decode(raw_body)
        event = connector.parse(body)
        prof = db.execute(select(PspSourcePermissionProfile).where(
            PspSourcePermissionProfile.source_id == src.id)).scalar_one_or_none()
        if prof is None:
            raise IngestRefused("no_profile")
        if prof.expires_at is not None and _as_utc(prof.expires_at) < now:
            raise IngestRefused("profile_expired")
        if event.purpose not in parse_scope(prof.permitted_purposes, ALLOWED_PURPOSES):
            raise IngestRefused("purpose_not_permitted")
        for field in event.fields_present:
            if field not in parse_scope(prof.permitted_fields, ALLOWED_FIELDS):
                raise IngestRefused(f"unpermitted_field:{field}")
        if not event.consent_granted:
            raise IngestRefused("consent_missing")
        if not event.notice_version:
            raise IngestRefused("notice_missing")
        evidence = db.get(PspPermissionEvidence, event.evidence_ref)
        if evidence is None or evidence.source_id != src.id:
            raise IngestRefused("evidence_not_found")
        reason = ev_rules.usable_reason(_state_of(evidence), now=now, purpose=event.purpose,
                                        notice_version=event.notice_version)
        if reason is not None:
            raise IngestRefused(reason)
    except IngestRefused as refusal:
        return _reject(db, source_id=src.id, reason=refusal.reason)

    # Phase B: claim the event. Committed alone so a crash later is visible as RECEIVED.
    phash = payload_hash(body)
    claim = PspIngestionEvent(source_id=src.id, idempotency_key=event.event_id, payload_hash=phash,
                              status="RECEIVED", received_at=now)
    db.add(claim)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _resolve_existing(db, src, event.event_id, phash)
    claim_id = claim.id

    # Phase C: one atomic transaction via the canonical prospect service (commit=False).
    # The consent record is derived from the APPROVED evidence (basis CONSENT), never from the raw payload.
    # Defence in depth: refuse here too if the basis is not CONSENT (should already be refused in Phase A).
    if evidence.lawful_basis != ev_rules.CONSENT_BASIS:
        _mark_reconcile(db, claim_id, src.id)
        return IngestResult(RECONCILE, "evidence_basis_not_supported")
    try:
        prospect = ingest_prospect(
            db, owner_member_id=src.owner_member_id, name=event.name, source=src.category,
            consent_purpose=evidence.purpose, consent_granted=True,
            whatsapp=event.whatsapp, email=event.email, commit=False,
        )
        db.add(PspProspectProvenance(prospect_id=prospect.id, source_id=src.id, ingestion_event_id=claim_id,
                                     category=src.category, collected_at=now,
                                     notice_version=event.notice_version, purpose=event.purpose,
                                     evidence_id=evidence.id, lawful_basis=evidence.lawful_basis))
        row = db.get(PspIngestionEvent, claim_id)
        if row is None:
            raise RuntimeError("claim vanished inside transaction")
        row.status = "ACCEPTED"
        row.prospect_id = prospect.id
        _audit(db, source_id=src.id, action="ingest.accepted", outcome="ALLOWED", detail=src.category)
        db.commit()
    except Exception:
        db.rollback()
        _mark_reconcile(db, claim_id, src.id)
        return IngestResult(RECONCILE, "outcome_unknown")
    return IngestResult(ACCEPTED, None, prospect.id)


def _mark_reconcile(db: Session, claim_id: str, source_id: str) -> None:
    row = db.get(PspIngestionEvent, claim_id)
    if row is not None and row.status == "RECEIVED":
        row.status = "RECONCILE"
        row.reason = "outcome_unknown"
    _audit(db, source_id=source_id, action="ingest.reconcile", outcome="REFUSED", detail="outcome_unknown")
    db.commit()


def _resolve_existing(db: Session, src: PspSource, event_id: str, phash: str) -> IngestResult:
    existing = db.execute(select(PspIngestionEvent).where(
        PspIngestionEvent.source_id == src.id, PspIngestionEvent.idempotency_key == event_id)).scalar_one()
    if existing.payload_hash != phash:
        return _reject(db, source_id=src.id, reason="idempotency_conflict")
    if existing.status == "ACCEPTED":
        _audit(db, source_id=src.id, action="ingest.duplicate", outcome="ALLOWED", detail="no-op")
        db.commit()
        return IngestResult(DUPLICATE, None, existing.prospect_id)
    if existing.status == "REJECTED":
        return IngestResult(REJECTED, existing.reason)
    if existing.status == "RECEIVED":
        # Fresh claim = another worker is plausibly still in Phase C -> in-flight, not an unknown outcome.
        # Stale claim (older than IN_FLIGHT_WINDOW_S) = the writer most likely crashed -> RECONCILE.
        # Neither path retries automatically.
        age = (_now() - _as_utc(existing.received_at)).total_seconds()
        if age <= IN_FLIGHT_WINDOW_S:
            return IngestResult(IN_PROGRESS, "claim_in_flight")
        return IngestResult(RECONCILE, "outcome_unknown")
    # RECONCILE: outcome unknown. Never retried automatically; requires operator reconciliation.
    return IngestResult(RECONCILE, "outcome_unknown")
