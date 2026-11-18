from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User, UserSession
from app.services import auth
from app.utils import crypto

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def current_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    sess = auth.resolve_session(db, request.cookies.get(auth.SESSION_COOKIE))
    if sess is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    if request.method not in SAFE_METHODS:
        header = request.headers.get("x-csrf-token", "")
        if not header or not crypto.constant_time_equals(header, sess.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "missing or invalid CSRF token")
    return sess


def current_user(sess: UserSession = Depends(current_session), db: Session = Depends(get_db)) -> User:
    user = db.get(User, sess.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    return user


def capture_agent(request: Request) -> None:
    """Authenticate the Windows capture agent with its shared bearer token."""
    expected = get_settings().agent_token
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "CAPTURE_AGENT_TOKEN is not configured")
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    if not token or not crypto.constant_time_equals(token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid agent token")
