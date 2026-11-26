"""Tests for the Phase 5 draw engine. Nothing here runs against production data."""
import pytest
from sqlalchemy import select

from app.models.gold_pool import (
    GpAuditLog, GpCoupon, GpCycle, GpDraw, GpDrawEntry, GpDrawSnapshot,
    GpParticipation, GpPrize, GpWinnerCooldown,
)
from app.services import gold_pool_draw as settings_svc
from app.services import gold_pool_engine as eng
from app.services import gold_pool_issuance as iss
from app.services import gold_pool_verify as ver


def _enable(db, *, legal=True, enabled=True):
    from app.services.gold_pool_draw import GpDrawSettings
    row = db.get(GpDrawSettings, 1) or GpDrawSettings(id=1)
    row.enabled = enabled
    row.legal_review_approved = legal
    row.scheduled_at = None
    db.merge(row)
    db.commit()


def _verified_coupon(db, tx):
    iss.record_manual(db, actor_id="admin-x", member_email="andi@example.test",
                      transaction_id=tx, tx_type="NEW_PARTNER", lp=150,
                      verified_at="2026-11-20T10:00:00+07:00")
    c = db.execute(select(GpCoupon).where(GpCoupon.transaction_pk.isnot(None),
                                          GpCoupon.status == "ISSUED")
                   .order_by(GpCoupon.issued_at.desc())).scalars().first()
    ver.verify_coupon(db, coupon_id=c.id, actor_id="admin-x", reason="cek bukti")
    return c


def _cycle(db):
    return db.execute(select(GpCycle)).scalars().first()


def test_draw_blocked_when_not_enabled(db):
    _enable(db, enabled=False)
    _verified_coupon(db, "TX-E1")
    with pytest.raises(eng.DrawBlocked) as e:
        eng.run_draw(db, cycle_id=_cycle(db).id, actor_id="admin-x", rng=lambda n: 0)
    assert e.value.code == "DRAW_NOT_ENABLED"
    assert db.execute(select(GpDraw)).scalars().first() is None


def test_draw_blocked_without_legal_review(db):
    _enable(db, legal=False)
    _verified_coupon(db, "TX-E2")
    with pytest.raises(eng.DrawBlocked) as e:
        eng.run_draw(db, cycle_id=_cycle(db).id, actor_id="admin-x", rng=lambda n: 0)
    assert e.value.code == "LEGAL_REVIEW_PENDING"


def test_issued_coupon_never_enters_snapshot(db):
    _enable(db)
    _verified_coupon(db, "TX-E3")
    # A second coupon that stays ISSUED must not be in the snapshot.
    iss.record_manual(db, actor_id="admin-x", member_email="andi@example.test",
                      transaction_id="TX-E3B", tx_type="NEW_PARTNER", lp=150,
                      verified_at="2026-11-20T10:00:00+07:00")
    eng.run_draw(db, cycle_id=_cycle(db).id, actor_id="admin-x", rng=lambda n: 0)
    snap = db.execute(select(GpDrawSnapshot)).scalars().one()
    assert snap.entry_count == 1


def test_draw_runs_once_per_cycle(db):
    _enable(db)
    _verified_coupon(db, "TX-E4")
    cid = _cycle(db).id
    eng.run_draw(db, cycle_id=cid, actor_id="admin-x", rng=lambda n: 0)
    with pytest.raises(eng.DrawBlocked) as e:
        eng.run_draw(db, cycle_id=cid, actor_id="admin-x", rng=lambda n: 0)
    assert e.value.code == "DRAW_ALREADY_EXECUTED"
    assert len(db.execute(select(GpDraw)).scalars().all()) == 1


def test_winner_prize_cooldown_and_participation_recorded(db):
    _enable(db)
    c = _verified_coupon(db, "TX-E5")
    res = eng.run_draw(db, cycle_id=_cycle(db).id, actor_id="admin-x", rng=lambda n: 0)
    assert res["winning_member_id"] == c.owner_member_id
    assert db.execute(select(GpPrize)).scalars().one().prize_status == "DRAW_CONFIRMED"
    cd = db.execute(select(GpWinnerCooldown)).scalars().one()
    assert cd.status == "ACTIVE" and cd.member_id == c.owner_member_id
    assert len(db.execute(select(GpParticipation)).scalars().all()) == 1
    assert _cycle(db).status == "DRAWN"


def test_snapshot_hash_is_recorded_and_audited(db):
    _enable(db)
    _verified_coupon(db, "TX-E6")
    res = eng.run_draw(db, cycle_id=_cycle(db).id, actor_id="admin-x", rng=lambda n: 0)
    snap = db.execute(select(GpDrawSnapshot)).scalars().one()
    assert snap.snapshot_hash == res["snapshot_hash"] and len(snap.snapshot_hash) == 64
    log = db.execute(select(GpAuditLog).where(GpAuditLog.action == "DRAW_EXECUTED")).scalars().one()
    assert log.before_value == "OPEN" and "DRAWN" in log.after_value


def test_no_verified_coupons_means_no_draw(db):
    _enable(db)
    iss.record_manual(db, actor_id="admin-x", member_email="andi@example.test",
                      transaction_id="TX-E7", tx_type="NEW_PARTNER", lp=150,
                      verified_at="2026-11-20T10:00:00+07:00")
    with pytest.raises(eng.DrawBlocked) as e:
        eng.run_draw(db, cycle_id=_cycle(db).id, actor_id="admin-x", rng=lambda n: 0)
    assert e.value.code == "NO_ELIGIBLE_DRAW_ENTRIES"
    assert db.execute(select(GpDraw)).scalars().first() is None
