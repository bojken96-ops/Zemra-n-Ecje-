"""Playwright-managed Chrome windows playing authorised livestreams.

* The owner signs in to Google manually, once, in a dedicated "master" persistent profile
  (``python -m capture.agent login``). StreamPulse never sees or stores the password.
* Each capture session gets its own copy of that profile so concurrent windows are isolated
  (Chrome cannot open one profile directory twice).
* The window is tagged with a unique title so the capture backend records exactly that window.
* Player health (readiness, stalls, ads, end of stream) is read from the page's <video> element.
"""
from __future__ import annotations

import asyncio
import ctypes
import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("capture.browser")

SKIP_PROFILE_PARTS = {"Cache", "Code Cache", "GPUCache", "GrShaderCache", "ShaderCache", "Service Worker",
                      "Crashpad", "DawnCache", "DawnGraphiteCache", "BrowserMetrics", "optimization_guide_model_store"}
SKIP_PROFILE_FILES = {"SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile", "LOCK"}

CHROME_ARGS = [
    "--autoplay-policy=no-user-gesture-required",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",   # keep rendering when covered by other windows
    "--disable-features=CalculateNativeWinOcclusion,MediaSessionService",
    "--no-first-run", "--no-default-browser-check",
    "--use-fake-ui-for-media-stream",              # auto-accept the device-label permission used for setSinkId
]

TITLE_SCRIPT = """
(() => {
  const tag = %s;
  const apply = () => { if (document.title !== tag) document.title = tag; };
  const start = () => {
    apply();
    const el = document.querySelector('title') || document.head.appendChild(document.createElement('title'));
    new MutationObserver(apply).observe(el, {childList: true, characterData: true, subtree: true});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  setInterval(apply, 1000);
})();
"""

# Player-only layout: the <video> fills the viewport so the capture contains the stream, not the page UI.
LAYOUT_SCRIPT = """
(() => {
  if (document.getElementById('streampulse-layout')) return true;
  const player = document.querySelector('#movie_player');
  if (!player) return false;
  const style = document.createElement('style');
  style.id = 'streampulse-layout';
  style.textContent = `
    html, body { overflow: hidden !important; background: #000 !important; }
    #movie_player { position: fixed !important; inset: 0 !important; width: 100vw !important;
                    height: 100vh !important; z-index: 2147483646 !important; background: #000 !important; }
    #masthead-container, ytd-masthead, #secondary, #below, #chat, ytd-live-chat-frame { visibility: hidden !important; }
    .ytp-chrome-bottom, .ytp-chrome-top, .ytp-gradient-bottom, .ytp-gradient-top, .ytp-ce-element,
    .ytp-paid-content-overlay, .ytp-cards-teaser, .iv-branding { opacity: 0 !important; }
    .html5-video-container video { width: 100vw !important; height: 100vh !important; left: 0 !important;
                                   top: 0 !important; object-fit: contain !important; }`;
  document.head.appendChild(style);
  window.dispatchEvent(new Event('resize'));
  return true;
})()
"""

STATE_SCRIPT = """
(() => {
  const v = document.querySelector('#movie_player video') || document.querySelector('video');
  const p = document.querySelector('#movie_player');
  const txt = (document.querySelector('.ytp-offline-slate-main-text, .ytp-error-content-wrap-reason, ' +
               'yt-playability-error-supported-renderers') || {}).innerText || '';
  return {
    hasVideo: !!v,
    paused: v ? v.paused : null,
    ended: v ? v.ended : null,
    readyState: v ? v.readyState : 0,
    currentTime: v ? v.currentTime : 0,
    muted: v ? v.muted : null,
    volume: v ? v.volume : null,
    width: v ? v.videoWidth : 0,
    height: v ? v.videoHeight : 0,
    adShowing: !!(p && p.classList.contains('ad-showing')),
    errorText: txt.trim().slice(0, 200),
    signedIn: !!document.querySelector('#avatar-btn, button#avatar-btn'),
    sinkId: v && v.sinkId !== undefined ? v.sinkId : null,
  };
})()
"""

SINK_SCRIPT = """
async (label) => {
  try { const s = await navigator.mediaDevices.getUserMedia({audio: true}); s.getTracks().forEach(t => t.stop()); }
  catch (e) { /* labels may already be available */ }
  const devices = await navigator.mediaDevices.enumerateDevices();
  const out = devices.find(d => d.kind === 'audiooutput' && d.label.toLowerCase().includes(label.toLowerCase()));
  if (!out) return {ok: false, error: 'audio output device not found: ' + label,
                    available: devices.filter(d => d.kind === 'audiooutput').map(d => d.label)};
  const v = document.querySelector('#movie_player video') || document.querySelector('video');
  if (!v || !v.setSinkId) return {ok: false, error: 'video element not ready'};
  await v.setSinkId(out.deviceId);
  v.muted = false; if (v.volume < 0.5) v.volume = 1.0;
  if (v.paused) { try { await v.play(); } catch (e) {} }
  return {ok: true, sinkId: v.sinkId};
}
"""


def copy_profile(master: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)

    def ignore(dirpath: str, names: list[str]) -> set[str]:
        return {n for n in names if n in SKIP_PROFILE_PARTS or n in SKIP_PROFILE_FILES}

    shutil.copytree(master, dest, ignore=ignore)


def find_window_handle(title: str) -> int | None:
    """Return the HWND of the top-level window with exactly this title (Windows only)."""
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    found: list[int] = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value.startswith(title) and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(proto(cb), 0)
    return found[0] if found else None


def window_is_minimised(hwnd: int) -> bool:
    if sys.platform != "win32":
        return False
    return bool(ctypes.windll.user32.IsIconic(hwnd))  # type: ignore[attr-defined]


def restore_window(hwnd: int) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # type: ignore[attr-defined]  # SW_RESTORE


@dataclass
class PlayerState:
    ok: bool
    reason: str
    raw: dict


def assess(prev: dict | None, cur: dict, stalled_for: float) -> PlayerState:
    if not cur.get("hasVideo"):
        return PlayerState(False, "no_video_element", cur)
    if cur.get("errorText"):
        text = cur["errorText"].lower()
        if any(k in text for k in ("ended", "offline", "has ended", "is over")):
            return PlayerState(False, "stream_ended", cur)
        if any(k in text for k in ("sign in", "private", "members-only", "unavailable")):
            return PlayerState(False, "access_denied", cur)
        return PlayerState(False, "player_error", cur)
    if cur.get("ended"):
        return PlayerState(False, "stream_ended", cur)
    if cur.get("paused"):
        return PlayerState(False, "paused", cur)
    if stalled_for > 15:
        return PlayerState(False, "stalled", cur)
    if cur.get("readyState", 0) < 3:
        return PlayerState(True, "buffering", cur)
    return PlayerState(True, "playing", cur)


class BrowserSession:
    def __init__(self, session_id: str, url: str, profile_dir: Path, window_title: str):
        self.session_id, self.url, self.profile_dir, self.window_title = session_id, url, profile_dir, window_title
        self.context = None
        self.page = None
        self.hwnd: int | None = None
        self.last_time = 0.0
        self.last_advance = 0.0
        self.prev_state: dict | None = None


class BrowserManager:
    def __init__(self, profiles_dir: Path, channel: str = "chrome", width: int = 1920, height: int = 1080):
        self.profiles_dir = profiles_dir
        self.master = profiles_dir / "master"
        self.channel, self.width, self.height = channel, width, height
        self._pw = None
        self.sessions: dict[str, BrowserSession] = {}

    async def _playwright(self):
        if self._pw is None:
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
        return self._pw

    async def _launch(self, user_data: Path, url: str | None):
        pw = await self._playwright()
        ctx = await pw.chromium.launch_persistent_context(
            str(user_data), channel=self.channel or None, headless=False, no_viewport=True,
            args=[*CHROME_ARGS, f"--window-size={self.width},{self.height + 80}"],
            ignore_default_args=["--enable-automation", "--mute-audio"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        if url:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        return ctx, page

    async def login(self) -> None:
        """Open the master profile so the owner can sign in to Google manually."""
        self.master.mkdir(parents=True, exist_ok=True)
        ctx, page = await self._launch(self.master, "https://accounts.google.com/ServiceLogin?continue=https://www.youtube.com/")
        print("Sign in to the Google account that has access to the livestreams, then close the browser window.")
        closed = asyncio.Event()
        ctx.on("close", lambda *_: closed.set())
        await closed.wait()

    def has_master_profile(self) -> bool:
        return (self.master / "Default").exists()

    async def open(self, session_id: str, url: str) -> BrowserSession:
        if not self.has_master_profile():
            raise RuntimeError("No signed-in browser profile. Run: python -m capture.agent login")
        profile = self.profiles_dir / "sessions" / session_id
        copy_profile(self.master, profile)
        title = f"StreamPulse::{session_id}"
        sess = BrowserSession(session_id, url, profile, title)
        sess.context, sess.page = await self._launch(profile, None)
        await sess.page.add_init_script(TITLE_SCRIPT % repr(title))
        await sess.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await sess.page.evaluate(TITLE_SCRIPT % repr(title))
        self.sessions[session_id] = sess
        await self.wait_ready(sess)
        for _ in range(20):
            sess.hwnd = find_window_handle(title)
            if sess.hwnd or sys.platform != "win32":
                break
            await asyncio.sleep(0.5)
        if sys.platform == "win32" and not sess.hwnd:
            raise RuntimeError("browser window not found by title; is another app renaming windows?")
        return sess

    async def wait_ready(self, sess: BrowserSession, timeout: float = 60) -> dict:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        state: dict = {}
        while loop.time() < deadline:
            await sess.page.evaluate(LAYOUT_SCRIPT)
            state = await sess.page.evaluate(STATE_SCRIPT)
            if state.get("hasVideo") and state.get("readyState", 0) >= 3 and not state.get("paused"):
                sess.last_time, sess.last_advance = state["currentTime"], loop.time()
                return state
            if state.get("hasVideo") and state.get("paused"):
                await sess.page.evaluate("(() => { const v=document.querySelector('video'); v && v.play(); })()")
            if state.get("errorText"):
                break
            await asyncio.sleep(1)
        raise RuntimeError(f"player not ready: {state.get('errorText') or state}")

    async def route_audio(self, sess: BrowserSession, sink_label: str) -> dict:
        result = await sess.page.evaluate(SINK_SCRIPT, sink_label)
        if not result.get("ok"):
            raise RuntimeError(f"audio routing failed: {result}")
        return result

    async def check(self, sess: BrowserSession) -> PlayerState:
        loop = asyncio.get_running_loop()
        try:
            cur = await sess.page.evaluate(STATE_SCRIPT)
        except Exception as exc:  # page crashed / closed
            return PlayerState(False, "page_crashed", {"error": str(exc)})
        if cur.get("currentTime", 0) > sess.last_time + 0.2 or cur.get("adShowing"):
            sess.last_time, sess.last_advance = cur.get("currentTime", 0), loop.time()
        stalled_for = loop.time() - sess.last_advance if sess.last_advance else 0
        if sess.hwnd and window_is_minimised(sess.hwnd):
            restore_window(sess.hwnd)  # WGC/gdigrab cannot capture minimised windows
        state = assess(sess.prev_state, cur, stalled_for)
        sess.prev_state = cur
        return state

    async def recover(self, sess: BrowserSession, sink_label: str | None) -> None:
        """Reload the player after a stall/crash (e.g. internet interruption) and re-apply routing/layout."""
        try:
            await sess.page.reload(wait_until="domcontentloaded", timeout=60_000)
        except Exception:
            ctx, page = await self._launch(sess.profile_dir, sess.url)
            sess.context, sess.page = ctx, page
            await page.add_init_script(TITLE_SCRIPT % repr(sess.window_title))
            await page.evaluate(TITLE_SCRIPT % repr(sess.window_title))
        await self.wait_ready(sess, timeout=90)
        if sink_label:
            await self.route_audio(sess, sink_label)
        sess.hwnd = find_window_handle(sess.window_title) or sess.hwnd

    async def close(self, session_id: str) -> None:
        sess = self.sessions.pop(session_id, None)
        if sess and sess.context:
            try:
                await sess.context.close()
            except Exception:
                pass
        if sess:
            shutil.rmtree(sess.profile_dir, ignore_errors=True)

    async def shutdown(self) -> None:
        for sid in list(self.sessions):
            await self.close(sid)
        if self._pw:
            await self._pw.stop()
