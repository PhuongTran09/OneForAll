from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import app.core.supabase as supabase_core
from app.models.job import Job, JobStatus
from supabase import AsyncClient


class JobRepository:
    def __init__(self, client: AsyncClient | None = None, session: Any = None):
        self._client = client

    async def _get_client(self) -> AsyncClient:
        if self._client is not None:
            return self._client
        return await supabase_core.get_async_supabase_client()

    async def create(
        self,
        *,
        job_id: str | None = None,
        user_id: str,
        type: str,
        input_key: str | None = None,
        metadata: dict | None = None,
    ) -> Job:
        client = await self._get_client()
        jid = job_id or str(uuid4())
        job_data = {
            "id": jid,
            "user_id": str(user_id),
            "type": type,
            "status": JobStatus.QUEUED.value,
            "progress": 0,
            "input_key": input_key,
            "metadata": metadata or {},
            "created_at": datetime.now(UTC).isoformat(),
        }
        res = await client.table("jobs").insert(job_data).execute()
        data = res.data[0] if res.data else job_data
        return Job.model_validate(data)

    async def get_for_user(self, job_id: str, user_id: str) -> Job | None:
        client = await self._get_client()
        res = (
            await client.table("jobs")
            .select("*")
            .eq("id", job_id)
            .eq("user_id", str(user_id))
            .execute()
        )
        if not res.data:
            return None
        return Job.model_validate(res.data[0])

    async def get(self, job_id: str) -> Job | None:
        client = await self._get_client()
        res = await client.table("jobs").select("*").eq("id", job_id).execute()
        if not res.data:
            return None
        return Job.model_validate(res.data[0])

    async def mark_processing(self, job: Job) -> Job:
        client = await self._get_client()
        started_at = datetime.now(UTC).isoformat()
        updates = {
            "status": JobStatus.PROCESSING.value,
            "started_at": started_at,
            "progress": max(job.progress, 1),
        }
        res = await client.table("jobs").update(updates).eq("id", job.id).execute()
        data = res.data[0] if res.data else {**job.model_dump(), **updates}
        return Job.model_validate(data)

    async def update_progress(self, job: Job, progress: int) -> Job:
        client = await self._get_client()
        updates = {"progress": max(0, min(100, progress))}
        res = await client.table("jobs").update(updates).eq("id", job.id).execute()
        data = res.data[0] if res.data else {**job.model_dump(), **updates}
        return Job.model_validate(data)

    async def mark_completed(
        self, job: Job, output_key: str | None, expires_at: datetime | None = None
    ) -> Job:
        client = await self._get_client()
        completed_at = datetime.now(UTC).isoformat()
        updates = {
            "status": JobStatus.COMPLETED.value,
            "progress": 100,
            "output_key": output_key,
            "completed_at": completed_at,
        }
        if expires_at is not None:
            updates["expires_at"] = (
                expires_at.isoformat()
                if isinstance(expires_at, datetime)
                else str(expires_at)
            )
        res = await client.table("jobs").update(updates).eq("id", job.id).execute()
        data = res.data[0] if res.data else {**job.model_dump(), **updates}
        return Job.model_validate(data)

    async def mark_failed(self, job: Job, error: str) -> Job:
        client = await self._get_client()
        updates = {
            "status": JobStatus.FAILED.value,
            "error": error,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        res = await client.table("jobs").update(updates).eq("id", job.id).execute()
        data = res.data[0] if res.data else {**job.model_dump(), **updates}
        return Job.model_validate(data)

    async def mark_cancelled(self, job: Job) -> Job:
        client = await self._get_client()
        updates = {
            "status": JobStatus.CANCELLED.value,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        res = await client.table("jobs").update(updates).eq("id", job.id).execute()
        data = res.data[0] if res.data else {**job.model_dump(), **updates}
        return Job.model_validate(data)

    async def mark_expired(self, job: Job) -> Job:
        client = await self._get_client()
        updates = {"status": JobStatus.EXPIRED.value}
        res = await client.table("jobs").update(updates).eq("id", job.id).execute()
        data = res.data[0] if res.data else {**job.model_dump(), **updates}
        return Job.model_validate(data)

    async def get_expired_jobs(self, now: datetime) -> list[Job]:
        """Fetch all completed jobs whose expires_at is earlier than or equal to now."""
        client = await self._get_client()
        res = (
            await client.table("jobs")
            .select("*")
            .eq("status", JobStatus.COMPLETED.value)
            .execute()
        )
        now_utc = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
        expired: list[Job] = []
        for item in res.data or []:
            job = Job.model_validate(item)
            if job.expires_at:
                exp = (
                    job.expires_at
                    if job.expires_at.tzinfo is not None
                    else job.expires_at.replace(tzinfo=UTC)
                )
                if exp <= now_utc:
                    expired.append(job)
        return expired
