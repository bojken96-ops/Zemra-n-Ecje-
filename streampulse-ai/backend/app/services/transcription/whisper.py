"""faster-whisper transcription with word timestamps, language detection and GPU/CPU selection."""
from __future__ import annotations

import logging
import threading
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

log = logging.getLogger(__name__)
_lock = threading.Lock()
SUPPORTED_HINTS = {"en", "sq"}


class TranscriptionUnavailable(RuntimeError):
    pass


def _device() -> tuple[str, str]:
    s = get_settings()
    device, compute = s.whisper_device, s.whisper_compute_type
    if device == "auto":
        try:
            import ctranslate2

            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:  # pragma: no cover - depends on host
            device = "cpu"
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"
    return device, compute


@lru_cache(maxsize=1)
def _model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionUnavailable("faster-whisper is not installed in this container") from exc
    device, compute = _device()
    log.info("loading whisper model", extra={"model": get_settings().whisper_model, "device": device, "compute": compute})
    try:
        return WhisperModel(get_settings().whisper_model, device=device, compute_type=compute)
    except Exception as exc:
        raise TranscriptionUnavailable(f"could not load whisper model: {exc}") from exc


def transcribe(path: str | Path, language: str | None = None) -> dict:
    """Return {language, language_probability, segments:[{start,end,text,words:[{start,end,word,probability}]}]}.

    ``language`` None = automatic detection. Albanian ("sq") and English ("en") are supported hints.
    """
    model = _model()
    with _lock:  # one transcription per process at a time (memory bound)
        segments, info = model.transcribe(
            str(path), language=language if language in SUPPORTED_HINTS else None, word_timestamps=True,
            vad_filter=True, beam_size=5, condition_on_previous_text=False,
        )
        out = []
        for seg in segments:
            words = [{"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word,
                      "probability": round(w.probability, 3)} for w in (seg.words or [])]
            out.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip(), "words": words})
    return {"language": info.language, "language_probability": round(info.language_probability, 3), "segments": out}
