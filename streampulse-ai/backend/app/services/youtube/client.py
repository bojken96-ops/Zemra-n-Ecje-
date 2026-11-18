"""YouTube Data API v3 client (official, supported endpoints only)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from app.config import get_settings

API = "https://www.googleapis.com/youtube/v3"
log = logging.getLogger(__name__)


class YouTubeAPIError(RuntimeError):
    def __init__(self, message: str, reason: str | None = None, status: int | None = None):
        super().__init__(message)
        self.reason = reason
        self.status = status


class QuotaExceeded(YouTubeAPIError):
    pass


class ConfigurationError(RuntimeError):
    pass


@dataclass
class VideoInfo:
    video_id: str
    title: str
    channel_id: str
    channel_title: str
    thumbnail_url: str | None
    live_broadcast_content: str  # live | upcoming | none
    is_livestream: bool
    scheduled_start: datetime | None = None
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    active_live_chat_id: str | None = None
    concurrent_viewers: int | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def status(self) -> str:
        """Liveness derived ONLY from liveStreamingDetails, never from the URL."""
        if not self.is_livestream:
            return "offline"
        if self.actual_end:
            return "ended"
        if self.actual_start:
            return "live"
        if self.scheduled_start or self.live_broadcast_content == "upcoming":
            return "upcoming"
        return "offline"


@dataclass
class ChannelInfo:
    channel_id: str
    title: str
    thumbnail_url: str | None


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _best_thumb(thumbs: dict) -> str | None:
    for key in ("maxres", "standard", "high", "medium", "default"):
        if key in thumbs:
            return thumbs[key]["url"]
    return None


class YouTubeClient:
    def __init__(self, api_key: str | None = None, access_token: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        self.api_key = api_key if api_key is not None else get_settings().youtube_api_key
        self.access_token = access_token
        if not self.api_key and not self.access_token:
            raise ConfigurationError("YOUTUBE_API_KEY is not configured")
        self._client = httpx.Client(timeout=20, transport=transport)

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, params: dict) -> dict:
        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        else:
            params = {**params, "key": self.api_key}
        resp = self._client.get(f"{API}/{path}", params=params, headers=headers)
        if resp.status_code >= 400:
            reason, message = None, resp.text[:300]
            try:
                err = resp.json()["error"]
                message = err.get("message", message)
                reason = (err.get("errors") or [{}])[0].get("reason")
            except (ValueError, KeyError):
                pass
            cls = QuotaExceeded if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded") else YouTubeAPIError
            raise cls(f"YouTube API {path}: {message}", reason=reason, status=resp.status_code)
        return resp.json()

    def get_video(self, video_id: str) -> VideoInfo | None:
        data = self._get("videos", {"part": "snippet,liveStreamingDetails", "id": video_id})
        items = data.get("items") or []
        if not items:
            return None
        return self._video_from_item(items[0])

    @staticmethod
    def _video_from_item(item: dict) -> VideoInfo:
        sn = item.get("snippet", {})
        lsd = item.get("liveStreamingDetails")
        viewers = (lsd or {}).get("concurrentViewers")
        return VideoInfo(
            video_id=item["id"],
            title=sn.get("title", ""),
            channel_id=sn.get("channelId", ""),
            channel_title=sn.get("channelTitle", ""),
            thumbnail_url=_best_thumb(sn.get("thumbnails", {})),
            live_broadcast_content=sn.get("liveBroadcastContent", "none"),
            is_livestream=lsd is not None,
            scheduled_start=_dt((lsd or {}).get("scheduledStartTime")),
            actual_start=_dt((lsd or {}).get("actualStartTime")),
            actual_end=_dt((lsd or {}).get("actualEndTime")),
            active_live_chat_id=(lsd or {}).get("activeLiveChatId"),
            concurrent_viewers=int(viewers) if viewers else None,
            raw=item,
        )

    def get_channel(self, channel_id: str | None = None, handle: str | None = None) -> ChannelInfo | None:
        params = {"part": "snippet"}
        if channel_id:
            params["id"] = channel_id
        elif handle:
            params["forHandle"] = handle
        else:
            raise ValueError("channel_id or handle required")
        items = self._get("channels", params).get("items") or []
        if not items:
            return None
        sn = items[0]["snippet"]
        return ChannelInfo(items[0]["id"], sn.get("title", ""), _best_thumb(sn.get("thumbnails", {})))

    def find_channel_broadcast(self, channel_id: str) -> str | None:
        """Return the video id of the channel's current live broadcast, else its next upcoming one.

        search.list costs 100 quota units per call; callers must throttle.
        """
        for event_type in ("live", "upcoming"):
            data = self._get("search", {"part": "id", "channelId": channel_id, "eventType": event_type,
                                        "type": "video", "maxResults": 5, "order": "date"})
            ids = [i["id"]["videoId"] for i in data.get("items", []) if i.get("id", {}).get("videoId")]
            if ids:
                return ids[0]
        return None

    def list_chat_messages(self, live_chat_id: str, page_token: str | None = None) -> dict:
        params = {"liveChatId": live_chat_id, "part": "snippet,authorDetails", "maxResults": 2000}
        if page_token:
            params["pageToken"] = page_token
        return self._get("liveChat/messages", params)
