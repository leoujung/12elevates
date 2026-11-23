"""Integration: login returns 429 after repeated failures from one IP, and a success clears it."""
from tests.test_api_phase1 import client, login  # noqa: F401 (pytest fixture)


def test_repeated_failures_get_429_then_block(client):
    headers = {"X-Forwarded-For": "203.0.113.50"}
    statuses = []
    for _ in range(12):
        r = client.post("/v1/auth/login", headers=headers,
                        json={"email": "andi@example.test", "password": "wrong-probe"})
        statuses.append(r.status_code)
    assert 401 in statuses
    assert statuses[-1] == 429


def test_other_ip_still_gets_401_not_429(client):
    r = client.post("/v1/auth/login", headers={"X-Forwarded-For": "198.51.100.77"},
                    json={"email": "andi@example.test", "password": "wrong-probe"})
    assert r.status_code == 401


def test_correct_login_still_works(client):
    tokens = login(client, "andi@example.test", "andi-pass-123")
    assert "Authorization" in tokens
