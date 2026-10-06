from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import UnauthorizedException
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import TokenPayload

reusable_oauth2 = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")
reusable_oauth2_optional = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login", auto_error=False
)

SessionDep = Annotated[AsyncSession, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]
OptionalTokenDep = Annotated[str | None, Depends(reusable_oauth2_optional)]


async def get_current_user(
    session: SessionDep,
    token: TokenDep,
) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except JWTError:
        raise UnauthorizedException(detail="Could not validate credentials")

    if not token_data.sub:
        raise UnauthorizedException(detail="Token missing subject")

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(int(token_data.sub))
    if not user:
        raise UnauthorizedException(detail="User not found")
    if not user.is_active:
        raise UnauthorizedException(detail="Inactive user")

    return user


async def get_current_user_optional(
    session: SessionDep,
    token: OptionalTokenDep,
) -> User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
        if not token_data.sub:
            return None
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(int(token_data.sub))
        if user and user.is_active:
            return user
    except Exception:  # noqa: BLE001
        return None
    return None


CurrentUserDep = Annotated[User, Depends(get_current_user)]
OptionalUserDep = Annotated[User | None, Depends(get_current_user_optional)]
