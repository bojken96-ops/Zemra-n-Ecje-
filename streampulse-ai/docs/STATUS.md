# Implementation and verification status

These checks ran in a Linux development container (4 CPU, 15 GB RAM, **no GPU**, FFmpeg 6.1, PostgreSQL 16,
Redis 7, Python 3.12, Node 22) on 2026-11-18. There was **no Windows desktop, no Docker daemon, no
YouTube/Gemini/TikTok/Instagram credentials, and no access to HuggingFace** (so no Whisper model).
Anything that depends on those is marked as such below. Don't treat those items as verified until
you've run them on your machine.

**Automated:** 74 backend tests pass (`cd backend && pytest`) against real PostgreSQL, Redis and FFmpeg.
The frontend type-checks and builds (`npm run typecheck && npm run build`).

**Live smoke test:** uvicorn + Celery worker + beat + `next start` ran together. Playwright created the
owner account, added an authorised creator, added a stream (the missing API key was reported in the
card) and loaded the settings with no browser errors. 16 synthetic 720p segments were then registered
through the agent API. The running worker analysed them, detected the moment, beat triggered the
evaluation, and a 1:20 vertical clip appeared in the dashboard as "Awaiting approval".

## Phases
| Phase | Status |
|---|---|
| 1 Foundation | Done. Compose file validated (`docker compose config`); images **not built here** (no daemon) |
| 2 YouTube management | Done. Tested against an HTTP-level fake of the Data API; **not yet tested with a real key** |
| 3 Capture agent | Done. Logic, FFmpeg command builder, recorder, segmenting, wall-clock anchoring, restart, stop and recovery were tested on Linux, with lavfi test sources standing in for the window and audio devices. **The gfxcapture/gdigrab + dshow + Chrome path needs a Windows run** (`capture.agent doctor`, then one real stream) |
| 4 Live intelligence | Done and tested with real media analysis + chat analytics |
| 5 Clip generation | Done and tested end to end with real FFmpeg (1080×1920 H.264/AAC, pre-event footage, sentence snapping, ASS styles, thumbnail, dedupe, regeneration). Whisper was **substituted** in tests because the model can't be downloaded here |
| 6 AI content | Done. Gemini request/response handling tested against a fake HTTP endpoint; **needs a real key** |
| 7 Publishing | Done. YouTube/TikTok/Instagram flows tested against fakes of the official APIs. Queue, retries, dedupe and confirm-before-published were tested for real. **Needs real app credentials and accounts** |
| 8 Polish | Analytics, notifications, storage management, docs done. Load and performance testing with several long real streams is still open |

## Required test list
| # | Test | Result |
|---|---|---|
| 1 | Adding a livestream URL | ✅ automated + UI smoke |
| 2 | Detecting a livestream starting | ✅ automated (scheduled → live transition queues capture) |
| 3 | Opening an authenticated browser | ⚠️ code complete; needs Windows + your Google login |
| 4 | Capturing video and audio | ⚠️ recorder pipeline verified with lavfi sources; real window/audio capture needs Windows |
| 5 | Multiple simultaneous streams | ✅ concurrency limits/audio route allocation automated; ⚠️ real multi-window capture needs Windows |
| 6 | Recovering from internet interruptions | ✅ player stall → reload, recorder crash → restart (automated); ⚠️ real network drop on Windows |
| 7 | Monitoring chat | ✅ automated (dedupe, errors, quota, ended/disabled) |
| 8 | Detecting a chat spike | ✅ automated (and verified that chat alone does not clip) |
| 9 | Detecting an exciting audio moment | ✅ automated with synthetic loud/motion segment |
| 10 | Clip with pre-event footage | ✅ automated + live worker smoke test |
| 11 | Synchronised subtitles | ✅ timing/rendering automated; ⚠️ real Whisper transcription not run here |
| 12 | Vertical video | ✅ 1080×1920, H.264/AAC verified with ffprobe |
| 13 | Publishing to each platform | ⚠️ protocol-level fakes only; needs real accounts |
| 14 | Recovering from publishing failures | ✅ automated (backoff, non-retryable, manual retry) |
| 15 | Insufficient storage | ✅ automated (alerts, safe cleanup); agent stops below min free disk |

## Known limitations
* Live chat uses `liveChatMessages.list` polling at the server-given interval. The newer streaming
  `streamList` method isn't used, which costs some extra quota but behaves the same.
* Facial-expression analysis isn't bundled. Visual signals are motion, scene cuts and black/frozen frames.
  Gemini sees keyframes for the semantic judgement.
* The capture timeline is accurate to about 0.5 s (encoder latency).
* Ads shown by YouTube during playback are recorded and flagged (`ad_showing`). They are not removed.
