from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth
class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=256)


class AuthState(BaseModel):
    authenticated: bool
    setup_required: bool
    username: str | None = None
    csrf_token: str | None = None


# ---- creators
class CreatorIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    youtube_channel_id: str | None = Field(None, pattern=r"^UC[A-Za-z0-9_-]{22}$")
    profile_image: HttpUrl | None = None
    authorised: bool = False
    authorisation_notes: str | None = Field(None, max_length=4000)
    preferred_language: Literal["en", "sq"] = "en"

    @model_validator(mode="after")
    def _authorisation_documented(self):
        if self.authorised and not (self.authorisation_notes or "").strip():
            raise ValueError("authorisation_notes are required when marking a creator as authorised")
        return self


class CreatorUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    profile_image: HttpUrl | None = None
    authorised: bool | None = None
    authorisation_notes: str | None = Field(None, max_length=4000)
    preferred_language: Literal["en", "sq"] | None = None


class CreatorOut(ORM):
    id: uuid.UUID
    name: str
    youtube_channel_id: str | None
    profile_image: str | None
    authorised: bool
    authorisation_notes: str | None
    preferred_language: str
    created_at: datetime


# ---- streams
class StreamIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    creator_id: uuid.UUID | None = None


class StreamUpdate(BaseModel):
    creator_id: uuid.UUID | None = None
    monitoring_enabled: bool | None = None
    auto_capture: bool | None = None


class CaptureOut(ORM):
    id: uuid.UUID
    status: str
    capture_method: str | None
    recording_path: str | None
    started_at: datetime | None
    ended_at: datetime | None
    error_message: str | None
    health: dict
    last_heartbeat_at: datetime | None


class StreamOut(ORM):
    id: uuid.UUID
    creator_id: uuid.UUID | None
    creator_name: str | None = None
    creator_image: str | None = None
    youtube_url: str
    youtube_video_id: str | None
    youtube_channel_id: str | None
    title: str | None
    thumbnail_url: str | None
    status: str
    monitoring_enabled: bool
    auto_capture: bool
    chat_status: str
    scheduled_start_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    last_checked_at: datetime | None
    last_error: str | None
    current_viral_score: float
    created_at: datetime
    capture: CaptureOut | None = None
    recording_seconds: float = 0
    chat_messages_last_minute: int = 0


class ChatEventOut(ORM):
    id: int
    message_id: str | None
    author_id: str | None
    message: str | None
    event_timestamp: datetime | None
    metadata_: dict | None = Field(None, serialization_alias="metadata")


class ActivityOut(ORM):
    start_time: datetime
    end_time: datetime
    chat_score: float | None
    audio_score: float | None
    visual_score: float | None
    emoji_score: float | None
    unique_user_score: float | None
    combined_score: float | None
    details: dict


# ---- clips
class ClipOut(ORM):
    id: uuid.UUID
    candidate_id: uuid.UUID | None
    stream_id: uuid.UUID
    creator_name: str | None = None
    file_url: str | None = None
    thumbnail_url: str | None = None
    subtitles_url: str | None = None
    start_time: datetime | None
    end_time: datetime | None
    duration: float | None
    title: str | None
    description: str | None
    language: str | None
    viral_score: float | None
    moment_type: str | None
    transcript: dict | None
    content: dict | None
    subtitle_style: str
    status: str
    error_message: str | None
    created_at: datetime
    publications: list[dict] = []


class ClipUpdate(BaseModel):
    title: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=2200)
    content: dict | None = None
    transcript_segments: list[dict] | None = None  # [{start,end,text}] edited subtitle text


class RegenerateIn(BaseModel):
    subtitle_style: Literal["clean", "highlight", "animated", "minimal"] | None = None
    regenerate_content: bool = False


# ---- publishing
class PublishJobIn(BaseModel):
    clip_id: uuid.UUID
    account_ids: list[uuid.UUID] | None = None
    scheduled_at: datetime | None = None
    overrides: dict[str, dict] | None = None


class PublishJobOut(ORM):
    id: uuid.UUID
    clip_id: uuid.UUID
    social_account_id: uuid.UUID
    platform: str
    status: str
    scheduled_at: datetime | None
    attempts: int
    platform_post_id: str | None
    error_message: str | None
    metadata_: dict = Field(serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime | None
    post_url: str | None = None
    clip_title: str | None = None


class AccountOut(ORM):
    id: uuid.UUID
    platform: str
    account_name: str | None
    account_id: str | None
    token_expires_at: datetime | None
    connected: bool
    enabled: bool
    scopes: str | None


# ---- capture agent
class AgentStatusIn(BaseModel):
    status: Literal["starting", "recording", "reconnecting", "stopped", "failed"]
    capture_method: str | None = Field(None, max_length=200)
    health: dict | None = None
    error: str | None = Field(None, max_length=4000)
    recording_path: str | None = Field(None, max_length=500)


class AgentSegmentIn(BaseModel):
    sequence: int = Field(ge=0)
    file_path: str = Field(max_length=500)  # relative to storage root
    start_time: datetime
    end_time: datetime
    size_bytes: int = Field(ge=0)
    width: int | None = None
    height: int | None = None
    fps: float | None = None
