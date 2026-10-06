from fastapi import APIRouter, status

from app.api.deps import CurrentUserDep, SessionDep
from app.schemas.job import JobAccepted, JobCreate
from app.schemas.tasks import VideoTaskRequest
from app.services.job_service import job_service

router = APIRouter(prefix="/video", tags=["Video"])


@router.post("/jobs", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_video_job(
    request: VideoTaskRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
):
    job = await job_service.create_and_enqueue(
        session=session,
        user=current_user,
        payload=JobCreate(
            user_id=str(current_user.id),
            type="video",
            input_key=request.input_file_key,
            metadata={
                "operation": request.operation,
                "options": request.params,
            },
        ),
    )
    return JobAccepted(
        job_id=job.id,
        status=job.status,
    )
