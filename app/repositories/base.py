from typing import Any, Generic, TypeVar

from pydantic import BaseModel

import app.core.supabase as supabase_core
from supabase import AsyncClient

ModelType = TypeVar("ModelType", bound=BaseModel)


class BaseRepository(Generic[ModelType]):
    """Generic repository performing CRUD operations against Supabase tables."""

    def __init__(
        self,
        model: type[ModelType],
        table_name: str,
        client: AsyncClient | None = None,
    ):
        self.model = model
        self.table_name = table_name
        self._client = client

    async def get_client(self) -> AsyncClient:
        if self._client is not None:
            return self._client
        return await supabase_core.get_async_supabase_client()

    async def get_by_id(self, id: Any) -> ModelType | None:
        client = await self.get_client()
        res = await client.table(self.table_name).select("*").eq("id", str(id)).execute()
        if not res.data:
            return None
        return self.model.model_validate(res.data[0])

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        client = await self.get_client()
        res = (
            await client.table(self.table_name)
            .select("*")
            .range(skip, skip + limit - 1)
            .execute()
        )
        return [self.model.model_validate(row) for row in res.data or []]

    async def create(self, obj: ModelType | dict[str, Any]) -> ModelType:
        client = await self.get_client()
        data = obj.model_dump() if isinstance(obj, BaseModel) else obj
        res = await client.table(self.table_name).insert(data).execute()
        result_data = res.data[0] if res.data else data
        return self.model.model_validate(result_data)

    async def update(self, id: Any, data: dict[str, Any]) -> ModelType | None:
        client = await self.get_client()
        res = await client.table(self.table_name).update(data).eq("id", str(id)).execute()
        if not res.data:
            return None
        return self.model.model_validate(res.data[0])

    async def delete(self, id: Any) -> None:
        client = await self.get_client()
        await client.table(self.table_name).delete().eq("id", str(id)).execute()
