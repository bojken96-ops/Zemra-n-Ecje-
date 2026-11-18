import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import Clip, PublishedPost, PublishingJob
from app.schemas.api import PublishJobIn, PublishJobOut
from app.services import app_settings as settings_svc
from app.services.publishing import queue

router = APIRouter(prefix="/api/publishing", tags=["publishing"], dependencies=[Depends(current_user)])


def serialize(db: Session, job: PublishingJob) -> PublishJobOut:
    out = PublishJobOut.model_validate(job)
    post = db.query(PublishedPost).filter(PublishedPost.publishing_job_id == job.id).first()
    out.post_url = post.post_url if post else None
    clip = db.get(Clip, job.clip_id)
    out.clip_title = clip.title if clip else None
    return out


@router.get("/jobs", response_model=list[PublishJobOut])
def list_jobs(status: str | None = None, platform: str | None = None, limit: int = Query(200, le=1000),
              db: Session = Depends(get_db)):
    q = db.query(PublishingJob)
    if status:
        q = q.filter(PublishingJob.status.in_(status.split(",")))
    if platform:
        q = q.filter(PublishingJob.platform == platform)
    return [serialize(db, j) for j in q.order_by(PublishingJob.created_at.desc()).limit(limit).all()]


@router.post("/jobs", response_model=list[PublishJobOut], status_code=201)
def create_jobs(body: PublishJobIn, db: Session = Depends(get_db)):
    clip = db.get(Clip, body.clip_id)
    if clip is None:
        raise HTTPException(404, "clip not found")
    if clip.status == "ready":
        clip.status = "approved"
        db.commit()
    try:
        jobs = queue.create_jobs_for_clip(db, clip, settings_svc.load_settings(db), body.account_ids,
                                          body.scheduled_at, body.overrides)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return [serialize(db, j) for j in jobs]


@router.post("/jobs/{job_id}/retry", response_model=PublishJobOut)
def retry(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.get(PublishingJob, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    try:
        queue.retry(db, job)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return serialize(db, job)


@router.post("/jobs/{job_id}/cancel", response_model=PublishJobOut)
def cancel(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.get(PublishingJob, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if job.status not in ("pending", "scheduled", "failed"):
        raise HTTPException(409, f"cannot cancel a job that is {job.status}")
    job.status = "cancelled"
    db.commit()
    return serialize(db, job)
