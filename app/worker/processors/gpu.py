import os
import tempfile
from pathlib import Path
from typing import Any

from app.services.bg_removal_service import bg_removal_service
from app.worker.processors.base import BaseProcessor


class GpuAiProcessor(BaseProcessor):
    """
    GPU & AI Processor handling:
    - remove_background / birefnet: High-accuracy AI background removal using BiRefNet.

    Operates directly on local SSD file paths.
    """

    def process_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        options: dict[str, Any],
    ) -> str:
        """Process image background removal directly from input_path to output_path."""
        bg_removal_service.remove_background_file(input_path, output_path)
        return "image/png"

    def _process_bytes(self, input_data: bytes, options: dict[str, Any]) -> tuple[bytes, str]:
        """Legacy in-memory processor for byte payloads."""
        output_png = bg_removal_service.remove_background(input_data)
        return output_png, "image/png"


gpu_ai_processor = GpuAiProcessor()
