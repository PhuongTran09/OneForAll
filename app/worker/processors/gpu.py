from typing import Any

from app.services.bg_removal_service import bg_removal_service
from app.worker.processors.base import BaseProcessor


class GpuAiProcessor(BaseProcessor):
    """
    GPU & AI Processor handling:
    - remove_background / birefnet: High-accuracy AI background removal using BiRefNet.
    """

    def process(self, input_data: bytes, options: dict[str, Any]) -> tuple[bytes, str]:
        # Uses BiRefNet background removal service on GPU/CPU
        output_png = bg_removal_service.remove_background(input_data)
        return output_png, "image/png"


gpu_ai_processor = GpuAiProcessor()
