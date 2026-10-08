import json
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.deps import OptionalUserDep, SessionDep
from app.schemas.job import JobAccepted, JobCreate
from app.services.format_detector import (
    detect_format,
    is_conversion_supported,
    normalize_format,
)
from app.services.job_service import job_service
from app.services.storage_service import storage_service

router = APIRouter(tags=["Convert File"])


@router.post(
    "/convert-file",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Tạo Job chuyển đổi file (multipart/form-data)",
    description=(
        "Tải lên file trực tiếp hoặc cung cấp input_key để tạo background job chuyển đổi. "
        "Hệ thống tự động nhận diện định dạng nguồn (MIME type, extension, file signature) "
        "mà không yêu cầu gửi tham số 'from'."
    ),
)
@router.post(
    "/convert",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Tạo Job chuyển đổi file (multipart/form-data)",
    description=(
        "Tải lên file trực tiếp hoặc cung cấp input_key để tạo background job chuyển đổi. "
        "Hệ thống tự động nhận diện định dạng nguồn (MIME type, extension, file signature) "
        "mà không yêu cầu gửi tham số 'from'."
    ),
)
async def create_convert_file_job(
    session: SessionDep,
    to: Annotated[
        str,
        Form(
            description="Định dạng đích cần chuyển sang (ví dụ: pdf, svg, docx, png, csv, webp)"
        ),
    ],
    file: Annotated[
        UploadFile | None,
        File(description="File tài liệu hoặc hình ảnh cần chuyển đổi"),
    ] = None,
    input_key: Annotated[
        str | None,
        Form(
            description="Hoặc input_key của file đã upload trước đó lên Cloudflare R2"
        ),
    ] = None,
    from_format: Annotated[
        str | None,
        Form(
            alias="from",
            description="Định dạng nguồn (tùy chọn; hệ thống sẽ tự động nhận diện từ file tải lên).",
        ),
    ] = None,
    options: Annotated[
        str | None,
        Form(
            description='JSON chuỗi các tùy chọn nâng cao (ví dụ: {"title": "Báo cáo"})'
        ),
    ] = None,
    current_user: OptionalUserDep = None,
):
    if not file and not input_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vui lòng tải lên file hoặc cung cấp input_key.",
        )

    job_id = str(uuid4())
    resolved_from: str | None = None

    if file:
        header = await file.read(4096)
        if not header:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File tải lên bị rỗng.",
            )
        await file.seek(0)

        # Tự động detect format dựa trên file upload (ưu tiên MIME type + extension + magic bytes)
        detected = detect_format(
            content=header,
            filename=file.filename,
            content_type=file.content_type,
        )
        if not detected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Không thể xác định định dạng của file tải lên. Vui lòng kiểm tra lại file.",
            )
        resolved_from = detected

        # Định dạng key chuẩn theo thiết kế: uploads/{job_id}/original.ext
        safe_ext = resolved_from
        target_key = f"uploads/{job_id}/original.{safe_ext}"
        storage_service.upload_fileobj(
            fileobj=file.file,
            key=target_key,
            content_type=file.content_type,
        )
        input_key = target_key

    elif input_key:
        # Trường hợp sử dụng input_key đã upload sẵn
        detected = detect_format(filename=input_key) or (
            normalize_format(from_format) if from_format else None
        )
        if not detected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Không thể xác định định dạng nguồn từ input_key. Vui lòng cung cấp tham số 'from'.",
            )
        resolved_from = detected

    if not resolved_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể xác định định dạng nguồn của file.",
        )

    target_to = normalize_format(to)
    if not target_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vui lòng chỉ định định dạng đích 'to'.",
        )

    # Validate định dạng trước khi enqueue Celery job
    if not is_conversion_supported(resolved_from, target_to):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Định dạng chuyển đổi từ '{resolved_from}' sang '{target_to}' hiện chưa được hỗ trợ.",
        )

    operation = f"{resolved_from}-to-{target_to}"

    parsed_options: dict = {}
    if options:
        try:
            parsed_options = json.loads(options)
        except json.JSONDecodeError:
            parsed_options = {}

    user_id = str(current_user.id) if current_user else "anonymous"

    job = await job_service.create_and_enqueue(
        session=session,
        user=current_user,
        payload=JobCreate(
            id=job_id,
            user_id=user_id,
            type="convert_file",
            input_key=input_key,
            metadata={
                "from": resolved_from,
                "to": target_to,
                "operation": operation,
                "options": parsed_options,
            },
        ),
    )

    return JobAccepted(
        job_id=job.id,
        status=job.status,
    )
