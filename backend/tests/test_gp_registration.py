"""Sponsor + registration channel: admin-only, validated, audited, and hidden from /v1/me."""
import pytest
from sqlalchemy import select

from app.models.core import Member
from app.models.gold_pool import GpAuditLog
from app.services.gold_pool_registration import RegistrationError, set_member_registration
from tests.test_api_phase1 import client, login  # noqa: F401 (pytest fixture)
from tests.test_gp_draw_routes import _seed_admin


def _admin_session(client):
    _seed_admin(client)
    return login(client, "seed-admin@example.test", "admin-pass-789")


def test_sponsor_set_and_audited(client):
    _admin_session(client)
    s = client.app.state.session_factory()
    try:
        m = set_member_registration(s, actor_id="admin-x", member_email="andi@example.test",
                                    sponsor_name="Sponsor Uji", sponsor_ref="4L-TEST-001",
                                    registration_channel="WA", reason="form diterima via WA")
        assert m.sponsor_name == "Sponsor Uji" and m.registration_channel == "WA"
        log = s.execute(select(GpAuditLog).where(GpAuditLog.action == "MEMBER_REGISTRATION_SET")).scalars().all()
        assert log and "form diterima via WA" == log[-1].reason
        assert "Sponsor Uji" in log[-1].after_value
    finally:
        s.close()


def test_invalid_channel_rejected(client):
    _admin_session(client)
    s = client.app.state.session_factory()
    try:
        with pytest.raises(RegistrationError) as e:
            set_member_registration(s, actor_id="a", member_email="andi@example.test",
                                    sponsor_name=None, sponsor_ref=None,
                                    registration_channel="TELEGRAM", reason="x")
        assert e.value.code == "INVALID_CHANNEL"
    finally:
        s.close()


def test_reason_required(client):
    _admin_session(client)
    s = client.app.state.session_factory()
    try:
        with pytest.raises(RegistrationError) as e:
            set_member_registration(s, actor_id="a", member_email="andi@example.test",
                                    sponsor_name=None, sponsor_ref=None,
                                    registration_channel="EMAIL", reason="   ")
        assert e.value.code == "REASON_REQUIRED"
    finally:
        s.close()


def test_sponsor_never_exposed_to_member(client):
    _admin_session(client)
    s = client.app.state.session_factory()
    try:
        set_member_registration(s, actor_id="a", member_email="andi@example.test",
                                sponsor_name="Sponsor Rahasia", sponsor_ref="4L-SECRET",
                                registration_channel="EMAIL", reason="uji privasi")
    finally:
        s.close()
    andi = login(client, "andi@example.test", "andi-pass-123")
    body = client.get("/v1/me", headers=andi).json()
    text = str(body)
    assert "Sponsor Rahasia" not in text and "4L-SECRET" not in text


def test_member_cannot_set_own_sponsor_via_api(client):
    andi = login(client, "andi@example.test", "andi-pass-123")
    # Only admin routes exist for this; a member token must not be able to reach them.
    assert client.post("/v1/admin/transactions", headers=andi,
                       json={"transaction_id": "X", "member_email": "andi@example.test",
                             "tx_type": "NEW_PARTNER", "lp": 1, "verified_at": "2026-11-23T10:00:00+07:00"}
                       ).status_code == 403
