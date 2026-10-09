from typing import Union

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import JobAuthDep, SessionDep
from app.schemas.job import JobPublicResponse, JobResponse
from app.services.job_service import job_service
from app.utils.download_token import verify_download_token

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get(
    "/{job_id}",
    response_model=Union[JobResponse, JobPublicResponse],
    summary="Get Job status",
)
async def get_job_status(
    job_id: str,
    session: SessionDep,
    current_user: JobAuthDep = None,
    token: str | None = Query(
        default=None,
        description="Download token cho job public/anonymous (tùy chọn, để nhận trạng thái job public)",
    ),
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

    is_public_job = job.user_id == "anonymous"

    if is_public_job:
        # Public job — anyone can check status, but return limited info
        # If token is valid, still only return JobPublicResponse (no storage paths)
        return JobPublicResponse.model_validate(job)

    # Private job — require authenticated user who owns it
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cần đăng nhập để xem trạng thái job này.",
        )
    if str(current_user.id) != job.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xem Job này.",
        )

    return job
