"""Celery tasks for manipulating courses."""
from __future__ import annotations

from typing import Any

from .celery_app import celery_app
from .config import get_settings
from .enrichment import CourseEnricher
from .logging_config import setup_logging
from .repository import CourseRepository, VersionConflictError


setup_logging()

def _get_repo() -> CourseRepository:
    settings = get_settings()
    return CourseRepository(settings.sqlite_path, settings.courses_path)


@celery_app.task(name="backend.app.tasks.add_course")
def add_course_task(payload: dict[str, Any]) -> dict[str, Any]:
    repo = _get_repo()
    course = repo.add_course(payload)
    export_courses_task.delay()
    return course.model_dump()


@celery_app.task(name="backend.app.tasks.update_course")
def update_course_task(course_id: str, version: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Update an existing course using optimistic concurrency control."""

    repo = _get_repo()
    print(f"DEBUG TASK: Received course_id='{course_id}' version={version}")
    course = repo.update_course(course_id, payload, expected_version=version)
    export_courses_task.delay()
    return course.model_dump()


@celery_app.task(name="backend.app.tasks.list_courses")
def list_courses_task(options: dict[str, Any] | None = None) -> dict[str, Any]:
    repo = _get_repo()
    result = repo.query_courses(**(options or {}))
    return result.as_dict()


@celery_app.task(name="backend.app.tasks.enrich_course")
def enrich_course_task(payload: dict[str, Any]) -> dict[str, Any]:
    repo = _get_repo()
    enricher = CourseEnricher()
    metadata = enricher.enrich(
        link=payload["link"],
        provider=payload.get("provider"),
        course_name=payload.get("course_name"),
    )
    data = metadata.to_dict()
    for attempt in range(2):
        existing = repo.get_course_by_link(data["link"])
        if existing is None:
            course = repo.add_course(data)
            break
        try:
            course = repo.update_course(
                existing.id,
                data,
                expected_version=existing.version,
            )
            break
        except VersionConflictError:
            if attempt == 1:
                raise
            continue
    export_courses_task.delay()
    return course.model_dump()


@celery_app.task(name="backend.app.tasks.export_courses")
def export_courses_task() -> str:
    settings = get_settings()
    repo = CourseRepository(settings.sqlite_path, settings.courses_path)
    repo.export_to_json(settings.courses_path)
    return str(settings.courses_path)
