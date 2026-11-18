"""Windows real-time window capture with FFmpeg.

Video backends (chosen by the owner in Settings → Capture; never swapped silently):

* ``gfxcapture`` - Windows Graphics Capture (WGC) via FFmpeg's ``gfxcapture`` source (FFmpeg 8.0+,
  Windows 10 2004+). Captures one specific window by HWND, including when it is covered by other
  windows, and never captures other desktop content. Preferred.
* ``gdigrab`` - GDI window capture by exact window title. Works with older FFmpeg builds but the
  window must stay visible (not minimised/covered) and Chrome may need GPU compositing disabled.

Audio comes from a DirectShow device (see audio_capture.py). Both inputs are stamped with wall-clock
timestamps so audio and video stay synchronised, and the output is split into fixed-length Matroska
segments with keyframes aligned to segment boundaries.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from capture.capture_adapter import CaptureAdapter, CaptureStatus, CaptureTarget, CaptureUnavailable
from capture.health_monitor import parse_progress_block

log = logging.getLogger("capture.windows")
ENCODER_ARGS = {
    "libx264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-tune", "zerolatency"],
    "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "21", "-b:v", "0"],
    "h264_qsv": ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "23"],
    "h264_amf": ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp", "-qp_i", "21", "-qp_p", "23"],
}


@lru_cache
def filter_options(ffmpeg: str, name: str) -> set[str] | None:
    """Return option names of an FFmpeg filter/source, or None when the build lacks it."""
    proc = subprocess.run([ffmpeg, "-hide_banner", "-h", f"filter={name}"], capture_output=True, text=True, timeout=30)
    text = proc.stdout + proc.stderr
    if proc.returncode != 0 or "Unknown filter" in text or f"Filter {name}" not in text:
        return None
    return set(re.findall(r"^\s{2,}([a-z_]+)\s+<", text, flags=re.M))


@lru_cache
def has_input_device(ffmpeg: str, fmt: str) -> bool:
    proc = subprocess.run([ffmpeg, "-hide_banner", "-devices"], capture_output=True, text=True, timeout=30)
    return any(line.split()[1:2] == [fmt] for line in proc.stdout.splitlines() if line.strip().startswith("D"))


@lru_cache
def pick_encoder(ffmpeg: str, preference: str) -> str:
    candidates = [preference] if preference != "auto" else ["h264_nvenc", "h264_qsv", "h264_amf", "libx264"]
    for enc in candidates:
        if enc == "libx264":
            return enc
        test = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                               "color=c=black:s=320x240:d=0.3", "-c:v", enc, "-f", "null", "-"],
                              capture_output=True, timeout=30)
        if test.returncode == 0:
            return enc
        if preference != "auto":
            raise CaptureUnavailable(f"video encoder {enc} is not usable on this machine")
    return "libx264"


def video_input_args(backend: str, target: CaptureTarget, gfx_opts: set[str] | None) -> list[str]:
    if backend == "gfxcapture":
        if gfx_opts is None:
            raise CaptureUnavailable("This FFmpeg build has no 'gfxcapture' (Windows Graphics Capture) source. "
                                     "Install FFmpeg 8.0+ (e.g. a gyan.dev full build) or select 'gdigrab' in "
                                     "Settings → Capture (window must then stay visible).")
        parts = []
        if target.hwnd and "hwnd" in gfx_opts:
            parts.append(f"hwnd={target.hwnd}")
        elif "window_text" in gfx_opts:
            parts.append(f"window_text={_escape_lavfi('^' + re.escape(target.window_title))}")
        else:
            raise CaptureUnavailable("gfxcapture source does not support window selection in this FFmpeg build")
        if "max_framerate" in gfx_opts:
            parts.append(f"max_framerate={target.framerate}")
        for opt in ("capture_cursor", "capture_border", "display_border"):
            if opt in gfx_opts:
                parts.append(f"{opt}=0")
        src = "gfxcapture=" + ":".join(parts) + ",hwdownload,format=bgra"
        return ["-use_wallclock_as_timestamps", "1", "-f", "lavfi", "-i", src]
    if backend == "gdigrab":
        return ["-use_wallclock_as_timestamps", "1", "-f", "gdigrab", "-framerate", str(target.framerate),
                "-draw_mouse", "0", "-i", f"title={target.window_title}"]
    raise CaptureUnavailable(f"unknown video backend {backend}")


def _escape_lavfi(value: str) -> str:
    return value.replace("\\", "\\\\\\\\").replace(":", "\\\\:").replace("'", "\\\\'").replace(",", "\\\\,")


def build_ffmpeg_command(ffmpeg: str, backend: str, target: CaptureTarget, encoder: str, start_number: int,
                         gfx_opts: set[str] | None = None, video_input: list[str] | None = None,
                         audio_input: list[str] | None = None) -> list[str]:
    """Build the recording command. ``video_input``/``audio_input`` override the device inputs (tests)."""
    vin = video_input or video_input_args(backend, target, gfx_opts)
    if audio_input is not None:
        ain = audio_input
    elif target.audio_source:
        ain = ["-use_wallclock_as_timestamps", "1", "-thread_queue_size", "4096", "-f", "dshow",
               "-audio_buffer_size", "50", "-i", f"audio={target.audio_source}"]
    else:
        raise CaptureUnavailable("no audio source assigned")
    w, h, fps, seg = target.width, target.height, target.framerate, target.segment_seconds
    graph = (f"[0:v]fps={fps},scale={w}:{h}:force_original_aspect_ratio=decrease,"
             f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v];"
             f"[1:a]aresample=async=1000:first_pts=0,aformat=sample_rates=48000:channel_layouts=stereo[a]")
    out_pattern = str(target.output_dir / "seg_%05d.mkv")
    return [ffmpeg, "-hide_banner", "-loglevel", "warning", "-progress", "pipe:1", "-stats_period", "1",
            "-thread_queue_size", "1024", *vin, *ain,
            "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
            *ENCODER_ARGS[encoder], "-g", str(fps * 2), "-force_key_frames", f"expr:gte(t,n_forced*{seg})",
            "-c:a", "aac", "-b:a", "160k",
            "-f", "segment", "-segment_time", str(seg), "-segment_format", "matroska", "-reset_timestamps", "1",
            "-segment_start_number", str(start_number), "-segment_list", str(target.output_dir / "segments.csv"),
            "-segment_list_type", "csv", "-segment_list_flags", "live", out_pattern]


class FFmpegRecorder:
    """One FFmpeg recording process with live progress parsing."""

    def __init__(self, cmd: list[str]):
        self.cmd = cmd
        self.proc: asyncio.subprocess.Process | None = None
        self.progress: dict = {}
        self.stderr_tail: list[str] = []
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        self.proc = await asyncio.create_subprocess_exec(*self.cmd, stdin=asyncio.subprocess.PIPE,
                                                         stdout=asyncio.subprocess.PIPE,
                                                         stderr=asyncio.subprocess.PIPE, **kwargs)
        self._tasks = [asyncio.create_task(self._read_progress()), asyncio.create_task(self._read_stderr())]

    async def _read_progress(self) -> None:
        block: list[str] = []
        assert self.proc and self.proc.stdout
        async for raw in self.proc.stdout:
            line = raw.decode(errors="replace").strip()
            block.append(line)
            if line.startswith("progress="):
                self.progress = {**self.progress, **parse_progress_block(block)}
                block = []

    async def _read_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        async for raw in self.proc.stderr:
            self.stderr_tail = (self.stderr_tail + [raw.decode(errors="replace").rstrip()])[-40:]

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def stop(self, timeout: float = 15) -> int | None:
        if self.proc is None:
            return None
        if self.proc.returncode is None:
            try:  # 'q' lets FFmpeg finalise the current segment cleanly
                self.proc.stdin.write(b"q")
                await self.proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError, AttributeError):
                pass
            try:
                await asyncio.wait_for(self.proc.wait(), timeout)
            except asyncio.TimeoutError:
                self.proc.kill()
                await self.proc.wait()
        for t in self._tasks:
            t.cancel()
        return self.proc.returncode


class WindowsCaptureAdapter(CaptureAdapter):
    """CaptureAdapter for Windows window capture (gfxcapture or gdigrab) + DirectShow audio."""

    def __init__(self, ffmpeg: str, backend: str, encoder_pref: str = "auto"):
        if sys.platform != "win32" and not os.environ.get("STREAMPULSE_CAPTURE_TEST"):
            raise CaptureUnavailable("Windows window capture is only available on Windows hosts")
        self.ffmpeg, self.backend, self.encoder_pref = ffmpeg, backend, encoder_pref
        self.method = f"{backend}+dshow"
        self.targets: dict[str, CaptureTarget] = {}
        self.recorders: dict[str, FFmpegRecorder] = {}
        self.next_number: dict[str, int] = {}

    def preflight(self) -> None:
        if self.backend == "gfxcapture" and filter_options(self.ffmpeg, "gfxcapture") is None:
            video_input_args("gfxcapture", CaptureTarget("x", "x", "x", None, None, Path(".")), None)
        if self.backend == "gdigrab" and not has_input_device(self.ffmpeg, "gdigrab"):
            raise CaptureUnavailable("This FFmpeg build has no gdigrab input device")
        if not has_input_device(self.ffmpeg, "dshow"):
            raise CaptureUnavailable("This FFmpeg build has no DirectShow (dshow) input for audio capture")

    def register(self, target: CaptureTarget) -> None:
        target.output_dir.mkdir(parents=True, exist_ok=True)
        self.targets[target.stream_id] = target
        self.next_number.setdefault(target.stream_id, 0)

    async def start_capture(self, stream_id: str) -> None:
        target = self.targets[stream_id]
        encoder = pick_encoder(self.ffmpeg, self.encoder_pref)
        gfx = filter_options(self.ffmpeg, "gfxcapture") if self.backend == "gfxcapture" else None
        cmd = build_ffmpeg_command(self.ffmpeg, self.backend, target, encoder, self.next_number[stream_id], gfx)
        rec = FFmpegRecorder(cmd)
        await rec.start()
        self.recorders[stream_id] = rec
        await asyncio.sleep(2)
        if not rec.running:
            raise CaptureUnavailable("FFmpeg exited immediately: " + " | ".join(rec.stderr_tail[-5:]))

    async def stop_capture(self, stream_id: str) -> None:
        rec = self.recorders.pop(stream_id, None)
        if rec:
            await rec.stop()

    def bump_sequence(self, stream_id: str, next_number: int) -> None:
        self.next_number[stream_id] = max(self.next_number.get(stream_id, 0), next_number)

    async def get_status(self, stream_id: str) -> CaptureStatus:
        rec = self.recorders.get(stream_id)
        if rec is None:
            return CaptureStatus("idle", self.method)
        if not rec.running:
            return CaptureStatus("failed", self.method, error=" | ".join(rec.stderr_tail[-5:]) or "ffmpeg exited",
                                 progress=rec.progress)
        return CaptureStatus("recording", self.method, pid=rec.proc.pid if rec.proc else None, progress=rec.progress)

    async def get_recording_path(self, stream_id: str) -> Path | None:
        t = self.targets.get(stream_id)
        return t.output_dir if t else None
