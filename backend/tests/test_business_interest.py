from app.services import central_prospect as cp
import pytest

def _ev(consents):
    return {"event_type": "BUSINESS_INTEREST", "event_id": "bi-1", "member_id": "m-biz",
            "lead": {"email": "tester@example.com", "name": "Tester"},
            "consents": consents, "notice_version": "v-draft", "attribution": {"source": "form"}}

def test_business_rejected_without_required_consent():
    with pytest.raises(cp.InboundError) as e:
        cp.validate_event(_ev({"marketing_optional": True}))
    assert e.value.code == "REJECTED_CONSENT"

def test_business_accepted_with_business_purpose():
    out = cp.validate_event(_ev({"business_interest_processing": True, "business_matching": True}))
    assert out["event_type"] == "BUSINESS_INTEREST"

def test_business_not_satisfied_by_partner_consent():
    with pytest.raises(cp.InboundError):
        cp.validate_event(_ev({"partner_contact": True}))

def test_prospect_type_business_and_old_unchanged():
    assert cp._prospect_type("BUSINESS_INTEREST") == "business"
    assert cp._prospect_type("PARTNER_INQUIRY") == "partner"
    assert cp._prospect_type("LEAD_SUBMITTED") == "lead"
