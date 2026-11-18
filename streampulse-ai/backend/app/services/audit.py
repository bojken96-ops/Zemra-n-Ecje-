from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import AuditLog, Notification
from app.services import events

log = logging.getLogger("streampulse.audit")


def audit(db: Session, action: str, **details) -> None:
    db.add(AuditLog(action=action, details=_jsonable(details)))
    log.info(action, extra={"audit": _jsonable(details)})


def notify(db: Session, category: str, message: str, level: str = "info", **details) -> None:
    db.add(Notification(category=category, message=message, level=level, details=_jsonable(details) or None))
    events.publish("notification", {"category": category, "message": message, "level": level})


def _jsonable(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        out[k] = v if isinstance(v, (str, int, float, bool, type(None), list, dict)) else str(v)
    return out
