"""Business consent gate (Business Interest Consent v1.2, Appendix B).

Covers the release acceptance tests that can run without Postgres:
- Consent 3 (business_followup) is optional and never required to submit.
- Contact details are dropped unless Consent 3 is granted.
- Consent 1 or 2 alone never permits contact.
- Business intake stays closed (503) unless BUSINESS_INTAKE_ENABLED is set.
"""
import pytest

from app.services import central_prospect as cp


def _event(**over):
    base = {
        "event_type": "BUSINESS_INTEREST",
        "event_id": "evt-1",
        "member_id": "member-a",
        "lead": {"name": "Calon", "email": "calon@example.com", "whatsapp": "081234567890"},
        "consents": {"business_interest_processing": True, "business_matching": True},
        "notice_version": "1.2",
        "attribution": {"source": "business_form", "referral_code": "REF123"},
    }
    base.update(over)
    return base


def test_followup_granted_keeps_contact():
    ev = cp.validate_event(_event(consents={
        "business_interest_processing": True,
        "business_matching": True,
        "business_followup": True,
    }))
    assert ev["email"] == "calon@example.com"
    assert ev["phone"] is not None


def test_followup_not_selected_drops_contact_and_still_accepts():
    # Consent 3 optional: submission must still succeed without it.
    ev = cp.validate_event(_event())
    assert ev["email"] is None
    assert ev["phone"] is None
    assert ev["consents"]["business_interest_processing"] is True


def test_followup_explicitly_false_drops_contact():
    ev = cp.validate_event(_event(consents={
        "business_interest_processing": True,
        "business_matching": True,
        "business_followup": False,
    }))
    assert ev["email"] is None and ev["phone"] is None


def test_consent_1_or_2_alone_never_grants_contact():
    # Consent 1 (processing) and 2 (matching) must not permit outreach.
    ev = cp.validate_event(_event(consents={
        "business_interest_processing": True,
        "business_matching": True,
    }))
    assert ev["email"] is None


def test_missing_interest_consent_is_rejected():
    with pytest.raises(cp.InboundError):
        cp.validate_event(_event(consents={"business_matching": True}))


def test_matching_required_by_form_is_enforced():
    # REQUIRED_EXTRA for BUSINESS_INTEREST includes business_matching.
    with pytest.raises(cp.InboundError):
        cp.validate_event(_event(consents={"business_interest_processing": True}))


def test_no_identifier_still_rejected_when_followup_granted():
    # Followup on without any usable channel: no contact to store -> rejected.
    with pytest.raises(cp.InboundError):
        cp.validate_event(_event(
            lead={"name": "X", "email": "", "whatsapp": ""},
            consents={"business_interest_processing": True,
                      "business_matching": True,
                      "business_followup": True},
        ))


def test_intake_closed_by_default(monkeypatch):
    from app.api.v1 import business_interest as bi
    monkeypatch.delenv("BUSINESS_INTAKE_ENABLED", raising=False)
    assert bi.business_intake_enabled() is False


def test_intake_open_only_when_flag_set(monkeypatch):
    from app.api.v1 import business_interest as bi
    monkeypatch.setenv("BUSINESS_INTAKE_ENABLED", "true")
    assert bi.business_intake_enabled() is True
