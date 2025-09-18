"""Shared course data model and JSON storage helpers."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Course(BaseModel):
    """Canonical representation of a course row."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    provider: str = Field(default="", alias="Provider")
    link: str = Field(default="", alias="Link")
    course_name: str = Field(default="Unknown", alias="Course Name")
    summary: str = Field(default="Unknown", alias="Summary")
    track: str = Field(default="", alias="Track")
    platform: str = Field(default="", alias="Platform")
    hands_on: str = Field(default="Unknown", alias="Hands On")
    skill_level: str = Field(default="Unknown", alias="Skill Level")
    difficulty: str = Field(default="Unknown", alias="Difficulty")
    length: str = Field(default="0 Hours", alias="Length")
    evidence_of_completion: str = Field(default="Unknown", alias="Evidence of Completion")

    @field_validator(
        "provider",
        "link",
        "course_name",
        "summary",
        "track",
        "platform",
        "hands_on",
        "skill_level",
        "difficulty",
        "length",
        "evidence_of_completion",
        mode="before",
    )
    @classmethod
    def _ensure_string(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, list):
            return ", ".join(str(v).strip() for v in value if str(v).strip())
        return str(value)

    @model_validator(mode="after")
    def _apply_defaults(self) -> "Course":
        def norm(data: str, default: str) -> str:
            return data.strip() or default

        self.provider = norm(self.provider, "")
        self.link = norm(self.link, "")
        self.course_name = norm(self.course_name, "Unknown")
        self.summary = norm(self.summary, "Unknown")
        self.track = self.track.strip()
        self.platform = self.platform.strip()
        self.hands_on = norm(self.hands_on, "Unknown")
        self.skill_level = norm(self.skill_level, "Unknown")
        self.difficulty = norm(self.difficulty, "Unknown")
        self.length = norm(self.length, "0 Hours")
        self.evidence_of_completion = norm(self.evidence_of_completion, "Unknown")
        return self

    def to_dict(self) -> dict[str, str]:
        return self.model_dump(by_alias=True)


def _ensure_path(path: str | Path) -> Path:
    return Path(path).expanduser()


DEFAULT_SOURCE_PATH = Path(os.getenv("SOURCE_COURSES_PATH", "data/courses.json")).expanduser()
DEFAULT_WORKING_PATH = Path(os.getenv("WORKING_COURSES_PATH", "working/courses.json")).expanduser()


@dataclass
class _CachedStore:
    """In-memory snapshot of a course store."""

    courses: list[Course]
    mtime: float


_CACHE_LOCK = RLock()
_STORE_CACHE: Dict[Path, _CachedStore] = {}


def _resolve(path: Path) -> Path:
    return path.resolve()


def _clone_courses(courses: Sequence[Course]) -> list[Course]:
    return [course.model_copy(deep=True) for course in courses]


def _read_courses_from_disk(path: Path) -> list[Course]:
    try:
        with path.open(encoding="utf-8") as fh:
            raw = json.load(fh) or []
    except json.JSONDecodeError:
        raw = []
    if not isinstance(raw, list):
        raise ValueError(f"Expected a list of courses in {path}, got {type(raw).__name__}")
    return [Course.model_validate(item or {}) for item in raw]


def _get_store(path: Path) -> _CachedStore:
    resolved = _resolve(path)
    with _CACHE_LOCK:
        cached = _STORE_CACHE.get(resolved)
        mtime = resolved.stat().st_mtime if resolved.exists() else 0.0
        if cached is None or cached.mtime < mtime:
            courses = _read_courses_from_disk(resolved) if resolved.exists() else []
            cached = _CachedStore(courses=courses, mtime=mtime)
            _STORE_CACHE[resolved] = cached
        return cached


def ensure_store(path: str | Path) -> Path:
    p = _resolve(_ensure_path(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("[]\n", encoding="utf-8")
        with _CACHE_LOCK:
            _STORE_CACHE[p] = _CachedStore(courses=[], mtime=p.stat().st_mtime)
    return p


def clear_store(path: str | Path) -> None:
    p = _resolve(_ensure_path(path))
    if p.exists():
        p.unlink()
    with _CACHE_LOCK:
        _STORE_CACHE.pop(p, None)


def load_courses(path: str | Path) -> List[Course]:
    p = ensure_store(path)
    store = _get_store(p)
    return _clone_courses(store.courses)


def save_courses(path: str | Path, courses: Sequence[Course]) -> None:
    p = ensure_store(path)
    normalised = [c if isinstance(c, Course) else Course.model_validate(c or {}) for c in courses]
    payload = [course.to_dict() for course in normalised]
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mtime = p.stat().st_mtime if p.exists() else 0.0
    with _CACHE_LOCK:
        _STORE_CACHE[p] = _CachedStore(courses=_clone_courses(normalised), mtime=mtime)


def append_course(path: str | Path, course: Course) -> None:
    existing = load_courses(path)
    existing.append(course if isinstance(course, Course) else Course.model_validate(course or {}))
    save_courses(path, existing)


def load_processed_links(path: str | Path) -> set[str]:
    return {course.link for course in load_courses(path) if course.link}


def placeholder_course(provider: str, link: str) -> Course:
    return Course(Provider=provider or "", Link=link or "")


def courses_from_iter(raw_rows: Iterable[dict[str, Any]]) -> List[Course]:
    return [Course.model_validate(row or {}) for row in raw_rows]


def load_source_courses(path: str | Path | None = None) -> List[Course]:
    return load_courses(path or DEFAULT_SOURCE_PATH)


def load_working_courses(path: str | Path | None = None) -> List[Course]:
    store = ensure_store(path or DEFAULT_WORKING_PATH)
    return load_courses(store)


def ensure_working_copy(
    source: str | Path | None = None,
    destination: str | Path | None = None,
    *,
    overwrite: bool = False,
) -> Path:
    src = _ensure_path(source or DEFAULT_SOURCE_PATH)
    dest = _ensure_path(destination or DEFAULT_WORKING_PATH)
    if overwrite or not dest.exists():
        courses = load_courses(src)
        save_courses(dest, courses)
    else:
        ensure_store(dest)
    return dest


def find_course_by_link(courses: Sequence[Course], link: str) -> Optional[Course]:
    target = (link or "").strip()
    if not target:
        return None
    for course in courses:
        if course.link.strip() == target:
            return course
    return None


def update_course_record(
    path: str | Path,
    link: str,
    updater: Callable[[Course], Course | dict[str, Any] | None],
    *,
    create_missing: bool = False,
) -> Course:
    courses = load_courses(path)
    target_link = (link or "").strip()
    if not target_link:
        raise ValueError("A non-empty link is required to update a course.")

    current = find_course_by_link(courses, target_link)
    if current is None:
        if not create_missing:
            raise ValueError(f"Course with link '{target_link}' not found in {path}.")
        current = placeholder_course("", target_link)
        courses.append(current)

    result = updater(current)
    if isinstance(result, Course):
        updated = result
    elif isinstance(result, dict):
        updated = current.model_copy(update=result)
    elif result is None:
        updated = current
    else:
        raise TypeError("Updater must return Course, dict, or None.")

    # Replace the course in collection
    for idx, existing in enumerate(courses):
        if existing.link.strip() == target_link:
            courses[idx] = updated
            break

    save_courses(path, courses)
    return updated


def upsert_course(path: str | Path, course: Course) -> Course:
    def _updater(_: Course) -> Course:
        return course

    return update_course_record(path, course.link, _updater, create_missing=True)


def publish_working_to_source(
    *,
    source: str | Path | None = None,
    working: str | Path | None = None,
) -> Path:
    src = _ensure_path(source or DEFAULT_SOURCE_PATH)
    work = _ensure_path(working or DEFAULT_WORKING_PATH)
    courses = load_courses(work)
    save_courses(src, courses)
    return src
