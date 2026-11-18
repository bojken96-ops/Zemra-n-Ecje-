from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.config import get_settings
from app.db import get_db
from app.services import app_settings as svc
from app.services.audit import audit
from app.utils.crypto import CryptoError
from processing import ffmpeg

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(current_user)])


def _environment() -> dict:
    s = get_settings()
    enc = ffmpeg.video_encoder()
    return {"youtube_api_key_configured": bool(s.youtube_api_key),
            "google_oauth_configured": bool(s.google_client_id and s.google_client_secret),
            "tiktok_configured": bool(s.tiktok_client_key), "instagram_configured": bool(s.instagram_app_id),
            "gemini_env_key_configured": bool(s.gemini_api_key),
            "capture_agent_token_configured": bool(s.agent_token),
            "token_encryption_configured": bool(s.token_encryption_key),
            "video_encoder": enc[1], "whisper_model": s.whisper_model, "whisper_device": s.whisper_device}


@router.get("")
def get(db: Session = Depends(get_db)):
    return {**svc.public_settings(svc.load_settings(db)), "environment": _environment()}


@router.put("")
def put(patch: dict = Body(...), db: Session = Depends(get_db)):
    patch.pop("environment", None)
    try:
        updated = svc.update_settings(db, patch)
    except (ValueError, ValidationError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except CryptoError as exc:
        db.rollback()
        raise HTTPException(500, str(exc)) from exc
    audit(db, "settings.updated", sections=list(patch))
    db.commit()
    return {**svc.public_settings(updated), "environment": _environment()}
