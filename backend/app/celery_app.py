"""Celery application instance."""
from __future__ import annotations

from celery import Celery

from .config import get_settings


settings = get_settings()

celery_app = Celery(
    "training_processing",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.task_routes = {"backend.app.tasks.*": {"queue": "courses"}}
celery_app.autodiscover_tasks(["backend.app"])
