"""HTTP-level fake of the YouTube Data API v3 (only the response shapes we consume)."""
import json

import httpx


class FakeYouTube:
    def __init__(self):
        self.videos: dict[str, dict] = {}
        self.channel_live: dict[str, str] = {}
        self.chat_pages: list[dict] = []
        self.chat_error: tuple[int, str] | None = None
        self.calls: list[str] = []

    def video(self, vid, *, live=False, upcoming=False, ended=False, chat_id="chat123", channel="UC" + "b" * 22,
              livestream=True, title="Test stream"):
        lsd = None
        if livestream:
            lsd = {"scheduledStartTime": "2026-11-18T10:00:00Z"}
            if live or ended:
                lsd["actualStartTime"] = "2026-11-18T10:01:00Z"
                lsd["activeLiveChatId"] = chat_id
            if ended:
                lsd["actualEndTime"] = "2026-11-18T12:00:00Z"
                lsd.pop("activeLiveChatId")
        item = {"id": vid, "snippet": {"title": title, "channelId": channel, "channelTitle": "Chan",
                                       "liveBroadcastContent": "live" if live else ("upcoming" if upcoming else "none"),
                                       "thumbnails": {"high": {"url": f"https://i.ytimg.com/vi/{vid}/hq.jpg"}}}}
        if lsd is not None:
            item["liveStreamingDetails"] = lsd
        self.videos[vid] = item

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.split("/youtube/v3/")[-1]
        params = dict(request.url.params)
        self.calls.append(path)
        if path == "videos":
            item = self.videos.get(params["id"])
            return httpx.Response(200, json={"items": [item] if item else []})
        if path == "channels":
            return httpx.Response(200, json={"items": [{"id": "UC" + "c" * 22, "snippet": {"title": "Handle Chan",
                                                                                         "thumbnails": {}}}]})
        if path == "search":
            vid = self.channel_live.get(params["channelId"]) if params["eventType"] == "live" else None
            return httpx.Response(200, json={"items": [{"id": {"videoId": vid}}] if vid else []})
        if path == "liveChat/messages":
            if self.chat_error:
                code, reason = self.chat_error
                return httpx.Response(code, json={"error": {"message": reason, "errors": [{"reason": reason}]}})
            page = self.chat_pages.pop(0) if self.chat_pages else {"items": [], "pollingIntervalMillis": 3000}
            return httpx.Response(200, content=json.dumps(page))
        return httpx.Response(404, json={"error": {"message": "unknown"}})

    def client(self):
        from app.services.youtube.client import YouTubeClient

        return YouTubeClient(api_key="test-key", transport=httpx.MockTransport(self.handler))
