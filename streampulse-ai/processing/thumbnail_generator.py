from __future__ import annotations

from pathlib import Path

from processing import ffmpeg


def generate_thumbnail(video: Path, at_seconds: float, out_path: Path, width: int = 540) -> Path:
    """Pick the sharpest-looking frame near ``at_seconds`` (ffmpeg thumbnail filter over a 2 s window)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dur = ffmpeg.probe(video).duration
    start = max(0.0, min(at_seconds - 1.0, max(0.0, dur - 2.0)))
    ffmpeg.run(["-ss", f"{start:.2f}", "-i", str(video), "-t", "2", "-vf", f"thumbnail=50,scale={width}:-2",
                "-frames:v", "1", "-q:v", "3", str(out_path)])
    return out_path
