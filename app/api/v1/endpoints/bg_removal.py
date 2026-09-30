from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from app.services.bg_removal_service import bg_removal_service

router = APIRouter()


# Dùng hàm 'def' đồng bộ để FastAPI tự động chạy trên worker threadpool,
# tránh block main asyncio event loop khi đang xử lý ảnh
@router.post(
    "/remove-bg",
    summary="Tách nền ảnh với BiRefNet-Lite",
    description="Nhận vào một file ảnh (PNG, JPG, WEBP,...), tách nền và trả về ảnh PNG có nền trong suốt.",
    response_class=Response,
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "Ảnh đã tách nền thành công định dạng PNG trong suốt.",
        },
        400: {"description": "File không hợp lệ hoặc không phải ảnh."},
        500: {"description": "Lỗi xử lý ảnh nội bộ."},
    },
)
def remove_background(
    file: Annotated[UploadFile, File(description="File ảnh cần tách nền")],
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vui lòng tải lên file định dạng ảnh hợp lệ.",
        )

    try:
        # Đọc dữ liệu ảnh từ client
        image_bytes = file.file.read()
        output_png = bg_removal_service.remove_background(image_bytes)
        return Response(content=output_png, media_type="image/png")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi xử lý ảnh: {e!s}",
        ) from e
    finally:
        file.file.close()
