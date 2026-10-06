from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.user import User
from app.repositories.job_repository import JobRepository
from app.schemas.job import JobCreate
from app.services.subscription_service import subscription_service
from app.services.task_queue_service import task_queue_service


class JobService:
    async def create_and_enqueue(
        self,
        *,
        session: AsyncSession,
        user: User | None = None,
        payload: JobCreate,
    ) -> Job:
        if user is not None:
            await subscription_service.ensure_can_create_job(user, payload.type)

        repo = JobRepository(session)
        job = await repo.create(
            job_id=payload.id,
            user_id=payload.user_id,
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
        self, *, session: AsyncSession, user: User | None = None, job_id: str
    ) -> Job | None:
        repo = JobRepository(session)
        job = await repo.get(job_id)
        if not job:
            return None
        if job.user_id == "anonymous":
            return job
        if user and job.user_id == str(user.id):
            return job
        return None


job_service = JobService()
