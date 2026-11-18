# StreamPulse AI

A private, locally hosted, automated livestream clipping system for **authorised** YouTube livestreams.

**Paste a YouTube livestream URL → StreamPulse monitors it → AI finds moments → clips are generated → clips are published.**

> Personal tool, not a SaaS. Capture only creators you have permission to clip. StreamPulse records the
> livestream exactly as your own signed-in browser plays it. It does not use unofficial YouTube
> downloaders, does not circumvent DRM and does not bypass authentication. If the configured capture
> method is unavailable, it stops and tells you why. It never quietly switches to another method.

## Architecture

```
 Windows host                                        Docker Desktop (WSL2), ports bound to 127.0.0.1
 ┌───────────────────────────────┐                   ┌──────────────────────────────────────────────┐
 │ capture agent (python)        │  HTTP + token     │ backend  FastAPI :8000 ── postgres, redis     │
 │  ├ Playwright Chrome window   │ ────────────────▶ │ worker   Celery: analysis, clips, publishing  │
 │  │  (signed-in profile)       │  pull commands,   │ beat     schedules: live checks, chat, queue  │
 │  ├ FFmpeg gfxcapture/gdigrab  │  report health,   │ frontend Next.js :3000 (proxies /api)         │
 │  └ FFmpeg dshow audio (cable) │  register segments└──────────────────────────────────────────────┘
 │ writes ./storage/recordings ──┼──── same folder bind-mounted as /data/storage ────────▲
 └───────────────────────────────┘
```

Docker containers can't see Windows desktop windows, so capture runs as a **native Windows process**.
It only makes outbound calls to `127.0.0.1:8000`, authenticated with `CAPTURE_AGENT_TOKEN`.

### Pipeline
1. **Streams**: the URL is parsed (watch, youtu.be, `/live/ID`, `@handle/live`, `/channel/UC…/live`). Liveness
   comes **only** from the YouTube Data API (`liveStreamingDetails`), never from the URL. Beat re-checks
   every 60 s, so scheduled streams are picked up when they start.
2. **Capture**: when a stream goes live and its creator is marked *authorised* (with notes), a capture
   session is queued. The agent opens the stream in a copy of your signed-in Chrome profile, gives the
   window a unique title, routes its audio to a dedicated virtual cable, and records 10 s Matroska segments
   with wall-clock timestamps.
3. **Chat**: `liveChatMessages.list` polling at the API's `pollingIntervalMillis`. Handles disabled, ended
   and missing chats, quota errors and reconnects.
4. **Detection**: each segment is analysed (loudness, voice brightness, spectral flux, laughter-like
   modulation, motion, scene cuts, black/frozen frames). This is combined with chat velocity, unique
   chatters, emoji bursts, repeated phrases and spam filtering into 10 s activity windows. A candidate
   needs the combined threshold **and** several elevated signals, **including audio or visual evidence**.
   Chat alone never creates a clip. Merging, cooldowns and deduplication are built in.
5. **Evaluation**: Gemini receives the transcript, a chat sample, signal scores and keyframes. It returns
   structured JSON (`interesting`, `viral_score`, `moment_type`, `reason`, `suggested_title`, offsets).
6. **Clip**: the footage is cut from the rolling segment buffer (45 s before / 35 s after by default) and
   extended so no sentence is cut in half. It is transcribed with faster-whisper (word timestamps, en/sq
   auto-detect), rendered as 1080×1920 H.264/AAC with loudness normalisation, given ASS subtitles in one
   of 4 styles, and gets a thumbnail.
7. **Content**: Gemini writes the title, Shorts title, TikTok description, Instagram caption, hook and
   hashtags in the creator's language. Any quote that doesn't appear verbatim in the transcript is stripped.
8. **Publishing**: official APIs only (YouTube resumable upload, TikTok Content Posting API, Instagram
   Graph API resumable Reels). There is one job per clip per account, so duplicates are impossible.
   Failed jobs retry with backoff. A post is marked *published* only after the platform confirms it.

## Quick start (Windows 11 + Docker Desktop)

See **[docs/INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md)** for the full walkthrough. In short:

```powershell
git clone <repo> C:\StreamPulse; cd C:\StreamPulse\streampulse-ai
copy .env.example .env
python scripts\generate_secrets.py      # paste the output into .env
notepad .env                            # YOUTUBE_API_KEY, GEMINI_API_KEY, CAPTURE_STORAGE_ROOT, ...
docker compose up -d --build            # GPU: add -f docker-compose.gpu.yml
# capture agent (native Windows):
powershell -ExecutionPolicy Bypass -File scripts\setup-capture-agent.ps1
.venv-agent\Scripts\python -m capture.agent login     # sign in to Google yourself, once
.venv-agent\Scripts\python -m capture.agent doctor
.venv-agent\Scripts\python -m capture.agent run
```
Then open http://localhost:3000, create the owner account, add a creator (marked authorised), and paste a URL.

## Documentation
| Doc | Contents |
|---|---|
| [docs/INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md) | Windows 11 / WSL2 / Docker setup, GPU, agent install |
| [docs/CAPTURE.md](docs/CAPTURE.md) | Capture design, Windows permissions, audio cables, health & recovery |
| [docs/API_SETUP.md](docs/API_SETUP.md) | Google Cloud, Gemini, TikTok, Instagram app setup, quotas and reviews |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Configuration, environment variables, storage, security, development & tests |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common problems and fixes |
| [docs/STATUS.md](docs/STATUS.md) | What was tested, and how; what still needs verifying on your machine |

## Repository layout
```
backend/        FastAPI app (api/, models/, schemas/, services/*, workers/), Alembic migrations, tests
processing/     FFmpeg: excerpting, vertical conversion, subtitles (ASS/SRT), thumbnails, media analysis
capture/        Windows capture agent (browser_manager, windows_capture, audio_capture, health_monitor, ...)
frontend/       Next.js 15 + TypeScript + Tailwind + shadcn/ui-style components + React Query + Recharts
docker/         Dockerfiles (backend, worker, frontend)
scripts/        entrypoint, secret generator, Windows setup scripts
storage/        recordings/ temporary/ clips/ thumbnails/ subtitles/ (bind-mounted)
```
