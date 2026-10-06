from typing import Any

from app.utils.logger import logger
from app.worker.celery_app import CeleryQueue, celery_app


@celery_app.task(
    name="app.worker.tasks.gpu.process_gpu_job", queue=CeleryQueue.GPU.value
)
def process_gpu_job(job_id: str, **kwargs: Any) -> dict[str, str]:
    """
    Main job processor for GPU / AI model workloads on the 'gpu' queue.
    Workloads: BiRefNet background removal, heavy PyTorch/CUDA model inference.
    """
    logger.info("[gpu-worker] Processing GPU job: %s", job_id)
    return {"job_id": job_id, "queue": CeleryQueue.GPU.value, "status": "processing"}


@celery_app.task(
    name="app.worker.tasks.gpu.birefnet_remove_bg", queue=CeleryQueue.GPU.value
)
def birefnet_remove_bg(input_key: str, **kwargs: Any) -> dict[str, str]:
    """Execute BiRefNet high-accuracy background removal on GPU."""
    logger.info("[gpu-worker] Executing BiRefNet background removal for %s", input_key)
    return {"input_key": input_key, "model": "BiRefNet", "status": "completed"}
