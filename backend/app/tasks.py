"""Celery tasks for manipulating courses."""
from __future__ import annotations

import logging
from typing import Any

from .celery_app import celery_app
from .config import get_settings
from .enrichment import CourseEnricher
from .logging_config import setup_logging
from .repository import CourseRepository, VersionConflictError


setup_logging()

logger = logging.getLogger(__name__)

def _get_repo() -> CourseRepository:
    settings = get_settings()
    return CourseRepository(
        settings.sqlite_path,
        settings.courses_path,
        redis_url=settings.redis_url,
    )


def _enrich_course_payload(payload: dict[str, Any]) -> dict[str, str]:
    enricher = CourseEnricher()
    metadata = enricher.enrich(
        link=payload["link"],
        provider=payload.get("provider"),
        course_name=payload.get("course_name"),
    )
    return metadata.to_dict()


def process_course_draft_sync(draft_id: str) -> dict[str, Any]:
    """Run the draft enrichment synchronously."""

    repo = _get_repo()
    draft = repo.get_draft(draft_id)
    if draft is None:
        raise KeyError(f"Draft not found: {draft_id}")

    logger.info("Processing course draft %s (link=%s)", draft_id, draft.link)

    repo.update_draft(
        draft_id,
        status="processing",
        message="Fetching course metadata…",
    )

    try:
        data = _enrich_course_payload(
            {
                "link": draft.link,
                "provider": draft.provider,
                "course_name": draft.course_name,
            }
        )
    except Exception as exc:
        logger.exception("Draft %s failed during enrichment", draft_id)
        repo.update_draft(
            draft_id,
            status="failed",
            message="Failed to enrich course",
            error=str(exc),
        )
        raise

    repo.update_draft(
        draft_id,
        status="ready",
        message="Draft ready for review",
        error="",
        course_payload=data,
    )
    updated = repo.get_draft(draft_id)
    logger.info("Draft %s completed successfully", draft_id)
    return updated.as_dict() if updated else {}


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
    data = _enrich_course_payload(payload)
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


@celery_app.task(name="backend.app.tasks.process_course_draft")
def process_course_draft_task(draft_id: str) -> dict[str, Any]:
    return process_course_draft_sync(draft_id)


@celery_app.task(name="backend.app.tasks.export_courses")
def export_courses_task() -> str:
    settings = get_settings()
    repo = CourseRepository(
        settings.sqlite_path,
        settings.courses_path,
        redis_url=settings.redis_url,
    )
    repo.export_to_json(settings.courses_path)
    return str(settings.courses_path)
