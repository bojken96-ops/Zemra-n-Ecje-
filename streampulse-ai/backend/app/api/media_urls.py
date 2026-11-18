def media_url(rel: str | None) -> str | None:
    return f"/api/media/{rel}" if rel else None
