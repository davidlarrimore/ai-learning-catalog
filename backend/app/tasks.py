"""Celery tasks for manipulating courses."""
from __future__ import annotations

from typing import Any

from .course_model import ensure_store

from .celery_app import celery_app
from .config import get_settings
from .enrichment import CourseEnricher
from .repository import CourseRepository


def _get_repo() -> CourseRepository:
    settings = get_settings()
    ensure_store(settings.courses_path)
    return CourseRepository(settings.courses_path)


@celery_app.task(name="backend.app.tasks.add_course")
def add_course_task(payload: dict[str, Any]) -> dict[str, Any]:
    repo = _get_repo()
    course = repo.add_course(payload)
    return course.model_dump()


@celery_app.task(name="backend.app.tasks.update_course")
def update_course_task(link: str, payload: dict[str, Any]) -> dict[str, Any]:
    repo = _get_repo()
    course = repo.update_course("link", link, payload)
    return course.model_dump()


@celery_app.task(name="backend.app.tasks.list_courses")
def list_courses_task() -> list[dict[str, Any]]:
    repo = _get_repo()
    return [course.model_dump() for course in repo.list_courses()]


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
    try:
        course = repo.update_course("link", data["link"], data)
    except KeyError:
        course = repo.add_course(data)
    return course.model_dump()
