from celery import Celery
from celery.signals import setup_logging

from app.config import get_settings
from app.utils.logging import configure_logging

settings = get_settings()
celery = Celery("streampulse", broker=settings.redis_url, backend=settings.redis_url, include=["app.workers.tasks"])
celery.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    timezone="UTC",
    task_default_queue="default",
    task_routes={
        "app.workers.tasks.analyse_segment": {"queue": "media"},
        "app.workers.tasks.evaluate_candidate": {"queue": "media"},
        "app.workers.tasks.generate_clip": {"queue": "media"},
        "app.workers.tasks.regenerate_clip": {"queue": "media"},
        "app.workers.tasks.publish_job": {"queue": "publishing"},
        "app.workers.tasks.poll_publish_status": {"queue": "publishing"},
    },
    beat_schedule={
        "refresh-streams": {"task": "app.workers.tasks.refresh_streams", "schedule": 60.0},
        "expire-stale-captures": {"task": "app.workers.tasks.expire_stale_captures", "schedule": 30.0},
        "evaluate-due-candidates": {"task": "app.workers.tasks.evaluate_due_candidates", "schedule": 15.0},
        "dispatch-publishing": {"task": "app.workers.tasks.dispatch_publishing", "schedule": 30.0},
        "poll-publishing": {"task": "app.workers.tasks.poll_publishing", "schedule": 60.0},
        "storage-cleanup": {"task": "app.workers.tasks.storage_cleanup", "schedule": 3600.0},
        "chat-watchdog": {"task": "app.workers.tasks.chat_watchdog", "schedule": 120.0},
    },
)


@setup_logging.connect
def _logging(**_):
    configure_logging(settings.log_level)
