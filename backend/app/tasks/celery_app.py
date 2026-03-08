"""Celery application configuration with beat schedule."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "linkedin_platform",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Concurrency & scaling
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Rate limiting at worker level
    task_default_rate_limit="10/m",

    # Queues
    task_routes={
        "app.tasks.posting_tasks.*": {"queue": "posting"},
        "app.tasks.connection_tasks.*": {"queue": "connections"},
        "app.tasks.sales_tasks.*": {"queue": "sales"},
        "app.tasks.followup_tasks.*": {"queue": "followups"},
        "app.tasks.campaign_tasks.*": {"queue": "campaigns"},
    },

    # Result expiry
    result_expires=3600,

    # Beat schedule – periodic tasks
    beat_schedule={
        "process-followups-every-30min": {
            "task": "app.tasks.followup_tasks.process_pending_followups",
            "schedule": crontab(minute="*/30"),
        },
        "daily-analytics-snapshot": {
            "task": "app.tasks.campaign_tasks.daily_analytics_snapshot",
            "schedule": crontab(hour=23, minute=55),
        },
        "check-active-posting-campaigns": {
            "task": "app.tasks.posting_tasks.check_scheduled_posts",
            "schedule": crontab(minute="*/15"),
        },
        "warmup-progression": {
            "task": "app.tasks.campaign_tasks.progress_warmup",
            "schedule": crontab(hour=0, minute=5),
        },
        # Auto-run active campaigns every hour (staggered to avoid overlap)
        "run-active-connection-campaigns": {
            "task": "app.tasks.connection_tasks.run_all_active_connection_campaigns",
            "schedule": crontab(minute=10),  # Every hour at :10
        },
        "run-active-sales-campaigns": {
            "task": "app.tasks.sales_tasks.run_all_active_sales_campaigns",
            "schedule": crontab(minute=25),  # Every hour at :25
        },
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks([
    "app.tasks.campaign_tasks",
    "app.tasks.posting_tasks",
    "app.tasks.connection_tasks",
    "app.tasks.sales_tasks",
    "app.tasks.followup_tasks",
    "app.tasks.campaign_scheduler",
])
