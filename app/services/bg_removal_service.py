import io
import threading
from typing import Any

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.core.exceptions import AppException
from app.utils.logger import logger

INPUT_SIZE = (1024, 1024)  # (W, H) cho PIL
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

# Giới hạn số pixel đầu vào để tránh decompression bomb / hết RAM
MAX_INPUT_PIXELS: int = getattr(settings, "MAX_IMAGE_PIXELS", 50_000_000)
# Có thể pin revision của model để tránh chạy code remote thay đổi ngoài ý muốn
MODEL_REVISION: str | None = getattr(settings, "BIREFNET_MODEL_REVISION", None)


class BackgroundRemovalService:
    def __init__(self):
        self._device: str | None = None
        self._model: Any = None
        self._mean: Any = None  # tensor mean/std nằm sẵn trên device
        self._std: Any = None
        self._load_lock = threading.Lock()
        # Chỉ cho 1 luồng chạy suy luận tại 1 thời điểm -> tránh OOM GPU khi nhiều request đồng thời
        self._infer_lock = threading.Lock()

    # ------------------------------------------------------------------ device
    @property
    def device(self) -> str:
        if self._device is None:
            self._device = self._resolve_device()
        return self._device

    @staticmethod
    def _resolve_device() -> str:
        try:
            import torch
        except ImportError:
            return "cpu"

        target = settings.MODEL_DEVICE.lower()
        cuda_ok = torch.cuda.is_available()
        mps_ok = getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()

        if target == "cuda":
            if not cuda_ok:
                logger.warning(
                    "[!] MODEL_DEVICE=cuda được chỉ định nhưng không tìm thấy CUDA/GPU khả dụng. Chuyển sang CPU."
                )
                return "cpu"
            return "cuda"

        if target != "auto":
            return target

        if cuda_ok:
            return "cuda"
        return "mps" if mps_ok else "cpu"

    # ------------------------------------------------------------------ model
    def load_model(self):
        """Tải mô hình vào bộ nhớ (VRAM/RAM)"""
        if self._model is not None:
            return

        with self._load_lock:
            if self._model is not None:
                return

            try:
                import torch
                from transformers import AutoModelForImageSegmentation
            except ImportError as e:
                raise AppException(
                    status_code=500,
                    detail="Thiếu thư viện AI (torch/transformers). Vui lòng cài đặt requirements.txt",
                ) from e

            dev = self.device
            logger.info(f"[*] Khởi động hệ thống trên thiết bị: {dev.upper()}")
            if dev == "cuda":
                logger.info(f"[*] GPU Name: {torch.cuda.get_device_name(0)}")
                # Tăng tốc matmul trên GPU Ampere+ mà sai số không đáng kể
                torch.set_float32_matmul_precision("high")
                torch.backends.cudnn.benchmark = True

            logger.info(f"[*] Đang tải mô hình ({settings.BIREFNET_MODEL_NAME})...")
            kwargs: dict[str, Any] = {"trust_remote_code": True}
            if MODEL_REVISION:
                kwargs["revision"] = MODEL_REVISION
            model = AutoModelForImageSegmentation.from_pretrained(
                settings.BIREFNET_MODEL_NAME, **kwargs
            )
            model.to(dev).float().eval()  # float32 để đảm bảo ổn định số học
            model.requires_grad_(False)

            self._mean = torch.tensor(IMAGENET_MEAN, device=dev).view(1, 3, 1, 1)
            self._std = torch.tensor(IMAGENET_STD, device=dev).view(1, 3, 1, 1)

            # Warm-up: lần chạy đầu luôn chậm (khởi tạo kernel/cudnn)
            try:
                with torch.inference_mode():
                    model(torch.zeros(1, 3, *INPUT_SIZE[::-1], device=dev))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[!] Warm-up thất bại (bỏ qua): {e}")

            self._model = model
            logger.info("[+] Mô hình đã sẵn sàng!")

    @property
    def is_model_loaded(self) -> bool:
        return self._model is not None

    def get_system_status(self) -> dict[str, Any]:
        gpu_available = False
        device_name = self.device
        try:
            import torch

            gpu_available = torch.cuda.is_available()
            if gpu_available and device_name == "cuda":
                device_name = f"cuda ({torch.cuda.get_device_name(0)})"
        except ImportError:
            pass

        return {
            "device": device_name,
            "gpu_available": gpu_available,
            "model_loaded": self.is_model_loaded,
            "model_name": settings.BIREFNET_MODEL_NAME,
        }

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _open_image(image_bytes: bytes) -> Image.Image:
        try:
            raw = Image.open(io.BytesIO(image_bytes))
            # Kiểm tra kích thước TRƯỚC khi giải mã toàn bộ ảnh
            if raw.width * raw.height > MAX_INPUT_PIXELS:
                raise AppException(
                    status_code=413,
                    detail=f"Ảnh quá lớn (tối đa {MAX_INPUT_PIXELS:,} pixel).",
                )
            # exif_transpose xoay ảnh smartphone đúng chiều
            return ImageOps.exif_transpose(raw).convert("RGB")
        except AppException:
            raise
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
            raise AppException(
                status_code=400, detail="File không phải ảnh hợp lệ hoặc đã bị hỏng."
            ) from e

    def _preprocess(self, image: Image.Image):
        import torch

        resized = image.resize(INPUT_SIZE, Image.BILINEAR)
        # uint8 HWC -> tensor; chuẩn hóa thực hiện trên device (nhanh hơn trên CPU)
        arr = np.array(resized, dtype=np.uint8)
        tensor = torch.from_numpy(arr).to(self.device).permute(2, 0, 1).unsqueeze(0)
        tensor = tensor.float().div_(255.0)
        return (tensor - self._mean) / self._std

    # ------------------------------------------------------------------ main
    def remove_background(self, image_bytes: bytes) -> bytes:
        """Tách nền ảnh đầu vào và trả về byte ảnh PNG trong suốt.

        Hàm này chặn (blocking). Trong FastAPI hãy gọi qua
        `await run_in_threadpool(service.remove_background, data)`
        hoặc khai báo endpoint là `def` thường.
        """
        if self._model is None:
            self.load_model()

        import torch
        import torch.nn.functional as F

        image = self._open_image(image_bytes)
        width, height = image.size

        try:
            with self._infer_lock, torch.inference_mode():
                x = self._preprocess(image)
                pred = self._model(x)[-1].sigmoid()  # (1, 1, 1024, 1024)
                # Resize mask về kích thước gốc ngay trên GPU (nhanh hơn PIL trên CPU)
                pred = F.interpolate(
                    pred, size=(height, width), mode="bilinear", align_corners=False
                )
                mask_np = (
                    (pred[0, 0] * 255.0).round_().clamp_(0, 255).to(torch.uint8).cpu().numpy()
                )
        except torch.cuda.OutOfMemoryError as e:
            torch.cuda.empty_cache()  # chỉ dọn cache khi thực sự OOM
            raise AppException(
                status_code=503, detail="GPU hết bộ nhớ, vui lòng thử lại sau."
            ) from e
        except Exception as e:
            logger.exception("[!] Lỗi khi suy luận tách nền")
            raise AppException(status_code=500, detail="Không thể xử lý ảnh.") from e

        # `image` là bản sao cục bộ (convert đã tạo mới) nên có thể putalpha trực tiếp
        image.putalpha(Image.fromarray(mask_np, mode="L"))

        buf = io.BytesIO()
        image.save(buf, format="PNG", compress_level=1)  # nén nhanh
        return buf.getvalue()


bg_removal_service = BackgroundRemovalService()