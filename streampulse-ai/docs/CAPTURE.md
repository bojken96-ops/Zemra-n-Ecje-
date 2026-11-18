# Real-time capture engine

## Why a host agent
Livestreams are captured exactly as your own signed-in Chrome plays them on your PC. Linux containers
can't see Windows windows, so `capture/` runs natively on Windows and talks to the backend over
loopback (`CAPTURE_API_URL` must be 127.0.0.1/localhost) with the shared `CAPTURE_AGENT_TOKEN`. The agent
**pulls** commands, so the backend never needs to reach into the host.

## What is NOT used (by design)
* No unofficial YouTube stream extractors (yt-dlp, streamlink, …), not even as a fallback.
* No DRM circumvention and no authentication bypass. You sign in to Google manually. StreamPulse never
  asks for or stores your password.
* Playwright screenshots are **not** used to record video.
* If the selected capture method can't run (e.g. FFmpeg lacks `gfxcapture`), the agent exits with
  `Capture method unavailable: …`, or marks the session *failed* with that reason in the dashboard.
  It does not switch to another method. Change the method yourself in Settings → Capture.

## Components
| File | Role |
|---|---|
| `capture_adapter.py` | `CaptureAdapter` interface (`start_capture`, `stop_capture`, `get_status`, `get_recording_path`) and `CaptureUnavailable` |
| `windows_capture.py` | `WindowsCaptureAdapter`: FFmpeg command builder, encoder probing (NVENC/QSV/AMF/x264), `FFmpegRecorder` with `-progress` parsing and graceful `q` stop |
| `browser_manager.py` | Playwright persistent Chrome contexts, per-session profile copies, unique window title, player-only layout, readiness/stall/end detection, reload recovery, `setSinkId` audio routing, HWND lookup |
| `audio_capture.py` | DirectShow device discovery and allocation of virtual-cable routes per session |
| `health_monitor.py` | progress parsing, segment-list tracking, wall-clock anchoring, fps/drop/stall/disk checks |
| `capture_manager.py` | command loop, per-session lifecycle, segment registration, heartbeats, restarts |
| `agent.py` | CLI: `doctor`, `login`, `run` |

## Video backends
**`gfxcapture` (recommended)** is Windows Graphics Capture through FFmpeg 8's `gfxcapture` source, targeted
by **HWND**. It captures only that window (never the rest of the desktop), keeps working when the window
is covered, and outputs GPU frames that are downloaded and encoded. `doctor` prints the option names
your FFmpeg build supports. The command builder uses `hwnd` when it's available and otherwise a window
title regex.

**`gdigrab`** captures the window by its exact title (`StreamPulse::<session id>`) and works with older
FFmpeg builds. The window must stay visible. Chrome with GPU compositing can produce black frames, which
the black-screen detector reports.

## Audio
Each Chrome instance plays the stream's `<video>` into its own virtual cable (`HTMLMediaElement.setSinkId`).
FFmpeg records the paired DirectShow endpoint. Concurrency is limited by the number of configured routes.
The `dshow_device` mode (e.g. Stereo Mix) records all desktop audio, so it is restricted to one capture.

## Timing and A/V sync
* Both FFmpeg inputs use `-use_wallclock_as_timestamps 1`, so audio and video share one clock.
  `aresample=async=1000` corrects drift.
* Output is split by the segment muxer (default 10 s, `-force_key_frames` on boundaries) into Matroska
  files. Each process run appends to `segments.csv`.
* Wall-clock anchor = `time.time() - out_time` (median of progress samples), taken per FFmpeg run.
  Each finished segment is registered with absolute start and end times, which lines it up with the chat
  timestamps from the YouTube API. Keep Windows time synchronised (Settings → Time → Sync now).
  Expected accuracy is about 0.5 s.
* Chat reactions are matched to footage with a 4 s reaction delay.

## Health monitoring and recovery
| Check | Action |
|---|---|
| FFmpeg exits / crashes | restart with backoff (up to 10). Sequence numbers continue. Remaining segments of the old run are flushed first |
| Encoder stalls >15 s, fps < 75 %, drops > 5 % | reported in health (`problems`) |
| Free disk < `min_free_disk_gb` | capture stops and the session fails with an explanation |
| Player paused / stalled >15 s / page crash / error (e.g. internet outage) | status `reconnecting`, page reload, audio route and layout re-applied |
| Window minimised | restored automatically |
| "Live stream ended" overlay for 60 s, or the backend sees `actualEndTime` | capture stops cleanly |
| Sign-in/age/member error | session fails: "re-run login" |
| Black / frozen frames | each segment is analysed by the worker and alerts appear in Capture health |
| Agent stops heartbeating for 90 s | backend marks the session failed and notifies you |

Ads that YouTube shows during playback are recorded like everything else, and `ad_showing` is reported
in health.
