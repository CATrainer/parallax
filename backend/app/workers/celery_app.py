"""Celery application + beat schedule (BUILD_SPEC §Celery contract, §5.6).

One ingest task per source, scheduled to its cadence. We keep the beat schedule simple:
each registered adapter gets a ``crontab`` derived from its declared ``cadence``
(daily | weekly | monthly | realtime/frequent). Tasks live in ``app.workers.tasks`` and are
auto-discovered.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.adapters.registry import ADAPTERS
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("parallax.celery")

celery_app = Celery(
    "parallax",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
)


def _schedule_for(cadence: str):
    """Map an adapter cadence to a crontab. Realtime/frequent sources poll hourly here
    (a true streaming consumer would run as its own long-lived worker)."""
    cadence = (cadence or "daily").lower()
    if cadence == "monthly":
        # 21st of the month (HMLR price-paid lands ~20th working day) at 02:00.
        return crontab(minute=0, hour=2, day_of_month=21)
    if cadence == "weekly":
        return crontab(minute=0, hour=3, day_of_week=1)  # Mondays 03:00
    if cadence in {"realtime", "frequent"}:
        return crontab(minute=0)  # hourly poll
    return crontab(minute=0, hour=4)  # daily 04:00 (default)


# Wire one scheduled ingest per registered adapter on its cadence.
beat_schedule: dict[str, dict] = {}
for _name, _adapter in ADAPTERS.items():
    beat_schedule[f"ingest-{_name}"] = {
        "task": "app.workers.tasks.ingest_source",
        "schedule": _schedule_for(getattr(_adapter, "cadence", "daily")),
        "args": (_name,),
    }

celery_app.conf.beat_schedule = beat_schedule
