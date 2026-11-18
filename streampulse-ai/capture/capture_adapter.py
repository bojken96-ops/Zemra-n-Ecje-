"""Capture adapter interface. Implementations must capture only authorised, owner-played content."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


class CaptureUnavailable(RuntimeError):
    """The configured capture method cannot run on this machine. Reported to the owner; never silently swapped."""


@dataclass
class CaptureTarget:
    session_id: str
    stream_id: str
    window_title: str          # unique title the browser window carries
    hwnd: int | None           # native window handle when known
    audio_source: str | None   # DirectShow device to record
    output_dir: Path
    segment_seconds: int = 10
    framerate: int = 30
    width: int = 1920
    height: int = 1080
    video_encoder: str = "auto"


@dataclass
class CaptureStatus:
    state: str                       # idle | recording | failed | stopped
    method: str
    pid: int | None = None
    error: str | None = None
    progress: dict = field(default_factory=dict)


class CaptureAdapter(ABC):
    method: str = "abstract"

    @abstractmethod
    async def start_capture(self, stream_id: str) -> None: ...

    @abstractmethod
    async def stop_capture(self, stream_id: str) -> None: ...

    @abstractmethod
    async def get_status(self, stream_id: str) -> CaptureStatus: ...

    @abstractmethod
    async def get_recording_path(self, stream_id: str) -> Path | None: ...
