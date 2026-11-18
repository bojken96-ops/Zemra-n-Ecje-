"""Live dashboard events via Redis pub/sub -> WebSocket fan-out."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from functools import lru_cache

import redis

from app.config import get_settings

CHANNEL = "streampulse:events"
log = logging.getLogger(__name__)


@lru_cache
def redis_client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


def publish(event_type: str, data: dict) -> None:
    payload = json.dumps({"type": event_type, "data": data, "ts": datetime.now(timezone.utc).isoformat()}, default=str)
    try:
        redis_client().publish(CHANNEL, payload)
    except redis.RedisError as exc:  # events are best-effort; never break the caller
        log.warning("event publish failed", extra={"error": str(exc), "event_type": event_type})
