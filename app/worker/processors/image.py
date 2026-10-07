import io
from typing import Any

from PIL import Image

from app.core.exceptions import AppException
from app.worker.processors.base import BaseProcessor


class ImageProcessProcessor(BaseProcessor):
    """
    Image processor handling:
    - compress (lossy/lossless JPEG/PNG/WEBP compression)
    - resize (dimension scaling with aspect ratio preserving)
    - crop (bounding box cropping)
    - format (format transcode via Pillow)
    """

    def process(self, input_data: bytes, options: dict[str, Any]) -> tuple[bytes, str]:
        operation = str(options.get("operation", "compress")).lower()
        sub_opts = options.get("options", {}) or options.get("params", {})

        try:
            image = Image.open(io.BytesIO(input_data))
        except Exception as exc:
            raise AppException(status_code=400, detail="Invalid image file") from exc

        orig_format = image.format or "PNG"
        target_format = str(sub_opts.get("format", orig_format)).upper()
        if target_format in ("JPG", "JPEG"):
            target_format = "JPEG"

        # 1. Resize operation
        if operation == "resize" or "width" in sub_opts or "height" in sub_opts:
            width = sub_opts.get("width")
            height = sub_opts.get("height")
            if width or height:
                orig_w, orig_h = image.size
                new_w = int(width) if width else int(orig_w * (int(height) / orig_h))
                new_h = int(height) if height else int(orig_h * (int(width) / orig_w))
                image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # 2. Crop operation
        if operation == "crop" and "box" in sub_opts:
            box = sub_opts["box"]  # (left, upper, right, lower)
            if isinstance(box, list | tuple) and len(box) == 4:
                image = image.crop((int(box[0]), int(box[1]), int(box[2]), int(box[3])))

        # 3. Format & Compress output
        out_buf = io.BytesIO()
        quality = int(sub_opts.get("quality", 85))

        if target_format == "JPEG":
            if image.mode in ("RGBA", "LA", "P"):
                bg_color = (255, 255, 255)
                rgb_img = Image.new("RGB", image.size, bg_color)
                if image.mode == "P":
                    image = image.convert("RGBA")
                rgb_img.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
                image = rgb_img
            image.save(out_buf, format="JPEG", quality=quality, optimize=True)
            return out_buf.getvalue(), "image/jpeg"

        elif target_format == "WEBP":
            lossless = bool(sub_opts.get("lossless", False))
            image.save(out_buf, format="WEBP", quality=quality, lossless=lossless)
            return out_buf.getvalue(), "image/webp"

        elif target_format == "PNG":
            image.save(out_buf, format="PNG", optimize=True, compress_level=6)
            return out_buf.getvalue(), "image/png"

        else:
            image.save(out_buf, format=target_format)
            return out_buf.getvalue(), f"image/{target_format.lower()}"


image_processor = ImageProcessProcessor()
