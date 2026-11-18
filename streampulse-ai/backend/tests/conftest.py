"""Test fixtures. Uses a real PostgreSQL test database, Redis and FFmpeg."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

_STORAGE = Path(tempfile.mkdtemp(prefix="sp_storage_"))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://streampulse:streampulse@localhost:5432/streampulse_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ["STORAGE_ROOT"] = str(_STORAGE)
os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["CAPTURE_AGENT_TOKEN"] = "test-agent-token-0123456789"
os.environ["YOUTUBE_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _schema():
    from app.db import engine

    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    subprocess.run([str(BACKEND.parent / ".venv/bin/alembic"), "upgrade", "head"], cwd=BACKEND, check=True,
                   env={**os.environ, "PYTHONPATH": f"{BACKEND}:{BACKEND.parent}"}, capture_output=True)
    from app.workers.celery_app import celery

    celery.conf.task_always_eager = True
    celery.conf.task_eager_propagates = True
    yield
    shutil.rmtree(_STORAGE, ignore_errors=True)


TABLES = ("notifications, audit_logs, application_settings, published_posts, publishing_jobs, oauth_states, "
          "social_accounts, clips, clip_candidates, activity_windows, chat_events, recording_segments, "
          "capture_sessions, streams, creators, user_sessions, users")


@pytest.fixture(autouse=True)
def _clean():
    from app.db import engine
    from app.services.events import redis_client

    with engine.begin() as c:
        c.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    redis_client().flushdb()
    for area in ("recordings", "temporary", "clips", "thumbnails", "subtitles"):
        shutil.rmtree(_STORAGE / area, ignore_errors=True)
        (_STORAGE / area).mkdir(parents=True)
    yield


@pytest.fixture
def db():
    from app.db import SessionLocal

    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def storage_root() -> Path:
    return _STORAGE


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, base_url="http://localhost") as c:
        yield c


STRONG_PASSWORD = "Correct-Horse-42!"


@pytest.fixture
def auth_client(client):
    r = client.post("/api/auth/setup", json={"username": "owner", "password": STRONG_PASSWORD})
    assert r.status_code == 200, r.text
    client.headers["x-csrf-token"] = r.json()["csrf_token"]
    return client


def make_media(path: Path, seconds: float, *, loud_from: float | None = None, motion_from: float | None = None,
               fps: int = 30, size: str = "640x360", black: bool = False) -> Path:
    """Generate a synthetic test recording with FFmpeg lavfi sources.

    Quiet tone + static image, optionally switching to a loud noisy signal (audio excitement) and a
    moving test pattern (visual activity) at the given offsets.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if black:
        vsrc = f"color=c=black:s={size}:r={fps}:d={seconds}"
    elif motion_from is not None:
        vsrc = (f"color=c=gray:s={size}:r={fps}:d={seconds}[bg];testsrc2=s={size}:r={fps}:d={seconds}[mv];"
                f"[bg][mv]overlay=enable='gte(t,{motion_from})'")
    else:
        vsrc = f"color=c=gray:s={size}:r={fps}:d={seconds}"
    if loud_from is not None:
        asrc = (f"sine=f=220:d={seconds}:sample_rate=48000,volume=0.02[q];"
                f"anoisesrc=d={seconds}:c=pink:a=0.8:sample_rate=48000,volume='if(gte(t,{loud_from}),1,0)':eval=frame[n];"
                f"[q][n]amix=inputs=2:normalize=0")
    else:
        asrc = f"sine=f=220:d={seconds}:sample_rate=48000,volume=0.02"
    graph = f"{vsrc}[v];{asrc}[a]"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "nullsrc",
                    "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-t", str(seconds), "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    return path
