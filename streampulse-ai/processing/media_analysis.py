"""Per-second audio and visual activity features extracted from recording segments.

Audio: RMS loudness, spectral centroid (brightness: shouting raises it), spectral
flux (sudden changes), and a 3-8 Hz envelope modulation measure that correlates with
laughter. Visual: frame-difference motion, scene-cut detection, black and frozen
frame detection (also used for capture health).

These are signal-processing heuristics, not trained classifiers. They are combined
with chat signals and an AI evaluation before any clip is created.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from processing import ffmpeg

SAMPLE_RATE = 16000
FRAME_W, FRAME_H, ANALYSIS_FPS = 160, 90, 4


@dataclass
class AudioFeatures:
    rms_db: list[float]
    centroid_hz: list[float]
    flux: list[float]
    laughter: list[float]
    silent_ratio: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class VisualFeatures:
    motion: list[float]
    scene_cuts: list[int]
    black_ratio: float
    frozen_ratio: float
    black_seconds: list[int]
    frozen_seconds: list[int]

    def as_dict(self) -> dict:
        return asdict(self)


def decode_audio(path: str | Path, start: float | None = None, duration: float | None = None) -> np.ndarray:
    args = []
    if start is not None:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(path)]
    if duration is not None:
        args += ["-t", f"{duration:.3f}"]
    args += ["-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"]
    raw = ffmpeg.run_bytes(args)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def audio_features(samples: np.ndarray, sr: int = SAMPLE_RATE) -> AudioFeatures:
    seconds = int(len(samples) // sr)
    rms_db, centroid, flux, laughter = [], [], [], []
    prev_spec = None
    silent = 0
    hop = sr // 50  # 20 ms envelope frames
    for i in range(seconds):
        chunk = samples[i * sr:(i + 1) * sr]
        rms = float(np.sqrt(np.mean(chunk ** 2)) + 1e-9)
        db = 20 * np.log10(rms)
        rms_db.append(round(db, 2))
        if db < -50:
            silent += 1
        spec = np.abs(np.fft.rfft(chunk * np.hanning(len(chunk))))
        freqs = np.fft.rfftfreq(len(chunk), 1 / sr)
        total = spec.sum() + 1e-9
        centroid.append(round(float((spec * freqs).sum() / total), 1))
        norm = spec / total
        flux.append(round(float(np.sqrt(((norm - prev_spec) ** 2).sum())) if prev_spec is not None else 0.0, 5))
        prev_spec = norm
        # envelope modulation in 3-8 Hz band (syllabic bursts typical of laughter)
        env = np.sqrt(np.mean(chunk[: (len(chunk) // hop) * hop].reshape(-1, hop) ** 2, axis=1))
        env = env - env.mean()
        if env.std() > 1e-5:
            mod = np.abs(np.fft.rfft(env))
            mfreq = np.fft.rfftfreq(len(env), 1 / 50)
            band = mod[(mfreq >= 3) & (mfreq <= 8)].sum()
            laughter.append(round(float(band / (mod[1:].sum() + 1e-9)), 4))
        else:
            laughter.append(0.0)
    return AudioFeatures(rms_db, centroid, flux, laughter, silent / seconds if seconds else 1.0)


def decode_frames(path: str | Path, fps: int = ANALYSIS_FPS) -> np.ndarray:
    raw = ffmpeg.run_bytes(["-i", str(path), "-an", "-vf", f"fps={fps},scale={FRAME_W}:{FRAME_H},format=gray",
                            "-f", "rawvideo", "-"])
    n = len(raw) // (FRAME_W * FRAME_H)
    return np.frombuffer(raw[: n * FRAME_W * FRAME_H], dtype=np.uint8).reshape(n, FRAME_H, FRAME_W).astype(np.float32)


def visual_features(frames: np.ndarray, fps: int = ANALYSIS_FPS) -> VisualFeatures:
    if len(frames) == 0:
        return VisualFeatures([], [], 1.0, 1.0, [], [])
    seconds = len(frames) // fps
    diffs = np.concatenate([[0.0], np.mean(np.abs(np.diff(frames, axis=0)), axis=(1, 2))])
    luma = frames.mean(axis=(1, 2))
    motion, cuts, black_s, frozen_s = [], [], [], []
    for s in range(seconds):
        d = diffs[s * fps:(s + 1) * fps]
        motion.append(round(float(d.mean()), 3))
        if float(d.max()) > 40:  # large full-frame change => hard cut / major scene change
            cuts.append(s)
        if float(luma[s * fps:(s + 1) * fps].mean()) < 12:
            black_s.append(s)
        elif float(d.max()) < 0.15:
            frozen_s.append(s)
    return VisualFeatures(motion, cuts, len(black_s) / max(1, seconds), len(frozen_s) / max(1, seconds), black_s,
                          frozen_s)


def analyse_file(path: str | Path) -> dict:
    probe = ffmpeg.probe(path)
    result: dict = {"duration": probe.duration, "width": probe.width, "height": probe.height, "fps": probe.fps}
    result["audio"] = audio_features(decode_audio(path)).as_dict() if probe.has_audio else None
    result["visual"] = visual_features(decode_frames(path)).as_dict() if probe.has_video else None
    return result
