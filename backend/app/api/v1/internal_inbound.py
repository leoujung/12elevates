"""Internal inbound intake route (E1.2). Called only by the Vercel/n8n intake path; authenticated by shared secret.

- Requires X-Internal-Key (constant-time compare). No key configured -> refuse (fail closed).
- Member JWTs are NOT accepted: this is service-to-service.
- Persistence failure returns 503 and never reports success.
"""
import hmac
import os

from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.services import central_prospect as cp


class InboundIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    event_type: str | None = None
    event_id: str | None = None
    member_id: str | None = None
    lead: dict | None = None
    consents: dict | None = None
    notice_version: str | None = None
    attribution: dict | None = None


def require_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("INTERNAL_SUPPRESSION_KEY", "")
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "inbound service not configured")
    if not x_internal_key or not hmac.compare_digest(x_internal_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid internal key")


def register_inbound_routes(app, get_db):
    @app.post("/v1/internal/inbound", status_code=200)
    def inbound(body: InboundIn, _=Depends(require_internal_key), db=Depends(get_db)):
        raw = body.model_dump()
        try:
            result = cp.persist_inbound(db, raw)
        except cp.InboundError as e:
            # Validation / consent rejections: nothing was written.
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"success": False, "status": e.code})
        except Exception:
            # Database failure: do NOT report success, do NOT enqueue. Detail is not returned.
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                {"success": False, "status": "PERSIST_FAILED"})
        return {"success": True, **result}
