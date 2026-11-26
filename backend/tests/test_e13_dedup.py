"""E1.3 regression tests: tenant-scoped event dedup, registration_id / assessment_id dedup, webhook result contract."""
import pytest
from tests.test_central_prospect import db, ev  # reuse the repo fixture + event builder


def test_same_event_id_in_other_tenant_is_not_a_duplicate(db):
    from app.services.central_prospect import persist_inbound
    a = persist_inbound(db, ev(event_id="EVT-SHARED", member_id="ptn_A"))
    b = persist_inbound(db, ev(event_id="EVT-SHARED", member_id="ptn_B"))
    assert a["status"] == "PERSISTED"
    assert b["status"] == "PERSISTED", "event_id from another tenant must not be ignored as duplicate"


def test_duplicate_registration_id_same_tenant_is_ignored(db):
    from app.services.central_prospect import persist_inbound
    first = persist_inbound(db, ev(event_id="EVT-R1", event_type="WEBINAR_REGISTERED",
                                   member_id="ptn_A", registration_id="REG-X1"))
    second = persist_inbound(db, ev(event_id="EVT-R2", event_type="WEBINAR_REGISTERED",
                                    member_id="ptn_A", registration_id="REG-X1"))
    assert first["status"] == "PERSISTED"
    assert second["status"] == "DUPLICATE_IGNORED"


def test_duplicate_registration_id_other_tenant_is_separate(db):
    from app.services.central_prospect import persist_inbound
    persist_inbound(db, ev(event_id="EVT-R3", event_type="WEBINAR_REGISTERED", member_id="ptn_A", registration_id="REG-X2"))
    b = persist_inbound(db, ev(event_id="EVT-R4", event_type="WEBINAR_REGISTERED", member_id="ptn_B", registration_id="REG-X2"))
    assert b["status"] == "PERSISTED"


ASSESS_CONSENT = {"assessment_processing": True, "marketing_optional": False}


def test_duplicate_assessment_id_same_tenant_is_ignored(db):
    from app.services.central_prospect import persist_inbound
    persist_inbound(db, ev(event_id="EVT-A1", event_type="ASSESSMENT_COMPLETED", member_id="ptn_A", assessment_id="ASM-X1", consents=ASSESS_CONSENT))
    again = persist_inbound(db, ev(event_id="EVT-A2", event_type="ASSESSMENT_COMPLETED", member_id="ptn_A", assessment_id="ASM-X1", consents=ASSESS_CONSENT))
    assert again["status"] == "DUPLICATE_IGNORED"


def test_reference_id_is_not_a_prefix_match(db):
    """REG-X1 must not be treated as a duplicate of REG-X10 (exact quoted match)."""
    from app.services.central_prospect import persist_inbound
    persist_inbound(db, ev(event_id="EVT-P1", event_type="WEBINAR_REGISTERED", member_id="ptn_A", registration_id="REG-X10"))
    b = persist_inbound(db, ev(event_id="EVT-P2", event_type="WEBINAR_REGISTERED", member_id="ptn_A", registration_id="REG-X1"))
    assert b["status"] == "PERSISTED"
