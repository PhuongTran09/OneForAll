import json
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

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

    Operates directly on local SSD file paths.
    """

    def process_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        options: dict[str, Any],
    ) -> str:
        from_format = str(options.get("from", "")).lower().strip()
        to_format = str(options.get("to", "")).lower().strip()
        op = options.get("operation") or f"{from_format}-to-{to_format}"
        sub_options = options.get("options", {}) or options.get("params", {})

        inp = Path(input_path)
        outp = Path(output_path)
        outp.parent.mkdir(parents=True, exist_ok=True)

        # 1. PNG sang SVG (VTracer)
        if op == "png-to-svg":
            colormode = sub_options.get("colormode", "color")
            mode = sub_options.get("mode", "spline")
            try:
                import vtracer

                vtracer.convert_image_to_svg_py(
                    str(inp),
                    str(outp),
                    colormode=colormode,
                    mode=mode,
                )
            except Exception:
                # Fallback to service if direct vtracer call fails
                svg_data = file_converter_service.png_to_svg(
                    inp.read_bytes(), colormode=colormode, mode=mode
                )
                outp.write_bytes(svg_data)
            return "image/svg+xml"

        # 2. DOCX / DOC sang PDF
        if op in ("docx-to-pdf", "doc-to-pdf"):
            pdf_bytes = file_converter_service.doc_to_pdf(inp.read_bytes())
            outp.write_bytes(pdf_bytes)
            return "application/pdf"

        # 3. TXT sang PDF & TXT sang DOCX
        if op == "txt-to-pdf":
            title = sub_options.get("title", "Tài liệu")
            pdf_bytes = file_converter_service.txt_to_pdf(inp.read_bytes(), title=title)
            outp.write_bytes(pdf_bytes)
            return "application/pdf"

        if op in ("txt-to-doc", "txt-to-docx"):
            title = sub_options.get("title")
            doc_bytes = file_converter_service.txt_to_doc(inp.read_bytes(), title=title)
            outp.write_bytes(doc_bytes)
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        # 4. XLSX sang CSV & XLSX sang JSON
        if op == "xlsx-to-csv":
            sheet_name = sub_options.get("sheet_name")
            csv_bytes = file_converter_service.xlsx_to_csv(
                inp.read_bytes(), sheet_name=sheet_name
            )
            outp.write_bytes(csv_bytes)
            return "text/csv; charset=utf-8"

        if op == "xlsx-to-json":
            sheet_name = sub_options.get("sheet_name")
            all_sheets = bool(sub_options.get("all_sheets", False))
            json_data = file_converter_service.xlsx_to_json(
                inp.read_bytes(), sheet_name=sheet_name, all_sheets=all_sheets
            )
            with open(outp, "w", encoding="utf-8") as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            return "application/json"

        # 4c. XLSX sang PDF
        if op == "xlsx-to-pdf":
            sheet_name = sub_options.get("sheet_name")
            title = sub_options.get("title", "Bảng tính Excel")
            pdf_bytes = file_converter_service.xlsx_to_pdf(
                inp.read_bytes(), sheet_name=sheet_name, title=title
            )
            outp.write_bytes(pdf_bytes)
            return "application/pdf"

        # 5. PNG sang JPG
        if op in ("png-to-jpg", "png-to-jpeg"):
            quality = int(sub_options.get("quality", 95))
            with Image.open(inp) as img:
                if img.mode in ("RGBA", "LA", "P"):
                    rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    rgb_img.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                    img = rgb_img
                else:
                    img = img.convert("RGB")
                img.save(outp, format="JPEG", quality=quality, optimize=True)
            return "image/jpeg"

        # 5b. JPG sang PNG
        if op in ("jpg-to-png", "jpeg-to-png"):
            with Image.open(inp) as img:
                img.save(outp, format="PNG")
            return "image/png"

        # 6. JPG sang WEBP
        if op in ("jpg-to-webp", "jpeg-to-webp"):
            quality = int(sub_options.get("quality", 90))
            lossless = bool(sub_options.get("lossless", False))
            with Image.open(inp) as img:
                img.save(outp, format="WEBP", quality=quality, lossless=lossless)
            return "image/webp"

        raise ValueError(
            f"Unsupported conversion format operation: '{op}' (from '{from_format}' to '{to_format}')"
        )

    def _process_bytes(self, input_data: bytes, options: dict[str, Any]) -> tuple[bytes, str]:
        """Legacy helper for byte-oriented conversions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            from_format = str(options.get("from", "bin")).lower().strip().lstrip(".")
            to_format = str(options.get("to", "bin")).lower().strip().lstrip(".")
            inp = os.path.join(tmp_dir, f"input.{from_format}")
            outp = os.path.join(tmp_dir, f"output.{to_format}")
            with open(inp, "wb") as f:
                f.write(input_data)
            content_type = self.process_file(inp, outp, options)
            with open(outp, "rb") as f:
                res_bytes = f.read()
            return res_bytes, content_type


document_processor = DocumentConvertProcessor()
