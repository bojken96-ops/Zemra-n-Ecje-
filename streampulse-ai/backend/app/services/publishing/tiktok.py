"""TikTok publishing via the official Content Posting API (Direct Post, FILE_UPLOAD).

Unaudited TikTok apps may only post with privacy SELF_ONLY; we read the creator's allowed
privacy options from creator_info and never try to bypass them.
"""
from __future__ import annotations

import math
from pathlib import Path
from urllib.parse import urlencode

import httpx

from app.services.publishing.base import (
    AuthExpired,
    PublisherAdapter,
    PublishError,
    PublishResult,
    TokenSet,
    raise_for,
)

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com/v2"
SCOPES = "user.info.basic,video.publish"
MIN_CHUNK, MAX_CHUNK = 5 * 1024 * 1024, 64 * 1024 * 1024


def authorize_url(client_key: str, redirect_uri: str, state: str) -> str:
    return AUTH_URL + "?" + urlencode({"client_key": client_key, "scope": SCOPES, "response_type": "code",
                                       "redirect_uri": redirect_uri, "state": state})


def _check(body: dict, context: str) -> dict:
    err = body.get("error") or {}
    code = err.get("code", "ok")
    if code in ("access_token_invalid", "scope_not_authorized", "token_expired"):
        raise AuthExpired(f"{context}: {code}")
    if code == "rate_limit_exceeded":
        raise PublishError(f"{context}: rate limited", retryable=True, retry_after_seconds=900)
    if code == "spam_risk_too_many_posts":
        raise PublishError(f"{context}: TikTok daily post cap reached", retryable=True, retry_after_seconds=6 * 3600)
    if code not in ("ok", ""):
        raise PublishError(f"{context}: {code} {err.get('message', '')}", retryable=False)
    return body.get("data") or {}


async def exchange_code(client_key: str, client_secret: str, redirect_uri: str, code: str, transport=None) -> TokenSet:
    async with httpx.AsyncClient(timeout=30, transport=transport) as c:
        r = await c.post(f"{API}/oauth/token/", data={"client_key": client_key, "client_secret": client_secret,
                                                      "code": code, "grant_type": "authorization_code",
                                                      "redirect_uri": redirect_uri})
        raise_for(r, "tiktok token exchange")
        tok = r.json()
        if "access_token" not in tok:
            raise PublishError(f"tiktok token exchange failed: {tok}", retryable=False)
        info = await c.get(f"{API}/user/info/", params={"fields": "open_id,display_name"},
                           headers={"Authorization": f"Bearer {tok['access_token']}"})
        user = _check(info.json(), "tiktok user info").get("user", {})
    return TokenSet(tok["access_token"], tok.get("refresh_token"), tok.get("expires_in"), tok.get("open_id"),
                    user.get("display_name"), tok.get("scope"))


async def refresh(client_key: str, client_secret: str, refresh_token: str, transport=None) -> TokenSet:
    async with httpx.AsyncClient(timeout=30, transport=transport) as c:
        r = await c.post(f"{API}/oauth/token/", data={"client_key": client_key, "client_secret": client_secret,
                                                      "grant_type": "refresh_token", "refresh_token": refresh_token})
        raise_for(r, "tiktok token refresh")
        tok = r.json()
        if "access_token" not in tok:
            raise AuthExpired("tiktok refresh token rejected; reconnect the account")
    return TokenSet(tok["access_token"], tok.get("refresh_token"), tok.get("expires_in"), tok.get("open_id"))


def chunk_plan(size: int) -> tuple[int, int]:
    """Return (chunk_size, total_chunk_count) per TikTok's media transfer rules."""
    if size <= MAX_CHUNK:
        return size, 1
    chunk = 10 * 1024 * 1024
    return chunk, math.floor(size / chunk)


class TikTokPublisher(PublisherAdapter):
    platform = "tiktok"

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self.creds.access_token}", "Content-Type": "application/json; charset=UTF-8"}

    async def authenticate(self) -> dict:
        async with self.client(30) as c:
            r = await c.get(f"{API}/user/info/", params={"fields": "open_id,display_name"}, headers=self._h())
            user = _check(r.json(), "tiktok auth check").get("user", {})
        return {"account_id": user.get("open_id"), "account_name": user.get("display_name")}

    async def creator_info(self, c: httpx.AsyncClient) -> dict:
        r = await c.post(f"{API}/post/publish/creator_info/query/", headers=self._h(), json={})
        return _check(r.json(), "tiktok creator info")

    async def publish_video(self, clip_path: Path, metadata: dict) -> PublishResult:
        size = clip_path.stat().st_size
        chunk, count = chunk_plan(size)
        async with self.client(600) as c:
            info = await self.creator_info(c)
            options = info.get("privacy_level_options") or []
            privacy = metadata.get("privacy", "SELF_ONLY")
            if privacy not in options:
                if "SELF_ONLY" in options:
                    privacy = "SELF_ONLY"
                else:
                    raise PublishError(f"privacy level {privacy} not allowed for this account ({options})", retryable=False)
            max_dur = info.get("max_video_post_duration_sec")
            if max_dur and metadata.get("duration") and metadata["duration"] > max_dur:
                raise PublishError(f"clip longer than TikTok allows for this account ({max_dur}s)", retryable=False)
            body = {
                "post_info": {"title": metadata.get("description", "")[:2200], "privacy_level": privacy,
                              "disable_comment": bool(info.get("comment_disabled")),
                              "disable_duet": bool(info.get("duet_disabled")),
                              "disable_stitch": bool(info.get("stitch_disabled")),
                              "video_cover_timestamp_ms": int(metadata.get("cover_ms", 1000))},
                "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk,
                                "total_chunk_count": count},
            }
            r = await c.post(f"{API}/post/publish/video/init/", headers=self._h(), json=body)
            data = _check(r.json(), "tiktok publish init")
            publish_id, upload_url = data["publish_id"], data["upload_url"]
            with clip_path.open("rb") as f:
                for i in range(count):
                    start = i * chunk
                    end = size if i == count - 1 else start + chunk
                    f.seek(start)
                    payload = f.read(end - start)
                    put = await c.put(upload_url, content=payload, headers={
                        "Content-Type": "video/mp4", "Content-Length": str(len(payload)),
                        "Content-Range": f"bytes {start}-{end - 1}/{size}"})
                    raise_for(put, f"tiktok chunk {i + 1}/{count}")
        return PublishResult("processing", job_ref=publish_id, extra={"privacy": privacy})

    async def get_publish_status(self, job_ref: str) -> PublishResult:
        async with self.client(30) as c:
            r = await c.post(f"{API}/post/publish/status/fetch/", headers=self._h(), json={"publish_id": job_ref})
            data = _check(r.json(), "tiktok status")
        status = data.get("status")
        if status == "PUBLISH_COMPLETE":
            ids = data.get("publicaly_available_post_id") or data.get("publicly_available_post_id") or []
            post_id = str(ids[0]) if ids else None
            url = f"https://www.tiktok.com/video/{post_id}" if post_id else None
            return PublishResult("published", job_ref=job_ref, post_id=post_id or job_ref, post_url=url,
                                 extra={"note": None if post_id else "published privately (SELF_ONLY) - no public URL"})
        if status == "FAILED":
            return PublishResult("failed", job_ref=job_ref, error=f"TikTok: {data.get('fail_reason', 'unknown')}")
        return PublishResult("processing", job_ref=job_ref, extra={"tiktok_status": status})
