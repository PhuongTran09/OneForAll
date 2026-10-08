import json
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

from app.api.deps import CurrentUserDep, SessionDep
from app.schemas.job import JobAccepted, JobCreate
from app.services.format_detector import detect_format
from app.services.job_service import job_service
from app.services.storage_service import storage_service

router = APIRouter(prefix="/image", tags=["Image"])


@router.post(
    "/process",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Tạo Job xử lý ảnh (multipart/form-data)",
    description=(
        "Tải lên file ảnh trực tiếp hoặc cung cấp input_key để tạo background job xử lý ảnh "
        "(nén, đổi kích thước, cắt, xóa nền, v.v.). Hỗ trợ định dạng multipart/form-data."
    ),
)
async def create_image_process_job(
    request: Request,
    session: SessionDep,
    current_user: CurrentUserDep,
    file: Annotated[
        UploadFile | None,
        File(description="File ảnh cần xử lý (tùy chọn nếu đã cung cấp input_key)"),
    ] = None,
    input_key: Annotated[
        str | None,
        Form(description="Hoặc input_key của file đã upload trước đó lên storage"),
    ] = None,
    operation: Annotated[
        str,
        Form(description="Thao tác xử lý: compress, resize, crop, remove_background"),
    ] = "compress",
    options: Annotated[
        str | None,
        Form(description='JSON chuỗi các tùy chọn (ví dụ: {"quality": 90, "width": 800})'),
    ] = None,
):
    resolved_op = operation
    resolved_input_key = input_key
    raw_options: Any = options

    # Hỗ trợ backward-compatibility nếu client gửi application/json
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
            if isinstance(body, dict):
                resolved_op = body.get("operation", resolved_op)
                resolved_input_key = body.get("input_key", resolved_input_key)
                raw_options = body.get("options", raw_options)
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
            or "png"
        )
        target_key = f"uploads/{job_id}/original.{detected_ext}"
        storage_service.upload_bytes(
            data=content,
            key=target_key,
            content_type=file.content_type,
        )
        resolved_input_key = target_key

    if not resolved_input_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vui lòng tải lên file ảnh hoặc cung cấp input_key.",
        )

    parsed_options: dict[str, Any] = {}
    if isinstance(raw_options, dict):
        parsed_options = raw_options
    elif isinstance(raw_options, str) and raw_options.strip():
        try:
            parsed_options = json.loads(raw_options)
        except json.JSONDecodeError:
            parsed_options = {}

    job = await job_service.create_and_enqueue(
        session=session,
        user=current_user,
        payload=JobCreate(
            id=job_id,
            user_id=str(current_user.id),
            type="image_process",
            input_key=resolved_input_key,
            metadata={
                "operation": resolved_op,
                "options": parsed_options,
            },
        ),
    )
    return JobAccepted(
        job_id=job.id,
        status=job.status,
    )
