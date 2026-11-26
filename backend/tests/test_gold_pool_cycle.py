"""Phase 2 cycle-engine tests (Spec v4.1 §6 + v4.0 §34, pure-logic subset)."""
import pytest

from app.services import gold_pool_cycle as cyc
from app.services import gold_pool_rules as rules

TARGET = 2  # cycle number being drawn


def new(cid, member="m1", verified=True, **kw):
    base = dict(coupon_id=cid, member_id=member, allocation_type=cyc.NEW, source_cycle_number=TARGET,
                target_cycle_number=TARGET, verified=verified, used=False, voided=False,
                lifetime_draws_completed=0, cooldown_active=False, network_ok=True, academy_ok=True)
    base.update(kw)
    return cyc.CouponState(**base)


def carry(cid, member="m1", **kw):
    base = dict(coupon_id=cid, member_id=member, allocation_type=cyc.CARRY_FORWARD, source_cycle_number=1,
                target_cycle_number=TARGET, verified=True, used=False, voided=False,
                lifetime_draws_completed=0, cooldown_active=False, network_ok=True, academy_ok=True)
    base.update(kw)
    return cyc.CouponState(**base)


# --- v4.1 §6 example: 30 new + 8 carry-forward = 38 entries, collective = 100% ---
def test_collective_counts_only_new_and_stays_100_percent():
    coupons = [new(f"n{i}") for i in range(30)] + [carry(f"c{i}") for i in range(8)]
    m = cyc.draw_metrics(coupons, TARGET)
    assert m["collective"]["count"] == 30
    assert m["collective"]["percent"] == 100
    assert m["carry_forward_entries_candidate"] == 8
    assert m["potential_draw_entries"] == 38


def test_carry_forward_does_not_inflate_collective_progress():
    coupons = [carry(f"c{i}") for i in range(10)]
    assert cyc.collective_progress_for_cycle(coupons, TARGET)["count"] == 0


def test_unverified_new_coupon_does_not_count_to_target():
    coupons = [new(f"n{i}") for i in range(29)] + [new("bad", verified=False)]
    assert cyc.collective_progress_for_cycle(coupons, TARGET)["count"] == 29


def test_new_coupon_from_other_cycle_not_counted():
    other = new("x")
    other = cyc.CouponState(**{**other.__dict__, "target_cycle_number": 9})
    assert cyc.collective_progress_for_cycle([other], TARGET)["count"] == 0


# --- v4.1 §1.2 carry-forward eligibility ---
def test_valid_carry_forward_is_eligible():
    assert cyc.is_carry_forward_eligible(carry("c"))[0] is True


@pytest.mark.parametrize("field,reason", [
    ("used", "ALREADY_USED"), ("voided", "VOIDED"), ("verified", None),
])
def test_carry_forward_rejects_used_voided_unverified(field, reason):
    kwargs = {field: False} if field == "verified" else {field: True}
    ok, reasons = cyc.is_carry_forward_eligible(carry("c", **kwargs))
    assert ok is False
    if reason:
        assert reason in reasons


def test_carry_forward_cannot_bypass_lifetime_limit():
    ok, reasons = cyc.is_carry_forward_eligible(carry("c", lifetime_draws_completed=10))
    assert ok is False and rules.REASON_LIFETIME in reasons


def test_carry_forward_cannot_bypass_cooldown_network_academy():
    ok, reasons = cyc.is_carry_forward_eligible(
        carry("c", cooldown_active=True, network_ok=False, academy_ok=False))
    assert ok is False
    assert set(reasons) == {rules.REASON_COOLDOWN, rules.REASON_NETWORK, rules.REASON_ACADEMY}


def test_carry_forward_source_must_be_earlier_cycle():
    bad = carry("c")
    bad = cyc.CouponState(**{**bad.__dict__, "source_cycle_number": TARGET})
    ok, reasons = cyc.is_carry_forward_eligible(bad)
    assert ok is False and "CARRY_FORWARD_SOURCE_NOT_EARLIER" in reasons


# --- v4.1 §2 snapshot + equal probability ---
def test_snapshot_includes_new_and_carry_forward_together():
    coupons = [new("n1"), carry("c1")]
    entries = cyc.build_draw_snapshot(coupons, TARGET, collective_target_reached=True)
    assert sorted(c for c, _ in entries) == ["c1", "n1"]


def test_snapshot_blocks_when_target_not_reached():
    with pytest.raises(cyc.SnapshotError) as e:
        cyc.build_draw_snapshot([new("n1")], TARGET, collective_target_reached=False)
    assert e.value.code == "COLLECTIVE_TARGET_NOT_REACHED"


def test_snapshot_blocks_on_zero_eligible():
    with pytest.raises(cyc.SnapshotError) as e:
        cyc.build_draw_snapshot([new("n1", network_ok=False)], TARGET, collective_target_reached=True)
    assert e.value.code == "NO_ELIGIBLE_DRAW_ENTRIES"


def test_snapshot_rejects_duplicate_coupon_ids():
    with pytest.raises(cyc.SnapshotError) as e:
        cyc.build_draw_snapshot([new("dup"), new("dup")], TARGET, collective_target_reached=True)
    assert e.value.code == "DUPLICATE_COUPON_IN_SNAPSHOT"


def test_no_per_member_deduplication():
    # member A with 3 coupons -> 3 entries, not 1
    coupons = [new("a1", "A"), new("a2", "A"), new("a3", "A"), new("b1", "B")]
    entries = cyc.build_draw_snapshot(coupons, TARGET, collective_target_reached=True)
    assert len(entries) == 4
    assert sum(1 for _, m in entries if m == "A") == 3


def test_ten_coupons_means_ten_entries():
    coupons = [new(f"x{i}", "X") for i in range(10)]
    entries = cyc.build_draw_snapshot(coupons, TARGET, collective_target_reached=True)
    assert len(entries) == 10


def test_snapshot_order_is_deterministic():
    coupons = [new("c"), new("a"), new("b")]
    assert cyc.build_draw_snapshot(coupons, TARGET, True) == cyc.build_draw_snapshot(list(reversed(coupons)), TARGET, True)


def test_equal_probability_per_coupon_with_injected_rng():
    # Winner chosen uniformly from coupon list: member with 3 of 6 entries should win 3/6 of the time.
    coupons = [new("a1", "A"), new("a2", "A"), new("a3", "A"), new("b1", "B"), new("c1", "C"), new("c2", "C")]
    entries = cyc.build_draw_snapshot(coupons, TARGET, True)
    wins = {"A": 0, "B": 0, "C": 0}
    for i in range(6):
        w = cyc.select_winner(entries, rng=lambda n, i=i: i)  # each coupon index exactly once
        wins[w["winning_member_id"]] += 1
    assert wins == {"A": 3, "B": 1, "C": 2}


def test_select_winner_never_picks_member_first():
    entries = [("a1", "A"), ("b1", "B")]
    assert cyc.select_winner(entries, rng=lambda n: 1)["winning_coupon_id"] == "b1"


# --- v4.1 §3 & §4 participation and consumption ---
def test_participation_one_per_member_regardless_of_coupon_count():
    entries = [("a1", "A"), ("a2", "A"), ("a3", "A"), ("b1", "B")]
    counts = cyc.participations_after_draw(entries, "draw-1", {})
    assert counts == {"A": 1, "B": 1}


def test_member_with_15_coupons_gets_one_participation():
    entries = [(f"a{i}", "A") for i in range(15)]
    assert cyc.participations_after_draw(entries, "d", {"A": 4}) == {"A": 5}


def test_all_snapshot_coupons_consumed_winner_and_non_winner():
    entries = [("w", "A"), ("x", "B"), ("y", "B")]
    assert cyc.coupons_consumed_by_draw(entries) == ["w", "x", "y"]


def test_ninth_participation_allowed_tenth_blocked():
    ok9, _ = cyc.is_carry_forward_eligible(carry("c", lifetime_draws_completed=9))
    ok10, _ = cyc.is_carry_forward_eligible(carry("c", lifetime_draws_completed=10))
    assert ok9 is True and ok10 is False
