"""Phase 3 transaction verification and coupon issuance (Spec v4.0 §5, §16, §17).

Only admins call this, through /v1/admin routes. Members can no longer create LP.

Guarantees:
- Idempotent: the same transaction_id is never processed twice (unique key + pre-check).
- Exactly one coupon per qualifying transaction, enforced by a DB unique constraint.
- Rules come from gold_pool_rules (>=150 LP, NEW_PARTNER or LOYALTY_ORDER, verified).
- The transaction row, coupon row, allocation row and audit row commit together or not at all.
"""
from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.core import Member
from app.models.gold_pool import (
    GpAuditLog,
    GpCoupon,
    GpCouponAllocation,
    GpCycle,
    GpTransaction,
)
from app.services import gold_pool_rules as rules

SOURCE_MANUAL = "ADMIN_MANUAL"
SOURCE_CSV = "CSV_IMPORT"
CSV_REQUIRED_COLUMNS = ("transaction_id", "member_email", "tx_type", "lp", "verified_at")
MAX_CSV_ROWS = 5000


class VerificationError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class IssueResult:
    transaction_id: str
    status: str            # ISSUED | DUPLICATE_IGNORED | NOT_QUALIFYING | REJECTED
    coupon_id: str | None
    reason: str | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_verified_at(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise VerificationError("INVALID_VERIFIED_AT", str(value))
    if dt.tzinfo is None:
        raise VerificationError("VERIFIED_AT_NEEDS_TIMEZONE", str(value))
    return dt


def _open_cycle(db: Session) -> GpCycle:
    """Coupons are issued into the currently OPEN cycle. Create cycle 1 on first use."""
    cycle = db.execute(select(GpCycle).where(GpCycle.status == "OPEN")
                       .order_by(GpCycle.cycle_number.desc())).scalars().first()
    if cycle is None:
        last = db.execute(select(GpCycle).order_by(GpCycle.cycle_number.desc())).scalars().first()
        number = (last.cycle_number + 1) if last else 1
        cycle = GpCycle(id=str(uuid.uuid4()), cycle_number=number, status="OPEN")
        db.add(cycle)
        db.flush()
    return cycle


def _audit(db: Session, *, actor_id: str | None, action: str, entity_id: str | None,
           after: str | None, reason: str | None = None) -> None:
    db.add(GpAuditLog(actor_id=actor_id, action=action, entity_type="transaction",
                      entity_id=entity_id, before_value=None, after_value=after, reason=reason, at=_now()))


def issue_for_transaction(db: Session, *, actor_id: str, transaction_id: str, member_id: str,
                          tx_type: str, lp: int, verified_at: datetime, source: str) -> IssueResult:
    """Record one verified transaction and issue at most one coupon. Caller commits."""
    transaction_id = (transaction_id or "").strip()
    if not transaction_id or len(transaction_id) > 64:
        raise VerificationError("INVALID_TRANSACTION_ID")

    existing = db.execute(select(GpTransaction).where(GpTransaction.transaction_id == transaction_id)).scalar_one_or_none()
    if existing is not None:
        return IssueResult(transaction_id, "DUPLICATE_IGNORED", None, "ALREADY_PROCESSED")

    if rules.coupon_count_for_transaction(tx_type, lp, True) == 0:
        reason = "UNSUPPORTED_TYPE" if tx_type not in rules.ELIGIBLE_TX_TYPES else "BELOW_150_LP"
        # Record the verified transaction (audit trail) without issuing a coupon.
        tx = GpTransaction(id=str(uuid.uuid4()), transaction_id=transaction_id, owner_member_id=member_id,
                           tx_type=tx_type, lp=lp, source=source, recorded_by=actor_id,
                           verified_at=verified_at, recorded_at=_now())
        db.add(tx)
        _audit(db, actor_id=actor_id, action="TX_RECORDED_NO_COUPON", entity_id=tx.id,
               after=f"lp={lp};type={tx_type}", reason=reason)
        return IssueResult(transaction_id, "NOT_QUALIFYING", None, reason)

    cycle = _open_cycle(db)
    tx = GpTransaction(id=str(uuid.uuid4()), transaction_id=transaction_id, owner_member_id=member_id,
                       tx_type=tx_type, lp=lp, source=source, recorded_by=actor_id,
                       verified_at=verified_at, recorded_at=_now())
    # Persist the transaction first so the coupon foreign key always points to a stored row.
    db.add(tx)
    db.flush()
    # A new coupon is ISSUED (waiting). It becomes VERIFIED only through a separate admin
    # verification step, never at creation (v4: no valid claim before verification).
    coupon = GpCoupon(id=str(uuid.uuid4()), transaction_pk=tx.id, owner_member_id=member_id,
                      original_cycle_id=cycle.id, lp_at_issue=lp, status=rules.ISSUED, issued_at=_now())
    allocation = GpCouponAllocation(id=str(uuid.uuid4()), coupon_id=coupon.id, source_cycle_id=cycle.id,
                                    target_cycle_id=cycle.id, allocation_type="NEW",
                                    eligibility_status=rules.ISSUED, included_in_snapshot=False,
                                    created_at=_now())
    db.add_all([coupon, allocation])
    _audit(db, actor_id=actor_id, action="COUPON_ISSUED", entity_id=coupon.id,
           after=f"tx={transaction_id};cycle={cycle.cycle_number};lp={lp}")
    return IssueResult(transaction_id, "ISSUED", coupon.id, None)


def _member_by_email(db: Session, email: str) -> Member | None:
    return db.execute(select(Member).where(Member.email == email.strip().lower())).scalar_one_or_none()


def record_manual(db: Session, *, actor_id: str, member_email: str, transaction_id: str,
                  tx_type: str, lp: int, verified_at: str) -> IssueResult:
    member = _member_by_email(db, member_email)
    if member is None:
        raise VerificationError("MEMBER_NOT_FOUND")
    result = issue_for_transaction(db, actor_id=actor_id, transaction_id=transaction_id,
                                   member_id=member.id, tx_type=tx_type, lp=lp,
                                   verified_at=_parse_verified_at(verified_at), source=SOURCE_MANUAL)
    db.commit()
    return result


def import_csv(db: Session, *, actor_id: str, content: str) -> dict:
    """Import a CSV of verified transactions. Each row is processed in its own savepoint so one
    bad row never rolls back the rest, and the same file can be re-imported safely."""
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames is None or any(c not in reader.fieldnames for c in CSV_REQUIRED_COLUMNS):
        raise VerificationError("CSV_MISSING_COLUMNS", ",".join(CSV_REQUIRED_COLUMNS))

    rows = list(reader)
    if len(rows) > MAX_CSV_ROWS:
        raise VerificationError("CSV_TOO_MANY_ROWS", str(MAX_CSV_ROWS))

    results: list[dict] = []
    for line_no, row in enumerate(rows, start=2):
        try:
            member = _member_by_email(db, row["member_email"] or "")
            if member is None:
                raise VerificationError("MEMBER_NOT_FOUND")
            lp_raw = (row["lp"] or "").strip()
            if not lp_raw.lstrip("-").isdigit():
                raise VerificationError("INVALID_LP")
            with db.begin_nested():
                res = issue_for_transaction(
                    db, actor_id=actor_id, transaction_id=row["transaction_id"],
                    member_id=member.id, tx_type=(row["tx_type"] or "").strip(),
                    lp=int(lp_raw), verified_at=_parse_verified_at(row["verified_at"]), source=SOURCE_CSV)
            results.append({"line": line_no, "transaction_id": res.transaction_id,
                            "status": res.status, "reason": res.reason})
        except VerificationError as e:
            results.append({"line": line_no, "transaction_id": (row.get("transaction_id") or "")[:64],
                            "status": "REJECTED", "reason": e.code})
        except IntegrityError:
            results.append({"line": line_no, "transaction_id": (row.get("transaction_id") or "")[:64],
                            "status": "DUPLICATE_IGNORED", "reason": "CONSTRAINT_ALREADY_PROCESSED"})

    summary = {"rows": len(results)}
    for status in ("ISSUED", "NOT_QUALIFYING", "DUPLICATE_IGNORED", "REJECTED"):
        summary[status.lower()] = sum(1 for r in results if r["status"] == status)
    _audit(db, actor_id=actor_id, action="CSV_IMPORT", entity_id=None,
           after=";".join(f"{k}={v}" for k, v in summary.items()))
    db.commit()
    return {"summary": summary, "results": results}
