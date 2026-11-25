"""PSI-2 hardening: permission evidence persistence and audited lifecycle (record, approve, revoke).

Every action is audited with reason codes only (no personal data, no evidence payloads).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.psi_evidence import PspPermissionEvidence
from app.models.psi_source import PspSource, PspSourceAuditEvent
from app.services.psi_evidence_rules import (
    ACTIVE, LEGAL_APPROVED, PENDING, REVOKED, EvidenceRuleError, EvidenceState,
    can_approve, can_revoke, validate_new,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(db: Session, *, source_id, actor, action, outcome, detail=None) -> None:
    db.add(PspSourceAuditEvent(source_id=source_id, actor_member_id=actor, action=action,
                               outcome=outcome, detail=(detail or "")[:300] or None, at=_now()))


def state_of(row: PspPermissionEvidence) -> EvidenceState:
    return EvidenceState(
        purpose=row.purpose, lawful_basis=row.lawful_basis,
        legal_review_status=row.legal_review_status, legal_review_ref=row.legal_review_ref,
        notice_version=row.notice_version, collection_method=row.collection_method,
        collected_at=row.collected_at, valid_until=row.valid_until,
        status=row.status, recorded_by=row.recorded_by,
    )


def record_evidence(db: Session, *, actor: str, source_id: str, purpose: str, lawful_basis: str,
                    notice_version: str, collection_method: str, collected_at: datetime,
                    valid_until: datetime | None = None, evidence_id: str | None = None) -> PspPermissionEvidence:
    if db.get(PspSource, source_id) is None:
        _audit(db, source_id=source_id, actor=actor, action="evidence.record", outcome="REFUSED",
               detail="source_not_found")
        db.commit()
        raise EvidenceRuleError("source_not_found")
    try:
        validate_new(purpose=purpose, lawful_basis=lawful_basis, notice_version=notice_version,
                     collection_method=collection_method, collected_at=collected_at, valid_until=valid_until)
    except EvidenceRuleError as e:
        _audit(db, source_id=source_id, actor=actor, action="evidence.record", outcome="REFUSED", detail=e.reason)
        db.commit()
        raise
    row = PspPermissionEvidence(
        id=evidence_id or str(uuid.uuid4()), source_id=source_id, purpose=purpose,
        lawful_basis=lawful_basis, legal_review_status="PENDING_LEGAL_REVIEW",
        notice_version=notice_version, collection_method=collection_method,
        collected_at=collected_at, valid_until=valid_until, status=PENDING,
        recorded_by=actor, created_at=_now(),
    )
    db.add(row)
    db.flush()
    _audit(db, source_id=source_id, actor=actor, action="evidence.record", outcome="ALLOWED", detail=lawful_basis)
    db.commit()
    return row


def approve_evidence(db: Session, *, actor: str | None, evidence_id: str, legal_review_ref: str | None) -> PspPermissionEvidence:
    row = db.get(PspPermissionEvidence, evidence_id)
    if row is None:
        raise EvidenceRuleError("evidence_not_found")
    try:
        can_approve(state_of(row), actor=actor, legal_review_ref=legal_review_ref)
    except EvidenceRuleError as e:
        _audit(db, source_id=row.source_id, actor=actor, action="evidence.approve", outcome="REFUSED", detail=e.reason)
        db.commit()
        raise
    row.legal_review_status = LEGAL_APPROVED
    row.legal_review_ref = legal_review_ref
    row.status = ACTIVE
    _audit(db, source_id=row.source_id, actor=actor, action="evidence.approve", outcome="ALLOWED")
    db.commit()
    return row


def revoke_evidence(db: Session, *, actor: str | None, evidence_id: str, reason_code: str) -> PspPermissionEvidence:
    row = db.get(PspPermissionEvidence, evidence_id)
    if row is None:
        raise EvidenceRuleError("evidence_not_found")
    try:
        can_revoke(state_of(row))
    except EvidenceRuleError as e:
        _audit(db, source_id=row.source_id, actor=actor, action="evidence.revoke", outcome="REFUSED", detail=e.reason)
        db.commit()
        raise
    row.status = REVOKED
    row.revoked_at = _now()
    _audit(db, source_id=row.source_id, actor=actor, action="evidence.revoke", outcome="ALLOWED", detail=reason_code)
    db.commit()
    return row
