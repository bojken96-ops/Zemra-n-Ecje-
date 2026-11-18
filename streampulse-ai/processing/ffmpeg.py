"""Thin, safe wrappers around ffmpeg/ffprobe (argument lists only; never shell=True)."""
from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)
FFMPEG = os.environ.get("FFMPEG_BINARY", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BINARY", "ffprobe")


class FFmpegError(RuntimeError):
    pass


def run(args: list[str], timeout: float = 3600) -> subprocess.CompletedProcess:
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", *args]
    log.debug("ffmpeg", extra={"cmd": cmd})
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace")[-2000:]
        raise FFmpegError(f"ffmpeg failed ({proc.returncode}): {tail}")
    return proc


def run_bytes(args: list[str], timeout: float = 600) -> bytes:
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.decode(errors="replace")[-2000:])
    return proc.stdout


@dataclass
class ProbeResult:
    duration: float
    width: int | None
    height: int | None
    fps: float | None
    has_audio: bool
    has_video: bool


def probe(path: str | Path) -> ProbeResult:
    proc = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                          capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed: {proc.stderr.decode(errors='replace')[-500:]}")
    data = json.loads(proc.stdout)
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    fps = None
    if v and v.get("avg_frame_rate") and v["avg_frame_rate"] != "0/0":
        num, den = v["avg_frame_rate"].split("/")
        fps = float(num) / float(den) if float(den) else None
    duration = float(data.get("format", {}).get("duration") or (v or a or {}).get("duration") or 0)
    return ProbeResult(duration, v.get("width") if v else None, v.get("height") if v else None, fps, a is not None,
                       v is not None)


@lru_cache
def available_encoders() -> set[str]:
    proc = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, timeout=30)
    names = set()
    for line in proc.stdout.decode(errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS":
            names.add(parts[1])
    return names


@lru_cache
def video_encoder(preference: str = "auto") -> list[str]:
    """Pick an H.264 encoder: NVENC when present *and working*, else libx264 (CPU fallback)."""
    pref = os.environ.get("FFMPEG_HWACCEL", preference)
    if pref in ("auto", "nvenc") and "h264_nvenc" in available_encoders():
        try:
            run(["-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2", "-c:v", "h264_nvenc", "-f", "null", "-"], timeout=30)
            return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "0"]
        except (FFmpegError, subprocess.TimeoutExpired):
            log.info("h264_nvenc listed but unusable; falling back to libx264")
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
