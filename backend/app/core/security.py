"""Authentication: password hashing and JWT issue/verify.

The signing secret is read from the environment (APP_JWT_SECRET). It is never
hard-coded and never printed. Tests inject a throwaway secret.
"""
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(hours=8)
_BCRYPT_MAX_BYTES = 72


def _encode_password(plain: str) -> bytes:
    raw = plain.encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        # Refuse instead of silently truncating: truncation would let two different
        # long passwords collide.
        raise ValueError("password exceeds 72 bytes")
    return raw


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_encode_password(plain), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_encode_password(plain), hashed.encode("ascii"))
    except ValueError:
        return False


def _secret() -> str:
    secret = os.environ.get("APP_JWT_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("APP_JWT_SECRET must be set (32+ chars)")
    return secret


def issue_token(member_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": member_id, "iat": now, "exp": now + TOKEN_TTL}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def member_id_from_token(token: str) -> str:
    """Raises jwt exceptions on invalid/expired tokens."""
    data = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    return data["sub"]
