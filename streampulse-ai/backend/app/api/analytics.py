from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import CaptureSession, Clip, ClipCandidate, Creator, Notification, PublishedPost, PublishingJob, Stream
from app.services.storage.manager import usage
from app.utils.time import utcnow

router = APIRouter(prefix="/api", tags=["analytics"], dependencies=[Depends(current_user)])


@router.get("/analytics")
def analytics(days: int = Query(14, ge=1, le=365), db: Session = Depends(get_db)):
    now = utcnow()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since = start_of_day - timedelta(days=days - 1)
    overview = {
        "active_streams": db.query(Stream).filter(Stream.status.in_(("live", "reconnecting"))).count(),
        "total_streams": db.query(Stream).count(),
        "active_captures": db.query(CaptureSession).filter(
            CaptureSession.status.in_(("starting", "recording", "reconnecting"))).count(),
        "clips_today": db.query(Clip).filter(Clip.created_at >= start_of_day).count(),
        "clips_awaiting_approval": db.query(Clip).filter(Clip.status == "ready").count(),
        "published_clips": db.query(func.count(func.distinct(PublishedPost.clip_id))).scalar(),
        "failed_jobs": db.query(PublishingJob).filter(PublishingJob.status == "failed").count(),
        "candidates_today": db.query(ClipCandidate).filter(ClipCandidate.created_at >= start_of_day).count(),
    }
    day = func.date_trunc("day", Clip.created_at)
    clips_per_day = {r[0].date().isoformat(): r[1] for r in
                     db.query(day, func.count()).filter(Clip.created_at >= since).group_by(day).all()}
    pday = func.date_trunc("day", PublishedPost.published_at)
    posts_per_day = {r[0].date().isoformat(): r[1] for r in
                     db.query(pday, func.count()).filter(PublishedPost.published_at >= since).group_by(pday).all()}
    series = []
    for i in range(days):
        d = (since + timedelta(days=i)).date().isoformat()
        series.append({"date": d, "clips": clips_per_day.get(d, 0), "published": posts_per_day.get(d, 0)})
    by_type = [{"moment_type": t or "unknown", "count": c} for t, c in
               db.query(Clip.moment_type, func.count()).group_by(Clip.moment_type).all()]
    by_platform = [{"platform": p, "status": s, "count": c} for p, s, c in
                   db.query(PublishingJob.platform, PublishingJob.status, func.count())
                   .group_by(PublishingJob.platform, PublishingJob.status).all()]
    by_creator = [{"creator": n or "Unassigned", "clips": c} for n, c in
                  db.query(Creator.name, func.count(Clip.id)).select_from(Clip)
                  .join(Stream, Stream.id == Clip.stream_id).outerjoin(Creator, Creator.id == Stream.creator_id)
                  .group_by(Creator.name).all()]
    candidates = {s: c for s, c in db.query(ClipCandidate.status, func.count()).group_by(ClipCandidate.status).all()}
    avg_score = db.query(func.avg(Clip.viral_score)).scalar()
    return {"overview": overview, "series": series, "by_moment_type": by_type, "by_platform": by_platform,
            "by_creator": by_creator, "candidates": candidates,
            "average_viral_score": round(float(avg_score), 1) if avg_score else None, "storage": usage(db)}


@router.get("/storage")
def storage_usage(db: Session = Depends(get_db)):
    return usage(db)


@router.get("/notifications")
def notifications(unread_only: bool = False, limit: int = Query(50, le=500), db: Session = Depends(get_db)):
    q = db.query(Notification)
    if unread_only:
        q = q.filter(Notification.read.is_(False))
    return [{"id": n.id, "level": n.level, "category": n.category, "message": n.message, "details": n.details,
             "read": n.read, "created_at": n.created_at} for n in q.order_by(Notification.created_at.desc()).limit(limit)]


@router.post("/notifications/read")
def mark_read(db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.read.is_(False)).update({Notification.read: True})
    db.commit()
    return {"ok": True}
