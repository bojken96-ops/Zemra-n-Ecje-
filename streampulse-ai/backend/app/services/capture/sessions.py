"""Backend side of the capture control plane.

The Windows capture agent *pulls* commands from the backend (it runs on the host,
the backend runs in Docker), reports status/health and registers each finished
recording segment. The backend never reaches into the host.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import CaptureSession, Creator, RecordingSegment, Stream
from app.services import audit as audit_svc
from app.services import events
from app.utils.time import utcnow

log = logging.getLogger(__name__)
ACTIVE = ("pending", "starting", "recording", "reconnecting", "stopping")
HEARTBEAT_TIMEOUT = timedelta(seconds=90)


class CaptureNotAllowed(RuntimeError):
    pass


def active_session(db: Session, stream_id) -> CaptureSession | None:
    return (db.query(CaptureSession)
            .filter(CaptureSession.stream_id == stream_id, CaptureSession.status.in_(ACTIVE))
            .one_or_none())


def assert_authorised(db: Session, stream: Stream) -> None:
    creator = db.get(Creator, stream.creator_id) if stream.creator_id else None
    if creator is None:
        raise CaptureNotAllowed("Capture blocked: assign this stream to a creator first.")
    if not creator.authorised:
        raise CaptureNotAllowed(
            f"Capture blocked: creator '{creator.name}' is not marked as authorised. "
            "Record the authorisation on the creator before capturing."
        )


def request_start(db: Session, stream: Stream) -> CaptureSession:
    assert_authorised(db, stream)
    if stream.status not in ("live", "reconnecting"):
        raise CaptureNotAllowed("Capture can only start while the stream is live (checked via the YouTube API).")
    existing = active_session(db, stream.id)
    if existing:
        return existing
    sess = CaptureSession(stream_id=stream.id, status="pending")
    db.add(sess)
    db.flush()
    audit_svc.audit(db, "capture.requested", stream_id=str(stream.id), session_id=str(sess.id))
    events.publish("capture.updated", session_to_event(sess))
    return sess


def request_stop(db: Session, stream: Stream, reason: str = "user") -> CaptureSession | None:
    sess = active_session(db, stream.id)
    if sess is None:
        return None
    if sess.status == "pending":
        sess.status = "stopped"
        sess.ended_at = utcnow()
    else:
        sess.stop_requested = True
        sess.status = "stopping"
    audit_svc.audit(db, "capture.stop_requested", stream_id=str(stream.id), session_id=str(sess.id), reason=reason)
    events.publish("capture.updated", session_to_event(sess))
    return sess


def session_to_event(sess: CaptureSession) -> dict:
    return {"id": str(sess.id), "stream_id": str(sess.stream_id), "status": sess.status,
            "capture_method": sess.capture_method, "health": sess.health, "error_message": sess.error_message}


def pending_commands(db: Session, max_concurrent: int) -> list[dict]:
    """Commands for the agent: start pending sessions (respecting concurrency) and stop requested ones."""
    commands: list[dict] = []
    running = db.query(CaptureSession).filter(CaptureSession.status.in_(("starting", "recording", "reconnecting"))).count()
    for sess in db.query(CaptureSession).filter(CaptureSession.stop_requested.is_(True),
                                                 CaptureSession.status == "stopping").all():
        commands.append({"action": "stop", "session_id": str(sess.id), "stream_id": str(sess.stream_id)})
    pending = (db.query(CaptureSession).filter(CaptureSession.status == "pending")
               .order_by(CaptureSession.created_at).all())
    for sess in pending:
        if running >= max_concurrent:
            break
        stream = db.get(Stream, sess.stream_id)
        if stream is None or not stream.youtube_video_id:
            continue
        sess.status = "starting"
        sess.last_heartbeat_at = utcnow()
        running += 1
        commands.append({
            "action": "start", "session_id": str(sess.id), "stream_id": str(stream.id),
            "url": f"https://www.youtube.com/watch?v={stream.youtube_video_id}",
            "recording_dir": f"recordings/{stream.id}/{sess.id}",
        })
    db.commit()
    return commands


def update_status(db: Session, sess: CaptureSession, status: str, capture_method: str | None,
                  health: dict | None, error: str | None, recording_path: str | None) -> CaptureSession:
    previous = sess.status
    if status not in ("starting", "recording", "reconnecting", "stopped", "failed"):
        raise ValueError("invalid capture status")
    # a stop request must not be overwritten by a late "recording" heartbeat
    if sess.stop_requested and status in ("starting", "recording", "reconnecting"):
        status = "stopping"
    sess.status = status
    sess.last_heartbeat_at = utcnow()
    if capture_method:
        sess.capture_method = capture_method
    if health is not None:
        sess.health = health
    if recording_path:
        sess.recording_path = recording_path
    if error:
        sess.error_message = error[:2000]
    if status == "recording" and sess.started_at is None:
        sess.started_at = utcnow()
    if status in ("stopped", "failed"):
        sess.ended_at = sess.ended_at or utcnow()
    stream = db.get(Stream, sess.stream_id)
    if stream is not None:
        if status == "reconnecting" and stream.status == "live":
            stream.status = "reconnecting"
        elif status == "recording" and stream.status == "reconnecting":
            stream.status = "live"
    if previous != status:
        audit_svc.audit(db, "capture.status", session_id=str(sess.id), previous=previous, status=status, error=error)
        if status == "failed":
            audit_svc.notify(db, "capture", f"Capture failed: {error or 'unknown error'}", level="error",
                             session_id=str(sess.id))
    db.commit()
    events.publish("capture.updated", session_to_event(sess))
    return sess


def register_segment(db: Session, sess: CaptureSession, sequence: int, file_path: str, start_time: datetime,
                     end_time: datetime, size_bytes: int, width: int | None, height: int | None,
                     fps: float | None) -> RecordingSegment:
    seg = (db.query(RecordingSegment)
           .filter(RecordingSegment.capture_session_id == sess.id, RecordingSegment.sequence == sequence)
           .one_or_none())
    if seg is None:
        seg = RecordingSegment(capture_session_id=sess.id, stream_id=sess.stream_id, sequence=sequence,
                               file_path=file_path, start_time=start_time, end_time=end_time)
        db.add(seg)
    seg.size_bytes, seg.width, seg.height, seg.fps = size_bytes, width, height, fps
    sess.last_heartbeat_at = utcnow()
    db.commit()
    return seg


def expire_stale_sessions(db: Session) -> int:
    """Mark sessions whose agent stopped heartbeating as failed."""
    cutoff = utcnow() - HEARTBEAT_TIMEOUT
    stale = (db.query(CaptureSession)
             .filter(CaptureSession.status.in_(("starting", "recording", "reconnecting", "stopping")),
                     CaptureSession.last_heartbeat_at < cutoff).all())
    for sess in stale:
        sess.status = "failed"
        sess.error_message = "Capture agent stopped responding (no heartbeat for 90s)."
        sess.ended_at = utcnow()
        audit_svc.notify(db, "capture", sess.error_message, level="error", session_id=str(sess.id))
        events.publish("capture.updated", session_to_event(sess))
    db.commit()
    return len(stale)
