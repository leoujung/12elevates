"""Tests for Phase 4 admin read endpoints."""
from app.services import gold_pool_admin_read as adm
from app.services import gold_pool_issuance as iss
from app.services import gold_pool_verify as ver
from sqlalchemy import select
from app.models.gold_pool import GpCoupon


def _issue(db, tx):
    iss.record_manual(db, actor_id="admin-x", member_email="andi@example.test",
                      transaction_id=tx, tx_type="NEW_PARTNER", lp=150,
                      verified_at="2026-11-20T10:00:00+07:00")


def test_pending_lists_only_issued_coupons(db):
    _issue(db, "TX-P4-1")
    _issue(db, "TX-P4-2")
    c = db.execute(select(GpCoupon).where(GpCoupon.status == "ISSUED")).scalars().first()
    ver.verify_coupon(db, coupon_id=c.id, actor_id="admin-x", reason="ok")
    pending = adm.pending_coupons(db)["coupons"]
    assert len(pending) == 1
    assert pending[0]["coupon_id"] != c.id


def test_cycle_counts_separate_verified_and_waiting(db):
    _issue(db, "TX-P4-3")
    cycles = adm.list_cycles(db)["cycles"]
    assert cycles[0]["waiting_coupons"] == 1
    assert cycles[0]["verified_coupons"] == 0
    assert cycles[0]["target"] == 30


def test_audit_log_is_newest_first_and_has_reason(db):
    _issue(db, "TX-P4-4")
    c = db.execute(select(GpCoupon).where(GpCoupon.status == "ISSUED")).scalars().first()
    ver.verify_coupon(db, coupon_id=c.id, actor_id="admin-x", reason="bukti dicek")
    entries = adm.audit_log(db)["entries"]
    assert entries[0]["action"] == "COUPON_VERIFIED"
    assert entries[0]["reason"] == "bukti dicek"
    assert entries[0]["before"] == "ISSUED" and entries[0]["after"] == "VERIFIED"


def test_prizes_empty_when_no_draw_has_run(db):
    assert adm.prize_list(db) == {"prizes": []}
