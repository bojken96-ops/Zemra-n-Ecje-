"""Extract an accurately-cut, A/V-synchronised excerpt from wall-clock aligned recording segments."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from processing import ffmpeg


@dataclass
class SegmentRef:
    path: Path
    start_time: datetime
    end_time: datetime


class FootageUnavailable(RuntimeError):
    pass


def covering_segments(segments: list[SegmentRef], start: datetime, end: datetime) -> list[SegmentRef]:
    segs = sorted((s for s in segments if s.end_time > start and s.start_time < end), key=lambda s: s.start_time)
    if not segs:
        raise FootageUnavailable("no recording segments cover the requested time range")
    return segs


def extract_excerpt(segments: list[SegmentRef], start: datetime, end: datetime, out_path: Path,
                    encoder: list[str] | None = None) -> tuple[datetime, float]:
    """Concatenate the covering segments and cut [start, end] frame-accurately (re-encode, high quality).

    Returns (actual_start_wallclock, duration). If footage only partially covers the range
    (capture started late / stream ended) the excerpt is clamped to what exists.
    """
    segs = covering_segments(segments, start, end)
    actual_start = max(start, segs[0].start_time)
    actual_end = min(end, segs[-1].end_time)
    if (actual_end - actual_start).total_seconds() < 1:
        raise FootageUnavailable("less than one second of footage available for this range")
    for s in segs:
        if not s.path.exists():
            raise FootageUnavailable(f"segment file missing: {s.path.name}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    offset = (actual_start - segs[0].start_time).total_seconds()
    duration = (actual_end - actual_start).total_seconds()
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, dir=out_path.parent) as f:
        for s in segs:
            f.write(f"file '{s.path.resolve().as_posix()}'\n")
        list_path = Path(f.name)
    try:
        enc = encoder or ["-c:v", "libx264", "-preset", "veryfast", "-crf", "17"]
        ffmpeg.run(["-f", "concat", "-safe", "0", "-i", str(list_path), "-ss", f"{offset:.3f}", "-t", f"{duration:.3f}",
                    "-map", "0:v:0?", "-map", "0:a:0?", *enc, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                    "-af", "aresample=async=1:first_pts=0", "-movflags", "+faststart", str(out_path)])
    finally:
        list_path.unlink(missing_ok=True)
    return actual_start, ffmpeg.probe(out_path).duration


def trim(src: Path, start: float, end: float, out_path: Path) -> Path:
    ffmpeg.run(["-ss", f"{start:.3f}", "-i", str(src), "-t", f"{end - start:.3f}", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)])
    return out_path


def extract_wav(src: Path, out_path: Path) -> Path:
    ffmpeg.run(["-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out_path)])
    return out_path


def keyframes(src: Path, count: int = 4, width: int = 640) -> list[bytes]:
    dur = ffmpeg.probe(src).duration
    frames = []
    for i in range(count):
        t = dur * (i + 0.5) / count
        frames.append(ffmpeg.run_bytes(["-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", "-vf", f"scale={width}:-2",
                                        "-f", "image2", "-c:v", "mjpeg", "-q:v", "5", "-"]))
    return [f for f in frames if f]
