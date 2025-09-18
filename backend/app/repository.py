"""Persistence helpers backed by a SQLite database."""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .course_model import Course, course_sort_key, load_courses
from redis import Redis


SQLITE_PRAGMAS = (
    "PRAGMA journal_mode=WAL;",
    "PRAGMA synchronous=NORMAL;",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    link TEXT NOT NULL UNIQUE,
    version INTEGER NOT NULL DEFAULT 1,
    provider TEXT NOT NULL DEFAULT '',
    course_name TEXT NOT NULL DEFAULT 'Unknown',
    summary TEXT NOT NULL DEFAULT 'Unknown',
    track TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    hands_on TEXT NOT NULL DEFAULT 'Unknown',
    skill_level TEXT NOT NULL DEFAULT 'Unknown',
    difficulty TEXT NOT NULL DEFAULT 'Unknown',
    length TEXT NOT NULL DEFAULT '0 Hours',
    evidence_of_completion TEXT NOT NULL DEFAULT 'Unknown',
    date_created TEXT NOT NULL,
    last_updated TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_courses_provider ON courses(provider);
CREATE INDEX IF NOT EXISTS idx_courses_difficulty ON courses(difficulty);
CREATE INDEX IF NOT EXISTS idx_courses_skill_level ON courses(skill_level);
CREATE INDEX IF NOT EXISTS idx_courses_track ON courses(track);
"""


FILTERABLE_COLUMNS = (
    "provider",
    "platform",
    "difficulty",
    "skill_level",
    "hands_on",
    "track",
)

SEARCH_COLUMNS = (
    "course_name",
    "summary",
    "provider",
    "platform",
    "track",
)


class VersionConflictError(RuntimeError):
    """Raised when an optimistic concurrency check fails."""


def _normalize_course(course: Course | Mapping[str, Any]) -> Course:
    return course if isinstance(course, Course) else Course.model_validate(dict(course))


def _dict_from_course(course: Course) -> dict[str, Any]:
    # ``mode="json"`` ensures datetimes are serialised to ISO strings.
    return course.model_dump(by_alias=True, mode="json")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialise_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        return value
    raise TypeError(f"Unsupported datetime value: {value!r}")


def _course_to_db_payload(course: Course, **overrides: Any) -> dict[str, Any]:
    data = course.model_dump()
    data.update(overrides)
    data["date_created"] = _serialise_datetime(data["date_created"])
    data["last_updated"] = _serialise_datetime(data["last_updated"])
    return data


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Unsupported datetime payload: {value!r}")


COURSE_COLUMNS: tuple[str, ...] = (
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
)


_MISSING = object()

DRAFT_KEY_PREFIX = "courses:draft:"


def _normalise_course_fields(payload: Mapping[str, Any]) -> dict[str, str]:
    course = _normalize_course(payload)
    data = course.model_dump()
    return {column: data[column] for column in COURSE_COLUMNS}


def _draft_key(draft_id: str) -> str:
    return f"{DRAFT_KEY_PREFIX}{draft_id}"


def _loads_draft(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


@dataclass
class CourseQueryResult:
    items: list[Course]
    total: int
    page: int
    page_size: int
    total_pages: int
    available_filters: dict[str, list[str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "items": [item.model_dump() for item in self.items],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
            "available_filters": self.available_filters,
        }


@dataclass
class CourseDraft:
    id: str
    status: str
    status_message: str
    link: str
    provider: str
    course_name: str
    summary: str
    track: str
    platform: str
    hands_on: str
    skill_level: str
    difficulty: str
    length: str
    evidence_of_completion: str
    task_id: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime

    def course_payload(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "link": self.link,
            "course_name": self.course_name,
            "summary": self.summary,
            "track": self.track,
            "platform": self.platform,
            "hands_on": self.hands_on,
            "skill_level": self.skill_level,
            "difficulty": self.difficulty,
            "length": self.length,
            "evidence_of_completion": self.evidence_of_completion,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.course_payload()
        payload.update(
            {
                "id": self.id,
                "status": self.status,
                "status_message": self.status_message,
                "task_id": self.task_id,
                "error": self.error,
                "created_at": self.created_at.isoformat(),
                "updated_at": self.updated_at.isoformat(),
            }
        )
        return payload

    def as_dict(self) -> dict[str, Any]:
        return self.to_dict()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CourseDraft":
        base = {column: payload.get(column) for column in COURSE_COLUMNS}
        normalised = _normalise_course_fields({k: v for k, v in base.items() if v is not None})
        created_raw = payload.get("created_at") or _utc_now_iso()
        updated_raw = payload.get("updated_at") or created_raw
        return cls(
            id=str(payload.get("id") or uuid.uuid4().hex),
            status=str(payload.get("status") or "pending"),
            status_message=str(payload.get("status_message") or ""),
            link=normalised.get("link", ""),
            provider=normalised.get("provider", ""),
            course_name=normalised.get("course_name", ""),
            summary=normalised.get("summary", "Unknown"),
            track=normalised.get("track", ""),
            platform=normalised.get("platform", ""),
            hands_on=normalised.get("hands_on", "Unknown"),
            skill_level=normalised.get("skill_level", "Unknown"),
            difficulty=normalised.get("difficulty", "Unknown"),
            length=normalised.get("length", "0 Hours"),
            evidence_of_completion=normalised.get("evidence_of_completion", "Unknown"),
            task_id=(payload.get("task_id") or None),
            error=(payload.get("error") or None),
            created_at=_parse_datetime(created_raw),
            updated_at=_parse_datetime(updated_raw),
        )


class CourseRepository:
    """SQLite-backed course repository with Redis-backed draft storage."""

    def __init__(
        self,
        db_path: Path,
        seed_json: Path | None = None,
        *,
        redis_url: str | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.seed_json = Path(seed_json) if seed_json else None
        self._redis_url = redis_url
        self._redis: Redis | None = None
        self._initialise()

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        for pragma in SQLITE_PRAGMAS:
            conn.execute(pragma)
        return conn

    def _initialise(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._apply_migrations(conn)
        self._seed_from_json_if_needed()

    def _get_redis(self) -> Redis:
        if not self._redis_url:
            raise RuntimeError("Redis URL is not configured for draft storage")
        if self._redis is None:
            self._redis = Redis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _load_draft(self, draft_id: str) -> CourseDraft | None:
        redis = self._get_redis()
        data = _loads_draft(redis.get(_draft_key(draft_id)))
        if data is None:
            return None
        return CourseDraft.from_dict(data)

    def _persist_draft(self, draft: CourseDraft) -> CourseDraft:
        redis = self._get_redis()
        payload = json.dumps(draft.to_dict(), ensure_ascii=False)
        redis.set(_draft_key(draft.id), payload)
        return draft

    def _remove_draft(self, draft_id: str) -> None:
        redis = self._get_redis()
        redis.delete(_draft_key(draft_id))

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        info = self._table_columns(conn, "courses")
        if not info:
            return
        required = {"id", "version", "link"}
        if not required.issubset(info.keys()):
            self._migrate_legacy_courses(conn)
            info = self._table_columns(conn, "courses")

        missing_timestamps = {"date_created", "last_updated"} - set(info.keys())
        if missing_timestamps:
            self._add_timestamp_columns(conn, missing_timestamps)

    def _table_columns(self, conn: sqlite3.Connection, table: str) -> dict[str, sqlite3.Row]:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row["name"]: row for row in rows}

    def _migrate_legacy_courses(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT provider, link, course_name, summary, track, platform, hands_on, "
            "skill_level, difficulty, length, evidence_of_completion FROM courses"
        ).fetchall()
        conn.execute("ALTER TABLE courses RENAME TO courses_legacy")
        conn.executescript(SCHEMA)

        insert_sql = (
            """
            INSERT INTO courses (
                id, link, version, provider, course_name, summary, track, platform,
                hands_on, skill_level, difficulty, length, evidence_of_completion,
                date_created, last_updated
            ) VALUES (
                :id, :link, :version, :provider, :course_name, :summary, :track, :platform,
                :hands_on, :skill_level, :difficulty, :length, :evidence_of_completion,
                :date_created, :last_updated
            )
            """
        )

        for row in rows:
            course = _normalize_course(dict(row))
            payload = _course_to_db_payload(course)
            conn.execute(insert_sql, payload)

        conn.execute("DROP TABLE IF EXISTS courses_legacy")
        conn.commit()

    def _add_timestamp_columns(self, conn: sqlite3.Connection, missing: set[str]) -> None:
        for column in missing:
            conn.execute(f"ALTER TABLE courses ADD COLUMN {column} TEXT")

        now_iso = _utc_now_iso()
        if "date_created" in missing:
            conn.execute(
                "UPDATE courses SET date_created = COALESCE(date_created, last_updated, ?)",
                (now_iso,),
            )
        if "last_updated" in missing:
            conn.execute(
                "UPDATE courses SET last_updated = COALESCE(last_updated, date_created, ?)",
                (now_iso,),
            )
        conn.execute(
            "UPDATE courses SET date_created = COALESCE(date_created, ?), last_updated = COALESCE(last_updated, ?)",
            (now_iso, now_iso),
        )
        conn.commit()

    def _seed_from_json_if_needed(self) -> None:
        if not self.seed_json or not self.seed_json.exists():
            return
        with self._connect() as conn:
            total, = conn.execute("SELECT COUNT(*) FROM courses").fetchone()
            if total:
                return
            courses = load_courses(self.seed_json)
            if not courses:
                return
            payload = [
                (
                    course.id,
                    course.link,
                    course.version,
                    course.provider,
                    course.course_name,
                    course.summary,
                    course.track,
                    course.platform,
                    course.hands_on,
                    course.skill_level,
                    course.difficulty,
                    course.length,
                    course.evidence_of_completion,
                    _serialise_datetime(course.date_created),
                    _serialise_datetime(course.last_updated),
                )
                for course in courses
            ]
            conn.executemany(
                """
                INSERT OR IGNORE INTO courses (
                    id, link, version, provider, course_name, summary,
                    track, platform, hands_on, skill_level, difficulty,
                    length, evidence_of_completion, date_created, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            conn.commit()

    def _row_to_course(self, row: sqlite3.Row | Mapping[str, Any]) -> Course:
        return _normalize_course(dict(row))

    def get_course_by_id(self, course_id: str) -> Course | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, link, version, provider, course_name, summary, track, platform, "
                "hands_on, skill_level, difficulty, length, evidence_of_completion, "
                "date_created, last_updated "
                "FROM courses WHERE id = ?",
                (course_id,),
            ).fetchone()
        return self._row_to_course(row) if row else None

    def get_course_by_link(self, link: str) -> Course | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, link, version, provider, course_name, summary, track, platform, "
                "hands_on, skill_level, difficulty, length, evidence_of_completion, "
                "date_created, last_updated "
                "FROM courses WHERE link = ?",
                (link,),
            ).fetchone()
        return self._row_to_course(row) if row else None

    def get_draft(self, draft_id: str) -> CourseDraft | None:
        return self._load_draft(draft_id)

    # ------------------------------------------------------------------
    # Draft course helpers
    # ------------------------------------------------------------------
    def create_or_reset_draft(
        self,
        *,
        link: str,
        provider: str = "",
        course_name: str = "",
    ) -> CourseDraft:
        cleaned_link = link.strip()
        if not cleaned_link:
            raise ValueError("Course draft requires a link")
        base_payload: dict[str, Any] = {"link": cleaned_link}
        if provider:
            base_payload["provider"] = provider
        if course_name:
            base_payload["course_name"] = course_name

        course_fields = _normalise_course_fields(base_payload)
        now = datetime.now(timezone.utc)
        draft = CourseDraft(
            id=uuid.uuid4().hex,
            status="pending",
            status_message="Draft queued for processing",
            link=course_fields["link"],
            provider=course_fields["provider"],
            course_name=course_fields["course_name"],
            summary=course_fields["summary"],
            track=course_fields["track"],
            platform=course_fields["platform"],
            hands_on=course_fields["hands_on"],
            skill_level=course_fields["skill_level"],
            difficulty=course_fields["difficulty"],
            length=course_fields["length"],
            evidence_of_completion=course_fields["evidence_of_completion"],
            task_id=None,
            error=None,
            created_at=now,
            updated_at=now,
        )
        return self._persist_draft(draft)

    def update_draft(
        self,
        draft_id: str,
        *,
        status: str | None = None,
        message: str | None = None,
        task_id: Any = _MISSING,
        error: Any = _MISSING,
        course_payload: Mapping[str, Any] | None = None,
    ) -> CourseDraft:
        draft = self._load_draft(draft_id)
        if draft is None:
            raise KeyError(f"Draft not found: {draft_id}")
        updated = False
        if course_payload is not None:
            combined = {**draft.course_payload(), **course_payload}
            course_fields = _normalise_course_fields(combined)
            draft.link = course_fields["link"]
            draft.provider = course_fields["provider"]
            draft.course_name = course_fields["course_name"]
            draft.summary = course_fields["summary"]
            draft.track = course_fields["track"]
            draft.platform = course_fields["platform"]
            draft.hands_on = course_fields["hands_on"]
            draft.skill_level = course_fields["skill_level"]
            draft.difficulty = course_fields["difficulty"]
            draft.length = course_fields["length"]
            draft.evidence_of_completion = course_fields["evidence_of_completion"]
            updated = True
        if status is not None:
            draft.status = status
            updated = True
        if message is not None:
            draft.status_message = message
            updated = True
        if task_id is not _MISSING:
            draft.task_id = str(task_id) if task_id else None
            updated = True
        if error is not _MISSING:
            draft.error = str(error) if error else None
            updated = True

        if not updated:
            return draft

        draft.updated_at = datetime.now(timezone.utc)
        return self._persist_draft(draft)

    def delete_draft(self, draft_id: str) -> None:
        self._remove_draft(draft_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_courses(self) -> list[Course]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, link, version, provider, course_name, summary, track, platform, "
                "hands_on, skill_level, difficulty, length, evidence_of_completion, "
                "date_created, last_updated "
                "FROM courses ORDER BY course_name COLLATE NOCASE"
            ).fetchall()
        return [self._row_to_course(row) for row in rows]

    def add_course(self, payload: Mapping[str, Any]) -> Course:
        course = _normalize_course(payload)
        data = course.model_dump()

        update_sql = (
            """
            UPDATE courses SET
                link = :link,
                provider = :provider,
                course_name = :course_name,
                summary = :summary,
                track = :track,
                platform = :platform,
                hands_on = :hands_on,
                skill_level = :skill_level,
                difficulty = :difficulty,
                length = :length,
                evidence_of_completion = :evidence_of_completion,
                version = :version,
                date_created = :date_created,
                last_updated = :last_updated
            WHERE id = :id
            """
        )

        insert_sql = (
            """
            INSERT INTO courses (
                id, link, version, provider, course_name, summary, track, platform,
                hands_on, skill_level, difficulty, length, evidence_of_completion,
                date_created, last_updated
            ) VALUES (
                :id, :link, :version, :provider, :course_name, :summary, :track, :platform,
                :hands_on, :skill_level, :difficulty, :length, :evidence_of_completion,
                :date_created, :last_updated
            )
            """
        )

        select_sql = (
            "SELECT id, link, version, provider, course_name, summary, track, platform, "
            "hands_on, skill_level, difficulty, length, evidence_of_completion, "
            "date_created, last_updated "
            "FROM courses WHERE id = ?"
        )

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id, version, date_created FROM courses WHERE link = ?",
                (data["link"],),
            ).fetchone()

            if existing:
                course_id = existing["id"]
                next_version = int(existing["version"]) + 1
                now_iso = _utc_now_iso()
                payload = _course_to_db_payload(
                    course,
                    id=course_id,
                    version=next_version,
                    date_created=existing["date_created"],
                    last_updated=now_iso,
                )
                conn.execute(update_sql, payload)
                conn.commit()
                row = conn.execute(select_sql, (course_id,)).fetchone()
            else:
                now_iso = _utc_now_iso()
                payload = _course_to_db_payload(
                    course,
                    date_created=now_iso,
                    last_updated=now_iso,
                )
                conn.execute(insert_sql, payload)
                conn.commit()
                row = conn.execute(select_sql, (payload["id"],)).fetchone()

        return self._row_to_course(row)

    def update_course(
        self,
        course_id: str,
        payload: Mapping[str, Any],
        *,
        expected_version: int,
    ) -> Course:
        if expected_version < 1:
            raise ValueError("Version must be a positive integer")

        updates = {
            key: val
            for key, val in payload.items()
            if val is not None and key not in {"id", "version"}
        }
        if not updates:
            raise ValueError("No fields provided for update")

        set_clause = ", ".join(f"{column} = :{column}" for column in updates)
        params = dict(updates)
        params["id"] = course_id

        with self._connect() as conn:
            row = conn.execute(
                "SELECT version FROM courses WHERE id = ?",
                (course_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Course with id='{course_id}' not found")

            current_version = int(row["version"])
            if current_version != expected_version:
                raise VersionConflictError(
                    f"Course id='{course_id}' has version {current_version}, expected {expected_version}"
                )

            params["version"] = current_version + 1
            params["last_updated"] = _utc_now_iso()

            conn.execute(
                f"UPDATE courses SET {set_clause}, version = :version, last_updated = :last_updated WHERE id = :id",
                params,
            )
            conn.commit()
            updated = conn.execute(
                "SELECT id, link, version, provider, course_name, summary, track, platform, "
                "hands_on, skill_level, difficulty, length, evidence_of_completion, "
                "date_created, last_updated "
                "FROM courses WHERE id = ?",
                (course_id,),
            ).fetchone()

        if updated is None:
            raise KeyError(f"Course with id='{course_id}' not found")

        return self._row_to_course(updated)

    def query_courses(
        self,
        *,
        search: str | None = None,
        filters: Mapping[str, Iterable[str]] | None = None,
        page: int = 1,
        page_size: int = 25,
        include_filters: bool = True,
    ) -> CourseQueryResult:
        where_clauses: list[str] = []
        params: list[Any] = []

        if search and search.strip():
            like = f"%{search.strip().lower()}%"
            search_clause = " OR ".join(
                f"LOWER({column}) LIKE ?" for column in SEARCH_COLUMNS
            )
            where_clauses.append(f"({search_clause})")
            params.extend([like] * len(SEARCH_COLUMNS))

        if filters:
            for column, values in filters.items():
                if column not in FILTERABLE_COLUMNS:
                    continue
                values = [str(value).strip() for value in values if str(value).strip()]
                if not values:
                    continue
                placeholders = ",".join("?" for _ in values)
                where_clauses.append(f"{column} IN ({placeholders})")
                params.extend(values)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        page_size = max(1, min(int(page_size or 1), 200))
        page = max(1, int(page or 1))

        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM courses {where_sql}",
                params,
            ).fetchone()[0]

            total_pages = math.ceil(total / page_size) if total else 0
            if total_pages and page > total_pages:
                page = total_pages
            offset = (page - 1) * page_size if total else 0

            rows = conn.execute(
                "SELECT id, link, version, provider, course_name, summary, track, platform, hands_on, "
                "skill_level, difficulty, length, evidence_of_completion, date_created, last_updated "
                f"FROM courses {where_sql} ORDER BY course_name COLLATE NOCASE LIMIT ? OFFSET ?",
                (*params, page_size, offset),
            ).fetchall()

            available_filters: dict[str, list[str]] = {}
            if include_filters:
                for column in FILTERABLE_COLUMNS:
                    result = conn.execute(
                        f"SELECT DISTINCT {column} FROM courses WHERE {column} != '' ORDER BY {column} COLLATE NOCASE"
                    ).fetchall()
                    available_filters[column] = [row[column] for row in result if row[column]]

        courses = [self._row_to_course(row) for row in rows]

        return CourseQueryResult(
            items=courses,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            available_filters=available_filters,
        )

    def export_to_json(self, destination: Path) -> None:
        """Export all courses to a JSON file compatible with the existing format."""

        courses = sorted(self.list_courses(), key=course_sort_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = [_dict_from_course(course) for course in courses]
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
