"""Safe path handling inside the storage root (no path traversal, no symlink escape)."""
from __future__ import annotations

import shutil
from pathlib import Path

from app.config import get_settings

AREAS = ("recordings", "temporary", "clips", "thumbnails", "subtitles")


class UnsafePath(ValueError):
    pass


def root() -> Path:
    return get_settings().storage_root.resolve()


def resolve(relative: str | Path) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise UnsafePath(f"unsafe storage path: {relative}")
    full = (root() / rel).resolve()
    if root() not in full.parents and full != root():
        raise UnsafePath(f"path escapes storage root: {relative}")
    return full


def relative(path: Path) -> str:
    return path.resolve().relative_to(root()).as_posix()


def area(name: str) -> Path:
    if name not in AREAS:
        raise UnsafePath(name)
    p = root() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def disk_usage() -> dict:
    total, used, free = shutil.disk_usage(root())
    by_area = {}
    for name in AREAS:
        p = root() / name
        by_area[name] = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0
    return {"disk_total": total, "disk_used": used, "disk_free": free, "areas": by_area,
            "storage_used": sum(by_area.values())}
