"""Utility for exporting SQLite-backed courses to the JSON format."""
from __future__ import annotations

from pathlib import Path

from .config import get_settings
from .repository import CourseRepository


def export_courses() -> Path:
    settings = get_settings()
    repo = CourseRepository(
        settings.sqlite_path,
        settings.courses_path,
        redis_url=settings.redis_url,
    )
    repo.export_to_json(settings.courses_path)
    return settings.courses_path


if __name__ == "__main__":  # pragma: no cover - CLI helper
    path = export_courses()
    print(f"Exported courses to {path}")
