from datetime import datetime, timezone

import pytest

from app.services.draw_schedule import (
    COLLECTIVE_TARGET,
    DrawNotAllowed,
    DrawSchedule,
    enable_draw,
    status_for_member,
)

WHEN = datetime(2026, 12, 15, 19, 0, tzinfo=timezone.utc)


def _ready():
    return DrawSchedule(legal_review_approved=True, scheduled_at=WHEN, zoom_url="https://zoom.example/x")


def test_default_is_disabled_and_unavailable():
    s = status_for_member(DrawSchedule(), verified_coupons=0)
    assert s["available"] is False
    assert s["zoom_url"] is None
    assert "COUPON_TARGET_NOT_REACHED" in s["reasons"]


def test_cannot_enable_below_thirty_coupons():
    with pytest.raises(DrawNotAllowed) as e:
        enable_draw(_ready(), verified_coupons=COLLECTIVE_TARGET - 1)
    assert e.value.code == "COUPON_TARGET_NOT_REACHED"


def test_cannot_enable_without_legal_review():
    s = _ready()
    s.legal_review_approved = False
    with pytest.raises(DrawNotAllowed) as e:
        enable_draw(s, verified_coupons=30)
    assert e.value.code == "LEGAL_REVIEW_PENDING"


def test_cannot_enable_without_schedule():
    s = _ready()
    s.scheduled_at = None
    with pytest.raises(DrawNotAllowed) as e:
        enable_draw(s, verified_coupons=30)
    assert e.value.code == "SCHEDULE_REQUIRED"


def test_enable_succeeds_only_when_all_conditions_met():
    s = enable_draw(_ready(), verified_coupons=30)
    assert s.enabled is True
    view = status_for_member(s, verified_coupons=30)
    assert view["available"] is True
    assert view["zoom_url"] == "https://zoom.example/x"


def test_zoom_link_hidden_from_members_until_available():
    s = _ready()
    s.enabled = True
    view = status_for_member(s, verified_coupons=29)
    assert view["available"] is False
    assert view["zoom_url"] is None
