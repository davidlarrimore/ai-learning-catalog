"""Application settings and configuration helpers."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import os


class Settings:
    """Lightweight settings object backed by environment variables."""

    def __init__(self) -> None:
        base_dir = Path(os.getenv("APP_BASE_DIR", Path(__file__).resolve().parents[2]))
        self.base_dir = base_dir
        data_path = Path(os.getenv("COURSES_PATH", base_dir / "data" / "courses.json"))
        self.courses_path = data_path
        self.working_courses_path = data_path
        self.source_courses_path = data_path
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.celery_broker_url = os.getenv("CELERY_BROKER_URL", redis_url)
        self.celery_result_backend = os.getenv("CELERY_RESULT_BACKEND", redis_url)
        self.task_timeout = int(os.getenv("TASK_TIMEOUT", "10"))
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.openai_request_timeout = float(os.getenv("OPENAI_REQUEST_TIMEOUT", "60"))
        self.openai_context_chars = int(os.getenv("OPENAI_CONTEXT_CHARS", "6000"))


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""

    return Settings()
