"""End-to-end: recorded segments -> analysis -> activity windows -> candidate -> evaluation -> vertical clip."""
from datetime import datetime, timedelta, timezone

import pytest

from processing import ffmpeg
from tests.conftest import make_media

SEG = 10


@pytest.fixture
def recorded(db, storage_root):
    """A live stream with a capture session; returns a helper that records & registers segments."""
    from app.models import CaptureSession, Creator, Stream

    c = Creator(name="Ardit", authorised=True, authorisation_notes="contract", preferred_language="sq")
    db.add(c)
    db.flush()
    s = Stream(youtube_url="https://www.youtube.com/watch?v=AAAAAAAAAAA", youtube_video_id="AAAAAAAAAAA",
               status="live", creator_id=c.id, title="Late night stream", chat_status="active")
    db.add(s)
    db.flush()
    sess = CaptureSession(stream_id=s.id, status="recording", capture_method="test", last_heartbeat_at=datetime.now(timezone.utc))
    db.add(sess)
    db.commit()
    t0 = datetime(2026, 11, 18, 10, 0, 0, tzinfo=timezone.utc)

    def record(seq: int, **media_kw):
        from app.services.capture.sessions import register_segment
        from app.workers.tasks import analyse_segment

        rel = f"recordings/{s.id}/{sess.id}/seg_{seq:05d}.mp4"
        make_media(storage_root / rel, SEG, **media_kw)
        start = t0 + timedelta(seconds=seq * SEG)
        seg = register_segment(db, sess, seq, rel, start, start + timedelta(seconds=SEG), 0, None, None, None)
        analyse_segment(str(seg.id))
        db.expire_all()
        return seg

    return {"stream": s, "session": sess, "t0": t0, "record": record}


def _chat(db, stream, start, n, authors=None, text="nice"):
    from app.models import ChatEvent

    for i in range(n):
        db.add(ChatEvent(stream_id=stream.id, message_id=f"{start.timestamp()}-{i}", author_id=f"u{i % (authors or n)}",
                         message=text, event_timestamp=start + timedelta(seconds=i * (SEG / max(n, 1)))))
    db.commit()


def test_audio_and_visual_spike_raises_candidate_but_chat_alone_does_not(db, recorded):
    from app.models import ActivityWindow, ClipCandidate

    s, t0, record = recorded["stream"], recorded["t0"], recorded["record"]
    for seq in range(9):  # 90 s quiet baseline with light chat
        _chat(db, s, t0 + timedelta(seconds=seq * SEG + 4), 3)
        record(seq)
    assert db.query(ClipCandidate).count() == 0
    # chat-only spike over quiet footage -> no candidate
    _chat(db, s, t0 + timedelta(seconds=9 * SEG + 4), 60, authors=50, text="LMAO 😂😂😂")
    record(9)
    w = db.query(ActivityWindow).filter(ActivityWindow.start_time == t0 + timedelta(seconds=90)).one()
    assert w.chat_score > 0.8 and w.emoji_score > 0.8
    assert db.query(ClipCandidate).count() == 0, "chat spike alone must not create a candidate"
    # real moment: loud audio + motion + chat reaction
    _chat(db, s, t0 + timedelta(seconds=10 * SEG + 4), 60, authors=50, text="NO WAY 😂")
    record(10, loud_from=2, motion_from=2)
    w = db.query(ActivityWindow).filter(ActivityWindow.start_time == t0 + timedelta(seconds=100)).one()
    assert w.audio_score > 0.5 and w.visual_score > 0.5, w.details
    cand = db.query(ClipCandidate).one()
    assert cand.status == "pending" and cand.event_time == t0 + timedelta(seconds=105)
    assert cand.start_offset == -45 and cand.end_offset == 35
    # immediately following excitement merges into the same candidate (no duplicates)
    _chat(db, s, t0 + timedelta(seconds=11 * SEG + 4), 60, authors=50, text="omg")
    record(11, loud_from=0, motion_from=0)
    assert db.query(ClipCandidate).count() == 1


def test_capture_health_flags_black_screen(db, recorded):
    from app.models import CaptureSession
    from app.services.app_settings import update_settings

    update_settings(db, {"capture": {"black_screen_alert_seconds": 15}})
    recorded["record"](0, black=True)
    recorded["record"](1, black=True)
    sess = db.get(CaptureSession, recorded["session"].id)
    assert sess.health["black_alert"] is True and sess.health["black_seconds_recent"] >= 15


def _fake_transcript(duration: float) -> dict:
    words, t = [], 0.5
    sentence = ["Okay", "watch", "this", "jump", "right", "now!"]
    while t < duration - 1:
        for i, w in enumerate(sentence):
            words.append({"start": round(t, 2), "end": round(t + 0.3, 2), "word": " " + w, "probability": 0.9})
            t += 0.4
        t += 0.8
    segs, cur = [], []
    for w in words:
        cur.append(w)
        if w["word"].endswith("!"):
            segs.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": "".join(x["word"] for x in cur).strip(),
                         "words": cur})
            cur = []
    return {"language": "en", "language_probability": 0.98, "segments": segs}


def test_candidate_to_vertical_clip_with_pre_event_footage(db, recorded, monkeypatch, storage_root):
    """Whisper model weights are not downloadable in CI, so the transcription call is substituted."""
    from app.models import ClipCandidate, RecordingSegment
    from app.services import app_settings
    from app.services.clipping import pipeline
    from app.services.transcription import whisper

    monkeypatch.setattr(whisper, "transcribe", lambda path, language=None: _fake_transcript(ffmpeg.probe(path).duration))
    app_settings.update_settings(db, {
        "clips": {"pre_event_seconds": 20, "post_event_seconds": 12, "sentence_snap_max_seconds": 2,
                  "min_length_seconds": 10},
        "detection": {"require_ai_evaluation": False, "send_keyframes_to_ai": False},
        "ai": {"provider": "none"}, "subtitles": {"style": "highlight"}})
    s, t0, record = recorded["stream"], recorded["t0"], recorded["record"]
    for seq in range(6):
        record(seq, loud_from=2 if seq == 3 else None, motion_from=2 if seq == 3 else None)
    event = t0 + timedelta(seconds=35)
    cand = ClipCandidate(stream_id=s.id, event_time=event, start_offset=-20, end_offset=12, viral_score=80,
                         signals={"combined": 0.8, "audio": 0.9, "visual": 0.7}, status="pending")
    db.add(cand)
    db.commit()
    assert pipeline.evaluate_candidate(db, cand.id) == "accepted"
    clip = pipeline.create_clip_from_candidate(db, cand.id)
    assert clip is not None and clip.status == "ready", clip.error_message
    # pre-event footage is included
    assert clip.start_time <= event - timedelta(seconds=18)
    assert clip.end_time >= event + timedelta(seconds=10)
    out = ffmpeg.probe(storage_root / clip.file_path)
    assert (out.width, out.height) == (1080, 1920)
    assert out.has_audio and round(out.fps) == 30
    assert 10 <= clip.duration <= 40
    # codec checks
    import json
    import subprocess

    streams = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json",
                                         str(storage_root / clip.file_path)], capture_output=True).stdout)["streams"]
    assert {st["codec_name"] for st in streams} == {"h264", "aac"}
    assert (storage_root / clip.thumbnail_path).stat().st_size > 1000
    srt = (storage_root / clip.subtitles_path).read_text()
    assert "watch this jump right now!" in srt
    # subtitles are synchronised to the trimmed clip (first cue starts near 0, not at absolute offsets)
    first = clip.transcript["segments"][0]
    assert 0 <= first["start"] < 3 and first["words"][0]["start"] >= 0
    ass = (storage_root / clip.file_path).parent / "subtitles.ass"
    assert "\\c&H" in ass.read_text()  # highlighted keywords
    assert clip.title and clip.content["hashtags"]
    assert db.query(RecordingSegment).filter(RecordingSegment.protected.is_(True)).count() >= 2
    # duplicate candidate for the same moment is merged, not clipped twice
    dup = ClipCandidate(stream_id=s.id, event_time=event + timedelta(seconds=2), start_offset=-20, end_offset=12,
                        signals={"combined": 0.8}, status="accepted")
    db.add(dup)
    db.commit()
    assert pipeline.create_clip_from_candidate(db, dup.id) is None and dup.status == "merged"
    # regenerate with another subtitle style
    before = (storage_root / clip.file_path).stat().st_mtime_ns
    pipeline.regenerate(db, clip, subtitle_style="animated")
    assert clip.status == "ready" and clip.subtitle_style == "animated"
    assert (storage_root / clip.file_path).stat().st_mtime_ns != before
    assert "\\fscx112" in ass.read_text()


def test_ai_required_but_not_configured_fails_candidate(db, recorded):
    from app.models import ClipCandidate, Notification
    from app.services.clipping import pipeline

    s, t0, record = recorded["stream"], recorded["t0"], recorded["record"]
    for seq in range(3):
        record(seq)
    cand = ClipCandidate(stream_id=s.id, event_time=t0 + timedelta(seconds=15), start_offset=-10, end_offset=10,
                         signals={"combined": 0.8}, status="pending")
    db.add(cand)
    db.commit()
    from app.services import app_settings

    app_settings.update_settings(db, {"clips": {"pre_event_seconds": 10, "post_event_seconds": 10},
                                      "detection": {"send_keyframes_to_ai": False}})
    assert pipeline.evaluate_candidate(db, cand.id) == "failed"
    assert "AI evaluation required" in cand.ai_analysis["error"]
    assert db.query(Notification).filter(Notification.category == "ai").count() == 1


def test_waits_for_post_event_footage(db, recorded):
    from app.models import ClipCandidate
    from app.services.clipping import pipeline

    s, t0, record = recorded["stream"], recorded["t0"], recorded["record"]
    record(0)
    cand = ClipCandidate(stream_id=s.id, event_time=t0 + timedelta(seconds=8), signals={}, status="pending",
                         start_offset=-45, end_offset=35)
    db.add(cand)
    db.commit()
    with pytest.raises(pipeline.NotReady):
        pipeline.evaluate_candidate(db, cand.id)
