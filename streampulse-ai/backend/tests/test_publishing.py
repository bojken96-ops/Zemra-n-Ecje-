"""Publishing adapters (HTTP-level fakes of the official APIs) and queue semantics."""
import asyncio
import json
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from app.services.publishing.base import Credentials, PublishError
from app.services.publishing.instagram import InstagramPublisher
from app.services.publishing.tiktok import TikTokPublisher, chunk_plan
from app.services.publishing.youtube import YouTubePublisher

CREDS = Credentials("tok", "ref", None, "acct1")


@pytest.fixture
def video(tmp_path) -> Path:
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"\x00" * 2048)
    return p


def test_youtube_resumable_upload_and_confirmation(video):
    seen = []

    def handler(req: httpx.Request):
        seen.append((req.method, req.url.path))
        if req.url.path == "/upload/youtube/v3/videos":
            body = json.loads(req.content)
            assert body["status"]["privacyStatus"] == "private"
            assert "#Shorts" in body["snippet"]["description"]
            assert req.headers["x-upload-content-length"] == "2048"
            return httpx.Response(200, headers={"Location": "https://upload.example/session1"})
        if req.url.host == "upload.example":
            assert len(req.content) == 2048
            return httpx.Response(200, json={"id": "vid123", "status": {"uploadStatus": "uploaded"}})
        if req.url.path == "/youtube/v3/videos":
            return httpx.Response(200, json={"items": [{"status": {"uploadStatus": state["s"], "privacyStatus": "private"}}]})
        return httpx.Response(404)

    state = {"s": "uploaded"}
    pub = YouTubePublisher(CREDS, transport=httpx.MockTransport(handler))
    res = asyncio.run(pub.publish_video(video, {"title": "Big moment", "description": "desc", "privacy": "private"}))
    assert res.status == "processing" and res.job_ref == "vid123"  # not "published" yet
    assert asyncio.run(pub.get_publish_status("vid123")).status == "processing"
    state["s"] = "processed"
    done = asyncio.run(pub.get_publish_status("vid123"))
    assert done.status == "published" and done.post_url == "https://www.youtube.com/shorts/vid123"
    state["s"] = "rejected"
    assert asyncio.run(pub.get_publish_status("vid123")).status == "failed"


def test_tiktok_direct_post_respects_privacy_options(video):
    def handler(req: httpx.Request):
        p = req.url.path
        if p.endswith("/creator_info/query/"):
            return httpx.Response(200, json={"data": {"privacy_level_options": ["SELF_ONLY"],
                                                      "max_video_post_duration_sec": 600},
                                             "error": {"code": "ok"}})
        if p.endswith("/video/init/"):
            body = json.loads(req.content)
            assert body["post_info"]["privacy_level"] == "SELF_ONLY"  # downgraded: unaudited app
            assert body["source_info"] == {"source": "FILE_UPLOAD", "video_size": 2048, "chunk_size": 2048,
                                           "total_chunk_count": 1}
            return httpx.Response(200, json={"data": {"publish_id": "pub1", "upload_url": "https://up.tiktok/u"},
                                             "error": {"code": "ok"}})
        if req.url.host == "up.tiktok":
            assert req.headers["content-range"] == "bytes 0-2047/2048"
            return httpx.Response(201)
        if p.endswith("/status/fetch/"):
            return httpx.Response(200, json={"data": {"status": state["s"], "fail_reason": "spam"}, "error": {"code": "ok"}})
        return httpx.Response(404)

    state = {"s": "PROCESSING_UPLOAD"}
    pub = TikTokPublisher(CREDS, transport=httpx.MockTransport(handler))
    res = asyncio.run(pub.publish_video(video, {"description": "hi", "privacy": "PUBLIC_TO_EVERYONE", "duration": 30}))
    assert res.status == "processing" and res.job_ref == "pub1"
    assert asyncio.run(pub.get_publish_status("pub1")).status == "processing"
    state["s"] = "PUBLISH_COMPLETE"
    assert asyncio.run(pub.get_publish_status("pub1")).status == "published"
    state["s"] = "FAILED"
    assert asyncio.run(pub.get_publish_status("pub1")).error == "TikTok: spam"


def test_tiktok_chunking():
    assert chunk_plan(3 * 1024 * 1024) == (3 * 1024 * 1024, 1)
    size = 150 * 1024 * 1024
    chunk, count = chunk_plan(size)
    assert chunk == 10 * 1024 * 1024 and count == 15 and size - chunk * (count - 1) <= 128 * 1024 * 1024


def test_instagram_reels_container_flow(video):
    calls = []

    def handler(req: httpx.Request):
        calls.append(req.url.path)
        p = req.url.path
        if p.endswith("/content_publishing_limit"):
            return httpx.Response(200, json={"data": [{"quota_usage": 3, "config": {"quota_total": 50}}]})
        if p.endswith("/acct1/media"):
            assert b"media_type=REELS" in req.content and b"upload_type=resumable" in req.content
            return httpx.Response(200, json={"id": "cont1", "uri": "https://rupload.facebook.com/x"})
        if req.url.host == "rupload.facebook.com":
            assert req.headers["authorization"] == "OAuth tok" and req.headers["file_size"] == "2048"
            return httpx.Response(200, json={"success": True})
        if p.endswith("/cont1"):
            return httpx.Response(200, json={"status_code": state["s"]})
        if p.endswith("/media_publish"):
            return httpx.Response(200, json={"id": "media9"})
        if p.endswith("/media9"):
            return httpx.Response(200, json={"permalink": "https://www.instagram.com/reel/abc/"})
        return httpx.Response(404)

    state = {"s": "IN_PROGRESS"}
    pub = InstagramPublisher(CREDS, transport=httpx.MockTransport(handler))
    assert asyncio.run(pub.publish_video(video, {"description": "cap"})).job_ref == "cont1"
    assert asyncio.run(pub.get_publish_status("cont1")).status == "processing"
    assert not any(c.endswith("/media_publish") for c in calls)
    state["s"] = "FINISHED"
    res = asyncio.run(pub.get_publish_status("cont1"))
    assert res.status == "published" and res.post_id == "media9" and res.post_url.endswith("/reel/abc/")


def test_instagram_quota_exhausted_is_retryable(video):
    def handler(req):
        return httpx.Response(200, json={"data": [{"quota_usage": 50, "config": {"quota_total": 50}}]})

    pub = InstagramPublisher(CREDS, transport=httpx.MockTransport(handler))
    with pytest.raises(PublishError) as e:
        asyncio.run(pub.publish_video(video, {}))
    assert e.value.retryable


# ------------------------------------------------------------------ queue

@pytest.fixture
def ready_clip(db, storage_root):
    from app.models import Clip, SocialAccount, Stream
    from app.utils import crypto

    s = Stream(youtube_url="https://www.youtube.com/watch?v=AAAAAAAAAAA")
    db.add(s)
    db.flush()
    (storage_root / "clips" / "c1").mkdir(parents=True)
    (storage_root / "clips" / "c1" / "clip.mp4").write_bytes(b"\x00" * 100)
    clip = Clip(stream_id=s.id, status="ready", file_path="clips/c1/clip.mp4", title="T", duration=30,
                content={"youtube_title": "YT title", "tiktok_description": "tt", "instagram_caption": "ig",
                         "hashtags": ["#a", "#b"]})
    db.add(clip)
    for p in ("youtube", "tiktok", "instagram"):
        db.add(SocialAccount(platform=p, account_id=f"{p}1", account_name=p, connected=True,
                             encrypted_access_token=crypto.encrypt("tok")))
    db.commit()
    return clip


class FakeAdapter:
    def __init__(self, outcomes):
        self.outcomes = outcomes

    async def publish_video(self, path, meta):
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o

    async def get_publish_status(self, ref):
        return self.outcomes.pop(0)


def test_approve_creates_one_job_per_platform_without_duplicates(auth_client, ready_clip, db):
    from app.models import PublishingJob

    r = auth_client.post(f"/api/clips/{ready_clip.id}/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert db.query(PublishingJob).count() == 3
    again = auth_client.post("/api/publishing/jobs", json={"clip_id": str(ready_clip.id)})
    assert again.status_code == 201 and again.json() == []  # duplicate publishing prevented
    assert db.query(PublishingJob).count() == 3
    jobs = {j["platform"]: j for j in auth_client.get("/api/publishing/jobs").json()}
    assert jobs["youtube"]["metadata"]["title"] == "YT title"
    assert jobs["instagram"]["metadata"]["description"].startswith("ig")


def test_queue_retry_backoff_and_confirmation(db, ready_clip, monkeypatch):
    from app.models import Clip, PublishedPost, PublishingJob
    from app.services.publishing import accounts, queue
    from app.services.publishing.base import PublishResult

    ready_clip.status = "approved"
    db.commit()
    queue.create_jobs_for_clip(db, ready_clip, account_ids=None)
    job = db.query(PublishingJob).filter(PublishingJob.platform == "tiktok").one()
    job.scheduled_at = job.scheduled_at - timedelta(minutes=1)
    db.commit()
    outcomes = [PublishError("network blip", retryable=True), PublishResult("processing", job_ref="pub1"),
                PublishResult("processing", job_ref="pub1"),
                PublishResult("published", job_ref="pub1", post_id="p1", post_url="https://tiktok/p1")]
    monkeypatch.setattr(accounts, "adapter_for", lambda db, acct: FakeAdapter(outcomes))

    assert queue.run_job(db, job.id) == "scheduled"  # retry scheduled with backoff
    assert job.attempts == 1 and "network blip" in job.error_message
    assert queue.run_job(db, job.id) == "skipped"  # not due yet
    job.scheduled_at = job.scheduled_at - timedelta(hours=1)
    db.commit()
    assert queue.run_job(db, job.id) == "processing"
    assert db.query(PublishedPost).count() == 0  # never reported as published before confirmation
    assert db.get(Clip, ready_clip.id).status == "publishing"
    assert queue.poll_job(db, job.id) == "processing"
    assert queue.poll_job(db, job.id) == "published"
    post = db.query(PublishedPost).one()
    assert post.post_url == "https://tiktok/p1"


def test_non_retryable_failure_and_manual_retry(auth_client, db, ready_clip, monkeypatch):
    from app.models import PublishingJob
    from app.services.publishing import accounts, queue

    ready_clip.status = "approved"
    db.commit()
    queue.create_jobs_for_clip(db, ready_clip)
    job = db.query(PublishingJob).filter(PublishingJob.platform == "youtube").one()
    job.scheduled_at = job.scheduled_at - timedelta(minutes=1)
    db.commit()
    monkeypatch.setattr(accounts, "adapter_for", lambda db, acct: FakeAdapter([PublishError("bad request", retryable=False)]))
    assert queue.run_job(db, job.id) == "failed"
    r = auth_client.post(f"/api/publishing/jobs/{job.id}/retry")
    assert r.status_code == 200 and r.json()["status"] == "scheduled"
    assert auth_client.post(f"/api/publishing/jobs/{job.id}/retry").status_code == 409


def test_oauth_connect_requires_configuration(auth_client):
    r = auth_client.post("/api/accounts/tiktok/connect")
    assert r.status_code == 422 and "TIKTOK_CLIENT_KEY" in r.json()["detail"]


def test_oauth_state_validation(auth_client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "google_client_id", "cid")
    monkeypatch.setattr(get_settings(), "google_client_secret", "sec")
    url = auth_client.post("/api/accounts/youtube/connect").json()["authorization_url"]
    assert "code_challenge_method=S256" in url and "youtube.upload" in url and "access_type=offline" in url
    r = auth_client.get("/api/accounts/youtube/callback?state=forged&code=x", follow_redirects=False)
    assert r.status_code == 307 and "invalid+or+expired" in r.headers["location"].replace("%20", "+")
