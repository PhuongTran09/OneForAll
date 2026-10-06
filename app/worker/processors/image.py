from abc import ABC, abstractmethod
from typing import Any

from app.services.bg_removal_service import bg_removal_service


class ImageProcessor(ABC):
    @abstractmethod
    def process(self, image_bytes: bytes, options: dict[str, Any]) -> bytes:
        raise NotImplementedError


class RemoveBackgroundProcessor(ImageProcessor):
    def process(self, image_bytes: bytes, options: dict[str, Any]) -> bytes:
        return bg_removal_service.remove_background(image_bytes)


class CompressImageProcessor(ImageProcessor):
    def process(self, image_bytes: bytes, options: dict[str, Any]) -> bytes:
        raise NotImplementedError("CompressImageProcessor is not implemented yet.")


class ResizeImageProcessor(ImageProcessor):
    def process(self, image_bytes: bytes, options: dict[str, Any]) -> bytes:
        raise NotImplementedError("ResizeImageProcessor is not implemented yet.")


IMAGE_PROCESSORS: dict[str, type[ImageProcessor]] = {
    "remove_background": RemoveBackgroundProcessor,
    "compress": CompressImageProcessor,
    "resize": ResizeImageProcessor,
}


def get_image_processor(operation: str) -> ImageProcessor:
    processor_cls = IMAGE_PROCESSORS[operation]
    return processor_cls()
