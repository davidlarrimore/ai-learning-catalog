"""Persistence helpers for course data."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .course_model import Course, append_course, ensure_store, load_courses, save_courses


FILTERABLE_FIELDS = (
    "provider",
    "platform",
    "difficulty",
    "skill_level",
    "hands_on",
    "track",
)


@dataclass
class CourseQueryResult:
    """Container for paginated course query results."""

    items: list[Course]
    total: int
    page: int
    page_size: int
    total_pages: int
    available_filters: dict[str, list[str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "items": [course.model_dump() for course in self.items],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
            "available_filters": self.available_filters,
        }


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

    def query_courses(
        self,
        *,
        search: str | None = None,
        filters: Mapping[str, Iterable[str]] | None = None,
        page: int = 1,
        page_size: int = 25,
        include_filters: bool = True,
    ) -> CourseQueryResult:
        courses = self.list_courses()

        # Prepare filter metadata before mutation so we can expose full facets to callers
        available_filters: dict[str, list[str]] = {}
        if include_filters:
            for field in FILTERABLE_FIELDS:
                values = {
                    getattr(course, field, "").strip()
                    for course in courses
                    if getattr(course, field, "").strip()
                }
                available_filters[field] = sorted(values, key=str.casefold)

        normalized_filters: dict[str, set[str]] = {}
        if filters:
            for field, values in filters.items():
                if field not in FILTERABLE_FIELDS or not values:
                    continue
                normalized = {
                    str(value).strip().lower()
                    for value in values
                    if str(value).strip()
                }
                if normalized:
                    normalized_filters[field] = normalized

        search_term = search.strip().lower() if search else ""
        search_fields = (
            "course_name",
            "summary",
            "provider",
            "platform",
            "track",
        )

        filtered: list[Course] = []
        for course in courses:
            if search_term:
                haystack = " ".join(
                    getattr(course, field, "") or ""
                    for field in search_fields
                ).lower()
                if search_term not in haystack:
                    continue

            matches_all_filters = True
            for field, expected in normalized_filters.items():
                value = getattr(course, field, "") or ""
                if value.strip().lower() not in expected:
                    matches_all_filters = False
                    break

            if matches_all_filters:
                filtered.append(course)

        page_size = max(1, min(int(page_size or 1), 200))
        total = len(filtered)
        total_pages = math.ceil(total / page_size) if total else 0
        page = max(1, int(page or 1))
        if total_pages and page > total_pages:
            page = total_pages
        elif not total_pages:
            page = 1

        start = (page - 1) * page_size
        end = start + page_size
        items = filtered[start:end]

        return CourseQueryResult(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            available_filters=available_filters if include_filters else {},
        )

    def update_course(self, unique_field: str, value: str, payload: dict) -> Course:
        """Update a course by matching on unique_field.

        Args:
            unique_field: The field name to match on (e.g., 'link')
            value: The value to search for
            payload: Dictionary of fields to update
            
        Returns:
            The updated Course object
            
        Raises:
            KeyError: If no course with the given field value is found
        """
        courses = self.list_courses()
        updated_course: Course | None = None
        
        search_value = value.strip()
        
        print(f"DEBUG REPO: Searching for {unique_field}='{search_value}'")
        
        for idx, existing in enumerate(courses):
            existing_value = getattr(existing, unique_field).strip()
            
            if existing_value == search_value:
                print(f"DEBUG REPO: Found exact match!")
                updated_course = existing.model_copy(update=payload)
                courses[idx] = updated_course
                break
                
        if updated_course is None:
            # Show what we have for debugging
            available_links = [getattr(c, unique_field) for c in courses]
            print(f"DEBUG REPO: No exact match found.")
            print(f"DEBUG REPO: Looking for: '{search_value}' (length: {len(search_value)})")
            print(f"DEBUG REPO: First few available links:")
            for link in available_links[:10]:
                print(f"  '{link}' (length: {len(link)}) matches: {link.strip() == search_value}")
            
            # Check if the ClassCentral course exists at all
            classcentral_courses = [link for link in available_links if 'classcentral.com' in link]
            if classcentral_courses:
                print(f"DEBUG REPO: Found ClassCentral courses:")
                for cc_link in classcentral_courses:
                    print(f"  '{cc_link}'")
            
            msg = f"Course with {unique_field}='{search_value}' not found. Available values: {available_links[:5]}"
            raise KeyError(msg)
            
        save_courses(self.store_path, courses)
        return updated_course
