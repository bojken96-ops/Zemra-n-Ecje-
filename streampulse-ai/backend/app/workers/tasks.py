"""Celery tasks. Each task opens its own DB session and is idempotent where possible."""
from __future__ import annotations

import logging
from datetime import timedelta

from app.db import session_scope
from app.models import CaptureSession, ClipCandidate, PublishingJob, RecordingSegment, Stream
from app.services import app_settings as settings_svc
from app.services.events import redis_client
from app.utils.time import utcnow
from app.workers.celery_app import celery

log = logging.getLogger(__name__)
CHAT_LOCK = "chatpoll:{}"
CHAT_TOKEN = "chatpoll:token:{}"


# ------------------------------------------------------------------------------------------ streams
@celery.task
def refresh_streams() -> int:
    from app.services.youtube.client import ConfigurationError, YouTubeAPIError, YouTubeClient
    from app.services.youtube.streams import refresh_stream

    try:
        client = YouTubeClient()
    except ConfigurationError as exc:
        log.warning("stream refresh skipped", extra={"error": str(exc)})
        return 0
    count = 0
    with session_scope() as db:
        for stream in db.query(Stream).filter(Stream.monitoring_enabled.is_(True)).all():
            try:
                refresh_stream(db, stream, client)
                count += 1
            except YouTubeAPIError as exc:
                stream.last_error = str(exc)[:500]
            db.commit()
    client.close()
    return count


# ------------------------------------------------------------------------------------------ chat
def schedule_chat_polling(stream_id) -> None:
    """Start a chat polling chain unless one is already running for this stream."""
    try:
        if redis_client().set(CHAT_LOCK.format(stream_id), "1", nx=True, ex=600):
            poll_chat.apply_async(args=[str(stream_id)], countdown=5)  # after the caller commits
    except Exception as exc:  # redis down: watchdog will retry
        log.warning("could not schedule chat polling", extra={"error": str(exc)})


@celery.task
def poll_chat(stream_id: str) -> str:
    from app.services.chat.ingest import poll_once
    from app.services.youtube.client import ConfigurationError, YouTubeClient

    r = redis_client()
    with session_scope() as db:
        stream = db.get(Stream, stream_id)
        if stream is None or not stream.monitoring_enabled or stream.status not in ("live", "reconnecting"):
            r.delete(CHAT_LOCK.format(stream_id), CHAT_TOKEN.format(stream_id))
            return "stopped"
        try:
            client = YouTubeClient()
        except ConfigurationError:
            stream.chat_status = "unavailable"
            r.delete(CHAT_LOCK.format(stream_id))
            return "no-api-key"
        result = poll_once(db, stream, r.get(CHAT_TOKEN.format(stream_id)), client)
        client.close()
        db.commit()
    if result.stop:
        r.delete(CHAT_LOCK.format(stream_id), CHAT_TOKEN.format(stream_id))
        return result.chat_status
    if result.next_page_token:
        r.set(CHAT_TOKEN.format(stream_id), result.next_page_token, ex=3600)
    r.expire(CHAT_LOCK.format(stream_id), int(result.poll_after_seconds) + 600)
    poll_chat.apply_async(args=[stream_id], countdown=result.poll_after_seconds)
    return result.chat_status


@celery.task
def chat_watchdog() -> int:
    with session_scope() as db:
        ids = [s.id for s in db.query(Stream.id).filter(Stream.status == "live", Stream.monitoring_enabled.is_(True),
                                                        Stream.live_chat_id.isnot(None),
                                                        Stream.chat_status.notin_(("ended", "disabled", "forbidden"))).all()]
    for sid in ids:
        schedule_chat_polling(sid)
    return len(ids)


# ------------------------------------------------------------------------------------------ capture
@celery.task
def expire_stale_captures() -> int:
    from app.services.capture.sessions import expire_stale_sessions

    with session_scope() as db:
        return expire_stale_sessions(db)


@celery.task
def analyse_segment(segment_id: str) -> str:
    from app.services.clipping.pipeline import analyse_segment as analyse, segment_quality_flags
    from app.services.detection.engine import score_window, windows_for_range

    with session_scope() as db:
        seg = analyse(db, segment_id)
        if seg is None or (seg.quality or {}).get("error"):
            return "skipped"
        cfg = settings_svc.load_settings(db)
        stream = db.get(Stream, seg.stream_id)
        sess = db.get(CaptureSession, seg.capture_session_id)
        if sess is not None:
            sess.health = {**(sess.health or {}), **segment_quality_flags(db, sess, cfg)}
        for ws in windows_for_range(seg.start_time, seg.end_time, cfg.detection.window_seconds):
            score_window(db, stream, ws, cfg)
        db.commit()
    return "ok"


# ------------------------------------------------------------------------------------------ clips
@celery.task
def evaluate_due_candidates() -> int:
    with session_scope() as db:
        cfg = settings_svc.load_settings(db)
        due_before = utcnow() - timedelta(seconds=cfg.clips.post_event_seconds + 2 * cfg.capture.segment_seconds)
        ids = [c.id for c in db.query(ClipCandidate.id).filter(ClipCandidate.status == "pending",
                                                               ClipCandidate.event_time <= due_before).all()]
    for cid in ids:
        lock = f"candidate:{cid}"
        if redis_client().set(lock, "1", nx=True, ex=1800):
            evaluate_candidate.delay(str(cid))
    return len(ids)


@celery.task(bind=True, max_retries=20)
def evaluate_candidate(self, candidate_id: str) -> str:
    from app.services.clipping.pipeline import NotReady, evaluate_candidate as evaluate

    try:
        with session_scope() as db:
            status = evaluate(db, candidate_id)
    except NotReady as exc:
        raise self.retry(exc=exc, countdown=15)
    finally:
        redis_client().delete(f"candidate:{candidate_id}")
    if status == "accepted":
        generate_clip.delay(candidate_id)
    return status


@celery.task
def generate_clip(candidate_id: str) -> str | None:
    from app.services.clipping.pipeline import create_clip_from_candidate

    with session_scope() as db:
        clip = create_clip_from_candidate(db, candidate_id)
        return str(clip.id) if clip else None


@celery.task
def regenerate_clip(clip_id: str, subtitle_style: str | None = None, regenerate_content: bool = False) -> str:
    from app.models import Clip
    from app.services.clipping.pipeline import regenerate

    with session_scope() as db:
        clip = db.get(Clip, clip_id)
        if clip is None:
            return "missing"
        regenerate(db, clip, subtitle_style=subtitle_style, regenerate_content=regenerate_content)
        return clip.status


# ------------------------------------------------------------------------------------------ publishing
@celery.task
def dispatch_publishing() -> int:
    from app.services.publishing.queue import due_jobs

    with session_scope() as db:
        jobs = due_jobs(db)
        ids = [str(j.id) for j in jobs]
    for jid in ids:
        publish_job.delay(jid)
    return len(ids)


@celery.task
def publish_job(job_id: str) -> str:
    from app.services.publishing.queue import run_job

    with session_scope() as db:
        return run_job(db, job_id)


@celery.task
def poll_publishing() -> int:
    with session_scope() as db:
        ids = [str(j.id) for j in db.query(PublishingJob.id).filter(PublishingJob.status == "processing").all()]
    for jid in ids:
        poll_publish_status.delay(jid)
    return len(ids)


@celery.task
def poll_publish_status(job_id: str) -> str:
    from app.services.publishing.queue import poll_job

    with session_scope() as db:
        return poll_job(db, job_id)


# ------------------------------------------------------------------------------------------ storage
@celery.task
def storage_cleanup() -> dict:
    from app.services.storage.manager import cleanup

    with session_scope() as db:
        report = cleanup(db)
    report.pop("usage", None)
    return report


__all__ = ["schedule_chat_polling", "RecordingSegment"]
