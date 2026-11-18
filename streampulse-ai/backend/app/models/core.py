"""ORM models. The schema is created by Alembic migrations (backend/migrations)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_col, uuid_pk


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(Text, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class Creator(Base):
    __tablename__ = "creators"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    youtube_channel_id: Mapped[str | None] = mapped_column(Text, unique=True)
    profile_image: Mapped[str | None] = mapped_column(Text)
    authorised: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    authorisation_notes: Mapped[str | None] = mapped_column(Text)
    preferred_language: Mapped[str] = mapped_column(Text, nullable=False, default="en")
    created_at: Mapped[datetime] = created_at_col()

    streams: Mapped[list[Stream]] = relationship(back_populates="creator")


class Stream(Base):
    __tablename__ = "streams"
    id: Mapped[uuid.UUID] = uuid_pk()
    creator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("creators.id", ondelete="SET NULL"))
    youtube_url: Mapped[str] = mapped_column(Text, nullable=False)
    youtube_video_id: Mapped[str | None] = mapped_column(Text)
    youtube_channel_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    # offline | upcoming | live | reconnecting | ended | error
    status: Mapped[str] = mapped_column(Text, default="offline", nullable=False)
    monitoring_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_capture: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    live_chat_id: Mapped[str | None] = mapped_column(Text)
    chat_status: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)
    scheduled_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    current_viral_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    creator: Mapped[Creator | None] = relationship(back_populates="streams")


class CaptureSession(Base):
    __tablename__ = "capture_sessions"
    id: Mapped[uuid.UUID] = uuid_pk()
    stream_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("streams.id", ondelete="CASCADE"), nullable=False)
    # pending | starting | recording | reconnecting | stopping | stopped | failed
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    capture_method: Mapped[str | None] = mapped_column(Text)
    recording_path: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    health: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    stop_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class RecordingSegment(Base):
    """One finalized file of the segmented recording. Wall-clock aligned."""

    __tablename__ = "recording_segments"
    __table_args__ = (UniqueConstraint("capture_session_id", "sequence", name="uq_segment_session_seq"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    capture_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capture_sessions.id", ondelete="CASCADE"), nullable=False
    )
    stream_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("streams.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)  # relative to storage root
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    analysed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    protected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quality: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class ChatEvent(Base):
    __tablename__ = "chat_events"
    __table_args__ = (UniqueConstraint("stream_id", "message_id", name="uq_chat_stream_message"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stream_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("streams.id", ondelete="CASCADE"), nullable=False)
    message_id: Mapped[str | None] = mapped_column(Text)
    author_id: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    event_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)


class ActivityWindow(Base):
    __tablename__ = "activity_windows"
    __table_args__ = (UniqueConstraint("stream_id", "start_time", name="uq_activity_stream_start"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    stream_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("streams.id", ondelete="CASCADE"), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    chat_score: Mapped[float | None] = mapped_column(Float)
    audio_score: Mapped[float | None] = mapped_column(Float)
    visual_score: Mapped[float | None] = mapped_column(Float)
    emoji_score: Mapped[float | None] = mapped_column(Float)
    unique_user_score: Mapped[float | None] = mapped_column(Float)
    combined_score: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class ClipCandidate(Base):
    __tablename__ = "clip_candidates"
    id: Mapped[uuid.UUID] = uuid_pk()
    stream_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("streams.id", ondelete="CASCADE"), nullable=False)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    start_offset: Mapped[float | None] = mapped_column(Float)
    end_offset: Mapped[float | None] = mapped_column(Float)
    viral_score: Mapped[float | None] = mapped_column(Float)
    moment_type: Mapped[str | None] = mapped_column(Text)
    ai_analysis: Mapped[dict | None] = mapped_column(JSONB)
    signals: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # pending | evaluating | accepted | rejected | merged | clipped | failed
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class Clip(Base):
    __tablename__ = "clips"
    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clip_candidates.id", ondelete="SET NULL"))
    stream_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("streams.id", ondelete="CASCADE"), nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text)
    source_path: Mapped[str | None] = mapped_column(Text)  # horizontal cut (kept for regeneration)
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    subtitles_path: Mapped[str | None] = mapped_column(Text)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration: Mapped[float | None] = mapped_column(Float)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    viral_score: Mapped[float | None] = mapped_column(Float)
    moment_type: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[dict | None] = mapped_column(JSONB)
    content: Mapped[dict | None] = mapped_column(JSONB)  # AI generated titles / captions / hashtags
    subtitle_style: Mapped[str] = mapped_column(Text, default="clean", nullable=False)
    # processing | ready | approved | publishing | published | failed | rejected
    status: Mapped[str] = mapped_column(Text, default="processing", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    __table_args__ = (UniqueConstraint("platform", "account_id", name="uq_social_platform_account"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    account_name: Mapped[str | None] = mapped_column(Text)
    account_id: Mapped[str | None] = mapped_column(Text)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str | None] = mapped_column(Text)
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class OAuthState(Base):
    __tablename__ = "oauth_states"
    state: Mapped[str] = mapped_column(Text, primary_key=True)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    code_verifier: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PublishingJob(Base):
    __tablename__ = "publishing_jobs"
    __table_args__ = (UniqueConstraint("clip_id", "social_account_id", name="uq_publish_clip_account"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    clip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clips.id", ondelete="CASCADE"), nullable=False)
    social_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    # pending | scheduled | uploading | processing | published | failed | cancelled
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    platform_post_id: Mapped[str | None] = mapped_column(Text)
    platform_job_ref: Mapped[str | None] = mapped_column(Text)  # e.g. TikTok publish_id / IG container id
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = created_at_col()


class PublishedPost(Base):
    __tablename__ = "published_posts"
    __table_args__ = (UniqueConstraint("platform", "post_id", name="uq_published_platform_post"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    clip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clips.id", ondelete="CASCADE"))
    publishing_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("publishing_jobs.id", ondelete="SET NULL"))
    platform: Mapped[str | None] = mapped_column(Text)
    post_id: Mapped[str | None] = mapped_column(Text)
    post_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApplicationSetting(Base):
    __tablename__ = "application_settings"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(Text, nullable=False, default="info")  # info | warning | error
    category: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB)
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = created_at_col()
