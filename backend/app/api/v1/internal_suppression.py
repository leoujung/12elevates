"""Internal suppression routes: called only by the Vercel intake functions, authenticated by a shared secret.

- Write (opt-out) and check (intake) both require X-Internal-Key.
- The key is compared in constant time. If the server has no key configured, the routes refuse (fail closed).
- Member JWTs are NOT accepted here: these are service-to-service calls.
"""
import hmac
import os

from fastapi import Depends, HTTPException, Header, status
from pydantic import BaseModel


class SuppressIn(BaseModel):
    identifier: str
    source: str = "optout"


class SuppressCheckIn(BaseModel):
    identifier: str


def require_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("INTERNAL_SUPPRESSION_KEY", "")
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "suppression service not configured")
    if not x_internal_key or not hmac.compare_digest(x_internal_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid internal key")


def register_suppression_routes(app, get_db):
    from app.services import suppression as sup

    @app.post("/v1/internal/suppression", status_code=201)
    def suppress(body: SuppressIn, _=Depends(require_internal_key), db=Depends(get_db)):
        if not sup.normalize(body.identifier):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "INVALID_IDENTIFIER")
        added = sup.add(db, identifier=body.identifier, source=body.source)
        return {"ok": True, "newly_added": added}

    @app.post("/v1/internal/suppression/check")
    def check(body: SuppressCheckIn, _=Depends(require_internal_key), db=Depends(get_db)):
        if not sup.normalize(body.identifier):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "INVALID_IDENTIFIER")
        return {"suppressed": sup.is_suppressed(db, body.identifier)}
