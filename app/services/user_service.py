from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.security import get_password_hash
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, session: AsyncSession):
        self.repository = UserRepository(session)

    async def get_user_by_id(self, user_id: int) -> User:
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise NotFoundException(detail=f"User with ID {user_id} not found")
        return user

    async def get_users(self, skip: int = 0, limit: int = 100) -> list[User]:
        return await self.repository.get_all(skip=skip, limit=limit)

    async def create_user(self, user_in: UserCreate) -> User:
        existing_email = await self.repository.get_by_email(user_in.email)
        if existing_email:
            raise BadRequestException(detail="Email already registered")

        existing_username = await self.repository.get_by_username(user_in.username)
        if existing_username:
            raise BadRequestException(detail="Username already taken")

        user = User(
            email=user_in.email,
            username=user_in.username,
            full_name=user_in.full_name,
            hashed_password=get_password_hash(user_in.password),
            is_active=user_in.is_active if user_in.is_active is not None else True,
        )
        return await self.repository.create(user)

    async def update_user(self, user_id: int, user_in: UserUpdate) -> User:
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

        if user_in.password is not None:
            user.hashed_password = get_password_hash(user_in.password)

        if user_in.is_active is not None:
            user.is_active = user_in.is_active

        return await self.repository.update(user)

    async def delete_user(self, user_id: int) -> None:
        user = await self.get_user_by_id(user_id)
        await self.repository.delete(user)
