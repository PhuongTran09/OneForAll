"""Security module for Supabase JWT verification.

Custom password hashing, bcrypt, and custom access tokens have been removed
in favor of Supabase Auth.
"""

from typing import Any

import jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedException


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """Verify Supabase JWT token and extract payload claims (including sub=user_id)."""
    if not token:
        raise UnauthorizedException(detail="Token is required")

    # 1. If SUPABASE_JWT_SECRET is configured, verify HMAC signature
    if settings.SUPABASE_JWT_SECRET:
        try:
            return jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            raise UnauthorizedException(detail=f"Invalid or expired Supabase JWT: {exc!s}") from exc

    # 2. Decode claims without signature verification if secret is not set (e.g. dev/local mode)
    try:
        return jwt.decode(
            token,
            options={"verify_signature": False, "verify_aud": False},
        )
    except Exception as exc:
        raise UnauthorizedException(detail=f"Unable to parse token: {exc!s}") from exc
