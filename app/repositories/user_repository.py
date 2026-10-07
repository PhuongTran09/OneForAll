from datetime import UTC, datetime
from typing import Any

from app.models.user import User
from app.repositories.base import BaseRepository
from supabase import AsyncClient


class UserRepository(BaseRepository[User]):
    def __init__(self, client: AsyncClient | None = None, session: Any = None):
        super().__init__(User, "profiles", client)

    async def get_by_email(self, email: str) -> User | None:
        client = await self.get_client()
        res = await client.table("profiles").select("*").eq("email", email).execute()
        if not res.data:
            return None
        return User.model_validate(res.data[0])

    async def get_by_username(self, username: str) -> User | None:
        client = await self.get_client()
        res = await client.table("profiles").select("*").eq("username", username).execute()
        if not res.data:
            return None
        return User.model_validate(res.data[0])

    async def update_user(self, user: User) -> User:
        client = await self.get_client()
        payload = user.model_dump(exclude={"id"})
        payload["updated_at"] = datetime.now(UTC).isoformat()
        res = await client.table("profiles").update(payload).eq("id", user.id).execute()
        data = res.data[0] if res.data else user.model_dump()
        return User.model_validate(data)

    async def delete_user(self, user_or_id: User | str) -> None:
        user_id = user_or_id.id if isinstance(user_or_id, User) else str(user_or_id)
        await self.delete(user_id)
