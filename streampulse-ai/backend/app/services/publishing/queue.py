"""Publishing queue: job creation (duplicate-safe), dispatch, retries and confirmation polling."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Clip, PublishedPost, PublishingJob, SocialAccount
from app.services import app_settings as settings_svc
from app.services import audit as audit_svc
from app.services import events
from app.services.publishing import accounts
from app.services.publishing.base import AuthExpired, PublishError, PublishResult
from app.utils import storage
from app.utils.time import utcnow

log = logging.getLogger(__name__)
BACKOFF = [60, 300, 900, 3600, 3 * 3600, 6 * 3600]


def build_metadata(clip: Clip, platform: str, cfg, overrides: dict | None = None) -> dict:
    c = clip.content or {}
    tags = c.get("hashtags") or [t for t in cfg.publishing.hashtag_template.split() if t.startswith("#")]
    hashtags = " ".join(tags)
    caption = {"tiktok": c.get("tiktok_description"), "instagram": c.get("instagram_caption"),
               "youtube": c.get("tiktok_description")}.get(platform) or clip.description or clip.title or ""
    description = cfg.publishing.description_template.format(caption=caption, hashtags=hashtags, title=clip.title or "")
    meta = {
        "title": (c.get("youtube_title") if platform == "youtube" else None) or clip.title or "Livestream highlight",
        "description": description.strip(),
        "tags": [t.lstrip("#") for t in tags],
        "duration": clip.duration,
        "privacy": cfg.publishing.youtube_privacy if platform == "youtube" else cfg.publishing.tiktok_privacy,
    }
    meta.update(overrides or {})
    return meta


def create_jobs_for_clip(db: Session, clip: Clip, cfg=None, account_ids: list | None = None,
                         scheduled_at=None, overrides: dict | None = None) -> list[PublishingJob]:
    cfg = cfg or settings_svc.load_settings(db)
    if clip.status not in ("approved", "published", "publishing"):
        raise ValueError("clip must be approved before publishing")
    q = db.query(SocialAccount).filter(SocialAccount.connected.is_(True), SocialAccount.enabled.is_(True))
    if account_ids:
        q = q.filter(SocialAccount.id.in_(account_ids))
    when = scheduled_at or (utcnow() + timedelta(minutes=cfg.publishing.default_delay_minutes))
    created = []
    for acct in q.all():
        if not account_ids and not cfg.publishing.platforms.get(acct.platform, False):
            continue
        meta = build_metadata(clip, acct.platform, cfg, (overrides or {}).get(acct.platform))
        stmt = (insert(PublishingJob.__table__)
                .values(clip_id=clip.id, social_account_id=acct.id, platform=acct.platform, status="scheduled",
                        scheduled_at=when, metadata=meta)
                .on_conflict_do_nothing(constraint="uq_publish_clip_account")  # duplicate publishing prevention
                .returning(PublishingJob.__table__.c.id))
        row = db.execute(stmt).first()
        if row:
            created.append(db.get(PublishingJob, row[0]))
    if created:
        audit_svc.audit(db, "publish.jobs_created", clip_id=str(clip.id), count=len(created))
    db.commit()
    for job in created:
        events.publish("publish.updated", job_event(job))
    return created


def job_event(job: PublishingJob) -> dict:
    return {"id": str(job.id), "clip_id": str(job.clip_id), "platform": job.platform, "status": job.status,
            "error_message": job.error_message}


def due_jobs(db: Session, limit: int = 10) -> list[PublishingJob]:
    return (db.query(PublishingJob)
            .filter(PublishingJob.status.in_(("pending", "scheduled")), PublishingJob.scheduled_at <= utcnow())
            .order_by(PublishingJob.scheduled_at).limit(limit).with_for_update(skip_locked=True).all())


def _record_result(db: Session, job: PublishingJob, result: PublishResult) -> None:
    clip = db.get(Clip, job.clip_id)
    job.platform_job_ref = result.job_ref or job.platform_job_ref
    if result.status == "published":
        job.status = "published"
        job.platform_post_id = result.post_id
        job.error_message = (result.extra or {}).get("note")
        stmt = (insert(PublishedPost.__table__)
                .values(clip_id=job.clip_id, publishing_job_id=job.id, platform=job.platform,
                        post_id=result.post_id, post_url=result.post_url, published_at=utcnow())
                .on_conflict_do_nothing(constraint="uq_published_platform_post"))
        db.execute(stmt)
        audit_svc.audit(db, "publish.confirmed", job_id=str(job.id), platform=job.platform, post_id=result.post_id)
        audit_svc.notify(db, "publishing", f"Published to {job.platform}: {clip.title if clip else job.clip_id}",
                         job_id=str(job.id), url=result.post_url)
    elif result.status == "failed":
        _fail(db, job, PublishError(result.error or "platform reported failure", retryable=False))
        return
    else:
        job.status = "processing"
        job.platform_post_id = result.post_id or job.platform_post_id
    _sync_clip_status(db, clip)
    db.commit()
    events.publish("publish.updated", job_event(job))


def _sync_clip_status(db: Session, clip: Clip | None) -> None:
    if clip is None:
        return
    statuses = [j.status for j in db.query(PublishingJob).filter(PublishingJob.clip_id == clip.id).all()]
    if statuses and all(s == "published" for s in statuses):
        clip.status = "published"
    elif any(s in ("uploading", "processing", "scheduled", "pending") for s in statuses):
        clip.status = "publishing"
    elif any(s == "published" for s in statuses):
        clip.status = "published"
    elif statuses:
        clip.status = "approved"


def _fail(db: Session, job: PublishingJob, exc: PublishError) -> None:
    cfg = settings_svc.load_settings(db)
    job.error_message = str(exc)[:2000]
    if exc.retryable and job.attempts < cfg.publishing.max_attempts:
        delay = exc.retry_after_seconds or BACKOFF[min(job.attempts, len(BACKOFF) - 1)]
        job.status = "scheduled"
        job.scheduled_at = utcnow() + timedelta(seconds=delay)
    else:
        job.status = "failed"
        audit_svc.notify(db, "publishing", f"Publishing to {job.platform} failed: {exc}", level="error",
                         job_id=str(job.id))
    _sync_clip_status(db, db.get(Clip, job.clip_id))
    db.commit()
    events.publish("publish.updated", job_event(job))


def run_job(db: Session, job_id) -> str:
    job = db.query(PublishingJob).filter(PublishingJob.id == job_id).with_for_update(skip_locked=True).one_or_none()
    if job is None or job.status not in ("pending", "scheduled"):
        return "skipped"
    if job.scheduled_at and job.scheduled_at > utcnow():
        return "skipped"  # not due (scheduled publishing or retry backoff)
    if job.platform_job_ref:  # upload already accepted earlier: never re-upload, just confirm
        job.status = "processing"
        db.commit()
        return "processing"
    clip = db.get(Clip, job.clip_id)
    acct = db.get(SocialAccount, job.social_account_id)
    if clip is None or not clip.file_path or acct is None:
        _fail(db, job, PublishError("clip file or account missing", retryable=False))
        return "failed"
    job.status = "uploading"
    job.attempts += 1
    db.commit()
    events.publish("publish.updated", job_event(job))
    try:
        adapter = accounts.adapter_for(db, acct)
        result = asyncio.run(adapter.publish_video(storage.resolve(clip.file_path), job.metadata_ or {}))
    except AuthExpired as exc:
        _fail(db, job, exc)
        return "failed"
    except PublishError as exc:
        _fail(db, job, exc)
        return job.status
    except Exception as exc:  # network errors etc. are retryable
        log.exception("publish error", extra={"job_id": str(job.id)})
        _fail(db, job, PublishError(f"{type(exc).__name__}: {exc}", retryable=True))
        return job.status
    _record_result(db, job, result)
    return job.status


def poll_job(db: Session, job_id) -> str:
    job = db.get(PublishingJob, job_id)
    if job is None or job.status != "processing" or not job.platform_job_ref:
        return "skipped"
    acct = db.get(SocialAccount, job.social_account_id)
    try:
        adapter = accounts.adapter_for(db, acct)
        result = asyncio.run(adapter.get_publish_status(job.platform_job_ref))
    except PublishError as exc:
        if not exc.retryable:
            _fail(db, job, exc)
        return job.status
    except Exception:
        log.exception("publish status poll error", extra={"job_id": str(job.id)})
        return job.status
    if job.updated_at and job.updated_at < utcnow() - timedelta(hours=24) and result.status == "processing":
        result = PublishResult("failed", job_ref=job.platform_job_ref, error="platform did not confirm within 24h")
    _record_result(db, job, result)
    return job.status


def retry(db: Session, job: PublishingJob) -> PublishingJob:
    if job.status not in ("failed", "cancelled"):
        raise ValueError("only failed or cancelled jobs can be retried")
    job.status = "scheduled"
    job.scheduled_at = utcnow()
    job.error_message = None
    job.platform_job_ref = None  # the previous upload failed on the platform side: a retry is a new upload
    audit_svc.audit(db, "publish.retry", job_id=str(job.id))
    _sync_clip_status(db, db.get(Clip, job.clip_id))
    db.commit()
    events.publish("publish.updated", job_event(job))
    return job
