"""GOLD ELEVATE POOL business-rule tests (Master Prompt v4.0 §34, pure-logic subset)."""
import pytest

from app.services import gold_pool_rules as r


# 1. Transaction -> coupon
@pytest.mark.parametrize("lp,expected", [(100, 0), (149, 0), (150, 1), (200, 1), (400, 1), (1000, 1)])
def test_lp_threshold_one_coupon_max(lp, expected):
    assert r.coupon_count_for_transaction("NEW_PARTNER", lp, True) == expected


def test_unverified_or_wrong_type_yields_no_coupon():
    assert r.coupon_count_for_transaction("NEW_PARTNER", 400, False) == 0
    assert r.coupon_count_for_transaction("OTHER", 400, True) == 0
    assert r.coupon_count_for_transaction("LOYALTY_ORDER", 400, True) == 1


def test_three_separate_transactions_make_three_coupons():
    txs = [("NEW_PARTNER", 150), ("LOYALTY_ORDER", 300), ("LOYALTY_ORDER", 400)]
    assert sum(r.coupon_count_for_transaction(t, lp, True) for t, lp in txs) == 3


def test_no_lp_multiplier():
    # 1000 LP / 150 would be 6; v4 says exactly one.
    assert r.coupon_count_for_transaction("LOYALTY_ORDER", 1000, True) == 1


def test_non_integer_lp_rejected():
    assert r.coupon_count_for_transaction("NEW_PARTNER", True, True) == 0
    assert r.coupon_count_for_transaction("NEW_PARTNER", 150.0, True) == 0


# 2. Collective target
def test_collective_target_is_30_and_counts_all_new_coupons():
    p = r.collective_progress(30)
    assert p["target"] == 30 and p["target_reached"] and p["percent"] == 100


def test_collective_progress_partial_and_capped():
    assert r.collective_progress(15)["percent"] == 50
    assert r.collective_progress(45)["percent"] == 100
    assert r.collective_progress(29)["target_reached"] is False


def test_negative_count_rejected():
    with pytest.raises(ValueError):
        r.collective_progress(-1)


# 3. Network 36 across Levels 0-3
def test_35_unique_members_do_not_qualify():
    nodes = [("root", 0)] + [(f"l1-{i}", 1) for i in range(4)] + [(f"l2-{i}", 2) for i in range(12)] + [(f"l3-{i}", 3) for i in range(18)]
    res = r.count_network(nodes)
    assert res["total"] == 35 and not res["qualified"]


def test_36_unique_members_qualify():
    nodes = [("root", 0)] + [(f"l1-{i}", 1) for i in range(5)] + [(f"l2-{i}", 2) for i in range(12)] + [(f"l3-{i}", 3) for i in range(18)]
    res = r.count_network(nodes)
    assert res["total"] == 36 and res["qualified"]
    assert (res["level0"], res["level1"], res["level2"], res["level3"]) == (1, 5, 12, 18)


def test_duplicate_members_counted_once_at_shallowest_level():
    res = r.count_network([("a", 3), ("a", 1), ("a", 2), ("b", 0)])
    assert res["total"] == 2 and res["level1"] == 1 and res["level3"] == 0


def test_members_beyond_level_3_ignored():
    res = r.count_network([("a", 0), ("b", 4), ("c", 7), ("d", -1)])
    assert res["total"] == 1


# 4. Academy: 3 NEW, verified, unused
def test_academy_requires_three_new_verified_videos():
    with pytest.raises(r.AcademyBatchError):
        r.validate_academy_batch([("v1", True), ("v2", True)], set())


def test_unverified_videos_do_not_count():
    with pytest.raises(r.AcademyBatchError):
        r.validate_academy_batch([("v1", False), ("v2", False), ("v3", True)], set())


def test_previously_used_videos_cannot_be_reused():
    with pytest.raises(r.AcademyBatchError):
        r.validate_academy_batch([("v1", True), ("v2", True), ("v3", True)], {"v1", "v2", "v3"})


def test_duplicate_video_ids_counted_once():
    with pytest.raises(r.AcademyBatchError):
        r.validate_academy_batch([("v1", True), ("v1", True), ("v2", True)], set())


def test_academy_picks_exactly_three_in_order():
    chosen = r.validate_academy_batch([("v1", True), ("v2", True), ("v3", True), ("v4", True)], {"v0"})
    assert chosen == ["v1", "v2", "v3"]


# 5. Lifetime participation
def test_participation_counts_distinct_draws_not_coupons():
    assert r.lifetime_participation_count(["d1", "d1", "d1", "d2"]) == 2


def test_nine_participations_may_still_enter():
    st, reasons = r.determine_eligibility(coupon_used=False, coupon_voided=False, lifetime_count=9,
                                          cooldown_active=False, network_ok=True, academy_ok=True)
    assert st == r.ELIGIBLE and reasons == []


def test_ten_participations_permanently_excluded():
    st, reasons = r.determine_eligibility(coupon_used=False, coupon_voided=False, lifetime_count=10,
                                          cooldown_active=False, network_ok=True, academy_ok=True)
    assert st == r.EXCLUDED_LIFETIME_LIMIT and r.REASON_LIFETIME in reasons


# 6. Eligibility priority and multiple reasons
def test_used_and_voided_are_never_eligible():
    assert r.determine_eligibility(coupon_used=True, coupon_voided=False, lifetime_count=0,
                                   cooldown_active=False, network_ok=True, academy_ok=True)[0] == r.USED
    assert r.determine_eligibility(coupon_used=False, coupon_voided=True, lifetime_count=0,
                                   cooldown_active=False, network_ok=True, academy_ok=True)[0] == r.VOIDED


def test_multiple_failed_conditions_are_all_reported():
    st, reasons = r.determine_eligibility(coupon_used=False, coupon_voided=False, lifetime_count=0,
                                          cooldown_active=True, network_ok=False, academy_ok=False)
    assert st == r.EXCLUDED_COOLDOWN
    assert set(reasons) == {r.REASON_COOLDOWN, r.REASON_NETWORK, r.REASON_ACADEMY}


def test_network_pending_precedes_academy_pending():
    assert r.determine_eligibility(coupon_used=False, coupon_voided=False, lifetime_count=0,
                                   cooldown_active=False, network_ok=False, academy_ok=False)[0] == r.PENDING_NETWORK


# 7. Snapshot integrity and secure selection
def test_snapshot_hash_is_deterministic_and_order_sensitive():
    a = [("c1", "m1"), ("c2", "m2")]
    assert r.snapshot_hash(a) == r.snapshot_hash(list(a))
    assert r.snapshot_hash(a) != r.snapshot_hash(list(reversed(a)))
    assert r.snapshot_hash(a) != r.snapshot_hash(a + [("c3", "m3")])


def test_zero_entries_blocks_draw():
    with pytest.raises(r.DrawError) as e:
        r.select_winner_index(0)
    assert e.value.code == "NO_ELIGIBLE_DRAW_ENTRIES"


def test_selection_uses_csprng_range_when_no_override():
    for _ in range(200):
        assert 0 <= r.select_winner_index(7) < 7


def test_invalid_random_index_rejected():
    with pytest.raises(r.DrawError):
        r.select_winner_index(5, rng=lambda n: n)
    with pytest.raises(r.DrawError):
        r.select_winner_index(5, rng=lambda n: True)
