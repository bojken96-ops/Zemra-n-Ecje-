import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import ActivityWindow, CaptureSession, ChatEvent, Creator, RecordingSegment, Stream
from app.schemas.api import ActivityOut, CaptureOut, ChatEventOut, StreamIn, StreamOut, StreamUpdate
from app.services import events
from app.services.audit import audit
from app.services.capture import sessions as capture_sessions
from app.services.youtube.client import ConfigurationError, YouTubeAPIError, YouTubeClient
from app.services.youtube.streams import StreamError, add_stream, refresh_stream, stream_to_event
from app.services.youtube.urls import InvalidYouTubeURL
from app.utils.time import utcnow

router = APIRouter(prefix="/api/streams", tags=["streams"], dependencies=[Depends(current_user)])


def serialize(db: Session, stream: Stream) -> StreamOut:
    out = StreamOut.model_validate(stream)
    creator = db.get(Creator, stream.creator_id) if stream.creator_id else None
    if creator:
        out.creator_name, out.creator_image = creator.name, creator.profile_image
    sess = (db.query(CaptureSession).filter(CaptureSession.stream_id == stream.id)
            .order_by(CaptureSession.created_at.desc()).first())
    if sess:
        out.capture = CaptureOut.model_validate(sess)
        total = (db.query(func.coalesce(func.sum(func.extract("epoch", RecordingSegment.end_time - RecordingSegment.start_time)), 0))
                 .filter(RecordingSegment.capture_session_id == sess.id).scalar())
        out.recording_seconds = float(total or 0)
    out.chat_messages_last_minute = (db.query(func.count(ChatEvent.id))
                                     .filter(ChatEvent.stream_id == stream.id,
                                             ChatEvent.event_timestamp >= utcnow() - timedelta(minutes=1)).scalar())
    return out


def _get(db: Session, stream_id: uuid.UUID) -> Stream:
    stream = db.get(Stream, stream_id)
    if stream is None:
        raise HTTPException(404, "stream not found")
    return stream


@router.post("", response_model=StreamOut, status_code=201)
def create(body: StreamIn, db: Session = Depends(get_db)):
    try:
        stream = add_stream(db, body.url, body.creator_id)
    except (InvalidYouTubeURL, StreamError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    return serialize(db, stream)


@router.get("", response_model=list[StreamOut])
def list_(db: Session = Depends(get_db)):
    return [serialize(db, s) for s in db.query(Stream).order_by(Stream.created_at.desc()).all()]


@router.get("/{stream_id}", response_model=StreamOut)
def get(stream_id: uuid.UUID, db: Session = Depends(get_db)):
    return serialize(db, _get(db, stream_id))


@router.patch("/{stream_id}", response_model=StreamOut)
def update(stream_id: uuid.UUID, body: StreamUpdate, db: Session = Depends(get_db)):
    stream = _get(db, stream_id)
    data = body.model_dump(exclude_unset=True)
    if "creator_id" in data and data["creator_id"] and db.get(Creator, data["creator_id"]) is None:
        raise HTTPException(422, "creator not found")
    for k, v in data.items():
        setattr(stream, k, v)
    if data.get("monitoring_enabled") is False:
        capture_sessions.request_stop(db, stream, reason="monitoring paused")
    audit(db, "stream.updated", stream_id=str(stream.id), changes=list(data))
    db.commit()
    events.publish("stream.updated", stream_to_event(stream))
    return serialize(db, stream)


@router.post("/{stream_id}/refresh", response_model=StreamOut)
def refresh(stream_id: uuid.UUID, db: Session = Depends(get_db)):
    stream = _get(db, stream_id)
    try:
        refresh_stream(db, stream, YouTubeClient(), force_search=True)
    except (ConfigurationError, YouTubeAPIError) as exc:
        stream.last_error = str(exc)
    db.commit()
    return serialize(db, stream)


@router.delete("/{stream_id}", status_code=204)
def delete(stream_id: uuid.UUID, db: Session = Depends(get_db)):
    stream = _get(db, stream_id)
    if capture_sessions.active_session(db, stream.id):
        raise HTTPException(409, "stop the capture before removing this stream")
    audit(db, "stream.deleted", stream_id=str(stream.id), url=stream.youtube_url)
    db.delete(stream)
    db.commit()


@router.post("/{stream_id}/start", response_model=StreamOut)
def start(stream_id: uuid.UUID, db: Session = Depends(get_db)):
    """Start monitoring + capture. Capture only begins once the YouTube API confirms the stream is live."""
    stream = _get(db, stream_id)
    stream.monitoring_enabled = True
    try:
        refresh_stream(db, stream, YouTubeClient())
    except (ConfigurationError, YouTubeAPIError) as exc:
        stream.last_error = str(exc)
    if stream.status in ("live", "reconnecting"):
        try:
            capture_sessions.request_start(db, stream)
        except capture_sessions.CaptureNotAllowed as exc:
            stream.last_error = str(exc)
            db.commit()
            raise HTTPException(409, str(exc)) from exc
        from app.workers.tasks import schedule_chat_polling

        schedule_chat_polling(stream.id)
    audit(db, "stream.start", stream_id=str(stream.id), status=stream.status)
    db.commit()
    return serialize(db, stream)


@router.post("/{stream_id}/stop", response_model=StreamOut)
def stop(stream_id: uuid.UUID, db: Session = Depends(get_db)):
    stream = _get(db, stream_id)
    stream.monitoring_enabled = False
    capture_sessions.request_stop(db, stream, reason="user")
    audit(db, "stream.stop", stream_id=str(stream.id))
    db.commit()
    return serialize(db, stream)


@router.get("/{stream_id}/chat", response_model=list[ChatEventOut])
def chat(stream_id: uuid.UUID, limit: int = Query(200, ge=1, le=2000), db: Session = Depends(get_db)):
    _get(db, stream_id)
    rows = (db.query(ChatEvent).filter(ChatEvent.stream_id == stream_id)
            .order_by(ChatEvent.event_timestamp.desc()).limit(limit).all())
    return rows


@router.get("/{stream_id}/activity", response_model=list[ActivityOut])
def activity(stream_id: uuid.UUID, minutes: int = Query(30, ge=1, le=24 * 60), db: Session = Depends(get_db)):
    _get(db, stream_id)
    return (db.query(ActivityWindow)
            .filter(ActivityWindow.stream_id == stream_id,
                    ActivityWindow.start_time >= utcnow() - timedelta(minutes=minutes))
            .order_by(ActivityWindow.start_time).all())
