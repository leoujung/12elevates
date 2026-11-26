"""Integration: Phase 4 admin read endpoints. Admin 200, member 403, no writes."""
from tests.test_api_phase1 import client, login  # noqa: F401 (pytest fixture)
from tests.test_gp_draw_routes import _seed_admin


def test_admin_can_read_phase4_views(client):
    _seed_admin(client)
    admin = login(client, "seed-admin@example.test", "admin-pass-789")
    for path in ["/v1/admin/gp/cycles", "/v1/admin/gp/coupons/pending",
                 "/v1/admin/gp/prizes", "/v1/admin/gp/audit-log"]:
        r = client.get(path, headers=admin)
        assert r.status_code == 200, (path, r.status_code)


def test_member_is_refused_on_every_phase4_view(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    for path in ["/v1/admin/gp/cycles", "/v1/admin/gp/coupons/pending",
                 "/v1/admin/gp/prizes", "/v1/admin/gp/audit-log"]:
        r = client.get(path, headers=andi)
        assert r.status_code == 403, (path, r.status_code)


def test_anonymous_is_refused_on_phase4_views(client):
    for path in ["/v1/admin/gp/cycles", "/v1/admin/gp/audit-log"]:
        r = client.get(path)
        assert r.status_code in (401, 403), (path, r.status_code)
