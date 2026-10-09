import asyncio
import mimetypes
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse, StreamingResponse

from app.api.deps import CurrentUserDep, DownloadAuthDep, SessionDep
from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.schemas.file import PresignedUrlRequest, PresignedUrlResponse
from app.services.storage_service import storage_service
from app.utils.download_token import verify_download_token
from app.utils.filename import build_content_disposition
from app.utils.logger import logger

router = APIRouter(prefix="/files", tags=["Files"])


def _validate_safe_storage_key(key: str) -> None:
    if not key or not isinstance(key, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Object key cannot be empty.")
    normalized = key.replace("\\", "/")
    if ".." in normalized or normalized.startswith("/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid object key path (path traversal detected).",
        )


@router.post("/presigned-upload-url", response_model=PresignedUrlResponse)
async def create_presigned_upload_url(
    request: PresignedUrlRequest,
    current_user: CurrentUserDep,
):
    _validate_safe_storage_key(request.key)
    # Users can only upload to uploads/ namespace, not overwrite outputs/
    if not current_user.is_superuser:
        if request.key.startswith("outputs/"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Direct uploads to 'outputs/' namespace are not permitted.",
            )
        # Prevent uploading into other users' private namespace: uploads/<other_user_id>/...
        parts = request.key.split("/")
        if len(parts) >= 3 and parts[0] == "uploads" and parts[1] != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot upload into another user's namespace.",
            )

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
    _validate_safe_storage_key(request.key)
    if not current_user.is_superuser:
        allowed = False
        parts = request.key.split("/")
        # User can download their own uploads: uploads/<user_id>/...
        if len(parts) >= 2 and parts[0] == "uploads" and parts[1] == str(current_user.id):
            allowed = True
        elif request.key.startswith("outputs/"):
            # outputs/<job_id>/...: verify user owns the job
            if len(parts) >= 2:
                job_id = parts[1]
                repo = JobRepository()
                job = await repo.get(job_id)
                if job and job.user_id == str(current_user.id):
                    allowed = True
        elif request.key.startswith("uploads/"):
            # Generic uploads allowed only if not scoped to another user
            if len(parts) < 3:
                allowed = True

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to download this object.",
            )

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
    current_user: DownloadAuthDep = None,
    token: str | None = Query(
        default=None,
        description="Download token cho job public/anonymous (bắt buộc nếu job không cần đăng nhập)",
    ),
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
            detail="Không tìm thấy Job.",
        )

    # --- Access Control ---
    is_public_job = job.user_id == "anonymous"
    metadata = job.job_metadata or {}

    if is_public_job:
        # Public job: strictly require valid download token
        stored_hash = metadata.get("download_token_hash")
        if not token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Job public yêu cầu download token. Vui lòng cung cấp ?token=<download_token>.",
            )
        if not stored_hash or not verify_download_token(token, stored_hash):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Download token không hợp lệ hoặc đã hết hạn.",
            )
    else:
        # Private job: require authenticated user who owns the job
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cần đăng nhập để tải file của job này.",
            )
        if str(current_user.id) != job.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền tải file của Job này.",
            )

    # 1. Kiểm tra đã hết hạn chưa (TTL 3 phút)
    now = datetime.now(UTC)
    expires_at = job.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if job.status == JobStatus.EXPIRED.value or (
        expires_at and expires_at <= now
    ):
        # Dọn dẹp idempotent ngay khi phát hiện hết hạn
        if job.output_key:
            try:
                storage_service.delete_file(key=job.output_key)
            except Exception:
                pass
        try:
            await repo.delete(job.id)
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="File kết quả đã hết hạn (3 phút) và đã được dọn dẹp khỏi hệ thống.",
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

    # Xác định tiêu đề / tên file tải về mong muốn
    raw_ext = job.output_key.split(".")[-1] if "." in job.output_key else ""
    sub_opts = metadata.get("options") or {} if isinstance(metadata.get("options"), dict) else {}

    title_candidate = (
        metadata.get("title")
        or sub_opts.get("title")
        or metadata.get("filename")
        or sub_opts.get("filename")
        or (Path(metadata["original_filename"]).stem if metadata.get("original_filename") else None)
        or "result"
    )

    final_filename, content_disposition = build_content_disposition(
        title=str(title_candidate),
        ext=raw_ext,
        fallback="result",
    )

    # Tùy chọn 1: Tải trực tiếp file nhị phân qua stream
    # Khi stream thành công toàn bộ: xóa R2 output ngay và DELETE job khỏi database.
    # Nếu client disconnect / abort giữa chừng: giữ nguyên R2 output và DB job để user retry.
    if direct:
        media_type, _ = mimetypes.guess_type(final_filename)
        media_type = media_type or "application/octet-stream"

        output_key = job.output_key
        target_job_id = job.id

        async def stream_and_cleanup():
            download_completed = False
            try:
                for chunk in storage_service.download_stream(key=output_key):
                    yield chunk
                download_completed = True
            except (GeneratorExit, asyncio.CancelledError):
                logger.warning(
                    "[download-stream] Client disconnected / aborted download for job %s. Keeping file for retry.",
                    target_job_id,
                )
                raise
            except Exception as stream_err:
                logger.error(
                    "[download-stream] Stream error for job %s: %s. Keeping file for retry.",
                    target_job_id,
                    stream_err,
                )
                raise
            finally:
                if download_completed:
                    logger.info(
                        "[download-stream] File %s downloaded successfully. Cleaning up R2 output and DB job...",
                        output_key,
                    )
                    # 1. Delete output R2 ngay (idempotent)
                    try:
                        storage_service.delete_file(key=output_key)
                        logger.info("[download-stream] Deleted R2 output: %s", output_key)
                    except Exception as del_err:  # noqa: BLE001
                        logger.warning("[download-stream] Error deleting R2 output %s: %s", output_key, del_err)

                    # 2. DELETE job khỏi database (idempotent)
                    try:
                        repo_cleanup = JobRepository()
                        await repo_cleanup.delete(target_job_id)
                        logger.info("[download-stream] Deleted DB job: %s", target_job_id)
                    except Exception as del_job_err:  # noqa: BLE001
                        logger.warning("[download-stream] Error deleting DB job %s: %s", target_job_id, del_job_err)

        return StreamingResponse(
            stream_and_cleanup(),
            media_type=media_type,
            headers={
                "Content-Disposition": content_disposition,
            },
        )

    # 3. Sinh presigned download URL (hết hạn sau 3 phút) kèm ResponseContentDisposition
    presigned = storage_service.create_presigned_download_url(
        key=job.output_key,
        expires_in=180,
        response_content_disposition=content_disposition,
    )

    # Tùy chọn 2: Chuyển hướng (HTTP 307)
    if redirect:
        return RedirectResponse(
            url=presigned.url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )

    # Tùy chọn 3: Trả về JSON PresignedUrlResponse
    return presigned


@router.post(
    "/{job_id}/consumed",
    summary="Mark job output consumed and delete from R2 and DB",
    description="Xác nhận tải file thành công qua presigned URL. Hệ thống sẽ xóa ngay file kết quả trên R2 và xóa Job khỏi DB.",
)
async def mark_job_result_consumed(
    job_id: str,
    session: SessionDep,
    current_user: DownloadAuthDep = None,
    token: str | None = Query(
        default=None,
        description="Download token cho job public/anonymous (bắt buộc nếu job là public)",
    ),
):
    repo = JobRepository(session)
    job = await repo.get(job_id)
    if not job:
        return {"status": "ok", "message": "Job đã được dọn dẹp hoặc không tồn tại."}

    is_public_job = job.user_id == "anonymous"
    metadata = job.job_metadata or {}

    if is_public_job:
        stored_hash = metadata.get("download_token_hash")
        if not stored_hash or not token or not verify_download_token(token, stored_hash):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Job public yêu cầu download token hợp lệ để dọn dẹp.",
            )
    else:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cần đăng nhập để thao tác trên Job này.",
            )
        if str(current_user.id) != job.user_id and not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền thao tác trên Job này.",
            )

    if job.output_key:
        try:
            storage_service.delete_file(key=job.output_key)
            logger.info("[consumed] Deleted R2 output file: %s", job.output_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[consumed] Failed to delete R2 output %s: %s", job.output_key, exc)

    try:
        await repo.delete(job.id)
        logger.info("[consumed] Deleted DB job: %s", job.id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[consumed] Failed to delete DB job %s: %s", job.id, exc)

    return {"status": "ok", "message": f"Job {job_id} đã được dọn dẹp thành công."}


@router.get("/r2/status", summary="Check Cloudflare R2 Connection Status")
async def check_r2_status(
    current_user: CurrentUserDep,
):
    return storage_service.test_connection()
