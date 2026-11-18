from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import make_media

AGENT = {"Authorization": "Bearer test-agent-token-0123456789"}


@pytest.fixture
def live_stream(db):
    from app.models import Creator, Stream

    c = Creator(name="C", authorised=True, authorisation_notes="ok")
    db.add(c)
    db.flush()
    s = Stream(youtube_url="https://www.youtube.com/watch?v=AAAAAAAAAAA", youtube_video_id="AAAAAAAAAAA",
               status="live", creator_id=c.id)
    db.add(s)
    db.commit()
    return s


def test_agent_requires_token(client):
    assert client.get("/api/agent/commands").status_code == 401
    assert client.get("/api/agent/commands", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_agent_full_lifecycle(client, db, live_stream, storage_root):
    from app.models import CaptureSession, RecordingSegment
    from app.services.capture.sessions import request_start, request_stop

    sess = request_start(db, live_stream)
    db.commit()
    cmds = client.get("/api/agent/commands", headers=AGENT).json()["commands"]
    assert cmds == [{"action": "start", "session_id": str(sess.id), "stream_id": str(live_stream.id),
                     "url": "https://www.youtube.com/watch?v=AAAAAAAAAAA",
                     "recording_dir": f"recordings/{live_stream.id}/{sess.id}"}]
    assert client.get("/api/agent/commands", headers=AGENT).json()["commands"] == []  # not re-issued
    r = client.post(f"/api/agent/sessions/{sess.id}/status", headers=AGENT,
                    json={"status": "recording", "capture_method": "gfxcapture+dshow", "health": {"fps": 30}})
    assert r.status_code == 200
    # segment registration validates path & existence
    rel = f"recordings/{live_stream.id}/{sess.id}/seg_00000.mkv"
    t0 = datetime.now(timezone.utc)
    body = {"sequence": 0, "file_path": rel, "start_time": t0.isoformat(),
            "end_time": (t0 + timedelta(seconds=4)).isoformat(), "size_bytes": 1}
    assert client.post(f"/api/agent/sessions/{sess.id}/segments", headers=AGENT, json=body).status_code == 422
    make_media(storage_root / rel, 4)
    assert client.post(f"/api/agent/sessions/{sess.id}/segments", headers=AGENT,
                       json={**body, "file_path": "../../etc/passwd"}).status_code == 422
    assert client.post(f"/api/agent/sessions/{sess.id}/segments", headers=AGENT,
                       json={**body, "file_path": "clips/x.mkv"}).status_code == 422
    r = client.post(f"/api/agent/sessions/{sess.id}/segments", headers=AGENT, json=body)
    assert r.status_code == 201, r.text
    db.expire_all()
    seg = db.query(RecordingSegment).one()
    assert seg.analysed  # eager celery ran the analysis task
    assert seg.quality["audio"]["rms_db"] and seg.quality["visual"]["motion"] is not None
    # stop flow
    request_stop(db, live_stream)
    db.commit()
    cmds = client.get("/api/agent/commands", headers=AGENT).json()["commands"]
    assert cmds[0]["action"] == "stop"
    late = client.post(f"/api/agent/sessions/{sess.id}/status", headers=AGENT, json={"status": "recording"})
    assert late.json()["status"] == "stopping" and late.json()["stop_requested"]
    client.post(f"/api/agent/sessions/{sess.id}/status", headers=AGENT, json={"status": "stopped"})
    db.expire_all()
    assert db.get(CaptureSession, sess.id).status == "stopped"


def test_concurrency_limit_and_reconnecting(client, db, live_stream):
    from app.models import Stream
    from app.services.app_settings import update_settings
    from app.services.capture.sessions import request_start

    update_settings(db, {"capture": {"max_concurrent_captures": 1}})
    s2 = Stream(youtube_url="https://www.youtube.com/watch?v=BBBBBBBBBBB", youtube_video_id="BBBBBBBBBBB",
                status="live", creator_id=live_stream.creator_id)
    db.add(s2)
    db.commit()
    a, b = request_start(db, live_stream), request_start(db, s2)
    db.commit()
    first = client.get("/api/agent/commands", headers=AGENT).json()["commands"]
    assert len(first) == 1
    client.post(f"/api/agent/sessions/{first[0]['session_id']}/status", headers=AGENT, json={"status": "reconnecting"})
    db.expire_all()
    assert db.get(Stream, live_stream.id).status == "reconnecting"
    client.post(f"/api/agent/sessions/{first[0]['session_id']}/status", headers=AGENT,
                json={"status": "failed", "error": "browser crashed"})
    second = client.get("/api/agent/commands", headers=AGENT).json()["commands"]
    assert len(second) == 1 and second[0]["session_id"] == str(b.id)
    assert {str(a.id), str(b.id)} == {first[0]["session_id"], second[0]["session_id"]}


def test_stale_sessions_expire(db, live_stream):
    from app.services.capture.sessions import expire_stale_sessions, request_start

    sess = request_start(db, live_stream)
    sess.status = "recording"
    sess.last_heartbeat_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.commit()
    assert expire_stale_sessions(db) == 1
    assert sess.status == "failed" and "heartbeat" in sess.error_message
