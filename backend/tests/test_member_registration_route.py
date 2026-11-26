"""HTTP: admin-only member registration endpoint (sponsor + WA/EMAIL channel)."""
from tests.test_api_phase1 import client, login  # noqa: F401 (pytest fixture)
from tests.test_gp_draw_routes import _seed_admin


def test_admin_can_set_registration(client):
    _seed_admin(client)
    admin = login(client, "seed-admin@example.test", "admin-pass-789")
    r = client.post("/v1/admin/member-registration", headers=admin, json={
        "member_email": "andi@example.test", "sponsor_name": "Sponsor Uji",
        "sponsor_ref": "4L-HTTP-1", "registration_channel": "WA", "reason": "uji http"})
    assert r.status_code == 200, r.text
    assert r.json()["registration_channel"] == "WA"


def test_member_cannot_call_registration(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.post("/v1/admin/member-registration", headers=andi, json={
        "member_email": "andi@example.test", "reason": "saya sendiri"})
    assert r.status_code == 403


def test_invalid_channel_is_422(client):
    _seed_admin(client)
    admin = login(client, "seed-admin@example.test", "admin-pass-789")
    r = client.post("/v1/admin/member-registration", headers=admin, json={
        "member_email": "andi@example.test", "registration_channel": "TELEGRAM", "reason": "x"})
    assert r.status_code == 422


def test_unknown_member_is_404(client):
    _seed_admin(client)
    admin = login(client, "seed-admin@example.test", "admin-pass-789")
    r = client.post("/v1/admin/member-registration", headers=admin, json={
        "member_email": "nobody@example.test", "reason": "x"})
    assert r.status_code == 404
