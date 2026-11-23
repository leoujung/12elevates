"""Phase 3 tests: admin-only verification, member LP disabled, idempotency, 150-LP rule, CSV import."""
import pytest
from sqlalchemy import select

from app.models.core import Member
from app.models.gold_pool import GpAuditLog, GpCoupon, GpTransaction
from app.services import gold_pool_issuance as iss


@pytest.fixture()
def admin_db(db):
    """Adds one admin member to the shared fixture DB (Andi=member, Budi=member)."""
    from app.models.core import Organization
    org = db.execute(select(Organization)).scalars().first()
    admin = Member(id="member-admin", organization_id=org.id, email="admin@example.test",
                   display_name="Admin", is_admin=True)
    db.add(admin)
    db.commit()
    return db


def _count(db, model):
    return len(db.execute(select(model)).scalars().all())


def test_manual_150lp_issues_exactly_one_coupon(admin_db):
    r = iss.record_manual(admin_db, actor_id="member-admin", member_email="andi@example.test",
                          transaction_id="TX-1", tx_type="NEW_PARTNER", lp=150,
                          verified_at="2026-11-20T10:00:00+07:00")
    assert r.status == "ISSUED" and r.coupon_id
    assert _count(admin_db, GpCoupon) == 1


def test_duplicate_transaction_is_idempotent(admin_db):
    kw = dict(actor_id="member-admin", member_email="andi@example.test", transaction_id="TX-DUP",
              tx_type="LOYALTY_ORDER", lp=400, verified_at="2026-11-20T10:00:00+07:00")
    first = iss.record_manual(admin_db, **kw)
    second = iss.record_manual(admin_db, **kw)
    assert first.status == "ISSUED"
    assert second.status == "DUPLICATE_IGNORED"
    assert _count(admin_db, GpCoupon) == 1
    assert _count(admin_db, GpTransaction) == 1


@pytest.mark.parametrize("lp", [100, 149])
def test_below_150_lp_issues_no_coupon(admin_db, lp):
    r = iss.record_manual(admin_db, actor_id="member-admin", member_email="andi@example.test",
                          transaction_id=f"TX-L{lp}", tx_type="NEW_PARTNER", lp=lp,
                          verified_at="2026-11-20T10:00:00+07:00")
    assert r.status == "NOT_QUALIFYING" and r.reason == "BELOW_150_LP"
    assert _count(admin_db, GpCoupon) == 0


def test_unsupported_type_issues_no_coupon(admin_db):
    r = iss.record_manual(admin_db, actor_id="member-admin", member_email="andi@example.test",
                          transaction_id="TX-T", tx_type="REFUND", lp=500,
                          verified_at="2026-11-20T10:00:00+07:00")
    assert r.status == "NOT_QUALIFYING" and r.reason == "UNSUPPORTED_TYPE"
    assert _count(admin_db, GpCoupon) == 0


def test_no_lp_multiplier_one_transaction_one_coupon(admin_db):
    iss.record_manual(admin_db, actor_id="member-admin", member_email="andi@example.test",
                      transaction_id="TX-BIG", tx_type="LOYALTY_ORDER", lp=1000,
                      verified_at="2026-11-20T10:00:00+07:00")
    assert _count(admin_db, GpCoupon) == 1


def test_three_separate_transactions_three_coupons(admin_db):
    for i, lp in enumerate([150, 300, 400]):
        iss.record_manual(admin_db, actor_id="member-admin", member_email="andi@example.test",
                          transaction_id=f"TX-S{i}", tx_type="LOYALTY_ORDER", lp=lp,
                          verified_at="2026-11-20T10:00:00+07:00")
    assert _count(admin_db, GpCoupon) == 3


def test_unknown_member_rejected(admin_db):
    with pytest.raises(iss.VerificationError) as e:
        iss.record_manual(admin_db, actor_id="member-admin", member_email="nobody@example.test",
                          transaction_id="TX-X", tx_type="NEW_PARTNER", lp=150,
                          verified_at="2026-11-20T10:00:00+07:00")
    assert e.value.code == "MEMBER_NOT_FOUND"


def test_timestamp_without_timezone_rejected(admin_db):
    with pytest.raises(iss.VerificationError) as e:
        iss.record_manual(admin_db, actor_id="member-admin", member_email="andi@example.test",
                          transaction_id="TX-TZ", tx_type="NEW_PARTNER", lp=150,
                          verified_at="2026-11-20T10:00:00")
    assert e.value.code == "VERIFIED_AT_NEEDS_TIMEZONE"


def test_audit_log_written_for_issuance(admin_db):
    iss.record_manual(admin_db, actor_id="member-admin", member_email="andi@example.test",
                      transaction_id="TX-AUD", tx_type="NEW_PARTNER", lp=150,
                      verified_at="2026-11-20T10:00:00+07:00")
    actions = {a.action for a in admin_db.execute(select(GpAuditLog)).scalars().all()}
    assert "COUPON_ISSUED" in actions


def test_csv_import_mixed_rows_and_safe_reimport(admin_db):
    csv_text = (
        "transaction_id,member_email,tx_type,lp,verified_at\n"
        "CSV-1,andi@example.test,NEW_PARTNER,150,2026-11-20T10:00:00+07:00\n"
        "CSV-2,andi@example.test,LOYALTY_ORDER,120,2026-11-20T10:00:00+07:00\n"
        "CSV-3,budi@example.test,LOYALTY_ORDER,300,2026-11-20T10:00:00+07:00\n"
        "CSV-4,ghost@example.test,NEW_PARTNER,150,2026-11-20T10:00:00+07:00\n"
        "CSV-5,andi@example.test,NEW_PARTNER,abc,2026-11-20T10:00:00+07:00\n"
    )
    out = iss.import_csv(admin_db, actor_id="member-admin", content=csv_text)
    s = out["summary"]
    assert s["issued"] == 2
    assert s["not_qualifying"] == 1
    assert s["rejected"] == 2
    assert _count(admin_db, GpCoupon) == 2

    again = iss.import_csv(admin_db, actor_id="member-admin", content=csv_text)
    assert again["summary"]["issued"] == 0
    # CSV-1 (issued) and CSV-2 (recorded as not-qualifying) are both already stored.
    # CSV-1 (issued), CSV-2 (not-qualifying) and CSV-3 (issued, budi) are already stored -> 3 duplicates.
    # CSV-4 (unknown member) and CSV-5 (bad LP) were never stored -> still rejected.
    assert again["summary"]["duplicate_ignored"] == 3
    assert again["summary"]["rejected"] == 2
    assert _count(admin_db, GpCoupon) == 2


def test_csv_missing_columns_rejected(admin_db):
    with pytest.raises(iss.VerificationError) as e:
        iss.import_csv(admin_db, actor_id="member-admin", content="transaction_id,lp\nA,150\n")
    assert e.value.code == "CSV_MISSING_COLUMNS"


def test_csv_too_many_rows_rejected(admin_db):
    header = "transaction_id,member_email,tx_type,lp,verified_at\n"
    body = "".join(f"T{i},andi@example.test,NEW_PARTNER,150,2026-11-20T10:00:00+07:00\n"
                   for i in range(iss.MAX_CSV_ROWS + 1))
    with pytest.raises(iss.VerificationError) as e:
        iss.import_csv(admin_db, actor_id="member-admin", content=header + body)
    assert e.value.code == "CSV_TOO_MANY_ROWS"


def test_new_coupon_is_stored_as_issued_not_verified(admin_db):
    # Regression: a coupon must be stored as ISSUED (waiting), never VERIFIED, at creation time.
    iss.record_manual(admin_db, actor_id="member-admin", member_email="andi@example.test",
                      transaction_id="TX-STATUS", tx_type="NEW_PARTNER", lp=150,
                      verified_at="2026-11-20T10:00:00+07:00")
    coupons = admin_db.execute(select(GpCoupon)).scalars().all()
    assert len(coupons) == 1
    assert coupons[0].status == "ISSUED"
