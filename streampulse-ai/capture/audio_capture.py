"""Per-stream audio isolation.

Each browser instance's <video> element is routed with HTMLMediaElement.setSinkId() to its own
virtual playback device (e.g. VB-Audio Virtual Cable "CABLE Input"); FFmpeg records the paired
capture endpoint ("CABLE Output") through DirectShow. One virtual cable per concurrent stream keeps
audio from different streams (and from the rest of the desktop) separate.

``dshow_device`` mode records a single device (e.g. "Stereo Mix") without routing; because that
mixes all desktop audio it is restricted to one capture at a time.
"""
from __future__ import annotations

import re
import subprocess
import threading

from capture.capture_adapter import CaptureUnavailable
from capture.config import AudioRoute

_DEVICE_RE = re.compile(r'"([^"]+)"\s*\((audio|video)\)')


def parse_dshow_devices(stderr: str) -> dict[str, list[str]]:
    devices: dict[str, list[str]] = {"audio": [], "video": []}
    for line in stderr.splitlines():
        if "Alternative name" in line:
            continue
        m = _DEVICE_RE.search(line)
        if m:
            devices[m.group(2)].append(m.group(1))
    return devices


def list_dshow_devices(ffmpeg: str) -> dict[str, list[str]]:
    proc = subprocess.run([ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                          capture_output=True, text=True, timeout=30)
    return parse_dshow_devices(proc.stderr)


class AudioRouter:
    def __init__(self, routes: list[AudioRoute], mode: str):
        self.routes, self.mode = routes, mode
        self._in_use: dict[str, AudioRoute] = {}
        self._lock = threading.Lock()

    def validate(self, available_sources: list[str]) -> None:
        if not self.routes:
            raise CaptureUnavailable(
                "No audio route configured. Install a virtual audio cable and set CAPTURE_AUDIO_ROUTES "
                '(e.g. [{"sink": "CABLE Input", "source": "CABLE Output (VB-Audio Virtual Cable)"}]).')
        missing = [r.source for r in self.routes if r.source not in available_sources]
        if missing:
            raise CaptureUnavailable(f"DirectShow audio device(s) not found: {missing}. Available: {available_sources}")
        if self.mode == "virtual_cable" and any(not r.sink for r in self.routes):
            raise CaptureUnavailable("virtual_cable mode requires a 'sink' (playback device name) for every route")

    def acquire(self, session_id: str) -> AudioRoute:
        with self._lock:
            if session_id in self._in_use:
                return self._in_use[session_id]
            if self.mode == "dshow_device" and self._in_use:
                raise CaptureUnavailable("dshow_device audio mode records all desktop audio; only one capture "
                                         "at a time is allowed. Configure virtual cables for concurrent streams.")
            used = {id(r) for r in self._in_use.values()}
            for r in self.routes:
                if id(r) not in used:
                    self._in_use[session_id] = r
                    return r
        raise CaptureUnavailable(f"All {len(self.routes)} audio route(s) are busy; add another virtual cable to "
                                 "capture more streams concurrently.")

    def release(self, session_id: str) -> None:
        with self._lock:
            self._in_use.pop(session_id, None)
