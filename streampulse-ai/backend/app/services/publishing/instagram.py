"""Instagram Reels publishing via the Instagram API with Instagram Login (Graph API, resumable upload).

Requires a professional (Business/Creator) account and the instagram_business_content_publish
permission. Respects the account's content_publishing_limit.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

import httpx

from app.services.publishing.base import AuthExpired, PublisherAdapter, PublishError, PublishResult, TokenSet, raise_for

AUTH_URL = "https://www.instagram.com/oauth/authorize"
TOKEN_URL = "https://api.instagram.com/oauth/access_token"
GRAPH = "https://graph.instagram.com"
VERSION = "v21.0"
RUPLOAD = "https://rupload.facebook.com/ig-api-upload"
SCOPES = "instagram_business_basic,instagram_business_content_publish"


def authorize_url(app_id: str, redirect_uri: str, state: str) -> str:
    return AUTH_URL + "?" + urlencode({"client_id": app_id, "redirect_uri": redirect_uri, "response_type": "code",
                                       "scope": SCOPES, "state": state})


def _graph_error(resp: httpx.Response, context: str) -> None:
    if resp.status_code < 400:
        return
    try:
        err = resp.json().get("error", {})
    except ValueError:
        err = {}
    if err.get("code") == 190:
        raise AuthExpired(f"{context}: {err.get('message')}")
    if err.get("code") in (4, 17, 32, 613) or resp.status_code == 429:
        raise PublishError(f"{context}: rate limited", retryable=True, retry_after_seconds=3600)
    raise_for(resp, context)


async def exchange_code(app_id: str, app_secret: str, redirect_uri: str, code: str, transport=None) -> TokenSet:
    async with httpx.AsyncClient(timeout=30, transport=transport) as c:
        r = await c.post(TOKEN_URL, data={"client_id": app_id, "client_secret": app_secret, "code": code,
                                          "grant_type": "authorization_code", "redirect_uri": redirect_uri})
        _graph_error(r, "instagram token exchange")
        body = r.json()
        short = (body.get("data") or [body])[0]
        lr = await c.get(f"{GRAPH}/access_token", params={"grant_type": "ig_exchange_token", "client_secret": app_secret,
                                                          "access_token": short["access_token"]})
        _graph_error(lr, "instagram long-lived token")
        long = lr.json()
        me = await c.get(f"{GRAPH}/{VERSION}/me", params={"fields": "user_id,username,account_type",
                                                          "access_token": long["access_token"]})
        _graph_error(me, "instagram profile")
        prof = me.json()
    if prof.get("account_type") not in (None, "BUSINESS", "MEDIA_CREATOR", "CREATOR"):
        raise PublishError("Instagram publishing requires a professional (Business/Creator) account", retryable=False)
    return TokenSet(long["access_token"], None, long.get("expires_in"), str(prof.get("user_id") or short.get("user_id")),
                    prof.get("username"), short.get("permissions") if isinstance(short.get("permissions"), str) else None)


async def refresh(access_token: str, transport=None) -> TokenSet:
    async with httpx.AsyncClient(timeout=30, transport=transport) as c:
        r = await c.get(f"{GRAPH}/refresh_access_token", params={"grant_type": "ig_refresh_token",
                                                                 "access_token": access_token})
        _graph_error(r, "instagram token refresh")
        tok = r.json()
    return TokenSet(tok["access_token"], None, tok.get("expires_in"))


class InstagramPublisher(PublisherAdapter):
    platform = "instagram"

    def _p(self, **kw) -> dict:
        return {"access_token": self.creds.access_token, **kw}

    async def authenticate(self) -> dict:
        async with self.client(30) as c:
            r = await c.get(f"{GRAPH}/{VERSION}/me", params=self._p(fields="user_id,username"))
            _graph_error(r, "instagram auth check")
            me = r.json()
        return {"account_id": str(me.get("user_id")), "account_name": me.get("username")}

    async def _quota_ok(self, c: httpx.AsyncClient) -> None:
        r = await c.get(f"{GRAPH}/{VERSION}/{self.creds.account_id}/content_publishing_limit",
                        params=self._p(fields="config,quota_usage"))
        if r.status_code >= 400:
            return  # informational endpoint; publishing call will enforce limits
        data = (r.json().get("data") or [{}])[0]
        total = (data.get("config") or {}).get("quota_total")
        if total is not None and data.get("quota_usage", 0) >= total:
            raise PublishError("Instagram 24h publishing limit reached", retryable=True, retry_after_seconds=3600)

    async def publish_video(self, clip_path: Path, metadata: dict) -> PublishResult:
        size = clip_path.stat().st_size
        async with self.client(600) as c:
            await self._quota_ok(c)
            r = await c.post(f"{GRAPH}/{VERSION}/{self.creds.account_id}/media",
                             data=self._p(media_type="REELS", upload_type="resumable",
                                          caption=metadata.get("description", "")[:2200], share_to_feed="true"))
            _graph_error(r, "instagram create container")
            container = r.json()
            cid = container["id"]
            up = await c.post(f"{RUPLOAD}/{VERSION}/{cid}", content=clip_path.read_bytes(), headers={
                "Authorization": f"OAuth {self.creds.access_token}", "offset": "0", "file_size": str(size)})
            _graph_error(up, "instagram upload")
            if not up.json().get("success", True):
                raise PublishError(f"instagram upload rejected: {up.text[:200]}")
        return PublishResult("processing", job_ref=cid, extra={"stage": "container"})

    async def get_publish_status(self, job_ref: str) -> PublishResult:
        """Poll the container; when FINISHED, call media_publish and confirm the media id."""
        async with self.client(60) as c:
            r = await c.get(f"{GRAPH}/{VERSION}/{job_ref}", params=self._p(fields="status_code,status"))
            _graph_error(r, "instagram container status")
            st = r.json()
            code = st.get("status_code")
            if code in ("ERROR", "EXPIRED"):
                return PublishResult("failed", job_ref=job_ref, error=f"Instagram container {code}: {st.get('status')}")
            if code == "PUBLISHED":
                # already published by an earlier poll whose result was not recorded
                return PublishResult("published", job_ref=job_ref, post_id=job_ref, post_url=None,
                                     extra={"note": "container reported PUBLISHED"})
            if code != "FINISHED":
                return PublishResult("processing", job_ref=job_ref, extra={"status_code": code})
            pub = await c.post(f"{GRAPH}/{VERSION}/{self.creds.account_id}/media_publish",
                               data=self._p(creation_id=job_ref))
            _graph_error(pub, "instagram media_publish")
            media_id = pub.json().get("id")
            if not media_id:
                return PublishResult("processing", job_ref=job_ref)
            link = await c.get(f"{GRAPH}/{VERSION}/{media_id}", params=self._p(fields="permalink"))
            permalink = link.json().get("permalink") if link.status_code < 400 else None
        return PublishResult("published", job_ref=job_ref, post_id=media_id, post_url=permalink)
