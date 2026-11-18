"""Initial StreamPulse AI schema.

Revision ID: 0001
Revises:
Create Date: 2026-11-18
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    user_agent TEXT,
    ip_address TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_user_sessions_expires ON user_sessions(expires_at);

CREATE TABLE creators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    youtube_channel_id TEXT UNIQUE,
    profile_image TEXT,
    authorised BOOLEAN NOT NULL DEFAULT FALSE,
    authorisation_notes TEXT,
    preferred_language TEXT NOT NULL DEFAULT 'en',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE streams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID REFERENCES creators(id) ON DELETE SET NULL,
    youtube_url TEXT NOT NULL,
    youtube_video_id TEXT,
    youtube_channel_id TEXT,
    title TEXT,
    thumbnail_url TEXT,
    status TEXT NOT NULL DEFAULT 'offline'
        CHECK (status IN ('offline','upcoming','live','reconnecting','ended','error')),
    monitoring_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    auto_capture BOOLEAN NOT NULL DEFAULT TRUE,
    live_chat_id TEXT,
    chat_status TEXT NOT NULL DEFAULT 'unknown',
    scheduled_start_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    last_error TEXT,
    current_viral_score FLOAT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_streams_status ON streams(status);
CREATE INDEX idx_streams_creator ON streams(creator_id);
-- one active entry per YouTube video (channel-style /live URLs may have NULL video id until resolved)
CREATE UNIQUE INDEX uq_streams_video_id ON streams(youtube_video_id) WHERE youtube_video_id IS NOT NULL;

CREATE TABLE capture_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stream_id UUID NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','starting','recording','reconnecting','stopping','stopped','failed')),
    capture_method TEXT,
    recording_path TEXT,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    error_message TEXT,
    health JSONB NOT NULL DEFAULT '{}'::jsonb,
    stop_requested BOOLEAN NOT NULL DEFAULT FALSE,
    last_heartbeat_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_capture_sessions_stream ON capture_sessions(stream_id, created_at DESC);
CREATE INDEX idx_capture_sessions_status ON capture_sessions(status);
-- at most one non-terminal capture session per stream
CREATE UNIQUE INDEX uq_capture_active_per_stream ON capture_sessions(stream_id)
    WHERE status IN ('pending','starting','recording','reconnecting','stopping');

CREATE TABLE recording_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    capture_session_id UUID NOT NULL REFERENCES capture_sessions(id) ON DELETE CASCADE,
    stream_id UUID NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    width INTEGER,
    height INTEGER,
    fps FLOAT,
    analysed BOOLEAN NOT NULL DEFAULT FALSE,
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    quality JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_segment_session_seq UNIQUE (capture_session_id, sequence),
    CHECK (end_time >= start_time)
);
CREATE INDEX idx_segments_stream_time ON recording_segments(stream_id, start_time, end_time);
CREATE INDEX idx_segments_unanalysed ON recording_segments(analysed) WHERE analysed = FALSE;

CREATE TABLE chat_events (
    id BIGSERIAL PRIMARY KEY,
    stream_id UUID NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
    message_id TEXT,
    author_id TEXT,
    message TEXT,
    event_timestamp TIMESTAMPTZ,
    metadata JSONB,
    CONSTRAINT uq_chat_stream_message UNIQUE (stream_id, message_id)
);
CREATE INDEX idx_chat_stream_timestamp ON chat_events(stream_id, event_timestamp);

CREATE TABLE activity_windows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stream_id UUID NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    chat_score FLOAT,
    audio_score FLOAT,
    visual_score FLOAT,
    emoji_score FLOAT,
    unique_user_score FLOAT,
    combined_score FLOAT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_activity_stream_start UNIQUE (stream_id, start_time)
);
CREATE INDEX idx_activity_stream_time ON activity_windows(stream_id, start_time);

CREATE TABLE clip_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stream_id UUID NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
    event_time TIMESTAMPTZ,
    start_offset FLOAT,
    end_offset FLOAT,
    viral_score FLOAT,
    moment_type TEXT,
    ai_analysis JSONB,
    signals JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','evaluating','accepted','rejected','merged','clipped','failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_candidates_score ON clip_candidates(viral_score);
CREATE INDEX idx_candidates_stream_time ON clip_candidates(stream_id, event_time);
CREATE INDEX idx_candidates_status ON clip_candidates(status);

CREATE TABLE clips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES clip_candidates(id) ON DELETE SET NULL,
    stream_id UUID NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
    file_path TEXT,
    source_path TEXT,
    thumbnail_path TEXT,
    subtitles_path TEXT,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    duration FLOAT,
    title TEXT,
    description TEXT,
    language TEXT,
    viral_score FLOAT,
    moment_type TEXT,
    transcript JSONB,
    content JSONB,
    subtitle_style TEXT NOT NULL DEFAULT 'clean',
    status TEXT NOT NULL DEFAULT 'processing'
        CHECK (status IN ('processing','ready','approved','publishing','published','failed','rejected')),
    error_message TEXT,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_clips_status ON clips(status);
CREATE INDEX idx_clips_stream_created ON clips(stream_id, created_at DESC);
CREATE UNIQUE INDEX uq_clips_candidate ON clips(candidate_id) WHERE candidate_id IS NOT NULL;

CREATE TABLE social_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL CHECK (platform IN ('youtube','tiktok','instagram')),
    account_name TEXT,
    account_id TEXT,
    encrypted_access_token TEXT,
    encrypted_refresh_token TEXT,
    token_expires_at TIMESTAMPTZ,
    scopes TEXT,
    connected BOOLEAN DEFAULT FALSE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_social_platform_account UNIQUE (platform, account_id)
);

CREATE TABLE oauth_states (
    state TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    code_verifier TEXT,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE publishing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clip_id UUID NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    social_account_id UUID NOT NULL REFERENCES social_accounts(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','scheduled','uploading','processing','published','failed','cancelled')),
    scheduled_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    platform_post_id TEXT,
    platform_job_ref TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- duplicate publishing prevention: one job per clip per account
    CONSTRAINT uq_publish_clip_account UNIQUE (clip_id, social_account_id)
);
CREATE INDEX idx_publish_status ON publishing_jobs(status);
CREATE INDEX idx_publish_scheduled ON publishing_jobs(scheduled_at) WHERE status IN ('pending','scheduled');

CREATE TABLE published_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clip_id UUID REFERENCES clips(id) ON DELETE CASCADE,
    publishing_job_id UUID REFERENCES publishing_jobs(id) ON DELETE SET NULL,
    platform TEXT,
    post_id TEXT,
    post_url TEXT,
    published_at TIMESTAMPTZ,
    CONSTRAINT uq_published_platform_post UNIQUE (platform, post_id)
);
CREATE INDEX idx_published_clip ON published_posts(clip_id);

CREATE TABLE application_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    action TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_created ON audit_logs(created_at DESC);

CREATE TABLE notifications (
    id BIGSERIAL PRIMARY KEY,
    level TEXT NOT NULL DEFAULT 'info' CHECK (level IN ('info','warning','error')),
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    details JSONB,
    read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_notifications_unread ON notifications(read, created_at DESC);
"""

DOWNGRADE_SQL = """
DROP TABLE IF EXISTS notifications, audit_logs, application_settings, published_posts, publishing_jobs,
    oauth_states, social_accounts, clips, clip_candidates, activity_windows, chat_events, recording_segments,
    capture_sessions, streams, creators, user_sessions, users CASCADE;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
