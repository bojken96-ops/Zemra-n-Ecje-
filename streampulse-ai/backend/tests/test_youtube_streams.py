import pytest

from app.services.youtube.urls import InvalidYouTubeURL, parse_youtube_url
from tests.fakes import FakeYouTube


@pytest.mark.parametrize("url,kind,value", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video", "dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=10", "video", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?si=abc", "video", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/live/dQw4w9WgXcQ?feature=share", "video", "dQw4w9WgXcQ"),
    ("youtube.com/watch?v=dQw4w9WgXcQ", "video", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/@SomeCreator/live", "handle", "@SomeCreator"),
    ("https://www.youtube.com/channel/UCaaaaaaaaaaaaaaaaaaaaaa/live", "channel", "UCaaaaaaaaaaaaaaaaaaaaaa"),
])
def test_parse_urls(url, kind, value):
    p = parse_youtube_url(url)
    assert p.kind == kind
    assert value in (p.video_id, p.handle, p.channel_id)


@pytest.mark.parametrize("url", ["https://vimeo.com/123", "https://www.youtube.com/shorts/dQw4w9WgXcQ",
                                 "https://www.youtube.com/watch?v=short", "javascript:alert(1)", ""])
def test_reject_urls(url):
    with pytest.raises(InvalidYouTubeURL):
        parse_youtube_url(url)


@pytest.fixture
def yt(monkeypatch):
    fake = FakeYouTube()
    import app.api.streams as api_streams
    import app.services.youtube.streams as svc

    monkeypatch.setattr(svc, "YouTubeClient", lambda *a, **k: fake.client())
    monkeypatch.setattr(api_streams, "YouTubeClient", lambda *a, **k: fake.client())
    return fake


def _creator(auth_client, authorised=True):
    body = {"name": "Creator", "authorised": authorised}
    if authorised:
        body["authorisation_notes"] = "Written permission on file"
    return auth_client.post("/api/creators", json=body).json()["id"]


def test_live_url_is_not_assumed_live(auth_client, yt):
    yt.video("AAAAAAAAAAA", upcoming=True)
    r = auth_client.post("/api/streams", json={"url": "https://www.youtube.com/live/AAAAAAAAAAA"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "upcoming"
    yt.video("BBBBBBBBBBB", livestream=False)
    r = auth_client.post("/api/streams", json={"url": "https://youtu.be/BBBBBBBBBBB"})
    assert r.json()["status"] == "offline"
    assert "not a livestream" in r.json()["last_error"]


def test_duplicate_stream_rejected(auth_client, yt):
    yt.video("AAAAAAAAAAA", live=True)
    assert auth_client.post("/api/streams", json={"url": "https://youtu.be/AAAAAAAAAAA"}).status_code == 201
    assert auth_client.post("/api/streams", json={"url": "https://www.youtube.com/watch?v=AAAAAAAAAAA"}).status_code == 422


def test_scheduled_stream_start_triggers_capture(auth_client, yt, db):
    from app.models import CaptureSession, Stream
    from app.services.youtube.streams import refresh_stream

    creator = _creator(auth_client)
    yt.video("CCCCCCCCCCC", upcoming=True)
    sid = auth_client.post("/api/streams", json={"url": "https://youtu.be/CCCCCCCCCCC", "creator_id": creator}).json()["id"]
    assert db.query(CaptureSession).count() == 0
    yt.video("CCCCCCCCCCC", live=True)  # the scheduled stream goes live
    stream = db.get(Stream, sid)
    refresh_stream(db, stream, yt.client())
    db.commit()
    assert stream.status == "live" and stream.live_chat_id == "chat123"
    sess = db.query(CaptureSession).one()
    assert sess.status == "pending"
    # stream ends -> capture stop requested
    yt.video("CCCCCCCCCCC", ended=True)
    sess.status = "recording"
    db.commit()
    refresh_stream(db, stream, yt.client())
    db.commit()
    db.refresh(sess)
    assert stream.status == "ended" and sess.status == "stopping" and sess.stop_requested


def test_capture_blocked_without_authorisation(auth_client, yt, db):
    from app.models import CaptureSession

    creator = _creator(auth_client, authorised=False)
    yt.video("DDDDDDDDDDD", live=True)
    sid = auth_client.post("/api/streams", json={"url": "https://youtu.be/DDDDDDDDDDD", "creator_id": creator}).json()["id"]
    assert db.query(CaptureSession).count() == 0
    r = auth_client.post(f"/api/streams/{sid}/start")
    assert r.status_code == 409 and "not marked as authorised" in r.json()["detail"]
    s = auth_client.get(f"/api/streams/{sid}").json()
    assert "authorised" in s["last_error"]


def test_channel_live_url_resolves_current_broadcast(auth_client, yt):
    yt.channel_live["UC" + "c" * 22] = "EEEEEEEEEEE"
    yt.video("EEEEEEEEEEE", live=True, channel="UC" + "c" * 22)
    r = auth_client.post("/api/streams", json={"url": "https://www.youtube.com/@Handle/live"})
    body = r.json()
    assert body["youtube_video_id"] == "EEEEEEEEEEE" and body["status"] == "live"


def test_pause_resume_and_delete(auth_client, yt, db):
    creator = _creator(auth_client)
    yt.video("FFFFFFFFFFF", live=True)
    sid = auth_client.post("/api/streams", json={"url": "https://youtu.be/FFFFFFFFFFF", "creator_id": creator}).json()["id"]
    s = auth_client.get(f"/api/streams/{sid}").json()
    assert s["capture"]["status"] == "pending"
    s = auth_client.post(f"/api/streams/{sid}/stop").json()
    assert s["monitoring_enabled"] is False and s["capture"]["status"] == "stopped"
    s = auth_client.post(f"/api/streams/{sid}/start").json()
    assert s["monitoring_enabled"] is True and s["capture"]["status"] == "pending"
    assert auth_client.delete(f"/api/streams/{sid}").status_code == 409  # capture active
    auth_client.post(f"/api/streams/{sid}/stop")
    assert auth_client.delete(f"/api/streams/{sid}").status_code == 204


def test_missing_api_key_is_reported(auth_client):
    r = auth_client.post("/api/streams", json={"url": "https://youtu.be/GGGGGGGGGGG"})
    assert r.status_code == 201
    assert "YOUTUBE_API_KEY" in r.json()["last_error"]
