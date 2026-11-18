"""Live chat ingestion through the YouTube Live Chat API (liveChatMessages.list polling).

The API returns ``pollingIntervalMillis``; we honour it. Handles disabled/ended chats,
quota errors and expired chat ids without crashing the pipeline.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import ChatEvent, Stream
from app.services.chat.analytics import count_emoji
from app.services.youtube.client import QuotaExceeded, YouTubeAPIError, YouTubeClient

log = logging.getLogger(__name__)
TERMINAL_REASONS = {"liveChatEnded": "ended", "liveChatDisabled": "disabled", "liveChatNotFound": "unavailable",
                    "forbidden": "forbidden"}


@dataclass
class PollResult:
    inserted: int
    next_page_token: str | None
    poll_after_seconds: float
    chat_status: str  # active | ended | disabled | unavailable | forbidden | quota | error
    stop: bool


def parse_items(items: list[dict]) -> list[dict]:
    rows = []
    for it in items:
        sn = it.get("snippet", {})
        author = it.get("authorDetails", {})
        msg_type = sn.get("type")
        text = sn.get("displayMessage") or sn.get("textMessageDetails", {}).get("messageText") or ""
        ts = sn.get("publishedAt")
        rows.append({
            "message_id": it.get("id"),
            "author_id": sn.get("authorChannelId") or author.get("channelId"),
            "message": text,
            "event_timestamp": datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None,
            "metadata_": {"type": msg_type, "emoji": count_emoji(text),
                          "author_name": author.get("displayName"),
                          "is_moderator": author.get("isChatModerator", False),
                          "is_owner": author.get("isChatOwner", False),
                          "is_member": author.get("isChatSponsor", False),
                          "super_chat": sn.get("superChatDetails", {}).get("amountDisplayString")},
        })
    return rows


def store_messages(db: Session, stream_id, rows: list[dict]) -> int:
    if not rows:
        return 0
    values = [{"stream_id": stream_id, "message_id": r["message_id"], "author_id": r["author_id"],
               "message": r["message"], "event_timestamp": r["event_timestamp"], "metadata": r["metadata_"]}
              for r in rows]
    stmt = (insert(ChatEvent.__table__).values(values).on_conflict_do_nothing(constraint="uq_chat_stream_message")
            .returning(ChatEvent.__table__.c.id))
    return len(db.execute(stmt).fetchall())


def poll_once(db: Session, stream: Stream, page_token: str | None, client: YouTubeClient) -> PollResult:
    if not stream.live_chat_id:
        stream.chat_status = "unavailable"
        return PollResult(0, None, 60, "unavailable", stop=True)
    try:
        data = client.list_chat_messages(stream.live_chat_id, page_token)
    except QuotaExceeded as exc:
        stream.chat_status = "quota"
        log.warning("chat quota exceeded", extra={"stream_id": str(stream.id), "reason": exc.reason})
        # back off substantially; quota resets daily (Pacific midnight)
        return PollResult(0, page_token, 300, "quota", stop=False)
    except YouTubeAPIError as exc:
        status = TERMINAL_REASONS.get(exc.reason or "")
        if status:
            stream.chat_status = status
            return PollResult(0, None, 0, status, stop=True)
        stream.chat_status = "error"
        log.warning("chat poll error", extra={"stream_id": str(stream.id), "error": str(exc)})
        return PollResult(0, page_token, 30, "error", stop=False)
    rows = parse_items(data.get("items", []))
    inserted = store_messages(db, stream.id, rows)
    stream.chat_status = "active"
    if data.get("offlineAt"):
        stream.chat_status = "ended"
        return PollResult(inserted, None, 0, "ended", stop=True)
    interval = max(1.0, data.get("pollingIntervalMillis", 5000) / 1000)
    return PollResult(inserted, data.get("nextPageToken"), interval, "active", stop=False)
