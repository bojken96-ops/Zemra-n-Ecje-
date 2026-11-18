"""Windows capture agent: pure logic + a runtime test of the real recorder/segment pipeline.

On Linux there is no window or DirectShow device, so the runtime test substitutes FFmpeg lavfi test
sources for the two device inputs; everything else (command builder, segment muxer, progress parsing,
wall-clock anchoring, registration, restart handling, stop flow) is the production code path.
"""
import asyncio
import os
from pathlib import Path

import httpx
import pytest

os.environ["STREAMPULSE_CAPTURE_TEST"] = "1"

from capture.audio_capture import AudioRouter, parse_dshow_devices  # noqa: E402
from capture.browser_manager import PlayerState, assess, copy_profile  # noqa: E402
from capture.capture_adapter import CaptureTarget, CaptureUnavailable  # noqa: E402
from capture.capture_manager import BackendClient, CaptureManager  # noqa: E402
from capture.config import AudioRoute  # noqa: E402
from capture.health_monitor import HealthState, WallclockAnchor, parse_progress_block, read_segment_list  # noqa: E402
from capture.windows_capture import FFmpegRecorder, WindowsCaptureAdapter, build_ffmpeg_command  # noqa: E402

TARGET = CaptureTarget("sess1", "stream1", "StreamPulse::sess1", 1234, "CABLE Output (VB-Audio Virtual Cable)",
                       Path("/tmp/out"), segment_seconds=10, framerate=30)


def test_gfxcapture_command_targets_one_window_with_synced_audio():
    cmd = build_ffmpeg_command("ffmpeg", "gfxcapture", TARGET, "libx264", 7,
                               gfx_opts={"hwnd", "window_text", "max_framerate", "capture_cursor"})
    joined = " ".join(cmd)
    assert "gfxcapture=hwnd=1234:max_framerate=30:capture_cursor=0,hwdownload,format=bgra" in joined
    assert joined.count("-use_wallclock_as_timestamps 1") == 2  # both inputs on the same clock (A/V sync)
    assert "audio=CABLE Output (VB-Audio Virtual Cable)" in cmd
    assert "-segment_start_number" in cmd and cmd[cmd.index("-segment_start_number") + 1] == "7"
    assert "expr:gte(t,n_forced*10)" in cmd  # keyframes on segment boundaries
    assert "desktop" not in joined  # never the whole desktop


def test_gdigrab_command_and_missing_gfxcapture_is_reported():
    cmd = build_ffmpeg_command("ffmpeg", "gdigrab", TARGET, "h264_nvenc", 0)
    assert "title=StreamPulse::sess1" in cmd and "h264_nvenc" in cmd
    with pytest.raises(CaptureUnavailable, match="FFmpeg 8.0"):
        build_ffmpeg_command("ffmpeg", "gfxcapture", TARGET, "libx264", 0, gfx_opts=None)


def test_progress_segments_anchor_health(tmp_path):
    p = parse_progress_block(["frame=300", "fps=29.97", "drop_frames=4", "out_time_us=10000000", "speed=1.0x",
                              "progress=continue"])
    assert p == {"frame": 300, "drop_frames": 4, "fps": 29.97, "out_time": 10.0, "speed": 1.0, "ended": False}
    (tmp_path / "segments.csv").write_text("seg_00000.mkv,0.000000,10.000000\nseg_00001.mkv,10.000000,20.0\n")
    assert [e.filename for e in read_segment_list(tmp_path / "segments.csv")] == ["seg_00000.mkv", "seg_00001.mkv"]
    a = WallclockAnchor()
    for t in (1, 2, 3):
        a.add(t, wall=1000 + t + 0.5)
    assert a.anchor == 1000.5
    h = HealthState(expected_fps=30, min_free_bytes=10 ** 18)
    h.update({"frame": 600, "drop_frames": 100}, now=100)
    ev = h.evaluate(tmp_path, {"fps": 12}, now=120)
    assert set(ev["problems"]) == {"encoder_stalled", "low_fps", "dropped_frames", "low_disk"}


def test_audio_routing_allocation():
    devs = parse_dshow_devices('[dshow @ 0] "Integrated Webcam" (video)\n[dshow @ 0] "CABLE Output (VB-Audio Virtual Cable)" (audio)\n'
                               '[dshow @ 0]   Alternative name "@device_cm_{X}"\n[dshow @ 0] "Stereo Mix (Realtek)" (audio)')
    assert devs == {"audio": ["CABLE Output (VB-Audio Virtual Cable)", "Stereo Mix (Realtek)"], "video": ["Integrated Webcam"]}
    r = AudioRouter([AudioRoute("CABLE Input", "CABLE Output (VB-Audio Virtual Cable)")], "virtual_cable")
    r.validate(devs["audio"])
    assert r.acquire("a").sink == "CABLE Input"
    with pytest.raises(CaptureUnavailable, match="busy"):
        r.acquire("b")
    r.release("a")
    assert r.acquire("b")
    with pytest.raises(CaptureUnavailable, match="not found"):
        AudioRouter([AudioRoute("X", "Missing device")], "virtual_cable").validate(devs["audio"])
    mix = AudioRouter([AudioRoute(None, "Stereo Mix (Realtek)"), AudioRoute(None, "Stereo Mix (Realtek)")], "dshow_device")
    mix.acquire("a")
    with pytest.raises(CaptureUnavailable, match="one capture"):
        mix.acquire("b")


def test_player_state_assessment():
    base = {"hasVideo": True, "paused": False, "ended": False, "readyState": 4, "errorText": ""}
    assert assess(None, base, 0).reason == "playing"
    assert assess(None, base, 20).reason == "stalled"
    assert assess(None, {**base, "errorText": "This live stream has ended."}, 0).reason == "stream_ended"
    assert assess(None, {**base, "errorText": "Sign in to confirm your age"}, 0).reason == "access_denied"
    assert assess(None, {**base, "paused": True}, 0).reason == "paused"
    assert assess(None, {"hasVideo": False}, 0).reason == "no_video_element"


def test_profile_copy_skips_locks_and_caches(tmp_path):
    master = tmp_path / "master"
    (master / "Default" / "Cache").mkdir(parents=True)
    (master / "Default" / "Cookies").write_text("c")
    (master / "SingletonLock").write_text("l")
    copy_profile(master, tmp_path / "copy")
    assert (tmp_path / "copy" / "Default" / "Cookies").exists()
    assert not (tmp_path / "copy" / "SingletonLock").exists() and not (tmp_path / "copy" / "Default" / "Cache").exists()


# ------------------------------------------------------------------ runtime


class LavfiAdapter(WindowsCaptureAdapter):
    """Production adapter with lavfi sources in place of the Windows window/audio devices."""

    def __init__(self):
        super().__init__("ffmpeg", "gdigrab", "libx264")
        self.crash_once = False

    async def start_capture(self, stream_id):
        t = self.targets[stream_id]
        cmd = build_ffmpeg_command("ffmpeg", self.backend, t, "libx264", self.next_number[stream_id],
                                   video_input=["-re", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=15"],
                                   audio_input=["-re", "-f", "lavfi", "-i", "sine=f=440:sample_rate=48000"])
        rec = FFmpegRecorder(cmd)
        await rec.start()
        self.recorders[stream_id] = rec


class FakeBrowser:
    def __init__(self):
        self.recovered = 0
        self.state = "playing"

    async def open(self, sid, url):
        return type("S", (), {"hwnd": None})()

    async def route_audio(self, sess, sink):
        return {"ok": True}

    async def check(self, sess):
        return PlayerState(self.state == "playing", self.state, {"adShowing": False})

    async def recover(self, sess, sink):
        self.recovered += 1
        self.state = "playing"

    async def close(self, sid):
        pass


def test_agent_records_registers_recovers_and_stops(client, db, storage_root):
    from app.main import app
    from app.models import CaptureSession, Creator, RecordingSegment, Stream
    from app.services.app_settings import update_settings
    from app.services.capture.sessions import request_start, request_stop

    update_settings(db, {"capture": {"segment_seconds": 2, "framerate": 15, "output_width": 640, "output_height": 360,
                                     "min_free_disk_gb": 1}})
    c = Creator(name="C", authorised=True, authorisation_notes="ok")
    db.add(c)
    db.flush()
    s = Stream(youtube_url="https://www.youtube.com/watch?v=AAAAAAAAAAA", youtube_video_id="AAAAAAAAAAA",
               status="live", creator_id=c.id)
    db.add(s)
    db.commit()
    sess = request_start(db, s)
    db.commit()

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        backend = BackendClient("http://127.0.0.1", "test-agent-token-0123456789", transport=transport)
        browser = FakeBrowser()
        adapter = LavfiAdapter()
        router = AudioRouter([AudioRoute("CABLE Input", "CABLE Output")], "virtual_cable")
        mgr = CaptureManager(backend, adapter, browser, router, storage_root, {})
        await mgr.poll_once()
        assert str(sess.id) in mgr.active
        await asyncio.sleep(9)
        # simulate an internet interruption: the player stalls -> agent reloads it
        browser.state = "stalled"
        await asyncio.sleep(3)
        assert browser.recovered >= 1
        # simulate a recorder crash -> restarted, sequence numbers continue
        adapter.recorders[str(s.id)].proc.kill()
        await asyncio.sleep(10)
        with __import__("app.db", fromlist=["SessionLocal"]).SessionLocal() as d2:
            st = d2.get(Stream, s.id)
            request_stop(d2, st)
            d2.commit()
        await mgr.poll_once()
        t_stop = asyncio.get_running_loop().time()
        for _ in range(60):
            if not mgr.active:
                break
            await asyncio.sleep(0.5)

        assert asyncio.get_running_loop().time() - t_stop < 8, "graceful stop should not hit the kill timeout"
        await backend.close()
        return mgr

    mgr = asyncio.run(scenario())
    assert not mgr.active
    db.expire_all()
    final = db.get(CaptureSession, sess.id)
    assert final.status == "stopped", (final.status, final.error_message)
    segs = db.query(RecordingSegment).filter(RecordingSegment.capture_session_id == sess.id).order_by(
        RecordingSegment.sequence).all()
    assert len(segs) >= 6
    seqs = [x.sequence for x in segs]
    assert seqs == sorted(set(seqs))  # unique, increasing across the recorder restart
    for a, b in zip(segs, segs[1:]):
        assert b.start_time >= a.start_time
        assert abs((a.end_time - a.start_time).total_seconds() - 2) < 0.6
    assert all(x.analysed and x.quality.get("audio") for x in segs[:3])  # backend analysed them
    assert all((storage_root / x.file_path).exists() for x in segs)
