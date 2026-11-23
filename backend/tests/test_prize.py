"""Tests for prize fulfillment (DRAW_CONFIRMED -> DELIVERED)."""
import uuid

import pytest
from sqlalchemy import select

from app.models.gold_pool import GpAuditLog, GpPrize
from app.services import gold_pool_prize as pz
from app.services import gold_pool_engine as eng
from app.services import gold_pool_issuance as iss
from app.services import gold_pool_verify as ver


@pytest.fixture
def prize_seed(db):
    """Prize created by the real draw engine (same path as test_gold_pool_engine)."""
    from app.services.gold_pool_draw import GpDrawSettings as _S
    from app.models.gold_pool import GpCoupon as _C, GpCycle as _Y
    row = db.get(_S, 1) or _S(id=1)
    row.enabled = True
    row.legal_review_approved = True
    db.merge(row)
    db.commit()
    iss.record_manual(db, actor_id="admin-x", member_email="andi@example.test",
                      transaction_id=f"TX-PZ-{uuid.uuid4().hex[:8]}", tx_type="NEW_PARTNER", lp=150,
                      verified_at="2026-11-20T10:00:00+07:00")
    c = db.execute(select(_C).where(_C.status == "ISSUED")).scalars().first()
    ver.verify_coupon(db, coupon_id=c.id, actor_id="admin-x", reason="cek bukti")
    cycle = db.execute(select(_Y)).scalars().first()
    eng.run_draw(db, cycle_id=cycle.id, actor_id="admin-x", rng=lambda n: 0)
    return db.execute(select(GpPrize)).scalars().one()


def test_mark_delivered_moves_confirmed_to_delivered_and_logs(db, prize_seed):
    pz.mark_delivered(db, prize_id=prize_seed.id, actor_id="admin-x", reason="serah terima di Zoom 05-12")
    db.refresh(prize_seed)
    assert prize_seed.prize_status == "DELIVERED"
    assert prize_seed.delivered_at is not None
    log = db.execute(select(GpAuditLog).where(GpAuditLog.action == "PRIZE_DELIVERED")).scalars().one()
    assert (log.before_value, log.after_value) == ("DRAW_CONFIRMED", "DELIVERED")


def test_delivering_twice_is_refused(db, prize_seed):
    pz.mark_delivered(db, prize_id=prize_seed.id, actor_id="admin-x", reason="serah terima")
    with pytest.raises(pz.PrizeNotDeliverable) as e:
        pz.mark_delivered(db, prize_id=prize_seed.id, actor_id="admin-x", reason="lagi")
    assert e.value.current_status == "DELIVERED"


def test_reason_is_required(db, prize_seed):
    with pytest.raises(ValueError):
        pz.mark_delivered(db, prize_id=prize_seed.id, actor_id="admin-x", reason="   ")
    db.refresh(prize_seed)
    assert prize_seed.prize_status == "DRAW_CONFIRMED"


def test_unknown_prize_is_not_found(db):
    with pytest.raises(pz.PrizeNotFound):
        pz.mark_delivered(db, prize_id=str(uuid.uuid4()), actor_id="admin-x", reason="x")
