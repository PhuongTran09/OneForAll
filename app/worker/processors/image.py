import io
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from app.core.exceptions import AppException
from app.worker.processors.base import BaseProcessor


MAX_RESIZE_DIMENSION: int = 8192
MAX_IMAGE_PIXELS: int = 50_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class ImageProcessProcessor(BaseProcessor):
    """
    Image processor handling:
    - compress (lossy/lossless JPEG/PNG/WEBP compression)
    - resize (dimension scaling with aspect ratio preserving)
    - crop (bounding box cropping)
    - format (format transcode via Pillow)

    Supports direct file-to-file processing avoiding full RAM buffering.
    """

    def process_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        options: dict[str, Any],
    ) -> str:
        """Process image file directly on disk from input_path to output_path."""
        operation = str(options.get("operation", "compress")).lower()
        sub_opts = options.get("options", {}) or options.get("params", {})

        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        try:
            image = Image.open(input_path)
        except Exception as exc:
            raise AppException(status_code=400, detail="Invalid image file") from exc

        orig_format = image.format or "PNG"
        target_format = str(sub_opts.get("format", out_p.suffix.lstrip(".") or orig_format)).upper()
        if target_format in ("JPG", "JPEG"):
            target_format = "JPEG"

        # 1. Resize operation with strict bounds checking
        if operation == "resize" or "width" in sub_opts or "height" in sub_opts:
            width = sub_opts.get("width")
            height = sub_opts.get("height")
            if width is not None or height is not None:
                try:
                    w_val = int(width) if width is not None else None
                    h_val = int(height) if height is not None else None
                except (ValueError, TypeError) as val_err:
                    raise AppException(status_code=400, detail="Width and height must be valid integers.") from val_err

                if w_val is not None and (w_val <= 0 or w_val > MAX_RESIZE_DIMENSION):
                    raise AppException(
                        status_code=400,
                        detail=f"Width must be between 1 and {MAX_RESIZE_DIMENSION} pixels.",
                    )
                if h_val is not None and (h_val <= 0 or h_val > MAX_RESIZE_DIMENSION):
                    raise AppException(
                        status_code=400,
                        detail=f"Height must be between 1 and {MAX_RESIZE_DIMENSION} pixels.",
                    )

                orig_w, orig_h = image.size
                new_w = w_val if w_val else int(orig_w * (h_val / orig_h))
                new_h = h_val if h_val else int(orig_h * (w_val / orig_w))

                if new_w > MAX_RESIZE_DIMENSION or new_h > MAX_RESIZE_DIMENSION or new_w <= 0 or new_h <= 0:
                    raise AppException(
                        status_code=400,
                        detail=f"Calculated dimensions exceed maximum allowed {MAX_RESIZE_DIMENSION} pixels.",
                    )

                image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # 2. Crop operation with coordinate validation
        if operation == "crop" and "box" in sub_opts:
            box = sub_opts["box"]  # (left, upper, right, lower)
            if not isinstance(box, (list, tuple)) or len(box) != 4:
                raise AppException(
                    status_code=400,
                    detail="Crop box must be a list/tuple of 4 coordinates [left, upper, right, lower].",
                )
            try:
                coords = [int(c) for c in box]
            except (ValueError, TypeError) as exc:
                raise AppException(status_code=400, detail="Crop box coordinates must be integers.") from exc

            if coords[0] < 0 or coords[1] < 0 or coords[2] <= coords[0] or coords[3] <= coords[1]:
                raise AppException(
                    status_code=400,
                    detail="Invalid crop box coordinates (left < right and upper < lower).",
                )
            image = image.crop((coords[0], coords[1], coords[2], coords[3]))

        # 3. Format & Compress output directly to disk
        quality = int(sub_opts.get("quality", 85))

        if target_format == "JPEG":
            if image.mode in ("RGBA", "LA", "P"):
                bg_color = (255, 255, 255)
                rgb_img = Image.new("RGB", image.size, bg_color)
                if image.mode == "P":
                    image = image.convert("RGBA")
                rgb_img.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
                image = rgb_img
            image.save(out_p, format="JPEG", quality=quality, optimize=True)
            return "image/jpeg"

        elif target_format == "WEBP":
            lossless = bool(sub_opts.get("lossless", False))
            image.save(out_p, format="WEBP", quality=quality, lossless=lossless)
            return "image/webp"

        elif target_format == "PNG":
            image.save(out_p, format="PNG", optimize=True, compress_level=6)
            return "image/png"

        else:
            image.save(out_p, format=target_format)
            return f"image/{target_format.lower()}"

    def _process_bytes(self, input_data: bytes, options: dict[str, Any]) -> tuple[bytes, str]:
        """Legacy in-memory processor for byte inputs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            inp = os.path.join(tmp_dir, "input.raw")
            outp = os.path.join(tmp_dir, "output.raw")
            with open(inp, "wb") as f:
                f.write(input_data)
            content_type = self.process_file(inp, outp, options)
            with open(outp, "rb") as f:
                res_bytes = f.read()
            return res_bytes, content_type


image_processor = ImageProcessProcessor()
