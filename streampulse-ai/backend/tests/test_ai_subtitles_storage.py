import json
import os
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.services.ai.providers import ClipContent, ContentContext, GeminiProvider, MomentContext, strip_unverified_quotes
from processing import subtitle_generator as subs


# ------------------------------------------------------------------ AI
def _gemini(payload: dict, capture: list):
    def handler(req: httpx.Request):
        capture.append(json.loads(req.content))
        assert req.headers["x-goog-api-key"] == "k"
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]})
    return GeminiProvider("k", "gemini-2.5-flash", transport=httpx.MockTransport(handler))


def test_gemini_moment_evaluation_structured_and_clamped():
    sent = []
    p = _gemini({"interesting": True, "viral_score": 92, "moment_type": "funny_reaction",
                 "reason": "Streamer has an unexpected reaction", "suggested_title": "You Won't Believe This Reaction",
                 "start_offset": -90, "end_offset": 80}, sent)
    ev = p.evaluate_moment(MomentContext(creator_name="A", stream_title="S", transcript="[+0.0s] wow", chat_sample=["lol"],
                                         signals={"combined": 0.8}, pre_seconds=45, post_seconds=35, language="sq",
                                         keyframes_jpeg=[b"\xff\xd8jpg"]))
    assert ev.viral_score == 92 and ev.start_offset == -45 and ev.end_offset == 35
    body = sent[0]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["contents"][0]["parts"][1]["inline_data"]["mime_type"] == "image/jpeg"
    assert "Albanian" in body["contents"][0]["parts"][0]["text"]


def test_gemini_content_language_and_hashtags():
    sent = []
    p = _gemini({"title": "Reagim i pabesueshëm", "youtube_title": "Reagim", "tiktok_description": "Shikoje",
                 "instagram_caption": "Shikoje", "hook": "Prit pak", "hashtags": ["shqip", "#live", "#live", "fun ny"]}, sent)
    c = p.generate_content(ContentContext(creator_name="A", stream_title="S", transcript="hello", moment_type="hype",
                                          reason="r", language="sq", hashtag_template="#shorts"))
    assert c.hashtags == ["#shqip", "#live", "#funny"]
    assert "Write everything in Albanian" in sent[0]["contents"][0]["parts"][0]["text"]


def test_fabricated_quotes_are_removed():
    c = ClipContent(title='He said "I quit streaming"', youtube_title='"watch this jump"', tiktok_description="x",
                    instagram_caption="x", hook="x", hashtags=[])
    out = strip_unverified_quotes(c, "okay watch this jump right now")
    assert out.title == "He said I quit streaming"
    assert out.youtube_title == '"watch this jump"'


def test_gemini_errors_surface():
    from app.services.ai.providers import AIError

    p = GeminiProvider("k", transport=httpx.MockTransport(lambda r: httpx.Response(429, text="quota")))
    with pytest.raises(AIError):
        p.generate_content(ContentContext(creator_name="A", stream_title="S", transcript="", moment_type=None,
                                          reason=None, language="en", hashtag_template=""))


# ------------------------------------------------------------------ subtitles
WORDS = [subs.Word(0.0, 0.4, "Hello"), subs.Word(0.5, 0.9, "everyone,"), subs.Word(1.0, 1.4, "this"),
         subs.Word(1.5, 2.0, "is"), subs.Word(2.1, 2.6, "incredible!"), subs.Word(4.0, 4.4, "Next"),
         subs.Word(4.5, 5.0, "sentence.")]


@pytest.mark.parametrize("style", ["clean", "highlight", "animated", "minimal"])
def test_ass_styles_render(style):
    ass = subs.render_ass(WORDS, {"style": style, "font": "Montserrat", "font_size": 70, "primary_color": "#FFFFFF",
                                  "highlight_color": "#00FF00", "outline_color": "#000000", "position": "middle",
                                  "margin_v": 100, "max_words_per_line": 4, "uppercase": style == "animated"})
    assert "Style: Default,Montserrat,"[:20] in ass and "Dialogue:" in ass
    assert ",5,60,60,100,1" in ass  # middle alignment + margin
    if style == "highlight":
        assert "{\\c&H0000FF00}incredible!" in ass
    if style == "animated":
        assert "INCREDIBLE!" in ass and "\\t(" in ass


def test_sentence_snapping_never_cuts_sentences():
    words = [subs.Word(i * 0.5, i * 0.5 + 0.4, w) for i, w in enumerate("one two three four. five six seven eight.".split())]
    s, e = subs.snap_boundaries(1.2, 2.7, words, max_shift=3, min_len=1, max_len=60, media_duration=10)
    assert s <= 0.0 + 0.01 and e >= 3.9  # extended to the full sentences
    s, e = subs.snap_boundaries(0.0, 30.0, words, max_shift=3, min_len=40, max_len=60, media_duration=100)
    assert e - s >= 40


def test_srt_and_shift():
    tr = {"segments": [{"start": 10.0, "end": 12.0, "text": "a b", "words": [
        {"start": 10.0, "end": 10.5, "word": "a"}, {"start": 11.0, "end": 12.0, "word": "b"}]}]}
    shifted = subs.shift_transcript(tr, 10.0, 10.0, 20.0)
    assert shifted["segments"][0]["words"][0]["start"] == 0.0
    assert "00:00:00,000 --> 00:00:02,000\na b" in subs.to_srt(subs.words_from_transcript(shifted))
    edited = {"segments": [{"start": 0, "end": 2, "text": "edited text here", "words": []}]}
    assert [w.text for w in subs.words_from_transcript(edited)] == ["edited", "text", "here"]


# ------------------------------------------------------------------ storage
def test_cleanup_keeps_protected_and_active_footage(db, storage_root):
    from app.models import CaptureSession, Clip, RecordingSegment, Stream
    from app.services.storage.manager import cleanup

    s = Stream(youtube_url="https://www.youtube.com/watch?v=AAAAAAAAAAA")
    db.add(s)
    db.flush()
    done = CaptureSession(stream_id=s.id, status="stopped")
    db.add(done)
    db.flush()
    old = datetime.now(timezone.utc) - timedelta(days=10)
    segs = {}
    for name, protected in (("expired", False), ("protected", True)):
        rel = f"recordings/{s.id}/{done.id}/{name}.mkv"
        (storage_root / rel).parent.mkdir(parents=True, exist_ok=True)
        (storage_root / rel).write_bytes(b"x" * 10)
        segs[name] = RecordingSegment(capture_session_id=done.id, stream_id=s.id, sequence=len(segs), file_path=rel,
                                      start_time=old, end_time=old + timedelta(seconds=10), protected=protected)
        db.add(segs[name])
    tmp_old = storage_root / "temporary" / "stale_job"
    tmp_old.mkdir()
    (tmp_old / "f").write_bytes(b"1")
    os.utime(tmp_old, (time.time() - 30 * 3600,) * 2)
    busy_clip = Clip(stream_id=s.id, status="processing")
    db.add(busy_clip)
    db.flush()
    busy_tmp = storage_root / "temporary" / f"clip_{busy_clip.id}"
    busy_tmp.mkdir()
    os.utime(busy_tmp, (time.time() - 30 * 3600,) * 2)
    db.commit()
    report = cleanup(db)
    assert report["segments_removed"] == 1 and report["temporary_removed"] == 1
    assert not (storage_root / segs["expired"].file_path).exists()
    assert (storage_root / segs["protected"].file_path).exists()
    assert busy_tmp.exists()


def test_low_disk_alert(db, monkeypatch):
    from app.models import Notification
    from app.services.storage import manager
    from app.utils import storage

    monkeypatch.setattr(storage, "disk_usage", lambda: {"disk_total": 100 * 1024 ** 3, "disk_used": 99 * 1024 ** 3,
                                                        "disk_free": 1 * 1024 ** 3, "areas": {}, "storage_used": 0})
    report = manager.cleanup(db)
    assert report["usage"]["low_disk"] is True
    assert db.query(Notification).filter(Notification.category == "storage").count() == 1


def test_cannot_delete_clip_while_publishing(auth_client, db):
    from app.models import Clip, Stream

    s = Stream(youtube_url="https://www.youtube.com/watch?v=AAAAAAAAAAA")
    db.add(s)
    db.flush()
    c = Clip(stream_id=s.id, status="publishing")
    db.add(c)
    db.commit()
    assert auth_client.delete(f"/api/clips/{c.id}").status_code == 409
    c.status = "ready"
    db.commit()
    assert auth_client.delete(f"/api/clips/{c.id}").status_code == 204


def test_media_endpoint_auth_and_traversal(auth_client, client, storage_root):
    (storage_root / "thumbnails" / "t.jpg").write_bytes(b"\xff\xd8data")
    assert auth_client.get("/api/media/thumbnails/t.jpg").status_code == 200
    assert auth_client.get("/api/media/recordings/x").status_code == 404
    assert auth_client.get("/api/media/thumbnails/..%2F..%2Fetc%2Fpasswd").status_code in (400, 404)
    r = auth_client.get("/api/media/thumbnails/t.jpg", headers={"Range": "bytes=0-1"})
    assert r.status_code == 206 and r.content == b"\xff\xd8"


def test_analytics_overview(auth_client):
    r = auth_client.get("/api/analytics?days=7")
    assert r.status_code == 200
    body = r.json()
    assert set(body["overview"]) >= {"active_streams", "clips_today", "clips_awaiting_approval", "failed_jobs"}
    assert len(body["series"]) == 7 and "disk_free" in body["storage"]
