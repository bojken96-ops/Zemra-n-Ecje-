"""Runtime-editable application settings stored in ``application_settings``.

Each top-level section is a row keyed by its name. Defaults live in code so a fresh
install works; the dashboard Settings page edits them through PUT /api/settings.
Secrets (AI key) are encrypted before storage and never returned in clear text.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.models import ApplicationSetting
from app.utils import crypto


class DetectionWeights(BaseModel):
    chat: float = 0.30
    audio: float = 0.25
    visual: float = 0.20
    emoji: float = 0.15
    unique_users: float = 0.10

    @model_validator(mode="after")
    def _sum(self):
        total = self.chat + self.audio + self.visual + self.emoji + self.unique_users
        if total <= 0:
            raise ValueError("detection weights must sum to a positive value")
        return self


class DetectionSettings(BaseModel):
    weights: DetectionWeights = DetectionWeights()
    window_seconds: int = Field(10, ge=5, le=60)
    baseline_minutes: int = Field(10, ge=2, le=60)
    candidate_threshold: float = Field(0.62, ge=0, le=1)
    min_signals_above: int = Field(2, ge=1, le=5)  # number of signals that must individually be elevated
    signal_elevated_threshold: float = Field(0.5, ge=0, le=1)
    min_viral_score: int = Field(70, ge=0, le=100)  # AI evaluation threshold for creating a clip
    cooldown_seconds: int = Field(90, ge=0, le=3600)
    require_ai_evaluation: bool = True
    send_keyframes_to_ai: bool = True


class ClipSettings(BaseModel):
    pre_event_seconds: float = Field(45, ge=0, le=300)
    post_event_seconds: float = Field(35, ge=0, le=300)
    min_length_seconds: float = Field(15, ge=3, le=600)
    max_length_seconds: float = Field(120, ge=5, le=600)
    merge_gap_seconds: float = Field(20, ge=0, le=300)
    sentence_snap_max_seconds: float = Field(6, ge=0, le=30)
    vertical_mode: Literal["blur_background", "center_crop", "fit_black"] = "blur_background"
    target_fps: Literal["auto", "30", "60"] = "auto"
    loudness_target_lufs: float = Field(-14, ge=-30, le=-5)


class SubtitleSettings(BaseModel):
    enabled: bool = True
    style: Literal["clean", "highlight", "animated", "minimal"] = "clean"
    font: str = "Arial"
    font_size: int = Field(64, ge=20, le=160)
    primary_color: str = "#FFFFFF"
    highlight_color: str = "#FFD400"
    outline_color: str = "#000000"
    position: Literal["bottom", "middle", "top"] = "bottom"
    margin_v: int = Field(320, ge=0, le=1200)
    max_words_per_line: int = Field(5, ge=1, le=12)
    uppercase: bool = False

    @field_validator("primary_color", "highlight_color", "outline_color")
    @classmethod
    def _hex(cls, v: str) -> str:
        v = v.strip()
        if len(v) != 7 or not v.startswith("#"):
            raise ValueError("colour must be #RRGGBB")
        int(v[1:], 16)
        return v.upper()


class CaptureSettings(BaseModel):
    segment_seconds: int = Field(10, ge=2, le=120)
    video_backend: Literal["gfxcapture", "gdigrab"] = "gfxcapture"
    framerate: int = Field(30, ge=10, le=60)
    output_width: int = Field(1920, ge=640, le=3840)
    output_height: int = Field(1080, ge=360, le=2160)
    audio_mode: Literal["virtual_cable", "dshow_device"] = "virtual_cable"
    video_encoder: Literal["auto", "libx264", "h264_nvenc", "h264_qsv", "h264_amf"] = "auto"
    max_concurrent_captures: int = Field(2, ge=1, le=8)
    black_screen_alert_seconds: int = Field(20, ge=5, le=600)
    frozen_frame_alert_seconds: int = Field(20, ge=5, le=600)
    min_free_disk_gb: float = Field(20, ge=1, le=10000)


class StorageSettings(BaseModel):
    max_storage_gb: float = Field(500, ge=1)
    recording_retention_hours: int = Field(72, ge=1)
    temporary_retention_hours: int = Field(6, ge=1)
    low_disk_alert_percent: float = Field(90, ge=50, le=99)
    keep_footage_used_by_clips: bool = True


class PublishingSettings(BaseModel):
    auto_publish: bool = False
    platforms: dict[str, bool] = {"youtube": True, "tiktok": True, "instagram": True}
    hashtag_template: str = "#shorts #livestream"
    description_template: str = "{caption}\n\n{hashtags}"
    default_delay_minutes: int = Field(0, ge=0, le=60 * 24 * 14)
    max_attempts: int = Field(5, ge=1, le=20)
    youtube_privacy: Literal["public", "unlisted", "private"] = "private"
    tiktok_privacy: Literal["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"] = "SELF_ONLY"


class AISettings(BaseModel):
    provider: Literal["gemini", "none"] = "gemini"
    model: str = "gemini-2.5-flash"
    api_key_encrypted: str | None = None  # write-only from the API
    default_language: Literal["en", "sq"] = "en"
    generate_content: bool = True


SECTIONS: dict[str, type[BaseModel]] = {
    "detection": DetectionSettings,
    "clips": ClipSettings,
    "subtitles": SubtitleSettings,
    "capture": CaptureSettings,
    "storage": StorageSettings,
    "publishing": PublishingSettings,
    "ai": AISettings,
}


class AppSettings(BaseModel):
    detection: DetectionSettings = DetectionSettings()
    clips: ClipSettings = ClipSettings()
    subtitles: SubtitleSettings = SubtitleSettings()
    capture: CaptureSettings = CaptureSettings()
    storage: StorageSettings = StorageSettings()
    publishing: PublishingSettings = PublishingSettings()
    ai: AISettings = AISettings()


def load_settings(db: Session) -> AppSettings:
    rows = {r.key: r.value for r in db.query(ApplicationSetting).filter(ApplicationSetting.key.in_(SECTIONS)).all()}
    data = {key: rows.get(key, {}) for key in SECTIONS}
    return AppSettings.model_validate(data)


def public_settings(settings: AppSettings) -> dict:
    data = settings.model_dump()
    ai = data["ai"]
    ai["api_key_configured"] = bool(ai.pop("api_key_encrypted"))
    return data


def update_settings(db: Session, patch: dict) -> AppSettings:
    """Deep-merge ``patch`` onto current settings, validate, persist."""
    current = load_settings(db).model_dump()
    for section, values in patch.items():
        if section not in SECTIONS:
            raise ValueError(f"unknown settings section: {section}")
        if not isinstance(values, dict):
            raise ValueError(f"settings section {section} must be an object")
        values = dict(values)
        if section == "ai":
            values.pop("api_key_encrypted", None)
            values.pop("api_key_configured", None)
            if "api_key" in values:
                key = values.pop("api_key")
                current["ai"]["api_key_encrypted"] = crypto.encrypt(key) if key else None
        _deep_merge(current[section], values)
    validated = AppSettings.model_validate(current)
    for section in patch:
        value = getattr(validated, section).model_dump()
        row = db.get(ApplicationSetting, section)
        if row is None:
            db.add(ApplicationSetting(key=section, value=value))
        else:
            row.value = value
    db.commit()
    return validated


def _deep_merge(target: dict, patch: dict) -> None:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            _deep_merge(target[k], v)
        else:
            target[k] = v


def gemini_api_key(settings: AppSettings) -> str | None:
    from app.config import get_settings

    if settings.ai.api_key_encrypted:
        return crypto.decrypt(settings.ai.api_key_encrypted)
    return get_settings().gemini_api_key or None
