from abc import ABC, abstractmethod
from typing import Any


class BaseProcessor(ABC):
    """Abstract base class for all conversion and media processors."""

    @abstractmethod
    def process(self, input_data: bytes, options: dict[str, Any]) -> tuple[bytes, str]:
        """
        Process the input payload.
        Args:
            input_data: Raw input bytes (image, doc, video, etc.)
            options: Dictionary of parameters (operation, formats, quality, etc.)
        Returns:
            tuple[bytes, str]: (output_bytes, content_type)
        """
        raise NotImplementedError
