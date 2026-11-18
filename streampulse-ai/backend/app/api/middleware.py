"""Security middleware: local-network restriction, rate limiting, security headers."""
from __future__ import annotations

import ipaddress
import logging
import time

import redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings
from app.services.events import redis_client

log = logging.getLogger("streampulse.security")


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "0.0.0.0"


class LocalNetworkMiddleware(BaseHTTPMiddleware):
    """Reject requests from outside the configured private networks.

    Combined with binding published ports to 127.0.0.1 in docker-compose this
    keeps the API (including capture-control endpoints) off the public internet.
    """

    def __init__(self, app):
        super().__init__(app)
        self.networks = [ipaddress.ip_network(n, strict=False) for n in get_settings().client_networks]

    async def dispatch(self, request: Request, call_next):
        host = client_ip(request)
        try:
            addr = ipaddress.ip_address(host)
            allowed = any(addr in net for net in self.networks)
        except ValueError:
            allowed = host in {"testclient", "localhost"}
        if not allowed:
            log.warning("blocked non-local client", extra={"client": host, "path": request.url.path})
            return JSONResponse({"detail": "access restricted to local network"}, status_code=403)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window per-IP rate limiting backed by Redis (fails open if Redis is down)."""

    async def dispatch(self, request: Request, call_next):
        s = get_settings()
        path = request.url.path
        if not path.startswith("/api") or path.startswith("/api/agent") or path == "/api/health":
            return await call_next(request)
        is_login = path in ("/api/auth/login", "/api/auth/setup")
        limit = s.login_rate_limit_per_minute if is_login else s.rate_limit_per_minute
        bucket = f"rl:{'login' if is_login else 'api'}:{client_ip(request)}:{int(time.time() // 60)}"
        try:
            r = redis_client()
            count = r.incr(bucket)
            if count == 1:
                r.expire(bucket, 70)
        except redis.RedisError:
            return await call_next(request)
        if count > limit:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429, headers={"Retry-After": "60"})
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Cache-Control", "no-store") if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/media") else None
        return response
