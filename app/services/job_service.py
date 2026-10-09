from typing import Any

from app.models.job import Job
from app.models.user import User
from app.repositories.job_repository import JobRepository
from app.schemas.job import JobCreate
from app.services.subscription_service import subscription_service
from app.services.task_queue_service import task_queue_service


class JobService:
    def __init__(self, repository: JobRepository | None = None):
        self.repository = repository or JobRepository()

    async def create_and_enqueue(
        self,
        *,
        session: Any = None,
        user: User | None = None,
        payload: JobCreate,
    ) -> Job:
        if user is not None:
            await subscription_service.ensure_can_create_job(user, payload.type)

        job = await self.repository.create(
            job_id=payload.id,
            user_id=str(payload.user_id),
            type=payload.type,
            input_key=payload.input_key,
            metadata=payload.metadata,
        )

        task_queue_service.enqueue_job(
            job_id=job.id,
            job_type=job.type,
            metadata=job.job_metadata,
        )
        return job

    async def get_for_user(
        self,
        *,
        session: Any = None,
        user: User | None = None,
        job_id: str,
    ) -> Job | None:
        job = await self.repository.get(job_id)
        if not job:
            return None
        return job


job_service = JobService()
