"""PSI-1 tests: source lifecycle rules (pure) and DB-backed service (SQLite in-memory, synthetic only)."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import psi_source  # noqa: F401  (registers tables on Base.metadata)
from app.models.core import Base, Member, Organization, AuditLog
from app.models.psi_source import PspSource, PspSourceAuditEvent, PspSourcePermissionProfile
from app.services import psi_source as svc
from app.services.psi_source_rules import (
    CATEGORIES, APPROVED, DRAFT, PENDING_REVIEW, REVOKED,
    SourceRuleError, SourceState, check_transition, can_ingest, can_member_view, validate_category,
)

ADMIN = "member-admin"
ANDI = "member-andi"
BUDI = "member-budi"


def _st(*, status: str = DRAFT, owner_member_id: str | None = ANDI, legal_record_ref: str | None = None,
        has_permission_profile: bool = False, approved_by: str | None = None,
        category: str = "INBOUND_LEADS"):
    return SourceState(category=category, status=status, owner_member_id=owner_member_id,
                       approved_by=approved_by, legal_record_ref=legal_record_ref,
                       has_permission_profile=has_permission_profile)


# ---------- pure rules ----------

def test_six_canonical_categories_exact():
    assert CATEGORIES == (
        "INBOUND_LEADS", "REFERRAL_NETWORK", "EVENTS_COMMUNITIES",
        "AUTHORIZED_BUSINESS_PARTNERSHIPS", "BUSINESS_DIRECTORIES_PUBLIC_SOURCES",
        "ADVERTISING_PLATFORMS",
    )
    assert len(CATEGORIES) == 6


@pytest.mark.parametrize("bad", ["", "inbound", "OTHER", "ADS", "inbound_leads"])
def test_unknown_category_refused(bad):
    with pytest.raises(SourceRuleError):
        validate_category(bad)


def test_state_machine_allowed_transitions():
    assert check_transition(_st(status=DRAFT), PENDING_REVIEW, ADMIN) is None
    assert check_transition(_st(status=PENDING_REVIEW), DRAFT, ADMIN) is None


@pytest.mark.parametrize("cur,tgt", [
    (DRAFT, APPROVED), (DRAFT, REVOKED), (PENDING_REVIEW, REVOKED),
    (APPROVED, DRAFT), (APPROVED, PENDING_REVIEW), (REVOKED, APPROVED), (REVOKED, DRAFT),
])
def test_illegal_transitions_refused(cur, tgt):
    with pytest.raises(SourceRuleError):
        check_transition(_st(status=cur, legal_record_ref="LR-1", has_permission_profile=True), tgt, ADMIN)


def test_approval_fail_closed_missing_legal_ref():
    with pytest.raises(SourceRuleError, match="legal_record_ref"):
        check_transition(_st(status=PENDING_REVIEW, has_permission_profile=True), APPROVED, ADMIN)


def test_approval_fail_closed_missing_profile():
    with pytest.raises(SourceRuleError, match="permission profile"):
        check_transition(_st(status=PENDING_REVIEW, legal_record_ref="LR-1"), APPROVED, ADMIN)


def test_approval_fail_closed_missing_approver():
    with pytest.raises(SourceRuleError, match="approver"):
        check_transition(_st(status=PENDING_REVIEW, legal_record_ref="LR-1", has_permission_profile=True),
                         APPROVED, None)


def test_owner_cannot_approve_own_source():
    with pytest.raises(SourceRuleError, match="separation"):
        check_transition(_st(status=PENDING_REVIEW, legal_record_ref="LR-1", has_permission_profile=True,
                             owner_member_id=ANDI), APPROVED, ANDI)


def test_approval_succeeds_with_all_controls():
    assert check_transition(_st(status=PENDING_REVIEW, legal_record_ref="LR-1", has_permission_profile=True,
                                owner_member_id=ANDI), APPROVED, ADMIN) is None


def test_only_approved_can_ingest_fail_closed():
    assert can_ingest(_st(status=APPROVED)) is True
    for s in (DRAFT, PENDING_REVIEW, REVOKED):
        assert can_ingest(_st(status=s)) is False


def test_member_view_is_owner_only():
    assert can_member_view(_st(owner_member_id=ANDI), ANDI) is True
    assert can_member_view(_st(owner_member_id=ANDI), BUDI) is False
    assert can_member_view(_st(owner_member_id=None), ANDI) is False  # central sources never member-visible


# ---------- DB-backed service ----------

@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    org = Organization(name="test org")
    s.add(org)
    s.flush()
    s.add_all([
        Member(id=ANDI, organization_id=org.id, email="andi@example.test", display_name="Andi"),
        Member(id=BUDI, organization_id=org.id, email="budi@example.test", display_name="Budi"),
        Member(id=ADMIN, organization_id=org.id, email="admin@example.test", display_name="Admin"),
    ])
    s.commit()
    yield s
    s.close()


def _approved_source(db, owner=ANDI, cat="INBOUND_LEADS"):
    src = svc.create_source(db, actor=ADMIN, category=cat, name="Synthetic src", owner_member_id=owner)
    svc.set_profile(db, actor=ADMIN, source_id=src.id, data_sharing_scope="NONE",
                    permitted_fields="name", permitted_purposes="follow_up", terms_ref="TERMS-SYN-1")
    svc.transition(db, actor=ADMIN, source_id=src.id, target=PENDING_REVIEW)
    svc.transition(db, actor="member-legal", source_id=src.id, target=APPROVED, legal_record_ref="LR-SYN-1")
    return src


def test_all_six_categories_creatable(db):
    for cat in CATEGORIES:
        src = svc.create_source(db, actor=ADMIN, category=cat, name=f"syn {cat}", owner_member_id=None)
        assert src.status == DRAFT and src.category == cat


def test_unknown_category_refused_and_audited(db):
    with pytest.raises(SourceRuleError):
        svc.create_source(db, actor=ADMIN, category="NOT_A_CATEGORY", name="x", owner_member_id=None)
    ev = db.execute(select(PspSourceAuditEvent)).scalars().all()
    assert any(e.outcome == "REFUSED" and e.action == "source.create" for e in ev)
    assert db.execute(select(PspSource)).scalars().all() == []


def test_unauthorized_source_cannot_be_activated(db):
    src = svc.create_source(db, actor=ADMIN, category="ADVERTISING_PLATFORMS", name="syn", owner_member_id=None)
    with pytest.raises(SourceRuleError):
        svc.transition(db, actor="member-legal", source_id=src.id, target=APPROVED, legal_record_ref="LR")
    db.refresh(src)
    assert src.status == DRAFT          # refused: no state change
    assert src.legal_record_ref is None  # refused: legal ref NOT written
    assert svc.ingest_gate(db, actor=ADMIN, source_id=src.id) is False


def test_refused_transition_does_not_mutate_legal_ref(db):
    src = svc.create_source(db, actor=ADMIN, category="INBOUND_LEADS", name="syn", owner_member_id=ANDI)
    with pytest.raises(SourceRuleError):
        svc.transition(db, actor=ADMIN, source_id=src.id, target=APPROVED, legal_record_ref="LR-EVIL")
    db.refresh(src)
    assert src.legal_record_ref is None and src.status == DRAFT


def test_full_lifecycle_and_ingest_gate(db):
    src = _approved_source(db)
    db.refresh(src)
    assert src.status == APPROVED and src.approved_by == "member-legal"
    assert svc.ingest_gate(db, actor="system", source_id=src.id) is True


def test_revoked_source_stops_ingestion(db):
    src = _approved_source(db)
    svc.transition(db, actor=ADMIN, source_id=src.id, target=REVOKED)
    db.refresh(src)
    assert src.status == REVOKED and src.revoked_at is not None
    assert svc.ingest_gate(db, actor="system", source_id=src.id) is False


def test_revoked_is_terminal(db):
    src = _approved_source(db)
    svc.transition(db, actor=ADMIN, source_id=src.id, target=REVOKED)
    with pytest.raises(SourceRuleError):
        svc.transition(db, actor=ADMIN, source_id=src.id, target=APPROVED, legal_record_ref="LR-2")


def test_member_isolation_in_listing(db):
    _approved_source(db, owner=ANDI)
    svc.create_source(db, actor=ADMIN, category="BUSINESS_DIRECTORIES_PUBLIC_SOURCES",
                      name="central", owner_member_id=None)
    andi = svc.list_sources_for_member(db, member_id=ANDI)
    budi = svc.list_sources_for_member(db, member_id=BUDI)
    assert len(andi) == 1 and andi[0].owner_member_id == ANDI
    assert budi == []
    assert all(s.owner_member_id is not None for s in andi)


def test_audit_records_allowed_and_refused(db):
    src = _approved_source(db)
    with pytest.raises(SourceRuleError):
        svc.transition(db, actor=ANDI, source_id=src.id, target=APPROVED, legal_record_ref="LR")
    ev = db.execute(select(PspSourceAuditEvent).where(PspSourceAuditEvent.source_id == src.id)).scalars().all()
    outcomes = {e.outcome for e in ev}
    assert {"ALLOWED", "REFUSED"} <= outcomes
    assert any(e.action == "source.create" for e in ev)


def test_ingest_refusal_is_audited(db):
    src = svc.create_source(db, actor=ADMIN, category="REFERRAL_NETWORK", name="syn", owner_member_id=ANDI)
    assert svc.ingest_gate(db, actor="system", source_id=src.id) is False
    ev = db.execute(select(PspSourceAuditEvent).where(
        PspSourceAuditEvent.action == "source.ingest")).scalars().all()
    assert ev and ev[-1].outcome == "REFUSED"


def test_psi_does_not_write_legacy_audit_logs(db):
    before = len(db.execute(select(AuditLog)).scalars().all())
    _approved_source(db)
    after = len(db.execute(select(AuditLog)).scalars().all())
    assert before == after  # PSI keeps its own audit table; legacy audit_logs untouched


def test_profile_one_per_source(db):
    src = svc.create_source(db, actor=ADMIN, category="INBOUND_LEADS", name="syn", owner_member_id=ANDI)
    svc.set_profile(db, actor=ADMIN, source_id=src.id, data_sharing_scope="NONE",
                    permitted_fields="a", permitted_purposes="b", terms_ref="T1")
    svc.set_profile(db, actor=ADMIN, source_id=src.id, data_sharing_scope="NONE",
                    permitted_fields="a2", permitted_purposes="b2", terms_ref="T2")
    profs = db.execute(select(PspSourcePermissionProfile)).scalars().all()
    assert len(profs) == 1 and profs[0].permitted_fields == "a2"
