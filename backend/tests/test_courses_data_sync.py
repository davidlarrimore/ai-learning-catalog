from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Dict

import pytest

from backend.app.config import get_settings
from backend.app.course_model import Course, load_courses

COMPARISON_FIELDS = (
    "id",
    "link",
    "version",
    "provider",
    "course_name",
    "summary",
    "track",
    "platform",
    "hands_on",
    "skill_level",
    "difficulty",
    "length",
    "evidence_of_completion",
    "date_created",
    "last_updated",
)


@pytest.fixture(scope="module")
def settings():
    return get_settings()


@pytest.fixture(scope="module")
def json_courses(settings) -> Dict[str, Course]:
    courses = load_courses(settings.courses_path)
    assert courses, f"No courses found in JSON file at {settings.courses_path}"
    return {course.id: course for course in courses}


@pytest.fixture(scope="module")
def db_courses(settings) -> Dict[str, Course]:
    with sqlite3.connect(settings.sqlite_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, link, version, provider, course_name, summary, track, platform, "
            "hands_on, skill_level, difficulty, length, evidence_of_completion, "
            "date_created, last_updated FROM courses"
        ).fetchall()
    courses = [Course.model_validate(dict(row)) for row in rows]
    assert courses, f"No courses found in database at {settings.sqlite_path}"
    return {course.id: course for course in courses}


def _normalise(course: Course) -> dict[str, object]:
    normalised: dict[str, object] = {}
    for field in COMPARISON_FIELDS:
        value = getattr(course, field)
        if isinstance(value, datetime):
            value = value.astimezone(timezone.utc)
        normalised[field] = value
    return normalised


def test_json_and_database_courses_are_in_sync(json_courses, db_courses, pytestconfig):
    reporter = pytestconfig.pluginmanager.getplugin("terminalreporter")
    if reporter:
        reporter.write_line(
            "Loaded courses counts -> JSON: "
            f"{len(json_courses)} | SQLite: {len(db_courses)}"
        )

    assert json_courses.keys() == db_courses.keys(), (
        "JSON and database contain different course IDs: "
        f"only_json={sorted(json_courses.keys() - db_courses.keys())}, "
        f"only_db={sorted(db_courses.keys() - json_courses.keys())}"
    )

    mismatches = []
    for course_id in sorted(json_courses):
        json_data = _normalise(json_courses[course_id])
        db_data = _normalise(db_courses[course_id])
        diff = {
            field: (json_data[field], db_data[field])
            for field in COMPARISON_FIELDS
            if json_data[field] != db_data[field]
        }
        if diff:
            mismatches.append((course_id, diff))

    assert not mismatches, (
        "Found mismatched course records between JSON and database. Sample diffs: "
        + "; ".join(
            f"{course_id}: "
            + ", ".join(
                f"{field} (json={json_val!r}, db={db_val!r})" for field, (json_val, db_val) in diffs.items()
            )
            for course_id, diffs in mismatches[:3]
        )
    )
