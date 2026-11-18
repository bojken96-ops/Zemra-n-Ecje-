"""9:16 1080x1920 conversion filter graphs."""
from __future__ import annotations

OUT_W, OUT_H = 1080, 1920


def vertical_filter(mode: str, fps: int, ass_path: str | None = None) -> str:
    """Return an ffmpeg -filter_complex graph producing [vout] from input 0.

    blur_background: full frame scaled to width, over a blurred, zoomed copy (no content lost).
    center_crop:     crop the centre 9:16 region (fills the screen, loses the sides).
    fit_black:       full frame letterboxed on black.
    """
    if mode == "blur_background":
        graph = (f"[0:v]split=2[bgsrc][fgsrc];"
                 f"[bgsrc]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},"
                 f"boxblur=luma_radius=40:luma_power=2,eq=brightness=-0.08[bg];"
                 f"[fgsrc]scale={OUT_W}:-2:flags=lanczos[fg];"
                 f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base]")
    elif mode == "center_crop":
        graph = (f"[0:v]scale=-2:{OUT_H}:flags=lanczos,crop={OUT_W}:{OUT_H}[base]")
    elif mode == "fit_black":
        graph = (f"[0:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease:flags=lanczos,"
                 f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:color=black[base]")
    else:
        raise ValueError(f"unknown vertical mode {mode}")
    tail = f"[base]fps={fps},setsar=1"
    if ass_path:
        tail += f",ass='{escape_filter_path(ass_path)}'"
    return f"{graph};{tail},format=yuv420p[vout]"


def escape_filter_path(path: str) -> str:
    # ffmpeg filter-arg escaping for paths (Windows drive colons, quotes, backslashes)
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def choose_fps(source_fps: float | None, setting: str) -> int:
    if setting in ("30", "60"):
        return int(setting)
    return 60 if (source_fps or 30) >= 50 else 30
