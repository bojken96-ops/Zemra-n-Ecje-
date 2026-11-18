"""Agent configuration from environment variables / capture/.env (see .env.example, section CAPTURE AGENT)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class AudioRoute:
    sink: str | None      # Windows playback device the browser is routed to (setSinkId), e.g. "CABLE Input"
    source: str           # DirectShow capture device FFmpeg records from, e.g. "CABLE Output (VB-Audio Virtual Cable)"


@dataclass
class AgentConfig:
    api_url: str
    token: str
    storage_root: Path
    ffmpeg: str
    ffprobe: str
    browser_channel: str
    profiles_dir: Path
    audio_routes: list[AudioRoute] = field(default_factory=list)
    poll_seconds: float = 3.0
    heartbeat_seconds: float = 10.0

    @classmethod
    def load(cls) -> AgentConfig:
        here = Path(__file__).resolve().parent
        _load_dotenv(here / ".env")
        _load_dotenv(here.parent / ".env")
        token = os.environ.get("CAPTURE_AGENT_TOKEN", "")
        if not token:
            raise SystemExit("CAPTURE_AGENT_TOKEN is not set (must match the backend's value)")
        routes_raw = os.environ.get("CAPTURE_AUDIO_ROUTES", "[]")
        try:
            routes = [AudioRoute(r.get("sink"), r["source"]) for r in json.loads(routes_raw)]
        except (ValueError, KeyError, TypeError) as exc:
            raise SystemExit(f"CAPTURE_AUDIO_ROUTES is not valid JSON: {exc}") from exc
        api = os.environ.get("CAPTURE_API_URL", "http://127.0.0.1:8000").rstrip("/")
        if not api.startswith(("http://127.0.0.1", "http://localhost", "https://127.0.0.1", "https://localhost")):
            raise SystemExit("CAPTURE_API_URL must point at the local machine (127.0.0.1/localhost)")
        return cls(
            api_url=api, token=token,
            storage_root=Path(os.environ.get("CAPTURE_STORAGE_ROOT", str(here.parent / "storage"))).resolve(),
            ffmpeg=os.environ.get("CAPTURE_FFMPEG", "ffmpeg"), ffprobe=os.environ.get("CAPTURE_FFPROBE", "ffprobe"),
            browser_channel=os.environ.get("CAPTURE_BROWSER_CHANNEL", "chrome"),
            profiles_dir=Path(os.environ.get("CAPTURE_PROFILES_DIR", str(here / "profiles"))).resolve(),
            audio_routes=routes,
        )
