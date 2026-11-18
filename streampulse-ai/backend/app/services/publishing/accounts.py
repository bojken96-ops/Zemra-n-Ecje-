"""OAuth connection flows and token lifecycle for social accounts (tokens encrypted at rest)."""
from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import OAuthState, SocialAccount
from app.services import audit as audit_svc
from app.services.publishing import instagram, tiktok, youtube
from app.services.publishing.base import AuthExpired, Credentials, PublisherAdapter, TokenSet
from app.utils import crypto
from app.utils.time import utcnow

PLATFORMS = ("youtube", "tiktok", "instagram")
ADAPTERS: dict[str, type[PublisherAdapter]] = {
    "youtube": youtube.YouTubePublisher, "tiktok": tiktok.TikTokPublisher, "instagram": instagram.InstagramPublisher,
}


class AccountError(ValueError):
    pass


def redirect_uri(platform: str) -> str:
    return f"{get_settings().oauth_redirect_base.rstrip('/')}/api/accounts/{platform}/callback"


def start_connect(db: Session, platform: str) -> str:
    s = get_settings()
    if platform not in PLATFORMS:
        raise AccountError("unknown platform")
    state = crypto.new_token(24)
    verifier, challenge = crypto.pkce_pair()
    if platform == "youtube":
        if not (s.google_client_id and s.google_client_secret):
            raise AccountError("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not configured")
        url = youtube.authorize_url(s.google_client_id, redirect_uri(platform), state, challenge)
    elif platform == "tiktok":
        if not (s.tiktok_client_key and s.tiktok_client_secret):
            raise AccountError("TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET are not configured")
        url = tiktok.authorize_url(s.tiktok_client_key, redirect_uri(platform), state)
    else:
        if not (s.instagram_app_id and s.instagram_app_secret):
            raise AccountError("INSTAGRAM_APP_ID / INSTAGRAM_APP_SECRET are not configured")
        url = instagram.authorize_url(s.instagram_app_id, redirect_uri(platform), state)
    db.add(OAuthState(state=state, platform=platform, code_verifier=verifier, expires_at=utcnow() + timedelta(minutes=15)))
    db.commit()
    return url


def complete_connect(db: Session, platform: str, state: str, code: str) -> SocialAccount:
    s = get_settings()
    st = db.get(OAuthState, state)
    if st is None or st.platform != platform or st.expires_at < utcnow():
        raise AccountError("invalid or expired OAuth state")
    db.delete(st)
    db.commit()
    if platform == "youtube":
        tok = asyncio.run(youtube.exchange_code(s.google_client_id, s.google_client_secret, redirect_uri(platform), code,
                                                st.code_verifier))
    elif platform == "tiktok":
        tok = asyncio.run(tiktok.exchange_code(s.tiktok_client_key, s.tiktok_client_secret, redirect_uri(platform), code))
    else:
        tok = asyncio.run(instagram.exchange_code(s.instagram_app_id, s.instagram_app_secret, redirect_uri(platform), code))
    return save_tokens(db, platform, tok)


def save_tokens(db: Session, platform: str, tok: TokenSet) -> SocialAccount:
    acct = (db.query(SocialAccount).filter(SocialAccount.platform == platform, SocialAccount.account_id == tok.account_id)
            .one_or_none())
    if acct is None:
        acct = SocialAccount(platform=platform, account_id=tok.account_id)
        db.add(acct)
    acct.account_name = tok.account_name or acct.account_name
    acct.encrypted_access_token = crypto.encrypt(tok.access_token)
    if tok.refresh_token:
        acct.encrypted_refresh_token = crypto.encrypt(tok.refresh_token)
    acct.token_expires_at = utcnow() + timedelta(seconds=tok.expires_in) if tok.expires_in else None
    acct.scopes = tok.scopes
    acct.connected = True
    audit_svc.audit(db, "account.connected", platform=platform, account=acct.account_name)
    db.commit()
    return acct


def credentials(db: Session, acct: SocialAccount) -> Credentials:
    """Decrypt tokens, refreshing them first if they expire within 5 minutes."""
    if not acct.connected:
        raise AuthExpired("account is disconnected")
    if acct.token_expires_at and acct.token_expires_at < utcnow() + timedelta(minutes=5):
        _refresh(db, acct)
    return Credentials(crypto.decrypt(acct.encrypted_access_token), crypto.decrypt(acct.encrypted_refresh_token),
                       acct.token_expires_at, acct.account_id)


def _refresh(db: Session, acct: SocialAccount) -> None:
    s = get_settings()
    refresh_token = crypto.decrypt(acct.encrypted_refresh_token)
    try:
        if acct.platform == "youtube":
            if not refresh_token:
                raise AuthExpired()
            tok = asyncio.run(youtube.refresh(s.google_client_id, s.google_client_secret, refresh_token))
        elif acct.platform == "tiktok":
            if not refresh_token:
                raise AuthExpired()
            tok = asyncio.run(tiktok.refresh(s.tiktok_client_key, s.tiktok_client_secret, refresh_token))
        else:
            tok = asyncio.run(instagram.refresh(crypto.decrypt(acct.encrypted_access_token)))
    except AuthExpired:
        acct.connected = False
        audit_svc.notify(db, "accounts", f"{acct.platform} account {acct.account_name} needs to be reconnected",
                         level="error")
        db.commit()
        raise
    acct.encrypted_access_token = crypto.encrypt(tok.access_token)
    if tok.refresh_token:
        acct.encrypted_refresh_token = crypto.encrypt(tok.refresh_token)
    acct.token_expires_at = utcnow() + timedelta(seconds=tok.expires_in) if tok.expires_in else None
    db.commit()


def adapter_for(db: Session, acct: SocialAccount) -> PublisherAdapter:
    return ADAPTERS[acct.platform](credentials(db, acct))
