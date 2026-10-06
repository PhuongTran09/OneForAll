from fastapi import APIRouter, HTTPException, status

from app.api.deps import OptionalUserDep, SessionDep
from app.schemas.job import JobResponse
from app.services.job_service import job_service

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/{job_id}", response_model=JobResponse)
async def get_job_status(
    job_id: str,
    session: SessionDep,
    current_user: OptionalUserDep = None,
):
    job = await job_service.get_for_user(
        session=session,
        user=current_user,
        job_id=job_id,
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return job
