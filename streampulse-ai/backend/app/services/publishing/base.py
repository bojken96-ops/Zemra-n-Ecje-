"""Publisher adapter interface and shared types."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx


class PublishError(RuntimeError):
    def __init__(self, message: str, retryable: bool = True, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class AuthExpired(PublishError):
    def __init__(self, message: str = "access token expired or revoked; reconnect the account"):
        super().__init__(message, retryable=False)


@dataclass
class Credentials:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    account_id: str | None


@dataclass
class PublishResult:
    """status: processing (platform accepted, not yet confirmed) | published (platform confirmed) | failed"""

    status: str
    job_ref: str | None = None
    post_id: str | None = None
    post_url: str | None = None
    error: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str | None
    expires_in: int | None
    account_id: str | None = None
    account_name: str | None = None
    scopes: str | None = None


class PublisherAdapter:
    platform: str = ""

    def __init__(self, creds: Credentials, transport: httpx.AsyncBaseTransport | None = None):
        self.creds = creds
        self.transport = transport

    def client(self, timeout: float = 120) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self.transport)

    async def authenticate(self) -> dict:
        """Verify the stored token works; return account info."""
        raise NotImplementedError

    async def publish_video(self, clip_path: Path, metadata: dict) -> PublishResult:
        raise NotImplementedError

    async def get_publish_status(self, job_ref: str) -> PublishResult:
        raise NotImplementedError


def raise_for(resp: httpx.Response, context: str) -> None:
    if resp.status_code in (401,):
        raise AuthExpired(f"{context}: unauthorized ({resp.text[:200]})")
    if resp.status_code == 429:
        retry = int(resp.headers.get("retry-after", "600") or 600)
        raise PublishError(f"{context}: rate limited", retryable=True, retry_after_seconds=retry)
    if resp.status_code >= 500:
        raise PublishError(f"{context}: server error {resp.status_code}", retryable=True)
    if resp.status_code >= 400:
        raise PublishError(f"{context}: {resp.status_code} {resp.text[:400]}", retryable=False)
