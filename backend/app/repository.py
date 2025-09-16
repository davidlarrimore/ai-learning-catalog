"""Persistence helpers for course data."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable
from urllib.parse import unquote

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