"""PSI-1 Source Registry service: DB-backed lifecycle with audit on every allowed AND refused action.

Deterministic only. No LLM. Synthetic data only during PSI-1.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.psi_source import PspSource, PspSourceAuditEvent, PspSourcePermissionProfile
from app.services.psi_source_rules import (
    DRAFT, APPROVED, REVOKED, PENDING_REVIEW,
    SourceRuleError, SourceState, check_transition, validate_category, can_ingest,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(db: Session, *, source_id: str | None, actor: str | None, action: str,
           outcome: str, detail: str | None = None) -> None:
    db.add(PspSourceAuditEvent(source_id=source_id, actor_member_id=actor, action=action,
                               outcome=outcome, detail=(detail or "")[:300] or None, at=_now()))


def _state(db: Session, src: PspSource) -> SourceState:
    has_profile = db.execute(
        select(PspSourcePermissionProfile.id).where(PspSourcePermissionProfile.source_id == src.id)
    ).first() is not None
    return SourceState(category=src.category, status=src.status, owner_member_id=src.owner_member_id,
                       approved_by=src.approved_by, legal_record_ref=src.legal_record_ref,
                       has_permission_profile=has_profile)


def source_state(db: Session, src: PspSource) -> SourceState:
    """Public read of a source's state (used by PSI-2 ingestion). Read-only."""
    return _state(db, src)


def create_source(db: Session, *, actor: str, category: str, name: str,
                  owner_member_id: str | None) -> PspSource:
    try:
        validate_category(category)
    except SourceRuleError as e:
        _audit(db, source_id=None, actor=actor, action="source.create", outcome="REFUSED", detail=str(e))
        db.commit()
        raise
    src = PspSource(category=category, name=name, owner_member_id=owner_member_id, status=DRAFT)
    db.add(src)
    db.flush()
    _audit(db, source_id=src.id, actor=actor, action="source.create", outcome="ALLOWED", detail=category)
    db.commit()
    return src


def set_profile(db: Session, *, actor: str, source_id: str, data_sharing_scope: str,
                permitted_fields: str, permitted_purposes: str, terms_ref: str | None) -> None:
    src = db.get(PspSource, source_id)
    if src is None:
        raise SourceRuleError("source not found")
    prof = db.execute(select(PspSourcePermissionProfile).where(
        PspSourcePermissionProfile.source_id == source_id)).scalar_one_or_none()
    if prof is None:
        prof = PspSourcePermissionProfile(source_id=source_id)
        db.add(prof)
    prof.data_sharing_scope = data_sharing_scope
    prof.permitted_fields = permitted_fields
    prof.permitted_purposes = permitted_purposes
    prof.terms_ref = terms_ref
    _audit(db, source_id=source_id, actor=actor, action="source.profile.set", outcome="ALLOWED")
    db.commit()


def transition(db: Session, *, actor: str, source_id: str, target: str,
               legal_record_ref: str | None = None) -> PspSource:
    src = db.get(PspSource, source_id)
    if src is None:
        _audit(db, source_id=source_id, actor=actor, action=f"source.transition.{target}",
               outcome="REFUSED", detail="source not found")
        db.commit()
        raise SourceRuleError("source not found")
    # Evaluate against the proposed legal ref WITHOUT mutating the row until the check passes,
    # so a refused attempt can never change the source.
    state = _state(db, src)
    if legal_record_ref is not None:
        state = SourceState(category=state.category, status=state.status,
                            owner_member_id=state.owner_member_id, approved_by=state.approved_by,
                            legal_record_ref=legal_record_ref,
                            has_permission_profile=state.has_permission_profile)
    try:
        check_transition(state, target, actor)
    except SourceRuleError as e:
        _audit(db, source_id=src.id, actor=actor, action=f"source.transition.{target}",
               outcome="REFUSED", detail=str(e))
        db.commit()
        raise
    if legal_record_ref is not None:
        src.legal_record_ref = legal_record_ref
    src.status = target
    if target == APPROVED:
        src.approved_by = actor
        src.approved_at = _now()
    if target == REVOKED:
        src.revoked_at = _now()
    _audit(db, source_id=src.id, actor=actor, action=f"source.transition.{target}", outcome="ALLOWED")
    db.commit()
    return src


def ingest_gate(db: Session, *, actor: str, source_id: str) -> bool:
    """Fail-closed gate for PSI-2. Returns True only for APPROVED sources. Audits refusals."""
    src = db.get(PspSource, source_id)
    if src is None or not can_ingest(_state(db, src)):
        _audit(db, source_id=source_id, actor=actor, action="source.ingest", outcome="REFUSED",
               detail="not approved or not found")
        db.commit()
        return False
    _audit(db, source_id=source_id, actor=actor, action="source.ingest", outcome="ALLOWED")
    db.commit()
    return True


def list_sources_for_member(db: Session, *, member_id: str) -> list[PspSource]:
    """Member sees only own sources. Central (owner NULL) sources are never returned here."""
    return list(db.execute(select(PspSource).where(PspSource.owner_member_id == member_id)).scalars())
