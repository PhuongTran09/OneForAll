from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus


class JobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        job_id: str | None = None,
        user_id: str,
        type: str,
        input_key: str | None,
        metadata: dict,
    ) -> Job:
        job_kwargs: dict = {
            "user_id": user_id,
            "type": type,
            "input_key": input_key,
            "job_metadata": metadata,
            "status": JobStatus.QUEUED.value,
            "progress": 0,
        }
        if job_id:
            job_kwargs["id"] = job_id

        job = Job(**job_kwargs)
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def get_for_user(self, job_id: str, user_id: str) -> Job | None:
        result = await self.session.execute(
            select(Job).where(Job.id == job_id, Job.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get(self, job_id: str) -> Job | None:
        result = await self.session.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    async def mark_processing(self, job: Job) -> Job:
        job.status = JobStatus.PROCESSING.value
        job.started_at = datetime.now(UTC)
        job.progress = max(job.progress, 1)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def update_progress(self, job: Job, progress: int) -> Job:
        job.progress = max(0, min(100, progress))
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def mark_completed(
        self, job: Job, output_key: str | None, expires_at: datetime | None = None
    ) -> Job:
        job.status = JobStatus.COMPLETED.value
        job.progress = 100
        job.output_key = output_key
        job.completed_at = datetime.now(UTC)
        if expires_at is not None:
            job.expires_at = expires_at
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def mark_failed(self, job: Job, error: str) -> Job:
        job.status = JobStatus.FAILED.value
        job.error = error
        job.completed_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def mark_cancelled(self, job: Job) -> Job:
        job.status = JobStatus.CANCELLED.value
        job.completed_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def mark_expired(self, job: Job) -> Job:
        job.status = JobStatus.EXPIRED.value
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def get_expired_jobs(self, now: datetime) -> list[Job]:
        """Lấy tất cả các job completed mà thời gian expires_at <= now."""
        result = await self.session.execute(
            select(Job).where(
                Job.status == JobStatus.COMPLETED.value,
                Job.expires_at.is_not(None),
            )
        )
        all_jobs = list(result.scalars().all())
        now_utc = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
        expired: list[Job] = []
        for j in all_jobs:
            if j.expires_at:
                exp = (
                    j.expires_at
                    if j.expires_at.tzinfo is not None
                    else j.expires_at.replace(tzinfo=UTC)
                )
                if exp <= now_utc:
                    expired.append(j)
        return expired
