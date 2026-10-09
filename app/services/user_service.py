from typing import Any
from uuid import uuid4

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserAdminUpdate, UserCreate, UserProfileUpdate, UserUpdate


class UserService:
    def __init__(
        self,
        repository: UserRepository | None = None,
        session: Any = None,
    ):
        self.repository = repository or UserRepository()

    async def get_user_by_id(self, user_id: str) -> User:
        user = await self.repository.get_by_id(str(user_id))
        if not user:
            raise NotFoundException(detail=f"User with ID {user_id} not found")
        return user

    async def get_users(self, skip: int = 0, limit: int = 100) -> list[User]:
        return await self.repository.get_all(skip=skip, limit=limit)

    async def create_user(self, user_in: UserCreate) -> User:
        if user_in.email:
            existing_email = await self.repository.get_by_email(user_in.email)
            if existing_email:
                raise BadRequestException(detail="Email already registered")

        existing_username = await self.repository.get_by_username(user_in.username)
        if existing_username:
            raise BadRequestException(detail="Username already taken")

        uid = user_in.id or str(uuid4())
        user = User(
            id=uid,
            email=user_in.email,
            username=user_in.username,
            full_name=user_in.full_name,
            is_active=user_in.is_active if user_in.is_active is not None else True,
            is_superuser=user_in.is_superuser if user_in.is_superuser is not None else False,
        )
        return await self.repository.create(user)

    async def update_profile(self, user_id: str, profile_in: UserProfileUpdate) -> User:
        user = await self.get_user_by_id(user_id)

        if profile_in.username and profile_in.username != user.username:
            existing = await self.repository.get_by_username(profile_in.username)
            if existing:
                raise BadRequestException(detail="Username already taken")
            user.username = profile_in.username

        if profile_in.full_name is not None:
            user.full_name = profile_in.full_name

        return await self.repository.update_user(user)

    async def update_user(self, user_id: str, user_in: UserAdminUpdate | UserUpdate) -> User:
        user = await self.get_user_by_id(user_id)

        if user_in.email and user_in.email != user.email:
            existing = await self.repository.get_by_email(user_in.email)
            if existing:
                raise BadRequestException(detail="Email already in use")
            user.email = user_in.email

        if user_in.username and user_in.username != user.username:
            existing = await self.repository.get_by_username(user_in.username)
            if existing:
                raise BadRequestException(detail="Username already taken")
            user.username = user_in.username

        if user_in.full_name is not None:
            user.full_name = user_in.full_name

        if user_in.is_active is not None:
            user.is_active = user_in.is_active

        if user_in.is_superuser is not None:
            user.is_superuser = user_in.is_superuser

        return await self.repository.update_user(user)

    async def delete_user(self, user_id: str) -> None:
        user = await self.get_user_by_id(user_id)
        await self.repository.delete_user(user.id)


user_service = UserService()
