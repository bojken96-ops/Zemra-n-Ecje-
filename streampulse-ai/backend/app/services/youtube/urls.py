"""YouTube URL parsing. Never infers liveness from the URL shape."""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
HANDLE_RE = re.compile(r"^@[A-Za-z0-9._-]{3,30}$")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}


class InvalidYouTubeURL(ValueError):
    pass


@dataclass(frozen=True)
class ParsedYouTubeURL:
    kind: str  # "video" | "channel" | "handle"
    video_id: str | None = None
    channel_id: str | None = None
    handle: str | None = None

    def canonical_url(self) -> str:
        if self.kind == "video":
            return f"https://www.youtube.com/watch?v={self.video_id}"
        if self.kind == "channel":
            return f"https://www.youtube.com/channel/{self.channel_id}/live"
        return f"https://www.youtube.com/{self.handle}/live"


def parse_youtube_url(raw: str) -> ParsedYouTubeURL:
    raw = (raw or "").strip()
    if not raw:
        raise InvalidYouTubeURL("URL is empty")
    if "://" not in raw:
        raw = "https://" + raw
    u = urlparse(raw)
    if u.scheme not in ("http", "https"):
        raise InvalidYouTubeURL("URL must use http or https")
    host = (u.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        raise InvalidYouTubeURL("not a YouTube URL")
    parts = [p for p in u.path.split("/") if p]

    if host.endswith("youtu.be"):
        if parts and VIDEO_ID_RE.match(parts[0]):
            return ParsedYouTubeURL("video", video_id=parts[0])
        raise InvalidYouTubeURL("youtu.be link without a valid video id")

    if parts[:1] == ["watch"] or not parts and "v" in parse_qs(u.query):
        vid = (parse_qs(u.query).get("v") or [""])[0]
        if VIDEO_ID_RE.match(vid):
            return ParsedYouTubeURL("video", video_id=vid)
        raise InvalidYouTubeURL("watch URL without a valid v= parameter")

    if len(parts) >= 2 and parts[0] in ("live", "embed", "v") and VIDEO_ID_RE.match(parts[1]):
        return ParsedYouTubeURL("video", video_id=parts[1])

    if parts and parts[0] == "shorts":
        raise InvalidYouTubeURL("Shorts URLs are not livestreams")

    if len(parts) >= 2 and parts[0] == "channel" and CHANNEL_ID_RE.match(parts[1]):
        return ParsedYouTubeURL("channel", channel_id=parts[1])

    if parts and HANDLE_RE.match(parts[0]):
        return ParsedYouTubeURL("handle", handle=parts[0])

    raise InvalidYouTubeURL("unsupported YouTube URL format")
