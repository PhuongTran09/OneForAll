import json
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

from app.api.deps import CurrentUserDep, SessionDep
from app.schemas.job import JobAccepted, JobCreate
from app.services.format_detector import detect_format
from app.services.job_service import job_service
from app.services.storage_service import storage_service

router = APIRouter(tags=["Media"])


@router.post(
    "/media/process",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Tạo Job xử lý video/audio/media (multipart/form-data)",
    description=(
        "Tải lên file video/audio trực tiếp, cung cấp input_file_key, hoặc cung cấp url "
        "(YouTube, TikTok, etc.) để tạo background job xử lý (transcode, extract-audio, thumbnail, download). "
        "Hỗ trợ định dạng multipart/form-data."
    ),
)
@router.post(
    "/video/process",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
@router.post(
    "/video/jobs",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
async def create_video_job(
    request: Request,
    session: SessionDep,
    current_user: CurrentUserDep,
    file: Annotated[
        UploadFile | None,
        File(description="File video hoặc audio cần xử lý"),
    ] = None,
    input_file_key: Annotated[
        str | None,
        Form(description="Hoặc input_file_key của file đã upload trước đó lên storage"),
    ] = None,
    input_key: Annotated[
        str | None,
        Form(description="Alias cho input_file_key"),
    ] = None,
    url: Annotated[
        str | None,
        Form(description="URL video (ví dụ: YouTube) nếu tải từ URL"),
    ] = None,
    operation: Annotated[
        str,
        Form(description="Thao tác: transcode, extract-audio, thumbnail, url_download, download"),
    ] = "transcode",
    params: Annotated[
        str | None,
        Form(description='JSON chuỗi tham số tùy chọn (ví dụ: {"format": "mp3", "time": "00:00:05"})'),
    ] = None,
    options: Annotated[
        str | None,
        Form(description="Alias cho params"),
    ] = None,
):
    resolved_op = operation
    resolved_key = input_file_key or input_key
    resolved_url = url
    raw_params: Any = params or options

    # Hỗ trợ backward-compatibility nếu client gửi application/json
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
            if isinstance(body, dict):
                resolved_op = body.get("operation", resolved_op)
                resolved_key = (
                    body.get("input_file_key")
                    or body.get("input_key")
                    or resolved_key
                )
                resolved_url = body.get("url", resolved_url)
                raw_params = body.get("params") or body.get("options") or raw_params
        except (json.JSONDecodeError, ValueError):
            pass

    job_id = str(uuid4())

    if file:
        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File tải lên bị rỗng.",
            )

        detected_ext = (
            detect_format(
                content=content,
                filename=file.filename,
                content_type=file.content_type,
            )
            or "mp4"
        )
        target_key = f"uploads/{job_id}/original.{detected_ext}"
        storage_service.upload_bytes(
            data=content,
            key=target_key,
            content_type=file.content_type,
        )
        resolved_key = target_key

    if resolved_key in ("", "string"):
        resolved_key = None
    if resolved_url in ("", "string"):
        resolved_url = None

    # Nếu xử lý từ URL và không upload file trực tiếp thì không gán key từ storage
    if resolved_url and not file:
        resolved_key = None

    if not resolved_key and not resolved_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either file, input_file_key, or url must be provided.",
        )

    parsed_params: dict[str, Any] = {}
    if isinstance(raw_params, dict):
        parsed_params = raw_params
    elif isinstance(raw_params, str) and raw_params.strip() and raw_params != "string":
        try:
            # Hỗ trợ cả trường hợp người dùng quên ngoặc nhọn JSON ví dụ '"format": "mp3"'
            trimmed = raw_params.strip()
            if not trimmed.startswith("{") and not trimmed.endswith("}") and ":" in trimmed:
                trimmed = f"{{{trimmed}}}"
            parsed_params = json.loads(trimmed)
            if not isinstance(parsed_params, dict):
                parsed_params = {}
        except json.JSONDecodeError:
            parsed_params = {}

    job = await job_service.create_and_enqueue(
        session=session,
        user=current_user,
        payload=JobCreate(
            id=job_id,
            user_id=str(current_user.id),
            type="video",
            input_key=resolved_key,
            metadata={
                "operation": resolved_op,
                "url": resolved_url,
                "options": parsed_params,
            },
        ),
    )
    return JobAccepted(
        job_id=job.id,
        status=job.status,
    )
