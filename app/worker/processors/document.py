import json
from typing import Any

from app.services.file_converter_service import file_converter_service
from app.worker.processors.base import BaseProcessor


class DocumentConvertProcessor(BaseProcessor):
    """
    Processor handling file and document format conversions:
    - PNG to SVG (VTracer vectorization)
    - DOCX to PDF (semantic HTML extraction + PDF rendering)
    - TXT to PDF & TXT to DOCX
    - XLSX to CSV & XLSX to JSON
    - PNG to JPG/JPEG
    - JPG to WEBP
    """

    def process(self, input_data: bytes, options: dict[str, Any]) -> tuple[bytes, str]:
        from_format = str(options.get("from", "")).lower().strip()
        to_format = str(options.get("to", "")).lower().strip()
        op = options.get("operation") or f"{from_format}-to-{to_format}"
        sub_options = options.get("options", {})

        # 1. PNG sang SVG (VTracer)
        if op == "png-to-svg":
            colormode = sub_options.get("colormode", "color")
            mode = sub_options.get("mode", "spline")
            return (
                file_converter_service.png_to_svg(
                    input_data, colormode=colormode, mode=mode
                ),
                "image/svg+xml",
            )

        # 2. DOCX / DOC sang PDF
        if op in ("docx-to-pdf", "doc-to-pdf"):
            return (
                file_converter_service.doc_to_pdf(input_data),
                "application/pdf",
            )

        # 3. TXT sang PDF & TXT sang DOCX
        if op == "txt-to-pdf":
            title = sub_options.get("title", "Tài liệu")
            return (
                file_converter_service.txt_to_pdf(input_data, title=title),
                "application/pdf",
            )

        if op in ("txt-to-doc", "txt-to-docx"):
            title = sub_options.get("title")
            return (
                file_converter_service.txt_to_doc(input_data, title=title),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        # 4. XLSX sang CSV & XLSX sang JSON
        if op == "xlsx-to-csv":
            sheet_name = sub_options.get("sheet_name")
            return (
                file_converter_service.xlsx_to_csv(input_data, sheet_name=sheet_name),
                "text/csv; charset=utf-8",
            )

        if op == "xlsx-to-json":
            sheet_name = sub_options.get("sheet_name")
            all_sheets = bool(sub_options.get("all_sheets", False))
            json_data = file_converter_service.xlsx_to_json(
                input_data, sheet_name=sheet_name, all_sheets=all_sheets
            )
            return (
                json.dumps(json_data, ensure_ascii=False, indent=2).encode("utf-8"),
                "application/json",
            )

        # 4c. XLSX sang PDF
        if op == "xlsx-to-pdf":
            sheet_name = sub_options.get("sheet_name")
            title = sub_options.get("title", "Bảng tính Excel")
            return (
                file_converter_service.xlsx_to_pdf(
                    input_data, sheet_name=sheet_name, title=title
                ),
                "application/pdf",
            )

        # 5. PNG sang JPG
        if op in ("png-to-jpg", "png-to-jpeg"):
            quality = int(sub_options.get("quality", 95))
            return (
                file_converter_service.png_to_jpg(input_data, quality=quality),
                "image/jpeg",
            )

        # 5b. JPG sang PNG
        if op in ("jpg-to-png", "jpeg-to-png"):
            return (
                file_converter_service.jpg_to_png(input_data),
                "image/png",
            )

        # 6. JPG sang WEBP
        if op in ("jpg-to-webp", "jpeg-to-webp"):
            quality = int(sub_options.get("quality", 90))
            lossless = bool(sub_options.get("lossless", False))
            return (
                file_converter_service.jpg_to_webp(
                    input_data, quality=quality, lossless=lossless
                ),
                "image/webp",
            )

        raise ValueError(
            f"Unsupported conversion format operation: '{op}' (from '{from_format}' to '{to_format}')"
        )


document_processor = DocumentConvertProcessor()
