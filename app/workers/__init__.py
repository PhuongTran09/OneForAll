import app.worker.tasks
from app.worker.celery_app import CeleryQueue, celery_app

app = celery_app

__all__ = ["CeleryQueue", "app", "celery_app"]
