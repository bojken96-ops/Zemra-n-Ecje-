"""Candidate evaluation and clip generation orchestration (DB + processing)."""
from __future__ import annotations

import logging
import shutil
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import CaptureSession, ChatEvent, Clip, ClipCandidate, Creator, RecordingSegment, Stream
from app.services import app_settings as settings_svc
from app.services import audit as audit_svc
from app.services import events
from app.services.ai.providers import AIError, ContentContext, HeuristicProvider, MomentContext, get_provider
from app.services.transcription import whisper
from app.utils import storage
from app.utils.time import utcnow
from processing import ffmpeg
from processing import subtitle_generator as subs
from processing import video_processor as vp
from processing.clip_generator import render_vertical
from processing.thumbnail_generator import generate_thumbnail

log = logging.getLogger(__name__)


class NotReady(RuntimeError):
    """Footage for the requested range is not recorded yet; retry later."""


def _segments(db: Session, stream_id, start, end) -> list[vp.SegmentRef]:
    rows = (db.query(RecordingSegment)
            .filter(RecordingSegment.stream_id == stream_id, RecordingSegment.deleted.is_(False),
                    RecordingSegment.end_time > start, RecordingSegment.start_time < end)
            .order_by(RecordingSegment.start_time).all())
    return [vp.SegmentRef(storage.resolve(r.file_path), r.start_time, r.end_time) for r in rows]


def _footage_ready(db: Session, stream_id, end) -> bool:
    latest = (db.query(RecordingSegment.end_time).filter(RecordingSegment.stream_id == stream_id)
              .order_by(RecordingSegment.end_time.desc()).first())
    if latest and latest[0] >= end:
        return True
    # capture no longer running => use whatever exists
    active = (db.query(CaptureSession).filter(CaptureSession.stream_id == stream_id,
                                               CaptureSession.status.in_(("starting", "recording", "reconnecting")))
              .first())
    return active is None


def _language(db: Session, stream: Stream, cfg) -> str:
    creator = db.get(Creator, stream.creator_id) if stream.creator_id else None
    return (creator.preferred_language if creator else None) or cfg.ai.default_language


def _transcribe_safe(path: Path, language: str | None) -> dict | None:
    """Transcribe with automatic language detection (creators mix Albanian and English).

    ``language`` is the creator's preference and is only used when it is set to a forced value
    of the form ``force:<code>``; normally detection is automatic.
    """
    forced = language.split(":", 1)[1] if language and language.startswith("force:") else None
    try:
        return whisper.transcribe(path, language=forced)
    except whisper.TranscriptionUnavailable as exc:
        log.warning("transcription unavailable", extra={"error": str(exc)})
        return None


def evaluate_candidate(db: Session, candidate_id) -> str:
    cand = db.get(ClipCandidate, candidate_id)
    if cand is None or cand.status not in ("pending", "evaluating"):
        return "skipped"
    cfg = settings_svc.load_settings(db)
    stream = db.get(Stream, cand.stream_id)
    pre, post = cfg.clips.pre_event_seconds, max(cfg.clips.post_event_seconds, cand.end_offset or 0)
    start, end = cand.event_time - timedelta(seconds=pre), cand.event_time + timedelta(seconds=post)
    if not _footage_ready(db, stream.id, end):
        raise NotReady("waiting for post-event footage")
    cand.status = "evaluating"
    db.commit()

    work = storage.area("temporary") / f"cand_{cand.id}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        excerpt = work / "excerpt.mp4"
        actual_start, _ = vp.extract_excerpt(_segments(db, stream.id, start, end), start, end, excerpt)
        offset0 = (actual_start - cand.event_time).total_seconds()
        transcript = _transcribe_safe(excerpt, None)
        chat = (db.query(ChatEvent.message).filter(ChatEvent.stream_id == stream.id,
                                                   ChatEvent.event_timestamp >= cand.event_time - timedelta(seconds=20),
                                                   ChatEvent.event_timestamp < cand.event_time + timedelta(seconds=40))
                .limit(80).all())
        creator = db.get(Creator, stream.creator_id) if stream.creator_id else None
        ctx = MomentContext(
            creator_name=creator.name if creator else "creator", stream_title=stream.title or "",
            transcript=subs.transcript_text(transcript, with_times=True, offset=offset0),
            chat_sample=[c[0] for c in chat if c[0]], signals=cand.signals or {},
            pre_seconds=pre, post_seconds=post, language=_language(db, stream, cfg),
            keyframes_jpeg=vp.keyframes(excerpt) if cfg.detection.send_keyframes_to_ai else [],
        )
        provider = get_provider(cfg, settings_svc.gemini_api_key(cfg))
        if provider is None:
            if cfg.detection.require_ai_evaluation:
                cand.status = "failed"
                cand.ai_analysis = {"error": "AI evaluation required but no AI provider/API key is configured"}
                audit_svc.notify(db, "ai", "Moment found but AI evaluation is not configured (Settings → AI).",
                                 level="warning", candidate_id=str(cand.id))
                db.commit()
                return "failed"
            provider = HeuristicProvider()
        try:
            ev = provider.evaluate_moment(ctx)
        except AIError as exc:
            cand.status = "failed"
            cand.ai_analysis = {"error": str(exc)}
            audit_svc.notify(db, "ai", f"AI evaluation failed: {exc}", level="error", candidate_id=str(cand.id))
            db.commit()
            return "failed"
        cand.ai_analysis = ev.model_dump()
        cand.moment_type = ev.moment_type
        cand.viral_score = float(ev.viral_score)
        cand.start_offset, cand.end_offset = ev.start_offset, ev.end_offset
        accepted = ev.interesting and ev.viral_score >= cfg.detection.min_viral_score
        cand.status = "accepted" if accepted else "rejected"
        audit_svc.audit(db, "candidate.evaluated", candidate_id=str(cand.id), accepted=accepted, score=ev.viral_score)
        db.commit()
        events.publish("candidate.evaluated", {"id": str(cand.id), "status": cand.status, "score": ev.viral_score})
        if accepted:
            # cache the transcript of the excerpt for the clip step
            (work / "transcript_offset.txt").write_text(str(offset0))
            if transcript is not None:
                import json

                (work / "transcript.json").write_text(json.dumps(transcript))
        else:
            shutil.rmtree(work, ignore_errors=True)
        return cand.status
    except vp.FootageUnavailable as exc:
        cand.status = "failed"
        cand.ai_analysis = {**(cand.ai_analysis or {}), "error": str(exc)}
        db.commit()
        shutil.rmtree(work, ignore_errors=True)
        return "failed"


def _is_duplicate(db: Session, stream_id, start, end) -> Clip | None:
    """A clip overlapping >50% of this range already exists."""
    for clip in (db.query(Clip).filter(Clip.stream_id == stream_id, Clip.start_time < end, Clip.end_time > start,
                                       Clip.status != "failed").all()):
        overlap = (min(end, clip.end_time) - max(start, clip.start_time)).total_seconds()
        if overlap > 0.5 * min((end - start).total_seconds(), (clip.end_time - clip.start_time).total_seconds()):
            return clip
    return None


def create_clip_from_candidate(db: Session, candidate_id) -> Clip | None:
    cand = db.get(ClipCandidate, candidate_id)
    if cand is None or cand.status != "accepted":
        return None
    cfg = settings_svc.load_settings(db)
    snap = cfg.clips.sentence_snap_max_seconds
    start = cand.event_time + timedelta(seconds=(cand.start_offset or -cfg.clips.pre_event_seconds) - snap)
    end = cand.event_time + timedelta(seconds=(cand.end_offset or cfg.clips.post_event_seconds) + snap)
    dup = _is_duplicate(db, cand.stream_id, start + timedelta(seconds=snap), end - timedelta(seconds=snap))
    if dup:
        cand.status = "merged"
        cand.ai_analysis = {**(cand.ai_analysis or {}), "duplicate_of": str(dup.id)}
        db.commit()
        return None
    ai = cand.ai_analysis or {}
    clip = Clip(candidate_id=cand.id, stream_id=cand.stream_id, status="processing", viral_score=cand.viral_score,
                moment_type=cand.moment_type, title=ai.get("suggested_title"),
                subtitle_style=cfg.subtitles.style)
    db.add(clip)
    cand.status = "clipped"
    db.commit()
    events.publish("clip.updated", {"id": str(clip.id), "status": clip.status})
    try:
        build_clip(db, clip, start, end, cand.event_time)
    except Exception as exc:  # record the failure on the clip; worker logs the traceback
        clip.status = "failed"
        clip.error_message = str(exc)[:2000]
        audit_svc.notify(db, "clip", f"Clip generation failed: {exc}", level="error", clip_id=str(clip.id))
        db.commit()
        events.publish("clip.updated", {"id": str(clip.id), "status": clip.status})
        raise
    return clip


def build_clip(db: Session, clip: Clip, start, end, event_time) -> Clip:
    cfg = settings_svc.load_settings(db)
    stream = db.get(Stream, clip.stream_id)
    clip_dir = storage.area("clips") / str(clip.id)
    clip_dir.mkdir(parents=True, exist_ok=True)
    work = storage.area("temporary") / f"clip_{clip.id}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        extended = work / "extended.mp4"
        actual_start, ext_dur = vp.extract_excerpt(_segments(db, clip.stream_id, start, end), start, end, extended)
        language = _language(db, stream, cfg)
        transcript = _transcribe_safe(extended, language)
        words = subs.words_from_transcript(transcript) if transcript else []
        snap = cfg.clips.sentence_snap_max_seconds
        nominal_s = max(0.0, (start - actual_start).total_seconds() + snap)
        nominal_e = min(ext_dur, (end - actual_start).total_seconds() - snap)
        s, e = subs.snap_boundaries(nominal_s, nominal_e, words, snap, cfg.clips.min_length_seconds,
                                    cfg.clips.max_length_seconds, ext_dur)
        source = clip_dir / "source.mp4"
        vp.trim(extended, s, e, source)
        clip_transcript = subs.shift_transcript(transcript, s, s, e) if transcript else None
        clip.source_path = storage.relative(source)
        clip.transcript = clip_transcript
        clip.language = (transcript or {}).get("language") or language
        clip.start_time = actual_start + timedelta(seconds=s)
        clip.end_time = actual_start + timedelta(seconds=e)
        db.commit()
        render_clip(db, clip, peak_offset=(event_time - clip.start_time).total_seconds())
        generate_content(db, clip)
        _protect_footage(db, clip)
        finalize(db, clip, cfg)
        return clip
    finally:
        shutil.rmtree(work, ignore_errors=True)
        cand_dir = storage.area("temporary") / f"cand_{clip.candidate_id}"
        shutil.rmtree(cand_dir, ignore_errors=True)


def render_clip(db: Session, clip: Clip, peak_offset: float | None = None) -> Clip:
    """(Re-)render the vertical MP4, subtitles and thumbnail from the clip's horizontal source."""
    cfg = settings_svc.load_settings(db)
    source = storage.resolve(clip.source_path)
    clip_dir = source.parent
    ass_path = None
    if cfg.subtitles.enabled and clip.transcript:
        words = subs.words_from_transcript(clip.transcript)
        if words:
            style = {**cfg.subtitles.model_dump(), "style": clip.subtitle_style or cfg.subtitles.style}
            ass_path = clip_dir / "subtitles.ass"
            ass_path.write_text(subs.render_ass(words, style), encoding="utf-8")
            (clip_dir / "subtitles.srt").write_text(subs.to_srt(words), encoding="utf-8")
            sub_copy = storage.area("subtitles") / f"{clip.id}.srt"
            shutil.copyfile(clip_dir / "subtitles.srt", sub_copy)
            clip.subtitles_path = storage.relative(sub_copy)
    tmp_out = clip_dir / "vertical.tmp.mp4"
    info = render_vertical(source, tmp_out, mode=cfg.clips.vertical_mode, fps_setting=cfg.clips.target_fps,
                           ass_path=ass_path, loudness_lufs=cfg.clips.loudness_target_lufs)
    final = clip_dir / "clip.mp4"
    tmp_out.replace(final)
    thumb = storage.area("thumbnails") / f"{clip.id}.jpg"
    peak = peak_offset if peak_offset is not None and 0 <= peak_offset <= info["duration"] else info["duration"] / 2
    generate_thumbnail(final, peak, thumb)
    clip.file_path = storage.relative(final)
    clip.thumbnail_path = storage.relative(thumb)
    clip.duration = round(info["duration"], 2)
    clip.size_bytes = info["size_bytes"] + source.stat().st_size
    db.commit()
    return clip


def generate_content(db: Session, clip: Clip) -> None:
    cfg = settings_svc.load_settings(db)
    if not cfg.ai.generate_content:
        return
    stream = db.get(Stream, clip.stream_id)
    creator = db.get(Creator, stream.creator_id) if stream and stream.creator_id else None
    lang = (creator.preferred_language if creator else cfg.ai.default_language)
    lang = lang if lang in ("en", "sq") else "en"
    provider = get_provider(cfg, settings_svc.gemini_api_key(cfg)) or HeuristicProvider()
    cand = db.get(ClipCandidate, clip.candidate_id) if clip.candidate_id else None
    ctx = ContentContext(creator_name=creator.name if creator else "creator", stream_title=(stream.title if stream else "") or "",
                         transcript=subs.transcript_text(clip.transcript), moment_type=clip.moment_type,
                         reason=(cand.ai_analysis or {}).get("reason") if cand else None, language=lang,
                         hashtag_template=cfg.publishing.hashtag_template)
    try:
        content = provider.generate_content(ctx)
    except AIError as exc:
        audit_svc.notify(db, "ai", f"Caption generation failed: {exc}", level="warning", clip_id=str(clip.id))
        return
    clip.content = {**content.model_dump(), "language": lang, "provider": type(provider).__name__}
    clip.title = content.title
    clip.description = content.tiktok_description
    db.commit()


def _protect_footage(db: Session, clip: Clip) -> None:
    cfg = settings_svc.load_settings(db)
    if not cfg.storage.keep_footage_used_by_clips:
        return
    (db.query(RecordingSegment)
     .filter(RecordingSegment.stream_id == clip.stream_id, RecordingSegment.start_time < clip.end_time,
             RecordingSegment.end_time > clip.start_time)
     .update({RecordingSegment.protected: True}, synchronize_session=False))


def finalize(db: Session, clip: Clip, cfg) -> None:
    clip.status = "ready"
    clip.error_message = None
    audit_svc.audit(db, "clip.ready", clip_id=str(clip.id), duration=clip.duration)
    audit_svc.notify(db, "clip", f"New clip ready: {clip.title or clip.id}", clip_id=str(clip.id))
    db.commit()
    events.publish("clip.updated", {"id": str(clip.id), "status": clip.status})
    if cfg.publishing.auto_publish:
        from app.services.publishing import queue

        clip.status = "approved"
        db.commit()
        queue.create_jobs_for_clip(db, clip, cfg)


def regenerate(db: Session, clip: Clip, subtitle_style: str | None = None, transcript: dict | None = None,
               regenerate_content: bool = False) -> Clip:
    if clip.status in ("publishing",):
        raise ValueError("clip is currently being published")
    if not clip.source_path:
        raise ValueError("clip has no source footage to regenerate from")
    if subtitle_style:
        clip.subtitle_style = subtitle_style
    if transcript is not None:
        clip.transcript = transcript
    clip.status = "processing"
    db.commit()
    events.publish("clip.updated", {"id": str(clip.id), "status": clip.status})
    try:
        render_clip(db, clip)
        if regenerate_content:
            generate_content(db, clip)
        clip.status = "ready"
        db.commit()
    except Exception as exc:
        clip.status = "failed"
        clip.error_message = str(exc)[:2000]
        db.commit()
        raise
    events.publish("clip.updated", {"id": str(clip.id), "status": clip.status})
    return clip


def analyse_segment(db: Session, segment_id) -> RecordingSegment | None:
    """Extract audio/visual features + quality flags from a freshly recorded segment."""
    from processing.media_analysis import analyse_file

    seg = db.get(RecordingSegment, segment_id)
    if seg is None or seg.analysed or seg.deleted:
        return seg
    path = storage.resolve(seg.file_path)
    if not path.exists():
        seg.quality = {"error": "file missing"}
        seg.analysed = True
        db.commit()
        return seg
    try:
        result = analyse_file(path)
    except ffmpeg.FFmpegError as exc:
        seg.quality = {"error": f"unreadable segment: {exc}"[:500]}
        seg.analysed = True
        db.commit()
        return seg
    seg.quality = result
    seg.width, seg.height, seg.fps = result.get("width"), result.get("height"), result.get("fps")
    seg.size_bytes = path.stat().st_size
    seg.analysed = True
    db.commit()
    return seg


def segment_quality_flags(db: Session, sess: CaptureSession, cfg) -> dict:
    """Black-screen / frozen-frame detection over the most recent segments of a capture session."""
    recent = (db.query(RecordingSegment).filter(RecordingSegment.capture_session_id == sess.id,
                                                RecordingSegment.analysed.is_(True))
              .order_by(RecordingSegment.sequence.desc()).limit(12).all())
    black = frozen = 0.0
    for seg in recent:
        v = (seg.quality or {}).get("visual") or {}
        black += len(v.get("black_seconds", []))
        frozen += len(v.get("frozen_seconds", []))
    flags = {"black_seconds_recent": black, "frozen_seconds_recent": frozen,
             "black_alert": black >= cfg.capture.black_screen_alert_seconds,
             "frozen_alert": frozen >= cfg.capture.frozen_frame_alert_seconds, "checked_at": utcnow().isoformat()}
    return flags
