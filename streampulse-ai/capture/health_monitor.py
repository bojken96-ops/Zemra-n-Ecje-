"""FFmpeg progress parsing, segment list tracking, disk checks and health evaluation."""
from __future__ import annotations

import csv
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path


def parse_progress_block(lines: list[str]) -> dict:
    """Parse one ``-progress`` block (key=value lines ending with progress=continue|end)."""
    out: dict = {}
    for line in lines:
        if "=" not in line:
            continue
        k, v = line.strip().split("=", 1)
        out[k] = v
    res = {}
    for k in ("frame", "drop_frames", "dup_frames"):
        if k in out and out[k].lstrip("-").isdigit():
            res[k] = int(out[k])
    if out.get("fps"):
        try:
            res["fps"] = float(out["fps"])
        except ValueError:
            pass
    if out.get("out_time_us", "").lstrip("-").isdigit():
        res["out_time"] = int(out["out_time_us"]) / 1e6
    if out.get("speed", "").endswith("x"):
        try:
            res["speed"] = float(out["speed"][:-1])
        except ValueError:
            pass
    res["ended"] = out.get("progress") == "end"
    return res


@dataclass
class SegmentEntry:
    filename: str
    start: float
    end: float


def read_segment_list(path: Path) -> list[SegmentEntry]:
    """FFmpeg segment muxer CSV list: filename,start,end (seconds relative to the recording start)."""
    if not path.exists():
        return []
    entries = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) >= 3:
                try:
                    entries.append(SegmentEntry(row[0], float(row[1]), float(row[2])))
                except ValueError:
                    continue
    return entries


class WallclockAnchor:
    """Maps FFmpeg output time to wall-clock time: anchor = wall_now - out_time (median of samples)."""

    def __init__(self):
        self.samples: list[float] = []

    def add(self, out_time: float, wall: float | None = None) -> None:
        if out_time <= 0:
            return
        self.samples.append((wall or time.time()) - out_time)
        self.samples = self.samples[-30:]

    @property
    def anchor(self) -> float | None:
        if not self.samples:
            return None
        s = sorted(self.samples)
        return s[len(s) // 2]


@dataclass
class HealthState:
    expected_fps: float
    min_free_bytes: int
    last_frame: int = 0
    last_frame_change: float = field(default_factory=time.time)
    drops_total: int = 0
    frames_total: int = 0
    problems: list[str] = field(default_factory=list)

    def update(self, progress: dict, now: float | None = None) -> None:
        now = now or time.time()
        frame = progress.get("frame", self.last_frame)
        if frame > self.last_frame:
            self.last_frame, self.last_frame_change = frame, now
        self.frames_total = frame
        self.drops_total = progress.get("drop_frames", self.drops_total)

    def evaluate(self, path: Path, progress: dict, now: float | None = None) -> dict:
        now = now or time.time()
        problems = []
        if now - self.last_frame_change > 15:
            problems.append("encoder_stalled")
        fps = progress.get("fps")
        if fps is not None and self.frames_total > self.expected_fps * 10 and fps < self.expected_fps * 0.75:
            problems.append("low_fps")
        drop_ratio = self.drops_total / max(1, self.frames_total + self.drops_total)
        if drop_ratio > 0.05:
            problems.append("dropped_frames")
        free = shutil.disk_usage(path).free
        if free < self.min_free_bytes:
            problems.append("low_disk")
        self.problems = problems
        return {"fps": fps, "frames": self.frames_total, "dropped_frames": self.drops_total,
                "drop_ratio": round(drop_ratio, 4), "speed": progress.get("speed"),
                "disk_free_gb": round(free / 1024 ** 3, 2), "problems": problems}
