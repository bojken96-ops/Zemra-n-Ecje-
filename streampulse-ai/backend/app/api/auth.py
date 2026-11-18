from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_session
from app.api.middleware import client_ip
from app.config import get_settings
from app.db import get_db
from app.models import User, UserSession
from app.schemas.api import AuthState, Credentials
from app.services import auth
from app.services.audit import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookies(response: Response, token: str, csrf: str) -> None:
    s = get_settings()
    max_age = s.session_ttl_hours * 3600
    response.set_cookie(auth.SESSION_COOKIE, token, httponly=True, secure=s.cookie_secure, samesite="strict",
                        max_age=max_age, path="/")
    response.set_cookie(auth.CSRF_COOKIE, csrf, httponly=False, secure=s.cookie_secure, samesite="strict",
                        max_age=max_age, path="/")


@router.get("/state", response_model=AuthState)
def state(request: Request, db: Session = Depends(get_db)):
    sess = auth.resolve_session(db, request.cookies.get(auth.SESSION_COOKIE))
    if sess is None:
        return AuthState(authenticated=False, setup_required=not auth.owner_exists(db))
    user = db.get(User, sess.user_id)
    return AuthState(authenticated=True, setup_required=False, username=user.username, csrf_token=sess.csrf_token)


@router.post("/setup", response_model=AuthState)
def setup(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    """Create the single owner account. Only allowed when no account exists."""
    if auth.owner_exists(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "owner account already exists")
    try:
        auth.validate_password_strength(body.password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    user = User(username=body.username, password_hash=auth.hash_password(body.password))
    db.add(user)
    db.flush()
    audit(db, "auth.setup", username=body.username, ip=client_ip(request))
    token, sess = auth.create_session(db, user, request.headers.get("user-agent"), client_ip(request))
    _set_cookies(response, token, sess.csrf_token)
    return AuthState(authenticated=True, setup_required=False, username=user.username, csrf_token=sess.csrf_token)


@router.post("/login", response_model=AuthState)
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).one_or_none()
    if user is None or not auth.verify_password(user.password_hash, body.password):
        audit(db, "auth.login_failed", username=body.username, ip=client_ip(request))
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid username or password")
    token, sess = auth.create_session(db, user, request.headers.get("user-agent"), client_ip(request))
    audit(db, "auth.login", username=user.username, ip=client_ip(request))
    db.commit()
    _set_cookies(response, token, sess.csrf_token)
    return AuthState(authenticated=True, setup_required=False, username=user.username, csrf_token=sess.csrf_token)


@router.post("/logout")
def logout(request: Request, response: Response, sess: UserSession = Depends(current_session),
           db: Session = Depends(get_db)):
    auth.destroy_session(db, request.cookies.get(auth.SESSION_COOKIE))
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    response.delete_cookie(auth.CSRF_COOKIE, path="/")
    return {"ok": True}
