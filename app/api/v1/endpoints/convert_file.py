import json
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.deps import OptionalUserDep, SessionDep
from app.schemas.job import JobAccepted, JobCreate
from app.services.job_service import job_service
from app.services.storage_service import storage_service

router = APIRouter(tags=["Convert File"])


@router.post(
    "/convert-file",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Tạo Job chuyển đổi file (multipart/form-data)",
    description="Tải lên file trực tiếp hoặc cung cấp input_key để tạo background job chuyển đổi.",
)
@router.post(
    "/convert",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Tạo Job chuyển đổi file (multipart/form-data)",
    description="Tải lên file trực tiếp hoặc cung cấp input_key để tạo background job chuyển đổi.",
)
async def create_convert_file_job(
    session: SessionDep,
    to: Annotated[
        str,
        Form(
            description="Định dạng đích cần chuyển sang (ví dụ: pdf, svg, docx, png, csv)"
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
            description="Định dạng nguồn (ví dụ: docx, txt, png). Để trống sẽ tự đoán từ tên file.",
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
    resolved_from = from_format

    if file and file.filename:
        if not resolved_from and "." in file.filename:
            resolved_from = file.filename.rsplit(".", 1)[-1].lower()

        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File tải lên bị rỗng.",
            )

        # Định dạng key chuẩn theo thiết kế: uploads/{job_id}/original.ext
        safe_ext = resolved_from or "bin"
        target_key = f"uploads/{job_id}/original.{safe_ext}"
        storage_service.upload_bytes(
            data=content,
            key=target_key,
            content_type=file.content_type,
        )
        input_key = target_key

    if not resolved_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không xác định được định dạng nguồn. Vui lòng nhập tham số 'from'.",
        )

    target_to = to.strip().lower()
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
