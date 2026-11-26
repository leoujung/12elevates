"""PSI-2 hardening: webhook secret lifecycle service (DB-backed, audited with kid only).

No secret value or secret reference is ever written to audit records.
"""
import os
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.psi_secret import PspSourceSecret
from app.models.psi_source import PspSource, PspSourceAuditEvent
from app.services import psi_secret_rules as rules
from app.services.psi_secret_rules import ACTIVE, PENDING, SecretRow, SecretRuleError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _audit(db: Session, *, source_id, actor, action, outcome, kid=None) -> None:
    # Detail carries the kid only. Never a secret value, never a secret reference.
    db.add(PspSourceAuditEvent(source_id=source_id, actor_member_id=actor, action=action,
                               outcome=outcome, detail=f"kid={kid}" if kid else None, at=_now()))


def _db_rows(db: Session, source_id: str) -> list[PspSourceSecret]:
    return list(db.execute(select(PspSourceSecret).where(PspSourceSecret.source_id == source_id)).scalars())


def _to_row(r: PspSourceSecret) -> SecretRow:
    return SecretRow(kid=r.kid, status=r.status, secret_ref=r.secret_ref,
                     retired_at=_utc(r.retired_at) if r.retired_at else None)


def begin_rotation(db: Session, *, actor: str, source_id: str, kid: str, secret_ref: str,
                   now: datetime | None = None) -> None:
    if db.get(PspSource, source_id) is None:
        raise SecretRuleError("source_not_found")
    rows = [_to_row(r) for r in _db_rows(db, source_id)]
    try:
        rules.check_begin(rows, kid, secret_ref)
    except SecretRuleError as e:
        _audit(db, source_id=source_id, actor=actor, action="secret.begin", outcome="REFUSED", kid=kid)
        db.commit()
        raise
    db.add(PspSourceSecret(source_id=source_id, kid=kid, secret_ref=secret_ref, status=PENDING,
                           created_at=now or _now()))
    _audit(db, source_id=source_id, actor=actor, action="secret.begin", outcome="ALLOWED", kid=kid)
    db.commit()


def activate_rotation(db: Session, *, actor: str, source_id: str, kid: str,
                      now: datetime | None = None) -> None:
    now = now or _now()
    rows = _db_rows(db, source_id)
    try:
        changes = rules.plan_activation([_to_row(r) for r in rows], kid, now)
    except SecretRuleError as e:
        _audit(db, source_id=source_id, actor=actor, action="secret.activate", outcome="REFUSED", kid=kid)
        db.commit()
        raise
    for r in rows:
        if r.kid in changes:
            new_status, retired_at = changes[r.kid]
            r.status = new_status
            if new_status == ACTIVE:
                r.activated_at = now
            r.retired_at = retired_at
    _audit(db, source_id=source_id, actor=actor, action="secret.activate", outcome="ALLOWED", kid=kid)
    db.commit()


def revoke_secret(db: Session, *, actor: str, source_id: str, kid: str,
                  now: datetime | None = None) -> None:
    now = now or _now()
    rows = _db_rows(db, source_id)
    try:
        new_status, revoked_at = rules.plan_revoke([_to_row(r) for r in rows], kid, now)
    except SecretRuleError:
        _audit(db, source_id=source_id, actor=actor, action="secret.revoke", outcome="REFUSED", kid=kid)
        db.commit()
        raise
    for r in rows:
        if r.kid == kid:
            r.status = new_status
            r.revoked_at = revoked_at
    _audit(db, source_id=source_id, actor=actor, action="secret.revoke", outcome="ALLOWED", kid=kid)
    db.commit()


def load_verification_keys(db: Session, *, source_id: str, now: datetime,
                           resolve: Callable[[str], Optional[bytes]]) -> list[tuple[str, bytes]]:
    """Returns [(kid, secret)] for keys allowed now. Unresolvable keys are skipped and audited (fail-closed)."""
    rows = _db_rows(db, source_id)
    by_kid = {r.kid: r for r in rows}
    out: list[tuple[str, bytes]] = []
    wrote = False
    for row in rules.verification_kids([_to_row(r) for r in rows], now):
        secret = resolve(row.secret_ref)
        if not secret:
            _audit(db, source_id=source_id, actor=None, action="secret.unresolvable", outcome="REFUSED", kid=row.kid)
            wrote = True
            continue
        out.append((row.kid, secret))
    if wrote:
        db.commit()
    return out


def env_resolver(ref: str) -> Optional[bytes]:
    """Production resolver for env: references. vault: is not wired yet and fails closed (returns None)."""
    if not ref.startswith("env:"):
        return None
    value = os.environ.get(ref[4:])
    return value.encode("utf-8") if value else None
