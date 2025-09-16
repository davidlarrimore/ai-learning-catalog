"""Persistence helpers for course data."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .course_model import Course, append_course, ensure_store, load_courses, save_courses


class CourseRepository:
    """Read/write helper backed by the JSON course store."""

    def __init__(self, store_path: Path) -> None:
        self.store_path = ensure_store(store_path)

    def list_courses(self) -> list[Course]:
        return load_courses(self.store_path)

    def add_course(self, payload: dict) -> Course:
        course = Course.model_validate(payload)
        append_course(self.store_path, course)
        return course

    def bulk_replace(self, courses: Iterable[Course]) -> None:
        save_courses(self.store_path, list(courses))

    def update_course(self, unique_field: str, value: str, payload: dict) -> Course:
        courses = self.list_courses()
        updated_course: Course | None = None
        for idx, existing in enumerate(courses):
            if getattr(existing, unique_field) == value:
                updated_course = existing.model_copy(update=payload)
                courses[idx] = updated_course
                break
        if updated_course is None:
            msg = f"Course with {unique_field}='{value}' not found"
            raise KeyError(msg)
        save_courses(self.store_path, courses)
        return updated_course
