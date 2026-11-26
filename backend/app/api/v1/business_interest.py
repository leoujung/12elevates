"""Public Business-interest intake (staging). Referral-only, consent-gated.

- POST /v1/inbound/business-interest
- Requires a valid referral code = a members.sponsor_ref of an existing member.
  No referral, or unknown referral -> 422, nothing written.
- Consent business_interest_processing must be true (checked in validate_event).
- Writes ONLY through central_prospect.persist_inbound (same transaction, suppression,
  consent ledger, provenance, audit).
- Member ownership = the referring member (never a default account).
- Rate limit / CORS: CORS is already limited to 12elevates.com origins in routes.py.
"""
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.services import central_prospect as cp


class BusinessInterestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    referral_code: str
    name: str | None = None
    email: str | None = None
    whatsapp: str | None = None
    notice_version: str
    consent_business_interest: bool
    consent_business_matching: bool = False
    consent_business_followup: bool = False
    event_id: str


def _resolve_referrer(db, code: str):
    if not code or len(code) > 100:
        return None
    row = db.execute(
        text("select id from members where sponsor_ref = :c limit 1"), {"c": code.strip()}
    ).first()
    return str(row[0]) if row else None


def register_business_interest_routes(app, get_db):
    @app.post("/v1/inbound/business-interest", status_code=200)
    def business_interest(body: BusinessInterestIn, db=Depends(get_db)):
        referrer = _resolve_referrer(db, body.referral_code)
        if referrer is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                {"success": False, "status": "INVALID_REFERRAL"})
        consents = {"business_interest_processing": body.consent_business_interest,
                    "business_matching": body.consent_business_matching,
                    "business_followup": body.consent_business_followup}
        raw = {
            "event_type": "BUSINESS_INTEREST",
            "event_id": body.event_id,
            "member_id": referrer,
            "lead": {"name": body.name, "email": body.email, "whatsapp": body.whatsapp},
            "consents": consents,
            "notice_version": body.notice_version,
            "attribution": {"source": "business_form", "referral_code": body.referral_code},
        }
        try:
            result = cp.persist_inbound(db, raw)
        except cp.InboundError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"success": False, "status": e.code})
        except Exception:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                {"success": False, "status": "PERSIST_FAILED"})
        return {"success": True, **result}
