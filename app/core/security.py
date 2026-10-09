"""Security module for Supabase JWT verification."""

from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import settings
from app.core.exceptions import UnauthorizedException


SUPABASE_JWKS_URL = (
    f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
)

_jwk_client = PyJWKClient(SUPABASE_JWKS_URL)


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """Verify Supabase JWT using either SUPABASE_JWT_SECRET (HS256) or Supabase JWKS (ES256/RS256)."""
    if not token:
        raise UnauthorizedException(detail="Token is required")

    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception as exc:
        raise UnauthorizedException(detail=f"Invalid token format: {exc!s}") from exc

    alg = unverified_header.get("alg", "ES256")

    # 1. Token sử dụng thuật toán đối xứng HMAC (HS256) - thường dùng trong test hoặc dự án cũ
    if alg == "HS256":
        if not settings.SUPABASE_JWT_SECRET:
            raise UnauthorizedException(
                detail="HS256 token verification is not configured on server (missing SUPABASE_JWT_SECRET)"
            )
        try:
            return jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_signature": True, "verify_exp": True, "verify_aud": False},
            )
        except jwt.ExpiredSignatureError as exc:
            raise UnauthorizedException(detail="Supabase JWT has expired") from exc
        except jwt.PyJWTError as exc:
            raise UnauthorizedException(detail=f"Invalid or expired Supabase JWT: {exc!s}") from exc

    # 2. Token sử dụng thuật toán bất đối xứng (ES256/RS256) từ Supabase Auth qua JWKS
    if alg in ("ES256", "RS256"):
        try:
            signing_key = _jwk_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience="authenticated",
                options={"verify_signature": True, "verify_exp": True},
            )
        except jwt.ExpiredSignatureError as exc:
            raise UnauthorizedException(
                detail="Supabase JWT has expired"
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise UnauthorizedException(
                detail=f"Invalid or expired Supabase JWT: {exc!s}"
            ) from exc
        except Exception as exc:
            raise UnauthorizedException(
                detail=f"Unable to verify Supabase JWT: {exc!s}"
            ) from exc

    raise UnauthorizedException(detail=f"Unsupported token algorithm: '{alg}'")