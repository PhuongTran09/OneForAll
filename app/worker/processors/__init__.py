from app.worker.processors.base import BaseProcessor
from app.worker.processors.document import DocumentConvertProcessor, document_processor
from app.worker.processors.gpu import GpuAiProcessor, gpu_ai_processor
from app.worker.processors.image import ImageProcessProcessor, image_processor
from app.worker.processors.video import VideoAudioProcessor, video_audio_processor

__all__ = [
    "BaseProcessor",
    "DocumentConvertProcessor",
    "GpuAiProcessor",
    "ImageProcessProcessor",
    "VideoAudioProcessor",
    "document_processor",
    "gpu_ai_processor",
    "image_processor",
    "video_audio_processor",
]
