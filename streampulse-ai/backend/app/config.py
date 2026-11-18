"""Application configuration.

Every value is read from environment variables (see ``.env.example`` for
documentation of each one). Nothing secret is hardcoded.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- core -------------------------------------------------------------
    environment: str = Field("development", alias="STREAMPULSE_ENV")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    database_url: str = Field(
        "postgresql+psycopg://streampulse:streampulse@localhost:5432/streampulse", alias="DATABASE_URL"
    )
    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")
    storage_root: Path = Field(Path("./storage"), alias="STORAGE_ROOT")
    # Path prefix the Windows capture agent uses for the *same* storage folder.
    # Agent-reported paths are relative to the storage root, so this is informational.
    public_base_url: str = Field("http://localhost:3000", alias="PUBLIC_BASE_URL")
    api_base_url: str = Field("http://localhost:8000", alias="API_BASE_URL")

    # --- security ---------------------------------------------------------
    session_secret: str = Field("", alias="SESSION_SECRET")
    session_ttl_hours: int = Field(24 * 7, alias="SESSION_TTL_HOURS")
    cookie_secure: bool = Field(False, alias="COOKIE_SECURE")
    token_encryption_key: str = Field("", alias="TOKEN_ENCRYPTION_KEY")
    agent_token: str = Field("", alias="CAPTURE_AGENT_TOKEN")
    allowed_origins: str = Field("http://localhost:3000,http://127.0.0.1:3000", alias="ALLOWED_ORIGINS")
    # Comma separated CIDRs allowed to talk to the API at all.
    allowed_client_networks: str = Field(
        "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16", alias="ALLOWED_CLIENT_NETWORKS"
    )
    rate_limit_per_minute: int = Field(600, alias="RATE_LIMIT_PER_MINUTE")
    login_rate_limit_per_minute: int = Field(10, alias="LOGIN_RATE_LIMIT_PER_MINUTE")

    # --- YouTube / Google -------------------------------------------------
    youtube_api_key: str = Field("", alias="YOUTUBE_API_KEY")
    google_client_id: str = Field("", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field("", alias="GOOGLE_CLIENT_SECRET")

    # --- AI ---------------------------------------------------------------
    ai_provider: str = Field("gemini", alias="AI_PROVIDER")
    gemini_api_key: str = Field("", alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-2.5-flash", alias="GEMINI_MODEL")
    whisper_model: str = Field("small", alias="WHISPER_MODEL")
    whisper_device: str = Field("auto", alias="WHISPER_DEVICE")  # auto | cuda | cpu
    whisper_compute_type: str = Field("auto", alias="WHISPER_COMPUTE_TYPE")

    # --- social -------------------------------------------------------------
    tiktok_client_key: str = Field("", alias="TIKTOK_CLIENT_KEY")
    tiktok_client_secret: str = Field("", alias="TIKTOK_CLIENT_SECRET")
    instagram_app_id: str = Field("", alias="INSTAGRAM_APP_ID")
    instagram_app_secret: str = Field("", alias="INSTAGRAM_APP_SECRET")
    oauth_redirect_base: str = Field("http://localhost:8000", alias="OAUTH_REDIRECT_BASE")

    # --- media --------------------------------------------------------------
    ffmpeg_binary: str = Field("ffmpeg", alias="FFMPEG_BINARY")
    ffprobe_binary: str = Field("ffprobe", alias="FFPROBE_BINARY")
    ffmpeg_hwaccel: str = Field("auto", alias="FFMPEG_HWACCEL")  # auto | nvenc | none

    @field_validator("storage_root", mode="before")
    @classmethod
    def _path(cls, v):
        return Path(v)

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def client_networks(self) -> list[str]:
        return [o.strip() for o in self.allowed_client_networks.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
