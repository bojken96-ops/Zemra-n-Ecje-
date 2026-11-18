"""Builds activity windows from chat + analysed recording segments and raises clip candidates."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import ActivityWindow, ChatEvent, ClipCandidate, RecordingSegment, Stream
from app.services import events
from app.services.app_settings import AppSettings
from app.services.chat.analytics import ChatMessage, score_chat, window_features
from app.services.detection.scoring import (
    SignalScores,
    audio_window_score,
    combine,
    qualifies,
    visual_window_score,
)

log = logging.getLogger(__name__)
CHAT_REACTION_DELAY = 4.0  # seconds viewers typically need to react in chat after seeing an event


def align(ts: datetime, window: int) -> datetime:
    epoch = ts.timestamp()
    return datetime.fromtimestamp(epoch - (epoch % window), tz=timezone.utc)


def _chat_messages(db: Session, stream_id, start: datetime, end: datetime) -> list[ChatMessage]:
    rows = (db.query(ChatEvent.author_id, ChatEvent.message, ChatEvent.event_timestamp)
            .filter(ChatEvent.stream_id == stream_id, ChatEvent.event_timestamp >= start,
                    ChatEvent.event_timestamp < end).all())
    return [ChatMessage(a, m or "", t.timestamp()) for a, m, t in rows if t is not None]


def _per_second(db: Session, stream_id, start: datetime, end: datetime) -> dict:
    """Collect per-second audio/visual features for [start, end) from analysed segments."""
    segs = (db.query(RecordingSegment)
            .filter(RecordingSegment.stream_id == stream_id, RecordingSegment.analysed.is_(True),
                    RecordingSegment.deleted.is_(False),
                    RecordingSegment.start_time < end, RecordingSegment.end_time > start)
            .order_by(RecordingSegment.start_time).all())
    out = {"rms_db": [], "centroid_hz": [], "flux": [], "laughter": [], "motion": [], "cuts": 0, "seconds": 0}
    for seg in segs:
        q = seg.quality or {}
        audio, visual = q.get("audio") or {}, q.get("visual") or {}
        n = max(len(audio.get("rms_db", [])), len(visual.get("motion", [])))
        for i in range(n):
            t = seg.start_time + timedelta(seconds=i)
            if not (start <= t < end):
                continue
            out["seconds"] += 1
            for key in ("rms_db", "centroid_hz", "flux", "laughter"):
                if i < len(audio.get(key, [])):
                    out[key].append(audio[key][i])
            if i < len(visual.get("motion", [])):
                out["motion"].append(visual["motion"][i])
            if i in visual.get("scene_cuts", []):
                out["cuts"] += 1
    return out


def score_window(db: Session, stream: Stream, window_start: datetime, cfg: AppSettings) -> ActivityWindow:
    det = cfg.detection
    ws = det.window_seconds
    window_end = window_start + timedelta(seconds=ws)
    delay = timedelta(seconds=CHAT_REACTION_DELAY)

    # chat: current window shifted by reaction delay, baseline = previous N minutes bucketed by window
    base_start = window_start - timedelta(minutes=det.baseline_minutes)
    msgs = _chat_messages(db, stream.id, base_start + delay, window_end + delay)
    buckets: dict[int, list[ChatMessage]] = {}
    for m in msgs:
        idx = int((m.ts - (base_start + delay).timestamp()) // ws)
        buckets.setdefault(idx, []).append(m)
    n_base = int((window_start - base_start).total_seconds() // ws)
    baseline = [window_features(buckets.get(i, []), ws) for i in range(n_base)]
    current = window_features(buckets.get(n_base, []), ws)
    has_chat = stream.chat_status == "active" or current.message_count > 0
    chat_scores = score_chat(current, baseline) if has_chat else None

    # audio / visual
    prev = (db.query(ActivityWindow).filter(ActivityWindow.stream_id == stream.id,
                                             ActivityWindow.start_time >= base_start,
                                             ActivityWindow.start_time < window_start).all())
    b_rms = [w.details["audio"]["peak_rms_db"] for w in prev if (w.details or {}).get("audio")]
    b_cent = [w.details["audio"]["mean_centroid"] for w in prev if (w.details or {}).get("audio")]
    b_motion = [w.details["visual"]["peak_motion"] for w in prev if (w.details or {}).get("visual")]
    ps = _per_second(db, stream.id, window_start, window_end)
    audio_score = visual_score = None
    details: dict = {"chat": chat_scores.details if chat_scores else None, "coverage_seconds": ps["seconds"]}
    if ps["rms_db"]:
        audio_score, details["audio"] = audio_window_score(ps["rms_db"], ps["centroid_hz"], ps["flux"],
                                                           ps["laughter"], b_rms, b_cent)
    if ps["motion"]:
        visual_score, details["visual"] = visual_window_score(ps["motion"], ps["cuts"], b_motion)

    scores = SignalScores(
        chat=chat_scores.chat if chat_scores else None,
        emoji=chat_scores.emoji if chat_scores else None,
        unique_users=chat_scores.unique_users if chat_scores else None,
        audio=audio_score, visual=visual_score,
    )
    combined = combine(scores, det.weights.model_dump())
    values = dict(stream_id=stream.id, start_time=window_start, end_time=window_end, chat_score=scores.chat,
                  audio_score=scores.audio, visual_score=scores.visual, emoji_score=scores.emoji,
                  unique_user_score=scores.unique_users, combined_score=combined, details=details)
    stmt = insert(ActivityWindow.__table__).values(**values)
    stmt = stmt.on_conflict_do_update(constraint="uq_activity_stream_start",
                                      set_={k: stmt.excluded[k] for k in values if k not in ("stream_id", "start_time")})
    db.execute(stmt)
    window = (db.query(ActivityWindow)
              .filter(ActivityWindow.stream_id == stream.id, ActivityWindow.start_time == window_start).one())
    db.refresh(window)
    stream.current_viral_score = round(combined * 100, 1)
    events.publish("activity", {"stream_id": str(stream.id), "start_time": window_start.isoformat(),
                                "combined": combined, **{k: v for k, v in scores.as_map().items()}})
    maybe_raise_candidate(db, stream, window, scores, combined, cfg)
    return window


def maybe_raise_candidate(db: Session, stream: Stream, window: ActivityWindow, scores: SignalScores,
                          combined: float, cfg: AppSettings) -> ClipCandidate | None:
    det, clips = cfg.detection, cfg.clips
    ok, reason = qualifies(scores, combined, det.candidate_threshold, det.signal_elevated_threshold,
                           det.min_signals_above)
    if not ok:
        return None
    event_time = window.start_time + (window.end_time - window.start_time) / 2
    recent = (db.query(ClipCandidate)
              .filter(ClipCandidate.stream_id == stream.id,
                      ClipCandidate.event_time >= event_time - timedelta(seconds=max(det.cooldown_seconds,
                                                                                      clips.merge_gap_seconds)))
              .order_by(ClipCandidate.event_time.desc()).first())
    signals = {**scores.as_map(), "combined": combined, "elevated": reason, "window_start": window.start_time.isoformat()}
    if recent is not None:
        gap = (event_time - recent.event_time).total_seconds()
        if recent.status in ("pending",) and gap <= clips.merge_gap_seconds + clips.post_event_seconds:
            # overlapping moment: extend the existing candidate instead of creating a duplicate
            recent.end_offset = max(recent.end_offset or 0, gap + clips.post_event_seconds)
            if combined > (recent.signals or {}).get("combined", 0):
                recent.signals = {**signals, "merged_from": (recent.signals or {}).get("window_start")}
            log.info("merged moment into candidate", extra={"candidate_id": str(recent.id)})
            return recent
        if gap < det.cooldown_seconds:
            return None
    cand = ClipCandidate(stream_id=stream.id, event_time=event_time, start_offset=-clips.pre_event_seconds,
                         end_offset=clips.post_event_seconds, viral_score=round(combined * 100, 1),
                         signals=signals, status="pending")
    db.add(cand)
    db.flush()
    log.info("clip candidate raised", extra={"candidate_id": str(cand.id), "stream_id": str(stream.id),
                                              "combined": combined, "signals": reason})
    events.publish("candidate.created", {"id": str(cand.id), "stream_id": str(stream.id), "score": cand.viral_score})
    return cand


def windows_for_range(start: datetime, end: datetime, window: int) -> list[datetime]:
    out, t = [], align(start, window)
    while t + timedelta(seconds=window) <= end + timedelta(seconds=0.5):
        out.append(t)
        t += timedelta(seconds=window)
    return out
