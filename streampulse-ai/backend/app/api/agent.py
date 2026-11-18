"""Capture-agent control plane. Authenticated by CAPTURE_AGENT_TOKEN; only reachable from the local machine."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import capture_agent
from app.db import get_db
from app.models import CaptureSession
from app.schemas.api import AgentSegmentIn, AgentStatusIn
from app.services import app_settings as settings_svc
from app.services.capture import sessions as svc
from app.utils import storage

router = APIRouter(prefix="/api/agent", tags=["capture-agent"], dependencies=[Depends(capture_agent)])


@router.get("/config")
def config(db: Session = Depends(get_db)):
    return settings_svc.load_settings(db).capture.model_dump()


@router.get("/commands")
def commands(db: Session = Depends(get_db)):
    cfg = settings_svc.load_settings(db)
    return {"commands": svc.pending_commands(db, cfg.capture.max_concurrent_captures),
            "capture": cfg.capture.model_dump()}


def _session(db: Session, session_id: uuid.UUID) -> CaptureSession:
    sess = db.get(CaptureSession, session_id)
    if sess is None:
        raise HTTPException(404, "capture session not found")
    return sess


@router.post("/sessions/{session_id}/status")
def status(session_id: uuid.UUID, body: AgentStatusIn, db: Session = Depends(get_db)):
    sess = _session(db, session_id)
    try:
        svc.update_status(db, sess, body.status, body.capture_method, body.health, body.error, body.recording_path)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"status": sess.status, "stop_requested": sess.stop_requested}


@router.post("/sessions/{session_id}/segments", status_code=201)
def segment(session_id: uuid.UUID, body: AgentSegmentIn, db: Session = Depends(get_db)):
    sess = _session(db, session_id)
    try:
        path = storage.resolve(body.file_path)
    except storage.UnsafePath as exc:
        raise HTTPException(422, str(exc)) from exc
    expected_prefix = f"recordings/{sess.stream_id}/{sess.id}/"
    if not body.file_path.startswith(expected_prefix):
        raise HTTPException(422, f"segment must live under {expected_prefix}")
    if not path.is_file():
        raise HTTPException(422, "segment file not found in shared storage (check the storage mount)")
    if body.end_time <= body.start_time:
        raise HTTPException(422, "end_time must be after start_time")
    seg = svc.register_segment(db, sess, body.sequence, body.file_path, body.start_time, body.end_time,
                               body.size_bytes, body.width, body.height, body.fps)
    from app.workers.tasks import analyse_segment

    analyse_segment.delay(str(seg.id))
    return {"id": str(seg.id), "stop_requested": sess.stop_requested}
