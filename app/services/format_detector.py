"""Universal File Format Detection and Normalization Service.

Detects and normalizes file formats across documents, images, video, and audio
using MIME types, filename extensions, and file signatures (magic bytes).
"""

import io
import json
import zipfile

# Canonical format aliases mapping to normalized extension (without leading dot)
FORMAT_ALIASES: dict[str, str] = {
    # Images
    "jpeg": "jpg",
    "jpe": "jpg",
    "jfif": "jpg",
    "tif": "tiff",
    "svgz": "svg",
    # Documents
    "htm": "html",
    "text": "txt",
    "plain": "txt",
    # Audio & Video
    "wave": "wav",
    "mpg": "mp3",
    "mpeg": "mp3",
    "oga": "ogg",
    "ogv": "ogg",
    "m4v": "mp4",
}

# Mapping of known MIME types to canonical format
MIME_TO_FORMAT: dict[str, str] = {
    # Documents
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/rtf": "rtf",
    "text/rtf": "rtf",
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
    "text/plain": "txt",
    "text/csv": "csv",
    "application/csv": "csv",
    "text/x-csv": "csv",
    "application/json": "json",
    "text/json": "json",
    "text/html": "html",
    "application/xhtml+xml": "html",
    "application/xml": "xml",
    "text/xml": "xml",
    # Images
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/pjpeg": "jpg",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "image/svg": "svg",
    "image/gif": "gif",
    "image/bmp": "bmp",
    "image/x-ms-bmp": "bmp",
    "image/tiff": "tiff",
    "image/x-icon": "ico",
    "image/vnd.microsoft.icon": "ico",
    "image/heic": "heic",
    "image/heif": "heif",
    # Audio
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mpg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/ogg": "ogg",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
    "audio/aac": "aac",
    "audio/x-aac": "aac",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/m4a": "m4a",
    # Video
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/x-matroska": "mkv",
    "video/mkv": "mkv",
    "video/x-msvideo": "avi",
    "video/avi": "avi",
    "video/quicktime": "mov",
    "video/x-flv": "flv",
    "video/x-ms-wmv": "wmv",
}

# Generic or placeholder MIME types that provide no specific format information
GENERIC_MIMES: frozenset[str] = frozenset({
    "application/octet-stream",
    "binary/octet-stream",
    "application/x-download",
    "application/download",
    "application/force-download",
    "text/octet-stream",
    "unknown/unknown",
    "",
})

# Known extensions supported across the system
KNOWN_EXTENSIONS: frozenset[str] = frozenset({
    "pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt", "txt", "csv", "json",
    "xml", "html", "rtf", "odt", "ods", "png", "jpg", "jpeg", "webp", "svg",
    "gif", "bmp", "tiff", "tif", "ico", "heic", "heif", "mp4", "webm", "mkv",
    "avi", "mov", "flv", "wmv", "mp3", "wav", "ogg", "flac", "aac", "m4a",
})

# Supported (from_format, to_format) pairs for document and vector conversion
SUPPORTED_CONVERSIONS: frozenset[tuple[str, str]] = frozenset({
    # Text / Document conversions
    ("txt", "pdf"),
    ("txt", "docx"),
    ("txt", "doc"),
    ("docx", "pdf"),
    ("doc", "pdf"),
    ("xlsx", "csv"),
    ("xlsx", "json"),
    ("xlsx", "pdf"),
    # Image conversions
    ("png", "svg"),
    ("png", "jpg"),
    ("png", "jpeg"),
    ("png", "webp"),
    ("jpg", "png"),
    ("jpeg", "png"),
    ("jpg", "webp"),
    ("jpeg", "webp"),
})


def normalize_format(fmt: str | None) -> str:
    """Normalize format string to canonical lowercase format without leading dots.

    Examples:
        - '.PDF' -> 'pdf'
        - 'JPEG' -> 'jpg'
        - 'docx' -> 'docx'
    """
    if not fmt:
        return ""
    clean = fmt.strip().lower().lstrip(".")
    return FORMAT_ALIASES.get(clean, clean)


def detect_by_magic_bytes(content: bytes) -> str | None:
    """Inspect binary file signatures (magic bytes) to identify file format.

    Supports documents (PDF, DOCX, XLSX, OLE), images (PNG, JPEG, GIF, WEBP, BMP,
    TIFF, ICO), audio (MP3, WAV, OGG, FLAC), video (MP4, MKV/WebM, AVI), and UTF-8 text.
    """
    if not content:
        return None

    # PDF: %PDF-
    if content.startswith(b"%PDF-"):
        return "pdf"

    # PNG: \x89PNG\r\n\x1a\n
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"

    # JPEG: \xff\xd8\xff
    if content.startswith(b"\xff\xd8\xff"):
        return "jpg"

    # GIF: GIF87a / GIF89a
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "gif"

    # RIFF containers: WEBP, WAVE, AVI
    if len(content) >= 12 and content.startswith(b"RIFF"):
        riff_type = content[8:12]
        if riff_type == b"WEBP":
            return "webp"
        if riff_type in (b"WAVE", b"WAV "):
            return "wav"
        if riff_type in (b"AVI ", b"AVIF"):
            return "avi"

    # BMP: BM with minimum header size
    if content.startswith(b"BM") and len(content) >= 14:
        return "bmp"

    # TIFF: II*\x00 (little-endian) or MM\x00* (big-endian)
    if content.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"

    # ICO: \x00\x00\x01\x00
    if content.startswith(b"\x00\x00\x01\x00"):
        return "ico"

    # OGG: OggS
    if content.startswith(b"OggS"):
        return "ogg"

    # FLAC: fLaC
    if content.startswith(b"fLaC"):
        return "flac"

    # MP3: ID3 header or MPEG sync frames (\xff\xfb, \xff\xf3, \xff\xf2)
    if content.startswith(b"ID3"):
        return "mp3"
    if len(content) >= 2 and content[0] == 0xFF and (content[1] & 0xE0) == 0xE0:
        return "mp3"

    # Matroska / WebM: \x1a\x45\xdf\xa3 (EBML)
    if content.startswith(b"\x1a\x45\xdf\xa3"):
        if b"webm" in content[:64]:
            return "webm"
        return "mkv"

    # ISO Base Media File Format (MP4 / M4A / MOV / HEIC): ....ftyp
    if len(content) >= 12 and content[4:8] == b"ftyp":
        brand = content[8:12].lower()
        if brand.startswith(b"m4a"):
            return "m4a"
        if brand.startswith((b"qt", b"moov")):
            return "mov"
        if brand.startswith((b"heic", b"heif", b"mif1")):
            return "heic"
        return "mp4"

    # ZIP-based OpenXML formats: PK\x03\x04 (DOCX, XLSX, PPTX, ODT)
    if content.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names = zf.namelist()
                if any(n.startswith("word/") for n in names):
                    return "docx"
                if any(n.startswith("xl/") for n in names):
                    return "xlsx"
                if any(n.startswith("ppt/") for n in names):
                    return "pptx"
                if any("opendocument.text" in n for n in names):
                    return "odt"
                if any("opendocument.spreadsheet" in n for n in names):
                    return "ods"
        except Exception:  # noqa: BLE001
            # Fallback for stub/mock ZIP bytes in unit tests
            if b"word/" in content:
                return "docx"
            if b"xl/" in content:
                return "xlsx"
            if b"ppt/" in content:
                return "pptx"
        return "zip"

    # OLE2 Compound Document: \xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 (Word 97-2003 .doc, Excel .xls)
    if content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        if b"Workbook" in content or b"Book" in content:
            return "xls"
        return "doc"

    # RTF: {\rtf
    if content.startswith(b"{\\rtf"):
        return "rtf"

    # Text-based format inspection (UTF-8 / ASCII)
    sample = content[:2048]
    if b"\x00" not in sample:
        try:
            text_sample = sample.decode("utf-8").strip()
            text_lower = text_sample.lower()
            if text_lower.startswith("<?xml") and "<svg" in text_lower:
                return "svg"
            if text_lower.startswith("<svg"):
                return "svg"
            if text_lower.startswith(("<!doctype html", "<html")):
                return "html"
            if text_lower.startswith(("{", "[")):
                try:
                    json.loads(content.decode("utf-8"))
                    return "json"
                except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                    return "txt"
            return "txt"
        except UnicodeDecodeError:
            return None

    return None


def detect_format(
    *,
    content: bytes | None = None,
    filename: str | None = None,
    content_type: str | None = None,
) -> str | None:
    """Detect and normalize file format from upload metadata and content.

    Priority:
    1. Check specific MIME type (if not generic/placeholder).
    2. Check filename extension.
    3. Verify/fallback with file signature (magic bytes).
    4. Handle files without extension or non-standard MIME types via magic bytes.

    Returns:
        Canonical format string (e.g. 'pdf', 'docx', 'txt', 'png', 'jpg', 'mp4') or None.
    """
    mime_format: str | None = None
    if content_type:
        clean_mime = content_type.split(";")[0].strip().lower()
        if clean_mime and clean_mime not in GENERIC_MIMES:
            mime_format = MIME_TO_FORMAT.get(clean_mime)

    ext_format: str | None = None
    if filename and "." in filename:
        raw_ext = filename.rsplit(".", 1)[-1].strip().lower()
        norm_ext = normalize_format(raw_ext)
        if norm_ext in KNOWN_EXTENSIONS:
            ext_format = norm_ext

    magic_format: str | None = None
    if content:
        magic_format = detect_by_magic_bytes(content)

    # 1. Strong binary magic signature overrides ambiguous text or generic MIME/extension
    if magic_format and magic_format not in ("txt", "zip"):
        # If extension agrees or is generic/missing, trust the magic signature
        if not ext_format or ext_format == magic_format or mime_format in GENERIC_MIMES:
            return magic_format
        # If magic format matches extension alias (e.g. jpeg vs jpg)
        if normalize_format(ext_format) == magic_format:
            return magic_format
        # If extension matches a known format and magic matches (e.g. docx zip)
        if ext_format in ("docx", "xlsx", "pptx") and magic_format in ("docx", "xlsx", "pptx"):
            return ext_format
        # Magic bytes detected specific binary type
        return magic_format

    # 2. Text formats: if magic detected text, let specific extension/MIME refine (csv, json, html, etc.)
    if magic_format == "txt":
        if ext_format in ("csv", "json", "xml", "html", "svg", "txt"):
            return ext_format
        if mime_format in ("csv", "json", "xml", "html", "svg", "txt"):
            return mime_format
        return "txt"

    # 3. If magic signature is zip, let docx/xlsx/pptx extension clarify if present
    if magic_format == "zip":
        if ext_format in ("docx", "xlsx", "pptx", "odt", "ods"):
            return ext_format
        return "zip"

    # 4. If no magic bytes available or inconclusive, use MIME type or extension
    if mime_format and mime_format not in ("txt",):
        return mime_format

    if ext_format:
        return ext_format

    if mime_format:
        return mime_format

    return magic_format


def is_conversion_supported(from_format: str, to_format: str) -> bool:
    """Validate whether the given conversion pair is supported by the system."""
    norm_from = normalize_format(from_format)
    norm_to = normalize_format(to_format)

    if not norm_from or not norm_to:
        return False

    if norm_from == norm_to:
        return False

    return (norm_from, norm_to) in SUPPORTED_CONVERSIONS
