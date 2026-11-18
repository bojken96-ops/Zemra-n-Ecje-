"""Final vertical clip render: 1080x1920, H.264/AAC MP4, loudness normalised, optional burned subtitles."""
from __future__ import annotations

from pathlib import Path

from processing import ffmpeg
from processing.vertical_cropper import choose_fps, vertical_filter


def render_vertical(src: Path, out_path: Path, mode: str = "blur_background", fps_setting: str = "auto",
                    ass_path: Path | None = None, loudness_lufs: float = -14.0,
                    encoder: list[str] | None = None) -> dict:
    probe = ffmpeg.probe(src)
    fps = choose_fps(probe.fps, fps_setting)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    graph = vertical_filter(mode, fps, str(ass_path) if ass_path else None)
    args = ["-i", str(src), "-filter_complex", graph, "-map", "[vout]"]
    if probe.has_audio:
        args += ["-map", "0:a:0", "-af", f"loudnorm=I={loudness_lufs}:TP=-1.5:LRA=11,aresample=48000",
                 "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    enc = encoder or ffmpeg.video_encoder()
    args += [*enc, "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(fps), "-g", str(fps * 2),
             "-movflags", "+faststart", str(out_path)]
    ffmpeg.run(args)
    result = ffmpeg.probe(out_path)
    return {"duration": result.duration, "width": result.width, "height": result.height, "fps": result.fps,
            "has_audio": result.has_audio, "size_bytes": out_path.stat().st_size}
