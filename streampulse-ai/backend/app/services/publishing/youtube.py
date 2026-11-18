"""YouTube Shorts publishing via the YouTube Data API v3 resumable upload (videos.insert)."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode

import httpx

from app.services.publishing.base import Credentials, PublisherAdapter, PublishError, PublishResult, TokenSet, raise_for

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
API = "https://www.googleapis.com/youtube/v3"
SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"


def authorize_url(client_id: str, redirect_uri: str, state: str, code_challenge: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPES,
        "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": state,
        "code_challenge": code_challenge, "code_challenge_method": "S256",
    })


async def exchange_code(client_id: str, client_secret: str, redirect_uri: str, code: str, verifier: str,
                        transport=None) -> TokenSet:
    async with httpx.AsyncClient(timeout=30, transport=transport) as c:
        r = await c.post(TOKEN_URL, data={"client_id": client_id, "client_secret": client_secret, "code": code,
                                          "grant_type": "authorization_code", "redirect_uri": redirect_uri,
                                          "code_verifier": verifier})
        raise_for(r, "google token exchange")
        tok = r.json()
        me = await c.get(f"{API}/channels", params={"part": "snippet", "mine": "true"},
                         headers={"Authorization": f"Bearer {tok['access_token']}"})
        raise_for(me, "youtube channel lookup")
        items = me.json().get("items") or []
        if not items:
            raise PublishError("this Google account has no YouTube channel", retryable=False)
    return TokenSet(tok["access_token"], tok.get("refresh_token"), tok.get("expires_in"), items[0]["id"],
                    items[0]["snippet"]["title"], tok.get("scope"))


async def refresh(client_id: str, client_secret: str, refresh_token: str, transport=None) -> TokenSet:
    async with httpx.AsyncClient(timeout=30, transport=transport) as c:
        r = await c.post(TOKEN_URL, data={"client_id": client_id, "client_secret": client_secret,
                                          "refresh_token": refresh_token, "grant_type": "refresh_token"})
        raise_for(r, "google token refresh")
        tok = r.json()
    return TokenSet(tok["access_token"], tok.get("refresh_token") or refresh_token, tok.get("expires_in"))


class YouTubePublisher(PublisherAdapter):
    platform = "youtube"

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self.creds.access_token}"}

    async def authenticate(self) -> dict:
        async with self.client(30) as c:
            r = await c.get(f"{API}/channels", params={"part": "snippet", "mine": "true"}, headers=self._h())
            raise_for(r, "youtube auth check")
            item = (r.json().get("items") or [{}])[0]
            return {"account_id": item.get("id"), "account_name": item.get("snippet", {}).get("title")}

    async def publish_video(self, clip_path: Path, metadata: dict) -> PublishResult:
        title = metadata.get("title", "")[:100] or "Livestream highlight"
        description = metadata.get("description", "")
        if "#shorts" not in (title + description).lower():
            description = (description + "\n\n#Shorts").strip()
        body = {
            "snippet": {"title": title, "description": description[:5000], "tags": metadata.get("tags", [])[:30],
                        "categoryId": metadata.get("category_id", "20")},
            "status": {"privacyStatus": metadata.get("privacy", "private"), "selfDeclaredMadeForKids": False},
        }
        size = clip_path.stat().st_size
        async with self.client(600) as c:
            init = await c.post(UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"},
                                headers={**self._h(), "Content-Type": "application/json; charset=UTF-8",
                                         "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
                                content=json.dumps(body))
            raise_for(init, "youtube upload init")
            location = init.headers.get("location")
            if not location:
                raise PublishError("youtube upload init returned no session URL")
            put = await c.put(location, content=clip_path.read_bytes(),
                              headers={**self._h(), "Content-Type": "video/mp4", "Content-Length": str(size)})
            raise_for(put, "youtube upload")
            video = put.json()
        vid = video.get("id")
        if not vid:
            raise PublishError("youtube upload returned no video id")
        return PublishResult("processing", job_ref=vid, post_id=vid, post_url=f"https://www.youtube.com/shorts/{vid}")

    async def get_publish_status(self, job_ref: str) -> PublishResult:
        async with self.client(30) as c:
            r = await c.get(f"{API}/videos", params={"part": "status,processingDetails", "id": job_ref}, headers=self._h())
            raise_for(r, "youtube status")
        items = r.json().get("items") or []
        if not items:
            return PublishResult("failed", job_ref=job_ref, error="video not found (deleted or rejected)")
        st = items[0]["status"]
        upload = st.get("uploadStatus")
        url = f"https://www.youtube.com/shorts/{job_ref}"
        if upload == "processed":
            return PublishResult("published", job_ref=job_ref, post_id=job_ref, post_url=url,
                                 extra={"privacy": st.get("privacyStatus")})
        if upload in ("failed", "rejected", "deleted"):
            reason = st.get("failureReason") or st.get("rejectionReason") or upload
            return PublishResult("failed", job_ref=job_ref, error=f"YouTube {upload}: {reason}")
        return PublishResult("processing", job_ref=job_ref, post_id=job_ref, post_url=url)
