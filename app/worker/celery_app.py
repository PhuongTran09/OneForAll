from enum import StrEnum

from celery import Celery
from kombu import Exchange, Queue

from app.core.config import settings


class CeleryQueue(StrEnum):
    CONVERT = "convert"
    IMAGE = "image"
    VIDEO = "video"
    GPU = "gpu"


# Direct exchange for explicit queue routing
default_exchange = Exchange("default", type="direct")

# Independent queues for distinct workloads
CELERY_QUEUES = (
    Queue(
        CeleryQueue.CONVERT.value,
        default_exchange,
        routing_key=CeleryQueue.CONVERT.value,
    ),
    Queue(
        CeleryQueue.IMAGE.value, default_exchange, routing_key=CeleryQueue.IMAGE.value
    ),
    Queue(
        CeleryQueue.VIDEO.value, default_exchange, routing_key=CeleryQueue.VIDEO.value
    ),
    Queue(CeleryQueue.GPU.value, default_exchange, routing_key=CeleryQueue.GPU.value),
)

# Automatic routing based on task namespace
CELERY_ROUTES = {
    # Tasks under convert (LibreOffice, VTracer, document conversions)
    "app.worker.tasks.convert.*": {"queue": CeleryQueue.CONVERT.value},
    # Tasks under image (Pillow: resize, compress, format)
    "app.worker.tasks.image.*": {"queue": CeleryQueue.IMAGE.value},
    # Tasks under video (FFmpeg, yt-dlp)
    "app.worker.tasks.video.*": {"queue": CeleryQueue.VIDEO.value},
    # Tasks under gpu (BiRefNet, AI models)
    "app.worker.tasks.gpu.*": {"queue": CeleryQueue.GPU.value},
}

celery_app = Celery(
    "oneforall",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.worker.tasks.convert",
        "app.worker.tasks.image",
        "app.worker.tasks.video",
        "app.worker.tasks.gpu",
        "app.worker.tasks.cleanup",
        "app.worker.tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_queue=settings.CELERY_DEFAULT_QUEUE,
    task_default_exchange="default",
    task_default_routing_key=settings.CELERY_DEFAULT_QUEUE,
    task_queues=CELERY_QUEUES,
    task_routes=CELERY_ROUTES,
    # Worker optimization settings for independent scaling & memory management
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,  # Recycle worker processes to prevent memory leaks
    result_expires=1800,  # Redis result keys expire after 30 minutes
    broker_connection_retry_on_startup=True,
    task_compression="gzip",
    result_compression="gzip",
    worker_disable_rate_limits=True,
    # Periodic Cleanup Schedule: runs every 60 seconds (1 minute)
    beat_schedule={
        "cleanup-expired-jobs-every-minute": {
            "task": "app.worker.tasks.cleanup.cleanup_expired_jobs_task",
            "schedule": 60.0,
            "options": {"queue": CeleryQueue.CONVERT.value},
        },
    },
)
