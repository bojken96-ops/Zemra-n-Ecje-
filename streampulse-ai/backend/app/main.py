import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import accounts, agent, analytics, auth, clips, creators, media, publishing, settings, streams, ws
from app.api.middleware import LocalNetworkMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
from app.config import get_settings
from app.db import engine
from app.services.events import redis_client
from app.utils.logging import configure_logging

cfg = get_settings()
configure_logging(cfg.log_level)
log = logging.getLogger("streampulse")

if cfg.is_production and not (cfg.token_encryption_key and cfg.agent_token):
    raise RuntimeError("TOKEN_ENCRYPTION_KEY and CAPTURE_AGENT_TOKEN must be set in production")

app = FastAPI(title="StreamPulse AI", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=cfg.origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["content-type", "x-csrf-token"])
app.add_middleware(LocalNetworkMiddleware)

for r in (auth, creators, streams, clips, publishing, accounts, analytics, settings, agent, media):
    app.include_router(r.router)
app.include_router(ws.router)


@app.get("/api/health")
def health():
    status = {"api": "ok"}
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        status["database"] = "ok"
    except Exception as exc:  # pragma: no cover
        status["database"] = f"error: {type(exc).__name__}"
    try:
        redis_client().ping()
        status["redis"] = "ok"
    except Exception as exc:  # pragma: no cover
        status["redis"] = f"error: {type(exc).__name__}"
    status["ok"] = all(v == "ok" for k, v in status.items() if k != "ok")
    return status
