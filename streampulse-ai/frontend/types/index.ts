export type StreamStatus = "offline" | "upcoming" | "live" | "reconnecting" | "ended" | "error";

export interface Creator {
  id: string;
  name: string;
  youtube_channel_id: string | null;
  profile_image: string | null;
  authorised: boolean;
  authorisation_notes: string | null;
  preferred_language: "en" | "sq";
  created_at: string;
}

export interface CaptureInfo {
  id: string;
  status: string;
  capture_method: string | null;
  recording_path: string | null;
  started_at: string | null;
  ended_at: string | null;
  error_message: string | null;
  health: Record<string, unknown>;
  last_heartbeat_at: string | null;
}

export interface Stream {
  id: string;
  creator_id: string | null;
  creator_name: string | null;
  creator_image: string | null;
  youtube_url: string;
  youtube_video_id: string | null;
  title: string | null;
  thumbnail_url: string | null;
  status: StreamStatus;
  monitoring_enabled: boolean;
  auto_capture: boolean;
  chat_status: string;
  scheduled_start_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  last_checked_at: string | null;
  last_error: string | null;
  current_viral_score: number;
  created_at: string;
  capture: CaptureInfo | null;
  recording_seconds: number;
  chat_messages_last_minute: number;
}

export interface ActivityWindow {
  start_time: string;
  end_time: string;
  chat_score: number | null;
  audio_score: number | null;
  visual_score: number | null;
  emoji_score: number | null;
  unique_user_score: number | null;
  combined_score: number | null;
  details: Record<string, unknown>;
}

export interface ChatEvent {
  id: number;
  author_id: string | null;
  message: string | null;
  event_timestamp: string | null;
  metadata: { author_name?: string; emoji?: number; super_chat?: string | null } | null;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
  words?: { start: number; end: number; word: string }[];
}

export interface ClipContent {
  title?: string;
  youtube_title?: string;
  tiktok_description?: string;
  instagram_caption?: string;
  hook?: string;
  hashtags?: string[];
  language?: string;
}

export interface Publication {
  job_id: string;
  platform: string;
  status: string;
  post_url: string | null;
  error: string | null;
}

export interface Clip {
  id: string;
  stream_id: string;
  creator_name: string | null;
  file_url: string | null;
  thumbnail_url: string | null;
  subtitles_url: string | null;
  start_time: string | null;
  duration: number | null;
  title: string | null;
  description: string | null;
  language: string | null;
  viral_score: number | null;
  moment_type: string | null;
  transcript: { language?: string; segments: TranscriptSegment[] } | null;
  content: ClipContent | null;
  subtitle_style: string;
  status: string;
  error_message: string | null;
  created_at: string;
  publications: Publication[];
}

export interface PublishJob {
  id: string;
  clip_id: string;
  clip_title: string | null;
  platform: "youtube" | "tiktok" | "instagram";
  status: string;
  scheduled_at: string | null;
  attempts: number;
  platform_post_id: string | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  post_url: string | null;
}

export interface SocialAccount {
  id: string;
  platform: string;
  account_name: string | null;
  account_id: string | null;
  token_expires_at: string | null;
  connected: boolean;
  enabled: boolean;
}

export interface StorageUsage {
  disk_total: number;
  disk_used: number;
  disk_free: number;
  storage_used: number;
  max_storage_bytes: number;
  storage_percent: number;
  disk_percent: number;
  low_disk: boolean;
  over_allocation: boolean;
  areas: Record<string, number>;
}

export interface Analytics {
  overview: {
    active_streams: number;
    total_streams: number;
    active_captures: number;
    clips_today: number;
    clips_awaiting_approval: number;
    published_clips: number;
    failed_jobs: number;
    candidates_today: number;
  };
  series: { date: string; clips: number; published: number }[];
  by_moment_type: { moment_type: string; count: number }[];
  by_platform: { platform: string; status: string; count: number }[];
  by_creator: { creator: string; clips: number }[];
  candidates: Record<string, number>;
  average_viral_score: number | null;
  storage: StorageUsage;
}

export interface Notification {
  id: number;
  level: "info" | "warning" | "error";
  category: string;
  message: string;
  read: boolean;
  created_at: string;
}

// Settings mirror backend/app/services/app_settings.py
export interface AppSettings {
  detection: {
    weights: { chat: number; audio: number; visual: number; emoji: number; unique_users: number };
    window_seconds: number;
    baseline_minutes: number;
    candidate_threshold: number;
    min_signals_above: number;
    signal_elevated_threshold: number;
    min_viral_score: number;
    cooldown_seconds: number;
    require_ai_evaluation: boolean;
    send_keyframes_to_ai: boolean;
  };
  clips: {
    pre_event_seconds: number;
    post_event_seconds: number;
    min_length_seconds: number;
    max_length_seconds: number;
    merge_gap_seconds: number;
    sentence_snap_max_seconds: number;
    vertical_mode: "blur_background" | "center_crop" | "fit_black";
    target_fps: "auto" | "30" | "60";
    loudness_target_lufs: number;
  };
  subtitles: {
    enabled: boolean;
    style: "clean" | "highlight" | "animated" | "minimal";
    font: string;
    font_size: number;
    primary_color: string;
    highlight_color: string;
    outline_color: string;
    position: "bottom" | "middle" | "top";
    margin_v: number;
    max_words_per_line: number;
    uppercase: boolean;
  };
  capture: {
    segment_seconds: number;
    video_backend: "gfxcapture" | "gdigrab";
    framerate: number;
    output_width: number;
    output_height: number;
    audio_mode: "virtual_cable" | "dshow_device";
    video_encoder: string;
    max_concurrent_captures: number;
    black_screen_alert_seconds: number;
    frozen_frame_alert_seconds: number;
    min_free_disk_gb: number;
  };
  storage: {
    max_storage_gb: number;
    recording_retention_hours: number;
    temporary_retention_hours: number;
    low_disk_alert_percent: number;
    keep_footage_used_by_clips: boolean;
  };
  publishing: {
    auto_publish: boolean;
    platforms: Record<string, boolean>;
    hashtag_template: string;
    description_template: string;
    default_delay_minutes: number;
    max_attempts: number;
    youtube_privacy: "public" | "unlisted" | "private";
    tiktok_privacy: string;
  };
  ai: {
    provider: "gemini" | "none";
    model: string;
    api_key_configured: boolean;
    default_language: "en" | "sq";
    generate_content: boolean;
  };
  environment: Record<string, string | boolean>;
}
