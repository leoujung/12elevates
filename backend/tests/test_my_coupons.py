"""GET /v1/gp/my-coupons: the signed-in member's own coupons, for the dashboard slots.

Rules (v4):
- Only the caller's coupons (owner_member_id from the token). Never another member's coupons.
- Only VERIFIED or USED count as verified. Everything else is shown as pending, never as valid.
- Returns the coupon number and a plain status; no transaction details, no other members.
"""
from tests.test_api_phase1 import client, login  # noqa: F401 (pytest fixture)


def test_my_coupons_requires_token(client):
    r = client.get("/v1/gp/my-coupons")
    assert r.status_code == 401


def test_my_coupons_empty_for_new_member(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.get("/v1/gp/my-coupons", headers=andi)
    assert r.status_code == 200
    body = r.json()
    assert body["coupons"] == []
    assert body["verified"] == 0
    assert body["target"] == 30


def test_my_coupons_hides_other_members(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    body = client.get("/v1/gp/my-coupons", headers=andi).json()
    assert "owner_member_id" not in str(body)
    assert "transaction" not in str(body).lower()
