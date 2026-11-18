import random

from app.services.chat.analytics import ChatMessage, count_emoji, score_chat, window_features
from tests.fakes import FakeYouTube


def _msgs(n, authors=None, text="nice stream", t0=0.0):
    authors = authors or n
    return [ChatMessage(f"user{i % authors}", text, t0 + i * 0.1) for i in range(n)]


def _baseline(k=30, mean=4):
    rnd = random.Random(1)
    return [window_features([ChatMessage(f"u{rnd.randint(0, 40)}", "hello", 0) for _ in range(rnd.randint(mean - 2, mean + 2))], 10)
            for _ in range(k)]


def test_chat_spike_detected():
    spike = window_features(_msgs(40, authors=35, text="OMG NO WAY 😂😂"), 10)
    s = score_chat(spike, _baseline())
    assert s.chat > 0.8
    assert s.unique_users > 0.8
    assert s.emoji > 0.8
    assert s.details["velocity"] == 4.0


def test_normal_chat_no_spike():
    normal = window_features(_msgs(5, authors=5), 10)
    s = score_chat(normal, _baseline())
    assert s.chat == 0 and s.unique_users == 0 and s.emoji == 0


def test_spam_flood_by_one_user_is_filtered():
    flood = window_features([ChatMessage("spammer", "BUY FOLLOWERS", i) for i in range(50)] +
                            [ChatMessage("x", "visit https://spam.example", 1)], 10)
    assert flood.filtered_count == 2 and flood.spam_removed == 49
    s = score_chat(flood, _baseline())
    assert s.chat == 0


def test_repeated_phrase_and_laughs():
    f = window_features([ChatMessage(f"u{i}", "hahahahaha" if i % 2 else "CLIP IT", 0) for i in range(20)], 10)
    assert f.top_phrase in ("clip it", "haha") and f.top_phrase_share >= 0.5
    assert f.laugh_count == 10 and f.hype_count == 10


def test_emoji_counting():
    assert count_emoji("lol 😂😂 :face-blue-smiling: 🔥") == 4


def test_ingest_dedupes_and_handles_errors(db):
    from app.models import ChatEvent, Stream
    from app.services.chat.ingest import poll_once

    fake = FakeYouTube()
    stream = Stream(youtube_url="https://www.youtube.com/watch?v=AAAAAAAAAAA", youtube_video_id="AAAAAAAAAAA",
                    status="live", live_chat_id="chat123")
    db.add(stream)
    db.commit()
    item = {"id": "m1", "snippet": {"type": "textMessageEvent", "displayMessage": "hi 😂", "authorChannelId": "UCx",
                                    "publishedAt": "2026-11-18T10:05:00.123Z"},
            "authorDetails": {"displayName": "Viewer"}}
    fake.chat_pages = [{"items": [item], "nextPageToken": "p2", "pollingIntervalMillis": 4000},
                       {"items": [item], "nextPageToken": "p3", "pollingIntervalMillis": 4000}]
    r1 = poll_once(db, stream, None, fake.client())
    r2 = poll_once(db, stream, "p2", fake.client())
    db.commit()
    assert (r1.inserted, r2.inserted) == (1, 0)
    assert r1.poll_after_seconds == 4.0 and r1.next_page_token == "p2" and stream.chat_status == "active"
    ev = db.query(ChatEvent).one()
    assert ev.metadata_["emoji"] == 1 and ev.event_timestamp.microsecond == 123000

    fake.chat_error = (403, "quotaExceeded")
    r = poll_once(db, stream, "p3", fake.client())
    assert r.chat_status == "quota" and not r.stop and r.poll_after_seconds >= 300
    fake.chat_error = (403, "liveChatDisabled")
    r = poll_once(db, stream, "p3", fake.client())
    assert r.stop and stream.chat_status == "disabled"
    fake.chat_error = (403, "liveChatEnded")
    assert poll_once(db, stream, "p3", fake.client()).chat_status == "ended"
    stream.live_chat_id = None
    assert poll_once(db, stream, None, fake.client()).chat_status == "unavailable"


def test_chat_endpoint(auth_client, db):
    from app.models import ChatEvent, Stream

    s = Stream(youtube_url="https://www.youtube.com/watch?v=AAAAAAAAAAA", youtube_video_id="AAAAAAAAAAA")
    db.add(s)
    db.commit()
    db.add(ChatEvent(stream_id=s.id, message_id="1", author_id="a", message="yo", metadata_={"emoji": 0}))
    db.commit()
    r = auth_client.get(f"/api/streams/{s.id}/chat")
    assert r.status_code == 200 and r.json()[0]["message"] == "yo" and r.json()[0]["metadata"] == {"emoji": 0}
