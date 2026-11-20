"""Core service: owner-scoped prospect access and consent-gated ingestion.

Rules enforced here (Architecture Map v1.0 Section 6 and 17):
- Every read/write of a prospect is scoped to the owning member.
- A prospect is not stored without a recorded consent for the stated purpose.
- Every write is audit-logged.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import AuditLog, ConsentRecord, Prospect


class ConsentRequired(Exception):
    pass


def ingest_prospect(db: Session, *, owner_member_id: str, name: str, source: str,
                    consent_purpose: str | None, consent_granted: bool,
                    whatsapp: str | None = None, email: str | None = None) -> Prospect:
    if not consent_purpose or not consent_granted:
        raise ConsentRequired("prospect cannot be stored without recorded consent")

    prospect = Prospect(owner_member_id=owner_member_id, name=name, source=source,
                        whatsapp=whatsapp, email=email)
    db.add(prospect)
    db.flush()
    db.add(ConsentRecord(prospect_id=prospect.id, purpose=consent_purpose, granted=True))
    db.add(AuditLog(actor_member_id=owner_member_id, action="prospect.created", target=prospect.id))
    db.commit()
    return prospect


def get_prospect_for_member(db: Session, *, member_id: str, prospect_id: str) -> Prospect | None:
    """Returns the prospect only if it belongs to member_id. Otherwise None (never leaks existence)."""
    stmt = select(Prospect).where(Prospect.id == prospect_id, Prospect.owner_member_id == member_id)
    return db.execute(stmt).scalar_one_or_none()


def list_prospects_for_member(db: Session, *, member_id: str) -> list[Prospect]:
    stmt = select(Prospect).where(Prospect.owner_member_id == member_id).order_by(Prospect.created_at)
    return list(db.execute(stmt).scalars())
