"""Authenticated media serving (clips, thumbnails, subtitles) with HTTP range support."""
import mimetypes

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import current_user
from app.utils import storage

router = APIRouter(prefix="/api/media", tags=["media"], dependencies=[Depends(current_user)])
SERVABLE = {"clips", "thumbnails", "subtitles"}


@router.get("/{path:path}")
def media(path: str, download: bool = False):
    if path.split("/", 1)[0] not in SERVABLE:
        raise HTTPException(404, "not found")
    try:
        full = storage.resolve(path)
    except storage.UnsafePath as exc:
        raise HTTPException(400, "invalid path") from exc
    if not full.is_file():
        raise HTTPException(404, "not found")
    media_type = mimetypes.guess_type(full.name)[0] or "application/octet-stream"
    headers = {"Cache-Control": "private, max-age=300"}
    return FileResponse(full, media_type=media_type, headers=headers,
                        filename=full.name if download else None,
                        content_disposition_type="attachment" if download else "inline")
