"""Local single-owner authentication with server-side sessions."""
from __future__ import annotations

from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User, UserSession
from app.utils import crypto
from app.utils.time import utcnow

_hasher = PasswordHasher()
SESSION_COOKIE = "sp_session"
CSRF_COOKIE = "sp_csrf"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def owner_exists(db: Session) -> bool:
    return db.query(User.id).first() is not None


def validate_password_strength(password: str) -> None:
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    classes = sum([any(c.islower() for c in password), any(c.isupper() for c in password),
                   any(c.isdigit() for c in password), any(not c.isalnum() for c in password)])
    if classes < 3:
        raise ValueError("password must mix at least 3 of: lowercase, uppercase, digits, symbols")


def create_session(db: Session, user: User, user_agent: str | None, ip: str | None) -> tuple[str, UserSession]:
    token = crypto.new_token()
    sess = UserSession(
        user_id=user.id,
        token_hash=crypto.sha256_hex(token),
        csrf_token=crypto.new_token(24),
        user_agent=(user_agent or "")[:300],
        ip_address=ip,
        expires_at=utcnow() + timedelta(hours=get_settings().session_ttl_hours),
    )
    db.add(sess)
    db.execute(delete(UserSession).where(UserSession.expires_at < utcnow()))
    db.commit()
    return token, sess


def resolve_session(db: Session, token: str | None) -> UserSession | None:
    if not token:
        return None
    sess = db.query(UserSession).filter(UserSession.token_hash == crypto.sha256_hex(token)).one_or_none()
    if sess is None or sess.expires_at < utcnow():
        return None
    return sess


def destroy_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == crypto.sha256_hex(token)))
        db.commit()
