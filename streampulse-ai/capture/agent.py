"""StreamPulse capture agent CLI.

    python -m capture.agent doctor   # check FFmpeg, capture backends, audio devices, backend connection
    python -m capture.agent login    # sign in to Google manually in the agent's browser profile
    python -m capture.agent run      # run the agent (pulls capture commands from the backend)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import platform
import shutil
import signal
import subprocess
import sys

import httpx

from capture.audio_capture import AudioRouter, list_dshow_devices
from capture.browser_manager import BrowserManager
from capture.capture_adapter import CaptureUnavailable
from capture.capture_manager import BackendClient, CaptureManager
from capture.config import AgentConfig
from capture.windows_capture import WindowsCaptureAdapter, filter_options, has_input_device, pick_encoder

log = logging.getLogger("capture")


def doctor(cfg: AgentConfig) -> int:
    ok = True

    def line(good: bool, msg: str) -> None:
        nonlocal ok
        ok &= good
        print(("  [ok]   " if good else "  [FAIL] ") + msg)

    print("StreamPulse capture agent diagnostics")
    line(sys.platform == "win32", f"Windows host ({platform.platform()})")
    ff = shutil.which(cfg.ffmpeg) or cfg.ffmpeg
    try:
        ver = subprocess.run([ff, "-hide_banner", "-version"], capture_output=True, text=True, timeout=20).stdout.split("\n")[0]
        line(True, f"FFmpeg: {ver}")
    except (OSError, subprocess.SubprocessError) as exc:
        line(False, f"FFmpeg not runnable ({exc}); set CAPTURE_FFMPEG")
        return 1
    gfx = filter_options(ff, "gfxcapture")
    line(gfx is not None, "Windows Graphics Capture source (gfxcapture) " + (f"options: {sorted(gfx)}" if gfx else
                                                                            "missing - needs FFmpeg 8.0+"))
    line(has_input_device(ff, "gdigrab"), "gdigrab input available")
    line(has_input_device(ff, "dshow"), "DirectShow (dshow) input available")
    print(f"  [info] H.264 encoder selected: {pick_encoder(ff, 'auto')}")
    devices = list_dshow_devices(ff) if sys.platform == "win32" else {"audio": []}
    print(f"  [info] DirectShow audio devices: {devices['audio']}")
    try:
        AudioRouter(cfg.audio_routes, "virtual_cable").validate(devices["audio"])
        line(True, f"audio routes: {[(r.sink, r.source) for r in cfg.audio_routes]}")
    except CaptureUnavailable as exc:
        line(False, str(exc))
    line(BrowserManager(cfg.profiles_dir, cfg.browser_channel).has_master_profile(),
         "signed-in browser profile (run 'login' if missing)")
    line(cfg.storage_root.exists() and (cfg.storage_root / "recordings").exists(),
         f"shared storage folder {cfg.storage_root} (must be the folder Docker mounts as /data/storage)")
    try:
        r = httpx.get(f"{cfg.api_url}/api/agent/config", headers={"Authorization": f"Bearer {cfg.token}"}, timeout=10)
        line(r.status_code == 200, f"backend {cfg.api_url} reachable and token accepted (HTTP {r.status_code})")
        if r.status_code == 200:
            print(f"  [info] capture settings: {r.json()}")
    except httpx.HTTPError as exc:
        line(False, f"backend not reachable: {exc}")
    print("\nAll checks passed." if ok else "\nSome checks failed - see docs/CAPTURE.md.")
    return 0 if ok else 1


async def run(cfg: AgentConfig) -> None:
    backend = BackendClient(cfg.api_url, cfg.token)
    r = await backend.http.get("/api/agent/config")
    r.raise_for_status()
    settings = r.json()
    adapter = WindowsCaptureAdapter(cfg.ffmpeg, settings.get("video_backend", "gfxcapture"),
                                    settings.get("video_encoder", "auto"))
    adapter.preflight()  # raises CaptureUnavailable with an explanation instead of switching methods
    router = AudioRouter(cfg.audio_routes, settings.get("audio_mode", "virtual_cable"))
    router.validate(list_dshow_devices(cfg.ffmpeg)["audio"])
    browser = BrowserManager(cfg.profiles_dir, cfg.browser_channel, settings.get("output_width", 1920),
                             settings.get("output_height", 1080))
    manager = CaptureManager(backend, adapter, browser, router, cfg.storage_root, settings)
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows: Ctrl+C raises KeyboardInterrupt instead
            pass
    log.info("capture agent running (backend %s, method %s)", cfg.api_url, adapter.method)
    try:
        while not stop.is_set():
            try:
                await manager.poll_once()
            except httpx.HTTPError as exc:
                log.warning("backend unreachable: %s", exc)
            try:
                await asyncio.wait_for(stop.wait(), timeout=cfg.poll_seconds)
            except asyncio.TimeoutError:
                pass
    finally:
        await manager.shutdown()
        await browser.shutdown()
        await backend.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="python -m capture.agent")
    p.add_argument("command", choices=["run", "login", "doctor"])
    args = p.parse_args()
    cfg = AgentConfig.load()
    if args.command == "doctor":
        sys.exit(doctor(cfg))
    if args.command == "login":
        asyncio.run(BrowserManager(cfg.profiles_dir, cfg.browser_channel).login())
        return
    try:
        asyncio.run(run(cfg))
    except CaptureUnavailable as exc:
        log.error("Capture method unavailable: %s", exc)
        sys.exit(2)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
