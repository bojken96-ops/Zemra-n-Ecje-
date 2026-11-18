"""Stream lifecycle: metadata, live detection, transitions that drive capture and chat."""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import Creator, Stream
from app.services import audit as audit_svc
from app.services import events
from app.services.capture import sessions as capture_sessions
from app.services.youtube.client import ConfigurationError, QuotaExceeded, VideoInfo, YouTubeAPIError, YouTubeClient
from app.services.youtube.urls import ParsedYouTubeURL, parse_youtube_url
from app.utils.time import utcnow

log = logging.getLogger(__name__)
CHANNEL_SEARCH_INTERVAL = timedelta(minutes=5)  # search.list costs 100 units


class StreamError(ValueError):
    pass


def stream_to_event(stream: Stream) -> dict:
    return {"id": str(stream.id), "status": stream.status, "title": stream.title,
            "chat_status": stream.chat_status, "current_viral_score": stream.current_viral_score}


def add_stream(db: Session, url: str, creator_id=None, client: YouTubeClient | None = None) -> Stream:
    parsed = parse_youtube_url(url)
    if parsed.kind == "video":
        existing = db.query(Stream).filter(Stream.youtube_video_id == parsed.video_id).one_or_none()
        if existing:
            raise StreamError("this livestream is already being tracked")
    creator = db.get(Creator, creator_id) if creator_id else None
    if creator_id and creator is None:
        raise StreamError("creator not found")
    stream = Stream(youtube_url=parsed.canonical_url(), youtube_video_id=parsed.video_id,
                    youtube_channel_id=parsed.channel_id, creator_id=creator_id, status="offline")
    db.add(stream)
    db.flush()
    try:
        client = client or YouTubeClient()
        _resolve_channel_handle(stream, parsed, client)
        refresh_stream(db, stream, client=client, force_search=True)
    except ConfigurationError as exc:
        stream.last_error = str(exc)
    except YouTubeAPIError as exc:
        stream.last_error = str(exc)
    if creator is None and stream.youtube_channel_id:
        creator = db.query(Creator).filter(Creator.youtube_channel_id == stream.youtube_channel_id).one_or_none()
        if creator:
            stream.creator_id = creator.id
    audit_svc.audit(db, "stream.added", stream_id=str(stream.id), url=stream.youtube_url)
    db.commit()
    events.publish("stream.updated", stream_to_event(stream))
    return stream


def _resolve_channel_handle(stream: Stream, parsed: ParsedYouTubeURL, client: YouTubeClient) -> None:
    if parsed.kind == "handle":
        ch = client.get_channel(handle=parsed.handle)
        if ch is None:
            raise StreamError(f"YouTube channel {parsed.handle} not found")
        stream.youtube_channel_id = ch.channel_id


def apply_video_info(db: Session, stream: Stream, info: VideoInfo) -> str:
    """Update stream from API data; return previous status."""
    previous = stream.status
    stream.youtube_video_id = info.video_id
    stream.youtube_channel_id = info.channel_id or stream.youtube_channel_id
    stream.title = info.title
    stream.thumbnail_url = info.thumbnail_url
    stream.scheduled_start_at = info.scheduled_start
    stream.started_at = info.actual_start
    stream.ended_at = info.actual_end
    stream.live_chat_id = info.active_live_chat_id
    new_status = info.status
    if not info.is_livestream:
        stream.last_error = "This video is not a livestream (no liveStreamingDetails)."
    else:
        stream.last_error = None
    if previous == "reconnecting" and new_status == "live":
        pass  # capture agent will report recovery; keep live
    stream.status = new_status
    if new_status == "live" and not stream.live_chat_id:
        stream.chat_status = "unavailable"
    return previous


def refresh_stream(db: Session, stream: Stream, client: YouTubeClient | None = None, force_search: bool = False) -> None:
    client = client or YouTubeClient()
    now = utcnow()
    is_channel_style = stream.youtube_url.endswith("/live") and "/watch" not in stream.youtube_url
    try:
        if is_channel_style and stream.youtube_channel_id and (
            stream.youtube_video_id is None or stream.status in ("ended", "offline")
        ):
            due = force_search or stream.last_checked_at is None or now - stream.last_checked_at >= CHANNEL_SEARCH_INTERVAL
            if due:
                vid = client.find_channel_broadcast(stream.youtube_channel_id)
                if vid and vid != stream.youtube_video_id:
                    stream.youtube_video_id = vid
                    stream.ended_at = None
                stream.last_checked_at = now
            if stream.youtube_video_id is None:
                stream.status = "offline"
                return
        if stream.youtube_video_id is None:
            return
        info = client.get_video(stream.youtube_video_id)
        stream.last_checked_at = now
        if info is None:
            stream.status = "error"
            stream.last_error = "Video not found or private."
            return
        previous = apply_video_info(db, stream, info)
    except QuotaExceeded as exc:
        stream.last_error = f"YouTube quota exceeded: {exc}"
        log.warning("youtube quota exceeded", extra={"stream_id": str(stream.id)})
        return
    on_status_change(db, stream, previous)


def on_status_change(db: Session, stream: Stream, previous: str) -> None:
    if previous == stream.status:
        return
    log.info("stream status changed", extra={"stream_id": str(stream.id), "from": previous, "to": stream.status})
    audit_svc.audit(db, "stream.status", stream_id=str(stream.id), previous=previous, status=stream.status)
    events.publish("stream.updated", stream_to_event(stream))
    if stream.status == "live":
        audit_svc.notify(db, "stream", f"{stream.title or 'Stream'} is live", stream_id=str(stream.id))
        if stream.monitoring_enabled and stream.auto_capture:
            try:
                capture_sessions.request_start(db, stream)
            except capture_sessions.CaptureNotAllowed as exc:
                stream.last_error = str(exc)
                audit_svc.notify(db, "capture", str(exc), level="warning", stream_id=str(stream.id))
        from app.workers.tasks import schedule_chat_polling  # local import avoids cycle

        schedule_chat_polling(stream.id)
    elif previous in ("live", "reconnecting") and stream.status in ("ended", "offline"):
        capture_sessions.request_stop(db, stream, reason="stream ended")
