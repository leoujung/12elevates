"""PSI-3: operator reconciliation for stuck ingestion events.

Scope (synthetic data only, no HTTP, no automatic retry):
  - list_stuck(): RECEIVED claims older than IN_FLIGHT_WINDOW_S and RECONCILE events.
  - resolve(): an operator closes one event with exactly one of two decisions:
      ACCEPT_LINKED      a provenance row exists for the event -> link prospect, status ACCEPTED.
      CLOSE_NO_PROSPECT  no provenance row exists -> status REJECTED, reason 'reconciled_no_prospect'.

Hard rules:
  - Never calls ingest_prospect() or any ingestion path. Never retries an event.
  - A fresh RECEIVED claim (younger than IN_FLIGHT_WINDOW_S) cannot be resolved; it may still be in flight.
  - ACCEPTED and REJECTED are final; resolve() refuses to change them.
  - ACCEPT_LINKED requires a provenance row for this event; CLOSE_NO_PROSPECT refuses if one exists.
  - Every decision is audited with reason codes only (no personal data, no secret values).
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.psi_ingest import PspIngestionEvent, PspProspectProvenance
from app.models.psi_source import PspSourceAuditEvent
from app.services.psi_ingest import IN_FLIGHT_WINDOW_S, RECONCILE

RECEIVED_STATUS = "RECEIVED"  # ledger status string (psi_ingest has no constant for it)

ACCEPT_LINKED = "ACCEPT_LINKED"
CLOSE_NO_PROSPECT = "CLOSE_NO_PROSPECT"
DECISIONS = (ACCEPT_LINKED, CLOSE_NO_PROSPECT)
FINAL_STATUSES = ("ACCEPTED", "REJECTED")


class ReconcileRefused(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _operator_ref(operator: str) -> str:
    """Stable, non-reversible operator reference for audit. The raw identifier is never stored."""
    import hashlib
    return hashlib.sha256(operator.encode("utf-8")).hexdigest()[:12]


def _audit(db: Session, *, source_id: str, action: str, outcome: str, detail: str) -> None:
    db.add(PspSourceAuditEvent(source_id=source_id, actor_member_id=None, action=action,
                               outcome=outcome, detail=detail[:300], at=_now()))


def list_stuck(db: Session, *, now: datetime | None = None) -> list[PspIngestionEvent]:
    """Events an operator must look at. Fresh in-flight claims are excluded."""
    now = now or _now()
    cutoff = now - timedelta(seconds=IN_FLIGHT_WINDOW_S)
    rows = db.execute(select(PspIngestionEvent).where(
        PspIngestionEvent.status.in_([RECEIVED_STATUS, RECONCILE]))).scalars().all()
    return [r for r in rows if r.status == RECONCILE or _as_utc(r.received_at) <= cutoff]


def resolve(db: Session, *, event_id: str, decision: str, operator: str,
            now: datetime | None = None) -> str:
    """Close one stuck event. Returns the final status. Raises ReconcileRefused on any violation."""
    if decision not in DECISIONS:
        raise ReconcileRefused("unknown_decision")
    now = now or _now()
    ev = db.get(PspIngestionEvent, event_id)
    if ev is None:
        raise ReconcileRefused("event_not_found")
    if ev.status in FINAL_STATUSES:
        raise ReconcileRefused("already_final")
    if ev.status == RECEIVED_STATUS and _as_utc(ev.received_at) > now - timedelta(seconds=IN_FLIGHT_WINDOW_S):
        raise ReconcileRefused("claim_in_flight")
    if ev.status not in (RECEIVED_STATUS, RECONCILE):
        raise ReconcileRefused("not_reconcilable")

    prov = db.execute(select(PspProspectProvenance).where(
        PspProspectProvenance.ingestion_event_id == ev.id)).scalar_one_or_none()

    if decision == ACCEPT_LINKED:
        if prov is None:
            raise ReconcileRefused("no_provenance_for_accept")
        ev.status = "ACCEPTED"
        ev.prospect_id = prov.prospect_id
        ev.reason = None
        final = "ACCEPTED"
    else:  # CLOSE_NO_PROSPECT
        if prov is not None:
            raise ReconcileRefused("provenance_exists_cannot_close")
        ev.status = "REJECTED"
        ev.prospect_id = None
        ev.reason = "reconciled_no_prospect"
        final = "REJECTED"

    _audit(db, source_id=ev.source_id, action=f"reconcile.{decision.lower()}", outcome="ALLOWED",
           detail=f"event={ev.id} operator_ref={_operator_ref(operator)}")
    db.commit()
    return final
