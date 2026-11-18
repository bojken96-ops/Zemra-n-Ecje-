"""Pure multi-signal scoring for activity windows."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.chat.analytics import z_to_score, zscore


@dataclass
class SignalScores:
    chat: float | None = None
    audio: float | None = None
    visual: float | None = None
    emoji: float | None = None
    unique_users: float | None = None
    details: dict = field(default_factory=dict)

    def as_map(self) -> dict[str, float | None]:
        return {"chat": self.chat, "audio": self.audio, "visual": self.visual, "emoji": self.emoji,
                "unique_users": self.unique_users}


def audio_window_score(rms_db: list[float], centroid: list[float], flux: list[float], laughter: list[float],
                       baseline_rms: list[float], baseline_centroid: list[float]) -> tuple[float, dict]:
    """Excitement from loudness jumps, voice brightness (shouting), sudden change and laughter-like bursts."""
    if not rms_db:
        return 0.0, {}
    peak_rms = max(rms_db)
    mean_centroid = sum(centroid) / len(centroid)
    z_loud = zscore(peak_rms, baseline_rms, poisson=False) if len(baseline_rms) >= 3 else 0.0
    z_bright = zscore(mean_centroid, baseline_centroid, poisson=False) if len(baseline_centroid) >= 3 else 0.0
    loud = z_to_score(z_loud, 1.0, 3.5)
    bright = z_to_score(z_bright, 1.0, 3.5)
    shouting = loud * 0.6 + bright * 0.4 if loud > 0 else 0.0
    flux_peak = max(flux) if flux else 0.0
    sudden = min(1.0, max(0.0, (flux_peak - 0.02) / 0.08))
    laugh = max(laughter) if laughter else 0.0
    laugh_score = min(1.0, max(0.0, (laugh - 0.35) / 0.35)) if peak_rms > -40 else 0.0
    score = min(1.0, 0.55 * shouting + 0.2 * sudden + 0.25 * laugh_score + (0.15 if loud > 0.8 else 0))
    return round(score, 4), {"peak_rms_db": peak_rms, "mean_centroid": round(mean_centroid, 1),
                             "z_loudness": round(z_loud, 3), "z_brightness": round(z_bright, 3),
                             "laughter": laugh, "flux_peak": flux_peak, "shouting": round(shouting, 3)}


def visual_window_score(motion: list[float], cuts: int, baseline_motion: list[float]) -> tuple[float, dict]:
    if not motion:
        return 0.0, {}
    peak = max(motion)
    z = zscore(peak, baseline_motion, poisson=False) if len(baseline_motion) >= 3 else 0.0
    score = z_to_score(z, 1.0, 4.0)
    score = min(1.0, score + min(0.3, 0.15 * cuts))
    return round(score, 4), {"peak_motion": peak, "z_motion": round(z, 3), "scene_cuts": cuts}


def combine(scores: SignalScores, weights: dict[str, float]) -> float:
    """Weighted mean over available signals (missing signals don't count as zero evidence)."""
    num = den = 0.0
    for name, value in scores.as_map().items():
        if value is None:
            continue
        w = weights.get(name, 0.0)
        num += w * value
        den += w
    if den == 0:
        return 0.0
    # Penalise windows where a large share of weight is unavailable
    total_w = sum(weights.values()) or 1.0
    coverage = den / total_w
    return round((num / den) * (0.6 + 0.4 * coverage), 4)


def qualifies(scores: SignalScores, combined: float, threshold: float, elevated: float, min_signals: int) -> tuple[bool, str]:
    m = scores.as_map()
    high = [k for k, v in m.items() if v is not None and v >= elevated]
    if combined < threshold:
        return False, "combined score below threshold"
    if len(high) < min_signals:
        return False, f"only {len(high)} elevated signal(s)"
    # never clip on chat activity alone: require an audio or visual signal in the footage itself
    if not any(k in high for k in ("audio", "visual")):
        return False, "no audio/visual evidence"
    return True, ",".join(high)
