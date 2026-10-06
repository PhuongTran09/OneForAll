import mimetypes
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse, Response

from app.api.deps import CurrentUserDep, OptionalUserDep, SessionDep
from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.schemas.file import PresignedUrlRequest, PresignedUrlResponse
from app.services.storage_service import storage_service

router = APIRouter(prefix="/files", tags=["Files"])


@router.post("/presigned-upload-url", response_model=PresignedUrlResponse)
async def create_presigned_upload_url(
    request: PresignedUrlRequest,
    current_user: CurrentUserDep,
):
    return storage_service.create_presigned_upload_url(
        key=request.key,
        content_type=request.content_type,
        expires_in=request.expires_in,
    )


@router.post("/presigned-download-url", response_model=PresignedUrlResponse)
async def create_presigned_download_url(
    request: PresignedUrlRequest,
    current_user: CurrentUserDep,
):
    return storage_service.create_presigned_download_url(
        key=request.key,
        expires_in=request.expires_in,
    )


@router.get(
    "/{job_id}/download",
    response_model=PresignedUrlResponse,
    summary="Download converted result file by Job ID",
    description="Kiểm tra trạng thái Job và expires_at. Hỗ trợ tải trực tiếp binary file (?direct=true), chuyển hướng (?redirect=true), hoặc lấy link presigned URL.",
)
async def download_job_result_file(
    job_id: str,
    session: SessionDep,
    current_user: OptionalUserDep = None,
    redirect: bool = Query(
        default=False,
        description="Nếu True sẽ tự động chuyển hướng (HTTP 307) tới link download trực tiếp trên R2",
    ),
    direct: bool = Query(
        default=False,
        description="Nếu True sẽ tải file trực tiếp (binary stream) từ server mà không cần chuyển hướng sang R2",
    ),
):
    repo = JobRepository(session)
    job = await repo.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy Job hoặc bạn không có quyền truy cập.",
        )

    if job.user_id != "anonymous":
        if not current_user or job.user_id != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền truy cập file này.",
            )

    # 1. Kiểm tra đã hết hạn chưa
    now = datetime.now(UTC)
    expires_at = job.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if job.status == JobStatus.EXPIRED.value or (
        expires_at and expires_at <= now
    ):
        if job.status != JobStatus.EXPIRED.value:
            await repo.mark_expired(job)
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="File kết quả đã hết hạn (20 phút) và đã được dọn dẹp khỏi hệ thống.",
        )

    # 2. Kiểm tra trạng thái đã hoàn thành chưa
    if job.status != JobStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job chưa hoàn thành (trạng thái hiện tại: {job.status}).",
        )

    if not job.output_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy file kết quả của Job.",
        )

    # Tùy chọn 1: Tải trực tiếp file nhị phân không cần chuyển hướng
    if direct:
        file_bytes = storage_service.download_bytes(key=job.output_key)
        filename = job.output_key.split("/")[-1]
        media_type, _ = mimetypes.guess_type(filename)
        media_type = media_type or "application/octet-stream"
        return Response(
            content=file_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    # 3. Sinh presigned download URL
    presigned = storage_service.create_presigned_download_url(
        key=job.output_key,
        expires_in=900,
    )

    # Tùy chọn 2: Chuyển hướng (HTTP 307)
    if redirect:
        return RedirectResponse(
            url=presigned.url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )

    # Tùy chọn 3: Trả về JSON PresignedUrlResponse
    return presigned


@router.get("/r2/status", summary="Check Cloudflare R2 Connection Status")
async def check_r2_status(
    current_user: CurrentUserDep,
):
    return storage_service.test_connection()
