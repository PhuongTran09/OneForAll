import re
from urllib.parse import quote


def sanitize_filename(name: str, fallback: str = "download") -> str:
    """Sanitize title or filename removing illegal filesystem/header characters."""
    if not name:
        return fallback
    # Remove filesystem illegal characters: \ / : * ? " < > | and control chars
    clean = re.sub(r'[\x00-\x1f\\/*?:"<>|]', "", name).strip()
    # Strip leading/trailing dots or spaces
    clean = clean.strip(". ")
    return clean or fallback


def build_content_disposition(title: str, ext: str, fallback: str = "result") -> tuple[str, str]:
    """Generate safe filename and RFC 5987/6266 Content-Disposition header value.

    Returns:
        (final_filename, content_disposition_header)
    """
    clean_ext = ext.lstrip(".") if ext else ""
    clean_stem = sanitize_filename(title, fallback=fallback)
    final_filename = f"{clean_stem}.{clean_ext}" if clean_ext else clean_stem

    # ASCII-safe fallback for older clients
    ascii_stem = re.sub(r"[^\w\s.-]", "", clean_stem).strip() or fallback
    ascii_filename = f"{ascii_stem}.{clean_ext}" if clean_ext else ascii_stem

    # RFC 5987 UTF-8 encoded filename for modern browsers (Chrome, Safari, Firefox, Edge)
    utf8_filename = quote(final_filename)

    header_val = f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{utf8_filename}'
    return final_filename, header_val
