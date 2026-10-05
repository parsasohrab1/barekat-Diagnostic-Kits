"""Celery application for asynchronous processing."""

from celery import Celery

from barekat_diagnostics.core.config import get_settings

settings = get_settings()

celery_app = Celery(
  "barekat_diagnostics",
  broker=settings.celery_broker_url,
  backend=settings.celery_result_backend,
)

celery_app.conf.update(
  task_serializer="json",
  accept_content=["json"],
  result_serializer="json",
  timezone="Asia/Tehran",
  enable_utc=True,
  task_track_started=True,
)

celery_app.autodiscover_tasks(["barekat_diagnostics.tasks"])
