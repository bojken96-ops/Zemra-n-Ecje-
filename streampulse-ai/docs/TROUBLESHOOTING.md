# Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Stream card: "YOUTUBE_API_KEY is not configured" | Set it in `.env`, then `docker compose up -d` |
| Stream stays *offline* though it's live | The API key lacks YouTube Data API v3, or quota is exceeded (card shows "quota"). For `@handle/live` URLs the channel is searched only every 5 min, so paste the `watch?v=` URL instead |
| "Capture blocked: creator … is not marked as authorised" | Streams → Creators → mark authorised and describe the authorisation |
| Capture stays *pending* | The agent isn't running, or `max_concurrent_captures` is reached. Run `python -m capture.agent doctor` |
| Agent: `Capture method unavailable: … gfxcapture …` | Your FFmpeg is older than 8.0 or lacks D3D11. Install a full 8.x build, or choose *gdigrab* in Settings → Capture |
| Agent: `DirectShow audio device(s) not found` | Names in `CAPTURE_AUDIO_ROUTES` must match `ffmpeg -list_devices true -f dshow -i dummy` exactly |
| `audio routing failed: audio output device not found` | `sink` must be part of the playback device name ("CABLE Input") |
| Clips have no sound | Check Windows Sound → Recording → CABLE Output shows level while the stream plays. Make sure the stream isn't muted in YouTube |
| Black frames / black alert | Window minimised, or gdigrab + GPU compositing. Use gfxcapture, or launch Chrome with hardware acceleration off |
| Frozen alert | The stream froze or the page stalled. The agent reloads it automatically; check your network |
| "YouTube denied playback … re-run login" | Your session expired or the stream is members-only. Run `python -m capture.agent login` |
| Segment registration 422 "file not found in shared storage" | `CAPTURE_STORAGE_ROOT` is not the folder compose mounts (`./storage`) |
| Agent: 401 invalid agent token | `CAPTURE_AGENT_TOKEN` differs between agent and backend `.env` |
| Moments detected but no clips; notification "AI evaluation is not configured" | Add a Gemini key, or turn off *Require AI evaluation* |
| Clips without subtitles; worker log "transcription unavailable" | The Whisper model failed to download/load. Check the internet connection and `WHISPER_MODEL`; for GPU, check the CUDA overlay |
| Whisper slow on CPU | Use `WHISPER_MODEL=base` or the GPU overlay |
| Publishing job failed "unauthorized" / account "Reconnect needed" | Token revoked or expired. Accounts → Reconnect |
| TikTok posts are private | Expected until TikTok audits your app (SELF_ONLY restriction) |
| YouTube uploads stay private | Unverified Google project: uploads are locked private until Google's audit |
| Instagram "requires a professional account" | Convert to Business/Creator in the Instagram app |
| Dashboard says "Live updates offline" | WebSocket to `ws://localhost:8000/api/ws` blocked. Check `NEXT_PUBLIC_WS_URL` and `ALLOWED_ORIGINS` |
| 403 "access restricted to local network" | You're not accessing from a private network. Adjust `ALLOWED_CLIENT_NETWORKS` only if you know why |
| Low disk alerts | Lower recording retention or max storage, or delete old clips. Published clips are never auto-deleted |

Logs: `docker compose logs -f backend worker beat` (JSON), and the agent console.
