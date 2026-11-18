"""Capture orchestration: pulls commands from the backend, runs browser + recorder per session,
registers finished segments, reports health, and recovers from failures."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from capture.audio_capture import AudioRouter
from capture.capture_adapter import CaptureTarget, CaptureUnavailable
from capture.health_monitor import HealthState, WallclockAnchor, read_segment_list

log = logging.getLogger("capture.manager")
MAX_RECORDER_RESTARTS = 10
ENDED_GRACE_SECONDS = 60


class BackendClient:
    def __init__(self, api_url: str, token: str, transport: httpx.AsyncBaseTransport | None = None):
        self.http = httpx.AsyncClient(base_url=api_url, headers={"Authorization": f"Bearer {token}"}, timeout=20,
                                      transport=transport)

    async def commands(self) -> dict:
        r = await self.http.get("/api/agent/commands")
        r.raise_for_status()
        return r.json()

    async def status(self, session_id: str, status: str, method: str | None = None, health: dict | None = None,
                     error: str | None = None, recording_path: str | None = None) -> dict:
        r = await self.http.post(f"/api/agent/sessions/{session_id}/status", json={
            "status": status, "capture_method": method, "health": health, "error": error, "recording_path": recording_path})
        r.raise_for_status()
        return r.json()

    async def segment(self, session_id: str, payload: dict) -> dict:
        r = await self.http.post(f"/api/agent/sessions/{session_id}/segments", json=payload)
        r.raise_for_status()
        return r.json()

    async def close(self) -> None:
        await self.http.aclose()


@dataclass
class ActiveCapture:
    session_id: str
    stream_id: str
    url: str
    recording_dir: str            # relative to storage root
    target: CaptureTarget
    sink: str | None
    anchor: WallclockAnchor = field(default_factory=WallclockAnchor)
    run_anchor: float | None = None
    registered: set = field(default_factory=set)
    next_sequence: int = 0
    restarts: int = 0
    ended_since: float | None = None
    health: HealthState | None = None
    stop: bool = False
    task: asyncio.Task | None = None
    reconnecting: bool = False


class CaptureManager:
    def __init__(self, backend: BackendClient, adapter, browser, router: AudioRouter, storage_root: Path,
                 settings: dict):
        self.backend, self.adapter, self.browser, self.router = backend, adapter, browser, router
        self.storage_root, self.settings = storage_root, settings
        self.active: dict[str, ActiveCapture] = {}

    # ------------------------------------------------------------------ command loop
    async def poll_once(self) -> None:
        data = await self.backend.commands()
        self.settings.update(data.get("capture", {}))
        for cmd in data.get("commands", []):
            if cmd["action"] == "start" and cmd["session_id"] not in self.active:
                ac = self._prepare(cmd)
                if ac:
                    ac.task = asyncio.create_task(self._run(ac))
            elif cmd["action"] == "stop" and cmd["session_id"] in self.active:
                self.active[cmd["session_id"]].stop = True

    def _prepare(self, cmd: dict) -> ActiveCapture | None:
        s = self.settings
        out_dir = self.storage_root / cmd["recording_dir"]
        target = CaptureTarget(session_id=cmd["session_id"], stream_id=cmd["stream_id"],
                               window_title=f"StreamPulse::{cmd['session_id']}", hwnd=None, audio_source=None,
                               output_dir=out_dir, segment_seconds=int(s.get("segment_seconds", 10)),
                               framerate=int(s.get("framerate", 30)), width=int(s.get("output_width", 1920)),
                               height=int(s.get("output_height", 1080)), video_encoder=s.get("video_encoder", "auto"))
        ac = ActiveCapture(cmd["session_id"], cmd["stream_id"], cmd["url"], cmd["recording_dir"], target, None)
        self.active[ac.session_id] = ac
        return ac

    async def _report(self, ac: ActiveCapture, status: str, **kw) -> None:
        try:
            resp = await self.backend.status(ac.session_id, status, method=getattr(self.adapter, "method", None),
                                             recording_path=ac.recording_dir, **kw)
            if resp.get("stop_requested"):
                ac.stop = True
        except httpx.HTTPError as exc:
            log.warning("status report failed: %s", exc)

    # ------------------------------------------------------------------ per-session lifecycle
    async def _run(self, ac: ActiveCapture) -> None:
        sid = ac.session_id
        try:
            await self._report(ac, "starting")
            route = self.router.acquire(sid)
            ac.target.audio_source, ac.sink = route.source, route.sink
            bsess = await self.browser.open(sid, ac.url)
            ac.target.hwnd = getattr(bsess, "hwnd", None)
            if ac.sink and self.settings.get("audio_mode", "virtual_cable") == "virtual_cable":
                await self.browser.route_audio(bsess, ac.sink)
            await self._start_recorder(ac)
            await self._report(ac, "recording", health={"state": "recording"})
            await self._monitor(ac, bsess)
            await self._finish(ac, "stopped")
        except CaptureUnavailable as exc:
            log.error("capture unavailable: %s", exc)
            await self._finish(ac, "failed", error=f"Capture method unavailable: {exc}")
        except Exception as exc:  # report every failure to the dashboard
            log.exception("capture session failed")
            await self._finish(ac, "failed", error=f"{type(exc).__name__}: {exc}")

    async def _start_recorder(self, ac: ActiveCapture) -> None:
        self.adapter.register(ac.target)
        self.adapter.bump_sequence(ac.stream_id, ac.next_sequence)
        ac.anchor = WallclockAnchor()
        ac.run_anchor = None
        ac.health = HealthState(expected_fps=ac.target.framerate,
                                min_free_bytes=int(float(self.settings.get("min_free_disk_gb", 20)) * 1024 ** 3))
        await self.adapter.start_capture(ac.stream_id)

    async def _monitor(self, ac: ActiveCapture, bsess) -> None:
        last_heartbeat = 0.0
        while not ac.stop:
            await asyncio.sleep(2)
            status = await self.adapter.get_status(ac.stream_id)
            progress = status.progress or {}
            if "out_time" in progress:
                ac.anchor.add(progress["out_time"])
            ac.health.update(progress)
            await self._register_new_segments(ac)

            # recorder failure -> restart (new segments continue the sequence; timeline stays wall-clock based)
            if status.state == "failed":
                ac.restarts += 1
                if ac.restarts > MAX_RECORDER_RESTARTS:
                    raise RuntimeError(f"recorder failed repeatedly: {status.error}")
                await self._report(ac, "reconnecting", error=f"recorder restart: {status.error}")
                await self.adapter.stop_capture(ac.stream_id)
                await self._register_new_segments(ac, final=True)  # flush the old run with its own anchor
                await asyncio.sleep(min(30, 2 ** ac.restarts))
                await self._start_recorder(ac)
                continue

            health = ac.health.evaluate(self.storage_root, progress)
            if "low_disk" in health["problems"]:
                raise RuntimeError("free disk space below the configured minimum; capture stopped to protect the system")

            # player health
            if bsess is not None:
                pstate = await self.browser.check(bsess)
                health["player"] = pstate.reason
                health["ad_showing"] = bool(pstate.raw.get("adShowing"))
                if pstate.reason == "stream_ended":
                    ac.ended_since = ac.ended_since or time.time()
                    if time.time() - ac.ended_since > ENDED_GRACE_SECONDS:
                        log.info("stream ended; stopping capture %s", ac.session_id)
                        break
                elif pstate.reason == "access_denied":
                    raise RuntimeError("YouTube denied playback (sign-in/permissions). Re-run 'python -m capture.agent login'.")
                elif not pstate.ok and pstate.reason in ("stalled", "page_crashed", "player_error", "no_video_element", "paused"):
                    ac.reconnecting = True
                    await self._report(ac, "reconnecting", health=health, error=f"player {pstate.reason}; reloading")
                    try:
                        await self.browser.recover(bsess, ac.sink if self.settings.get("audio_mode") == "virtual_cable" else None)
                        ac.reconnecting = False
                        await self._report(ac, "recording", health=health)
                    except Exception as exc:
                        log.warning("recover failed: %s", exc)
                        await asyncio.sleep(10)
                    continue
                else:
                    ac.ended_since = None

            if time.time() - last_heartbeat > 10:
                last_heartbeat = time.time()
                await self._report(ac, "reconnecting" if ac.reconnecting else "recording", health=health)

    async def _register_new_segments(self, ac: ActiveCapture, final: bool = False) -> None:
        """Register segments FFmpeg has finished (listed in the CSV) with wall-clock start/end times."""
        entries = read_segment_list(ac.target.output_dir / "segments.csv")
        if not entries:
            return
        if ac.run_anchor is None:
            ac.run_anchor = ac.anchor.anchor
        if ac.run_anchor is None:
            return
        for e in entries:
            if e.filename in ac.registered:
                continue
            path = ac.target.output_dir / e.filename
            if not path.exists():
                continue
            seq = int(Path(e.filename).stem.split("_")[-1])
            start = datetime.fromtimestamp(ac.run_anchor + e.start, tz=timezone.utc)
            end = datetime.fromtimestamp(ac.run_anchor + e.end, tz=timezone.utc)
            payload = {"sequence": seq, "file_path": f"{ac.recording_dir}/{e.filename}", "start_time": start.isoformat(),
                       "end_time": end.isoformat(), "size_bytes": path.stat().st_size,
                       "width": ac.target.width, "height": ac.target.height, "fps": float(ac.target.framerate)}
            try:
                resp = await self.backend.segment(ac.session_id, payload)
            except httpx.HTTPError as exc:
                log.warning("segment registration failed (will retry): %s", exc)
                return
            ac.registered.add(e.filename)
            ac.next_sequence = max(ac.next_sequence, seq + 1)
            if resp.get("stop_requested"):
                ac.stop = True
        # a restarted FFmpeg appends to the same CSV with times relative to ITS start: re-anchor per run
        if final:
            ac.run_anchor = None

    async def _finish(self, ac: ActiveCapture, status: str, error: str | None = None) -> None:
        try:
            await self.adapter.stop_capture(ac.stream_id)
            await self._register_new_segments(ac, final=True)
        except Exception as exc:
            log.warning("finalising recorder failed: %s", exc)
        try:
            await self.browser.close(ac.session_id)
        except Exception:
            pass
        self.router.release(ac.session_id)
        await self._report(ac, status, error=error)
        self.active.pop(ac.session_id, None)

    async def shutdown(self) -> None:
        for ac in list(self.active.values()):
            ac.stop = True
        tasks = [ac.task for ac in self.active.values() if ac.task]
        if tasks:
            await asyncio.wait(tasks, timeout=30)
