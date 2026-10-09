from typing import Annotated, Any

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import verify_supabase_jwt
from app.models.user import User
from app.repositories.user_repository import UserRepository

# HTTPBearer scheme for OpenAPI Docs / Swagger
security_bearer = HTTPBearer(auto_error=False)


async def get_token_from_header(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer),
    authorization: str | None = Header(default=None),
) -> str | None:
    if credentials and credentials.credentials:
        return credentials.credentials
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return None


async def get_current_user(
    token: str | None = Depends(get_token_from_header),
) -> User:
    """Verifies Supabase JWT and retrieves current User profile."""
    if not token:
        raise UnauthorizedException(detail="Not authenticated")

    payload = verify_supabase_jwt(token)
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedException(detail="Token missing subject (user_id)")

    repo = UserRepository()
    user = await repo.get_by_id(str(user_id))
    if not user:
        # Auto-provision profile linked to auth.users.id
        email = payload.get("email")
        metadata = payload.get("user_metadata", {})
        username = (
            metadata.get("username")
            or (email.split("@")[0] if email else f"user_{str(user_id)[:8]}")
        )
        full_name = metadata.get("full_name") or metadata.get("name")
        is_superuser = bool(
            payload.get("app_metadata", {}).get("is_superuser", False)
            or payload.get("role") == "service_role"
        )
        user = User(
            id=str(user_id),
            email=email,
            username=username,
            full_name=full_name,
            is_active=True,
            is_superuser=is_superuser,
        )
        user = await repo.create(user)

    if not user.is_active:
        raise UnauthorizedException(detail="Inactive user")

    return user


async def get_current_user_optional(
    token: str | None = Depends(get_token_from_header),
) -> User | None:
    """Optional auth dependency: returns User if valid token present, else None."""
    if not token:
        return None
    try:
        return await get_current_user(token)
    except Exception:  # noqa: BLE001
        return None


async def require_superuser(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Dependency verifying that the authenticated user has superuser privileges."""
    if not current_user.is_superuser:
        raise ForbiddenException(detail="Superuser access required")
    return current_user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentUserDep = CurrentUser

OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
OptionalUserDep = OptionalUser


def require_auth_if_enabled(flag_attr: str):
    """Dependency that enforces auth only when settings.<flag_attr> is True.

    If flag is True: requires Bearer token, raises 401 if missing/invalid.
    If flag is False: allows anonymous requests, returns User if valid token or None.
    """
    async def _dependency(
        token: str | None = Depends(get_token_from_header),
    ) -> User | None:
        if getattr(settings, flag_attr, False):
            return await get_current_user(token)
        return await get_current_user_optional(token)

    return _dependency


MediaAuthDep = Annotated[User | None, Depends(require_auth_if_enabled("AUTH_REQUIRED_MEDIA"))]
ImageAuthDep = Annotated[User | None, Depends(require_auth_if_enabled("AUTH_REQUIRED_IMAGE"))]
ConvertAuthDep = Annotated[User | None, Depends(require_auth_if_enabled("AUTH_REQUIRED_CONVERT"))]
JobAuthDep = Annotated[User | None, Depends(require_auth_if_enabled("AUTH_REQUIRED_JOBS"))]
DownloadAuthDep = Annotated[User | None, Depends(require_auth_if_enabled("AUTH_REQUIRED_DOWNLOAD"))]

# Superuser alias
SuperuserDep = Annotated[User, Depends(require_superuser)]

# Backwards compatibility dummy dependency
SessionDep = Annotated[Any, Depends(lambda: None)]
