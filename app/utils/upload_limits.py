from fastapi import HTTPException, UploadFile, status

from app.core.config import settings


async def validate_upload_size(file: UploadFile, max_bytes: int, category: str) -> None:
    """Count the actual uploaded file bytes and reject oversized files with HTTP 413."""
    if file.size is not None and file.size > max_bytes:
        raise _too_large(max_bytes, category)

    total = 0
    await file.seek(0)
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            await file.seek(0)
            raise _too_large(max_bytes, category)

    await file.seek(0)


def max_upload_bytes(category: str) -> int:
    limits = {
        "audio": settings.MAX_AUDIO_UPLOAD_BYTES,
        "image": settings.MAX_IMAGE_UPLOAD_BYTES,
        "background_removal": settings.MAX_BACKGROUND_REMOVAL_UPLOAD_BYTES,
        "document": settings.MAX_DOCUMENT_UPLOAD_BYTES,
        "video": settings.MAX_VIDEO_UPLOAD_BYTES,
    }
    return limits.get(category, settings.MAX_OTHER_UPLOAD_BYTES)


def _too_large(max_bytes: int, category: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail={
            "code": "upload_too_large",
            "category": category,
            "max_bytes": max_bytes,
            "message": f"File vượt quá giới hạn tải lên cho loại {category}.",
        },
    )
