import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.config import get_settings
from app.db import get_db
from app.models import PublishingJob, SocialAccount
from app.schemas.api import AccountOut
from app.services.audit import audit
from app.services.publishing import accounts
from app.services.publishing.base import PublishError
from app.utils.crypto import CryptoError

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut], dependencies=[Depends(current_user)])
def list_(db: Session = Depends(get_db)):
    return db.query(SocialAccount).order_by(SocialAccount.platform).all()


@router.get("/config", dependencies=[Depends(current_user)])
def config():
    s = get_settings()
    return {"youtube": bool(s.google_client_id and s.google_client_secret),
            "tiktok": bool(s.tiktok_client_key and s.tiktok_client_secret),
            "instagram": bool(s.instagram_app_id and s.instagram_app_secret),
            "redirect_uris": {p: accounts.redirect_uri(p) for p in accounts.PLATFORMS}}


@router.post("/{platform}/connect", dependencies=[Depends(current_user)])
def connect(platform: str, db: Session = Depends(get_db)):
    try:
        return {"authorization_url": accounts.start_connect(db, platform)}
    except accounts.AccountError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{platform}/callback")
def callback(platform: str, state: str = "", code: str = "", error: str | None = None, db: Session = Depends(get_db)):
    """OAuth redirect target.

    Session cookies are SameSite=strict and are not sent on the cross-site redirect back from the
    provider, so this endpoint is authorised by the single-use, 15-minute ``state`` value that only
    an authenticated owner could have created via POST /connect.
    """
    base = get_settings().public_base_url.rstrip("/")
    if error:
        return RedirectResponse(f"{base}/accounts?error={error[:100]}")
    try:
        acct = accounts.complete_connect(db, platform, state, code)
    except (accounts.AccountError, PublishError, CryptoError) as exc:
        audit(db, "account.connect_failed", platform=platform, error=str(exc))
        db.commit()
        return RedirectResponse(f"{base}/accounts?error={str(exc)[:200]}")
    return RedirectResponse(f"{base}/accounts?connected={acct.platform}")


@router.patch("/{account_id}", response_model=AccountOut, dependencies=[Depends(current_user)])
def toggle(account_id: uuid.UUID, enabled: bool, db: Session = Depends(get_db)):
    acct = db.get(SocialAccount, account_id)
    if acct is None:
        raise HTTPException(404, "account not found")
    acct.enabled = enabled
    db.commit()
    return acct


@router.delete("/{account_id}", status_code=204, dependencies=[Depends(current_user)])
def disconnect(account_id: uuid.UUID, db: Session = Depends(get_db)):
    acct = db.get(SocialAccount, account_id)
    if acct is None:
        raise HTTPException(404, "account not found")
    busy = db.query(PublishingJob).filter(PublishingJob.social_account_id == acct.id,
                                          PublishingJob.status.in_(("uploading", "processing"))).count()
    if busy:
        raise HTTPException(409, "account has uploads in progress")
    audit(db, "account.disconnected", platform=acct.platform, account=acct.account_name)
    db.delete(acct)
    db.commit()
