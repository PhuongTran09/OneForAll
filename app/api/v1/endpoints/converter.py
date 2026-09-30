import json
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException
from app.services.file_converter_service import file_converter_service

router = APIRouter(prefix="/convert", tags=["File & Document Converter"])


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Chuyển đổi chuỗi hex color như '#ffffff' sang tuple RGB (255, 255, 255)."""
    h = hex_str.strip().lstrip("#")
    if len(h) == 3:
        h = "".join([c * 2 for c in h])
    if len(h) != 6:
        return (255, 255, 255)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (255, 255, 255)


def _content_disposition_header(filename: str) -> dict[str, str]:
    """Tạo header Content-Disposition tuân thủ RFC 5987/6266 an toàn với ký tự Unicode/tiếng Việt."""
    return {"Content-Disposition": file_converter_service.build_content_disposition(filename)}


# -----------------------------------------------------------------------------
# 1. PNG sang SVG
# -----------------------------------------------------------------------------
@router.post(
    "/png-to-svg",
    summary="Chuyển đổi PNG sang SVG",
    description="Vector hóa ảnh PNG thành định dạng đồ họa vector SVG (vtracer).",
    response_class=Response,
    responses={
        200: {"content": {"image/svg+xml": {}}, "description": "File SVG kết quả."},
        400: {"description": "File hoặc tham số không hợp lệ."},
    },
)
def convert_png_to_svg(
    file: Annotated[UploadFile, File(description="File ảnh PNG cần chuyển sang SVG")],
    colormode: Annotated[
        Literal["color", "binary"],
        Form(description="Chế độ màu: 'color' (đa màu) hoặc 'binary' (đen trắng)"),
    ] = "color",
    mode: Annotated[
        Literal["spline", "polygon", "none"],
        Form(description="Thuật toán đường cong: 'spline', 'polygon', hoặc 'none'"),
    ] = "spline",
):
    try:
        content = file.file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File rỗng.")
        svg_bytes = file_converter_service.png_to_svg(content, colormode=colormode, mode=mode)
        filename = (
            file.filename.rsplit(".", 1)[0] + ".svg"
            if file.filename and "." in file.filename
            else "converted.svg"
        )
        return Response(
            content=svg_bytes,
            media_type="image/svg+xml",
            headers=_content_disposition_header(filename),
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    finally:
        file.file.close()


# -----------------------------------------------------------------------------
# 2. DOC / DOCX sang PDF
# -----------------------------------------------------------------------------
@router.post(
    "/doc-to-pdf",
    summary="Chuyển đổi DOC/DOCX sang PDF",
    description="Chuyển đổi file Microsoft Word (.docx) sang định dạng PDF giữ nguyên định dạng văn bản và bảng.",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "File PDF đã tạo."},
        400: {"description": "File tài liệu không hợp lệ."},
    },
)
def convert_doc_to_pdf(
    file: Annotated[UploadFile, File(description="File DOCX cần chuyển đổi sang PDF")],
):
    try:
        content = file.file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File rỗng.")
        pdf_bytes = file_converter_service.doc_to_pdf(content)
        filename = (
            file.filename.rsplit(".", 1)[0] + ".pdf"
            if file.filename and "." in file.filename
            else "converted.pdf"
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers=_content_disposition_header(filename),
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    finally:
        file.file.close()


# -----------------------------------------------------------------------------
# 3a. TXT sang PDF
# -----------------------------------------------------------------------------
@router.post(
    "/txt-to-pdf",
    summary="Chuyển đổi TXT sang PDF",
    description="Chuyển đổi file văn bản thô (.txt) sang PDF chuẩn A4, hỗ trợ đầy đủ font Tiếng Việt có dấu.",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "File PDF kết quả."},
        400: {"description": "Dữ liệu văn bản không hợp lệ."},
    },
)
def convert_txt_to_pdf(
    file: Annotated[UploadFile, File(description="File văn bản TXT")],
    title: Annotated[str, Form(description="Tiêu đề tài liệu PDF")] = "Tài liệu Text",
):
    try:
        content = file.file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File rỗng.")
        pdf_bytes = file_converter_service.txt_to_pdf(content, title=title)
        filename = (
            file.filename.rsplit(".", 1)[0] + ".pdf"
            if file.filename and "." in file.filename
            else "converted.pdf"
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers=_content_disposition_header(filename),
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    finally:
        file.file.close()


# -----------------------------------------------------------------------------
# 3b. TXT sang DOC / DOCX
# -----------------------------------------------------------------------------
@router.post(
    "/txt-to-doc",
    summary="Chuyển đổi TXT sang DOCX",
    description="Chuyển đổi file văn bản TXT sang định dạng tài liệu Microsoft Word (.docx).",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {}
            },
            "description": "File DOCX kết quả.",
        },
        400: {"description": "Dữ liệu không hợp lệ."},
    },
)
def convert_txt_to_doc(
    file: Annotated[UploadFile, File(description="File văn bản TXT")],
    title: Annotated[str | None, Form(description="Tiêu đề thêm vào đầu trang DOCX")] = None,
):
    try:
        content = file.file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File rỗng.")
        docx_bytes = file_converter_service.txt_to_doc(content, title=title)
        filename = (
            file.filename.rsplit(".", 1)[0] + ".docx"
            if file.filename and "." in file.filename
            else "converted.docx"
        )
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=_content_disposition_header(filename),
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    finally:
        file.file.close()


# -----------------------------------------------------------------------------
# 4a. XLSX sang CSV
# -----------------------------------------------------------------------------
@router.post(
    "/xlsx-to-csv",
    summary="Chuyển đổi XLSX sang CSV",
    description="Chuyển đổi bảng tính Excel sang định dạng CSV (mã hóa UTF-8 với BOM tương thích 100% tiếng Việt).",
    response_class=Response,
    responses={
        200: {"content": {"text/csv": {}}, "description": "File CSV kết quả."},
        400: {"description": "File Excel không hợp lệ."},
    },
)
def convert_xlsx_to_csv(
    file: Annotated[UploadFile, File(description="File bảng tính Excel (.xlsx)")],
    sheet_name: Annotated[
        str | None,
        Form(description="Tên sheet cần xuất (để trống sẽ lấy sheet đang hoạt động)"),
    ] = None,
):
    try:
        content = file.file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File rỗng.")
        csv_bytes = file_converter_service.xlsx_to_csv(content, sheet_name=sheet_name)
        filename = (
            file.filename.rsplit(".", 1)[0] + ".csv"
            if file.filename and "." in file.filename
            else "converted.csv"
        )
        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers=_content_disposition_header(filename),
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    finally:
        file.file.close()


# -----------------------------------------------------------------------------
# 4b. XLSX sang JSON
# -----------------------------------------------------------------------------
@router.post(
    "/xlsx-to-json",
    summary="Chuyển đổi XLSX sang JSON",
    description="Chuyển đổi bảng tính Excel sang JSON. Có thể tải về dưới dạng file hoặc nhận phản hồi JSON trực tiếp.",
    responses={
        200: {"description": "Dữ liệu JSON sau khi trích xuất từ Excel."},
        400: {"description": "File Excel không hợp lệ."},
    },
)
def convert_xlsx_to_json(
    file: Annotated[UploadFile, File(description="File bảng tính Excel (.xlsx)")],
    sheet_name: Annotated[
        str | None,
        Form(description="Tên sheet cần trích xuất (nếu all_sheets=False)"),
    ] = None,
    all_sheets: Annotated[
        bool,
        Form(description="Nếu True sẽ trả về JSON bao gồm tất cả các sheet"),
    ] = False,
    download: Annotated[
        bool,
        Query(description="Nếu True sẽ trả về file đính kèm .json để tải về máy"),
    ] = False,
):
    try:
        content = file.file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File rỗng.")
        json_data = file_converter_service.xlsx_to_json(
            content,
            sheet_name=sheet_name,
            all_sheets=all_sheets,
        )

        if download:
            json_bytes = json.dumps(json_data, ensure_ascii=False, indent=2).encode("utf-8")
            filename = (
                file.filename.rsplit(".", 1)[0] + ".json"
                if file.filename and "." in file.filename
                else "converted.json"
            )
            return Response(
                content=json_bytes,
                media_type="application/json; charset=utf-8",
                headers=_content_disposition_header(filename),
            )

        return JSONResponse(content=json_data)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    finally:
        file.file.close()


# -----------------------------------------------------------------------------
# 5. PNG sang JPG / JPEG
# -----------------------------------------------------------------------------
@router.post(
    "/png-to-jpg",
    summary="Chuyển đổi PNG sang JPG/JPEG",
    description="Chuyển đổi ảnh PNG sang JPG/JPEG. Tự động xử lý trong suốt (alpha) bằng màu nền tùy chọn.",
    response_class=Response,
    responses={
        200: {"content": {"image/jpeg": {}}, "description": "Ảnh JPEG kết quả."},
        400: {"description": "Ảnh hoặc tham số không hợp lệ."},
    },
)
def convert_png_to_jpg(
    file: Annotated[UploadFile, File(description="File ảnh PNG cần chuyển sang JPG")],
    quality: Annotated[
        int,
        Form(ge=1, le=100, description="Chất lượng nén ảnh JPEG (1 - 100)"),
    ] = 95,
    bg_color: Annotated[
        str,
        Form(description="Mã màu HEX cho nền thay thế vùng trong suốt (ví dụ: #ffffff)"),
    ] = "#ffffff",
):
    try:
        content = file.file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File rỗng.")
        rgb_color = _hex_to_rgb(bg_color)
        jpg_bytes = file_converter_service.png_to_jpg(content, quality=quality, bg_color=rgb_color)
        filename = (
            file.filename.rsplit(".", 1)[0] + ".jpg"
            if file.filename and "." in file.filename
            else "converted.jpg"
        )
        return Response(
            content=jpg_bytes,
            media_type="image/jpeg",
            headers=_content_disposition_header(filename),
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    finally:
        file.file.close()


# -----------------------------------------------------------------------------
# 6. JPG sang WEBP
# -----------------------------------------------------------------------------
@router.post(
    "/jpg-to-webp",
    summary="Chuyển đổi JPG/JPEG sang WEBP",
    description="Chuyển đổi ảnh JPG/JPEG sang định dạng WEBP siêu nhẹ cho web với chất lượng tùy biến.",
    response_class=Response,
    responses={
        200: {"content": {"image/webp": {}}, "description": "Ảnh WEBP kết quả."},
        400: {"description": "Ảnh không hợp lệ."},
    },
)
def convert_jpg_to_webp(
    file: Annotated[UploadFile, File(description="File ảnh JPG/JPEG cần chuyển sang WEBP")],
    quality: Annotated[
        int,
        Form(ge=1, le=100, description="Chất lượng ảnh WEBP (1 - 100)"),
    ] = 90,
    lossless: Annotated[
        bool,
        Form(description="Nếu True sẽ nén không suy hao chất lượng (lossless)"),
    ] = False,
):
    try:
        content = file.file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File rỗng.")
        webp_bytes = file_converter_service.jpg_to_webp(content, quality=quality, lossless=lossless)
        filename = (
            file.filename.rsplit(".", 1)[0] + ".webp"
            if file.filename and "." in file.filename
            else "converted.webp"
        )
        return Response(
            content=webp_bytes,
            media_type="image/webp",
            headers=_content_disposition_header(filename),
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    finally:
        file.file.close()
