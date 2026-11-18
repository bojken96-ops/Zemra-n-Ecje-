import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.media_urls import media_url
from app.db import get_db
from app.models import Clip, Creator, PublishedPost, PublishingJob, Stream
from app.schemas.api import ClipOut, ClipUpdate, RegenerateIn
from app.services import app_settings as settings_svc
from app.services import events
from app.services.audit import audit
from app.services.publishing import queue
from app.services.storage.manager import ClipBusy, can_delete_clip, delete_clip_files

router = APIRouter(prefix="/api/clips", tags=["clips"], dependencies=[Depends(current_user)])


def serialize(db: Session, clip: Clip) -> ClipOut:
    out = ClipOut.model_validate(clip)
    out.file_url, out.thumbnail_url, out.subtitles_url = (media_url(clip.file_path), media_url(clip.thumbnail_path),
                                                          media_url(clip.subtitles_path))
    stream = db.get(Stream, clip.stream_id)
    if stream and stream.creator_id:
        creator = db.get(Creator, stream.creator_id)
        out.creator_name = creator.name if creator else None
    posts = {p.publishing_job_id: p for p in db.query(PublishedPost).filter(PublishedPost.clip_id == clip.id).all()}
    out.publications = [{"job_id": str(j.id), "platform": j.platform, "status": j.status,
                         "post_url": posts[j.id].post_url if j.id in posts else None, "error": j.error_message}
                        for j in db.query(PublishingJob).filter(PublishingJob.clip_id == clip.id).all()]
    return out


def _get(db: Session, clip_id: uuid.UUID) -> Clip:
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "clip not found")
    return clip


@router.get("", response_model=list[ClipOut])
def list_(status: str | None = None, stream_id: uuid.UUID | None = None, limit: int = Query(100, ge=1, le=500),
          offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    q = db.query(Clip)
    if status:
        q = q.filter(Clip.status.in_(status.split(",")))
    if stream_id:
        q = q.filter(Clip.stream_id == stream_id)
    return [serialize(db, c) for c in q.order_by(Clip.created_at.desc()).offset(offset).limit(limit).all()]


@router.get("/{clip_id}", response_model=ClipOut)
def get(clip_id: uuid.UUID, db: Session = Depends(get_db)):
    return serialize(db, _get(db, clip_id))


@router.patch("/{clip_id}", response_model=ClipOut)
def update(clip_id: uuid.UUID, body: ClipUpdate, db: Session = Depends(get_db)):
    clip = _get(db, clip_id)
    if clip.status in ("publishing",):
        raise HTTPException(409, "clip is being published")
    rerender = False
    if body.title is not None:
        clip.title = body.title
    if body.description is not None:
        clip.description = body.description
    if body.content is not None:
        clip.content = {**(clip.content or {}), **body.content}
    if body.transcript_segments is not None:
        segs = []
        old = {(round(s["start"], 2), round(s["end"], 2)): s for s in (clip.transcript or {}).get("segments", [])}
        for s in body.transcript_segments:
            start, end, text = float(s["start"]), float(s["end"]), str(s.get("text", "")).strip()[:500]
            prev = old.get((round(start, 2), round(end, 2)))
            if prev and prev.get("text", "").strip() == text:
                segs.append(prev)  # unchanged: keep word timings
            else:
                segs.append({"start": start, "end": end, "text": text, "words": []})
        clip.transcript = {**(clip.transcript or {}), "segments": segs, "edited": True}
        rerender = True
    audit(db, "clip.updated", clip_id=str(clip.id))
    db.commit()
    if rerender:
        from app.workers.tasks import regenerate_clip

        clip.status = "processing"
        db.commit()
        regenerate_clip.delay(str(clip.id))
    return serialize(db, clip)


@router.delete("/{clip_id}", status_code=204)
def delete(clip_id: uuid.UUID, db: Session = Depends(get_db)):
    clip = _get(db, clip_id)
    try:
        can_delete_clip(db, clip)
    except ClipBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    delete_clip_files(clip)
    audit(db, "clip.deleted", clip_id=str(clip.id), title=clip.title, status=clip.status)
    db.delete(clip)
    db.commit()
    events.publish("clip.deleted", {"id": str(clip_id)})


@router.post("/{clip_id}/approve", response_model=ClipOut)
def approve(clip_id: uuid.UUID, publish: bool = True, db: Session = Depends(get_db)):
    clip = _get(db, clip_id)
    if clip.status not in ("ready", "approved", "rejected"):
        raise HTTPException(409, f"clip cannot be approved while {clip.status}")
    clip.status = "approved"
    audit(db, "clip.approved", clip_id=str(clip.id))
    db.commit()
    if publish:
        queue.create_jobs_for_clip(db, clip, settings_svc.load_settings(db))
    events.publish("clip.updated", {"id": str(clip.id), "status": clip.status})
    return serialize(db, clip)


@router.post("/{clip_id}/reject", response_model=ClipOut)
def reject(clip_id: uuid.UUID, db: Session = Depends(get_db)):
    clip = _get(db, clip_id)
    if clip.status not in ("ready", "approved"):
        raise HTTPException(409, f"clip cannot be rejected while {clip.status}")
    clip.status = "rejected"
    audit(db, "clip.rejected", clip_id=str(clip.id))
    db.commit()
    return serialize(db, clip)


@router.post("/{clip_id}/regenerate", response_model=ClipOut)
def regenerate(clip_id: uuid.UUID, body: RegenerateIn, db: Session = Depends(get_db)):
    clip = _get(db, clip_id)
    if clip.status in ("processing", "publishing"):
        raise HTTPException(409, f"clip is {clip.status}")
    if not clip.source_path:
        raise HTTPException(409, "clip has no source footage")
    from app.workers.tasks import regenerate_clip

    clip.status = "processing"
    db.commit()
    regenerate_clip.delay(str(clip.id), body.subtitle_style, body.regenerate_content)
    audit(db, "clip.regenerate", clip_id=str(clip.id), style=body.subtitle_style)
    return serialize(db, clip)
