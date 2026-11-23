"""CORS: only the official 12ELEVATE front-ends may call the API from a browser.

Tested with a real GET carrying an Origin header (a browser's simple cross-origin request).
Preflight OPTIONS is not used here because the route only registers GET; a 405 on OPTIONS
would not show whether the origin is allowed.
"""
from tests.test_api_phase1 import client, login  # noqa: F401 (pytest fixture)


def test_allowed_origin_gets_cors_header(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.get("/v1/gp/draw-schedule", headers={**andi, "Origin": "https://12elevates.com"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "https://12elevates.com"


def test_app_subdomain_origin_allowed(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.get("/v1/gp/draw-schedule", headers={**andi, "Origin": "https://app.12elevates.com"})
    assert r.headers.get("access-control-allow-origin") == "https://app.12elevates.com"


def test_foreign_origin_gets_no_cors_header(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.get("/v1/gp/draw-schedule", headers={**andi, "Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}
