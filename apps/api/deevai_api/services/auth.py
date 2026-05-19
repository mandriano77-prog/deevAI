"""Auth helpers — password hashing + JWT generation/verification.

Uses passlib (bcrypt) for passwords and python-jose for JWT.
Token claims:
  - sub: user_id
  - tid: tenant_id (canonical)
  - tenant_id: alias of `tid` for backward-compat (DEPRECATED)
  - role: 'owner' | 'member' | 'viewer'
  - exp: expiration timestamp
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from ..config import get_settings

JWT_ALGORITHM = "HS256"
JWT_TTL_DAYS = 30
PASSWORD_RESET_TTL_HOURS = 1
PASSWORD_RESET_PURPOSE = "pwd_reset"


def hash_password(plaintext: str) -> str:
    return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt()).decode()


def verify_password(plaintext: str, hashed: str) -> bool:
    return bcrypt.checkpw(plaintext.encode(), hashed.encode())


def create_access_token(*, user_id: str, tenant_id: str, role: str) -> str:
    settings = get_settings()
    payload: dict[str, Any] = {
        "sub": user_id,
        "tid": tenant_id,
        # DEPRECATED: tenant_id alias, remove after 2026-08.
        # Kept here so tokens issued post-uniformity stay readable by any
        # legacy code path that still reads `tenant_id` (e.g. external
        # debug tools). All in-tree code reads `tid` via
        # `deevai_api.deps.get_tenant_id`.
        "tenant_id": tenant_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_TTL_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.api_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.api_secret_key, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e
    return payload


def create_password_reset_token(*, user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "purpose": PASSWORD_RESET_PURPOSE,
        "exp": now + timedelta(hours=PASSWORD_RESET_TTL_HOURS),
        "iat": now,
    }
    return jwt.encode(payload, settings.api_secret_key, algorithm=JWT_ALGORITHM)


def decode_password_reset_token(token: str) -> str:
    """Return user_id if token is valid for password reset."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.api_secret_key, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e
    if payload.get("purpose") != PASSWORD_RESET_PURPOSE:
        raise ValueError("Invalid token purpose")
    user_id = payload.get("sub")
    if not user_id or not isinstance(user_id, str):
        raise ValueError("Invalid token subject")
    return user_id
