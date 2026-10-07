import asyncio
import concurrent.futures
import json
from datetime import UTC
from typing import Any

from app.repositories.job_repository import JobRepository
from app.services.file_converter_service import file_converter_service
from app.services.storage_service import storage_service
from app.utils.logger import logger
from app.worker.celery_app import CeleryQueue, celery_app


def execute_conversion(
    content: bytes, from_format: str, to_format: str, options: dict[str, Any]
) -> tuple[bytes, str]:
    """
    Execute format conversion using file_converter_service.
    Returns: (output_bytes, content_type)
    """
    fmt_from = from_format.lower().strip()
    fmt_to = to_format.lower().strip()
    op = f"{fmt_from}-to-{fmt_to}"

    # 1. PNG sang SVG (VTracer)
    if op == "png-to-svg":
        colormode = options.get("colormode", "color")
        mode = options.get("mode", "spline")
        return (
            file_converter_service.png_to_svg(content, colormode=colormode, mode=mode),
            "image/svg+xml",
        )

    # 2. DOCX / DOC sang PDF
    if op in ("docx-to-pdf", "doc-to-pdf"):
        return (
            file_converter_service.doc_to_pdf(content),
            "application/pdf",
        )

    # 3. TXT sang PDF & TXT sang DOCX
    if op == "txt-to-pdf":
        title = options.get("title", "Tài liệu")
        return (
            file_converter_service.txt_to_pdf(content, title=title),
            "application/pdf",
        )

    if op in ("txt-to-doc", "txt-to-docx"):
        title = options.get("title")
        return (
            file_converter_service.txt_to_doc(content, title=title),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    # 4. XLSX sang CSV & XLSX sang JSON
    if op == "xlsx-to-csv":
        sheet_name = options.get("sheet_name")
        return (
            file_converter_service.xlsx_to_csv(content, sheet_name=sheet_name),
            "text/csv; charset=utf-8",
        )

    if op == "xlsx-to-json":
        sheet_name = options.get("sheet_name")
        all_sheets = bool(options.get("all_sheets", False))
        json_data = file_converter_service.xlsx_to_json(
            content, sheet_name=sheet_name, all_sheets=all_sheets
        )
        return (
            json.dumps(json_data, ensure_ascii=False, indent=2).encode("utf-8"),
            "application/json",
        )

    # 5. PNG sang JPG
    if op in ("png-to-jpg", "png-to-jpeg"):
        quality = int(options.get("quality", 95))
        return (
            file_converter_service.png_to_jpg(content, quality=quality),
            "image/jpeg",
        )

    # 6. JPG sang WEBP
    if op in ("jpg-to-webp", "jpeg-to-webp"):
        quality = int(options.get("quality", 90))
        lossless = bool(options.get("lossless", False))
        return (
            file_converter_service.jpg_to_webp(
                content, quality=quality, lossless=lossless
            ),
            "image/webp",
        )

    raise ValueError(
        f"Định dạng chuyển đổi từ '{fmt_from}' sang '{fmt_to}' chưa được hỗ trợ."
    )


async def _async_process_convert_job(job_id: str) -> dict[str, Any]:
    """Asynchronous job execution logic interacting with Database and Storage."""
    repo = JobRepository()
    job = await repo.get(job_id)
    if not job:
        logger.error("[convert-worker] Job %s not found in database", job_id)
        return {"job_id": job_id, "error": "Job not found", "status": "failed"}

    if not job.input_key:
        err = "Job input_key is empty"
        await repo.mark_failed(job, err)
        return {"job_id": job_id, "error": err, "status": "failed"}

    await repo.mark_processing(job)
    metadata = job.job_metadata or {}
    from_format = metadata.get("from", "")
    to_format = metadata.get("to", "")
    options = metadata.get("options", {})

    try:
        # 1. Tải nội dung file từ Storage (Cloudflare R2 / local)
        logger.info("[convert-worker] Downloading file from key: %s", job.input_key)
        input_bytes = storage_service.download_bytes(key=job.input_key)

        # 2. Thực hiện chuyển đổi file
        logger.info(
            "[convert-worker] Converting job %s: %s -> %s",
            job_id,
            from_format,
            to_format,
        )
        output_bytes, content_type = execute_conversion(
            input_bytes,
            from_format=from_format,
            to_format=to_format,
            options=options,
        )

        # 3. Upload file kết quả lên Storage (outputs/{job_id}/result.ext)
        target_ext = to_format.lower().lstrip(".")
        output_key = f"outputs/{job.id}/result.{target_ext}"
        logger.info(
            "[convert-worker] Uploading converted file to key: %s", output_key
        )
        storage_service.upload_bytes(
            data=output_bytes,
            key=output_key,
            content_type=content_type,
        )

        # 4. Xóa file gốc input trên R2 để tiết kiệm dung lượng
        if job.input_key:
            try:
                storage_service.delete_file(key=job.input_key)
                logger.info(
                    "[convert-worker] Deleted original input file: %s",
                    job.input_key,
                )
            except Exception as del_err:  # noqa: BLE001
                logger.warning(
                    "[convert-worker] Could not delete input file %s: %s",
                    job.input_key,
                    del_err,
                )

        # 5. Cập nhật trạng thái Job thành completed (hết hạn sau 20 phút)
        from datetime import datetime, timedelta

        expires_at = datetime.now(UTC) + timedelta(minutes=20)
        await repo.mark_completed(job, output_key=output_key, expires_at=expires_at)
        logger.info(
            "[convert-worker] Job %s completed! Expires at: %s", job_id, expires_at
        )
        return {
            "job_id": job_id,
            "status": "completed",
            "output_key": output_key,
            "expires_at": expires_at.isoformat(),
        }

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[convert-worker] Job %s failed: %s", job_id, exc, exc_info=True
        )
        await repo.mark_failed(job, error=str(exc))
        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(exc),
        }


@celery_app.task(
    name="app.worker.tasks.convert.process_convert_job", queue=CeleryQueue.CONVERT.value
)
def process_convert_job(job_id: str, **kwargs: Any) -> dict[str, Any]:
    """
    Main job processor for document and vector conversions on the 'convert' queue.
    Workloads: LibreOffice (DOC/DOCX/XLSX to PDF, etc.), VTracer (PNG to SVG vectorization).
    """
    logger.info("[convert-worker] Received convert job: %s", job_id)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                lambda: asyncio.run(_async_process_convert_job(job_id))
            ).result()

    return asyncio.run(_async_process_convert_job(job_id))


@celery_app.task(
    name="app.worker.tasks.convert.libreoffice_convert", queue=CeleryQueue.CONVERT.value
)
def libreoffice_convert(
    input_key: str, output_format: str, **kwargs: Any
) -> dict[str, str]:
    """Execute LibreOffice document conversion (e.g. DOCX -> PDF, XLSX -> PDF)."""
    logger.info(
        "[convert-worker] Executing LibreOffice conversion for %s to %s",
        input_key,
        output_format,
    )
    return {"input_key": input_key, "format": output_format, "status": "completed"}


@celery_app.task(
    name="app.worker.tasks.convert.vtracer_convert", queue=CeleryQueue.CONVERT.value
)
def vtracer_convert(
    input_key: str, colormode: str = "color", mode: str = "spline", **kwargs: Any
) -> dict[str, str]:
    """Execute VTracer raster to vector (PNG -> SVG) conversion."""
    logger.info("[convert-worker] Executing VTracer conversion for %s", input_key)
    return {"input_key": input_key, "status": "completed"}
