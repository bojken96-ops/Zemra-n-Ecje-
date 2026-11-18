"""Storage management: usage accounting, retention cleanup, low-disk alerts.

Safety rules:
- published clips and their files are never deleted automatically;
- clips that are processing/publishing are never touched;
- recording segments marked ``protected`` (footage used by clips) are kept;
- segments still needed by pending candidates or active captures are kept.
"""
from __future__ import annotations

import logging
import shutil
import time
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import CaptureSession, Clip, ClipCandidate, PublishingJob, RecordingSegment
from app.services import app_settings as settings_svc
from app.services import audit as audit_svc
from app.utils import storage
from app.utils.time import utcnow

log = logging.getLogger(__name__)
BUSY_CLIP_STATUSES = ("processing", "publishing")


class ClipBusy(RuntimeError):
    pass


def usage(db: Session) -> dict:
    cfg = settings_svc.load_settings(db)
    u = storage.disk_usage()
    max_bytes = cfg.storage.max_storage_gb * 1024 ** 3
    u["max_storage_bytes"] = int(max_bytes)
    u["storage_percent"] = round(100 * u["storage_used"] / max_bytes, 2) if max_bytes else 0
    u["disk_percent"] = round(100 * u["disk_used"] / u["disk_total"], 2) if u["disk_total"] else 0
    u["low_disk"] = u["disk_percent"] >= cfg.storage.low_disk_alert_percent or \
        u["disk_free"] < cfg.capture.min_free_disk_gb * 1024 ** 3
    u["over_allocation"] = u["storage_used"] >= max_bytes
    return u


def can_delete_clip(db: Session, clip: Clip) -> None:
    if clip.status in BUSY_CLIP_STATUSES:
        raise ClipBusy(f"clip is {clip.status}; wait until it finishes")
    active = db.query(PublishingJob).filter(PublishingJob.clip_id == clip.id,
                                            PublishingJob.status.in_(("uploading", "processing"))).count()
    if active:
        raise ClipBusy("clip has publishing jobs in progress")


def delete_clip_files(clip: Clip) -> None:
    for rel in (clip.file_path, clip.thumbnail_path, clip.subtitles_path):
        if rel:
            storage.resolve(rel).unlink(missing_ok=True)
    if clip.file_path:
        shutil.rmtree(storage.resolve(clip.file_path).parent, ignore_errors=True)


def cleanup(db: Session) -> dict:
    cfg = settings_svc.load_settings(db)
    now = utcnow()
    report = {"temporary_removed": 0, "segments_removed": 0, "bytes_freed": 0}

    # 1) temporary files older than retention (never ones belonging to a processing clip)
    busy = {f"clip_{c.id}" for c in db.query(Clip.id).filter(Clip.status == "processing").all()}
    busy |= {f"cand_{c.id}" for c in db.query(ClipCandidate.id).filter(
        ClipCandidate.status.in_(("pending", "evaluating", "accepted"))).all()}
    tmp_cutoff = time.time() - cfg.storage.temporary_retention_hours * 3600
    for entry in storage.area("temporary").iterdir():
        if entry.name in busy or entry.name.startswith("."):
            continue
        if entry.stat().st_mtime < tmp_cutoff:
            size = _size(entry)
            shutil.rmtree(entry, ignore_errors=True) if entry.is_dir() else entry.unlink(missing_ok=True)
            report["temporary_removed"] += 1
            report["bytes_freed"] += size

    # 2) expired recording segments (unprotected, not needed by open candidates or active captures)
    cutoff = now - timedelta(hours=cfg.storage.recording_retention_hours)
    active_sessions = [s.id for s in db.query(CaptureSession.id).filter(
        CaptureSession.status.in_(("starting", "recording", "reconnecting", "stopping"))).all()]
    open_cands = db.query(ClipCandidate).filter(ClipCandidate.status.in_(("pending", "evaluating", "accepted"))).all()
    q = db.query(RecordingSegment).filter(RecordingSegment.deleted.is_(False), RecordingSegment.protected.is_(False),
                                          RecordingSegment.end_time < cutoff)
    if active_sessions:
        q = q.filter(RecordingSegment.capture_session_id.notin_(active_sessions))
    for seg in q.all():
        if any(c.stream_id == seg.stream_id and c.event_time and
               c.event_time - timedelta(seconds=300) < seg.end_time and c.event_time + timedelta(seconds=300) > seg.start_time
               for c in open_cands):
            continue
        path = storage.resolve(seg.file_path)
        if path.exists():
            report["bytes_freed"] += path.stat().st_size
            path.unlink()
        seg.deleted = True
        report["segments_removed"] += 1
    db.commit()

    u = usage(db)
    if u["low_disk"]:
        audit_svc.notify(db, "storage", f"Low disk space: {u['disk_free'] / 1024 ** 3:.1f} GB free ({u['disk_percent']}% used)",
                         level="warning")
    if u["over_allocation"]:
        audit_svc.notify(db, "storage", "Storage allocation exceeded: reduce retention or delete old clips. "
                         "Published clips and protected footage are never deleted automatically.", level="error")
    if report["segments_removed"] or report["temporary_removed"]:
        audit_svc.audit(db, "storage.cleanup", **report)
    db.commit()
    report["usage"] = u
    return report


def _size(p) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
