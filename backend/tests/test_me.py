"""GET /v1/me: the signed-in member's own profile (name comes from the server, not hardcoded)."""
from tests.test_api_phase1 import client, login  # noqa: F401 (pytest fixture)


def test_me_returns_own_profile(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    r = client.get("/v1/me", headers=andi)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "andi@example.test"
    assert body["display_name"]
    assert body["is_admin"] is False


def test_me_never_exposes_secrets(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    body = client.get("/v1/me", headers=andi).json()
    text = str(body).lower()
    assert "password" not in text
    assert "hash" not in text


def test_me_requires_token(client):
    r = client.get("/v1/me")
    assert r.status_code == 401
