"""FastAPI application for managing training courses."""
from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, cast

from celery.exceptions import TimeoutError
from fastapi import FastAPI, HTTPException, Query
from kombu.exceptions import OperationalError
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .enrichment import CourseEnricher
from .logging_config import setup_logging
from .repository import CourseDraft, CourseRepository, VersionConflictError
from .schemas import (
    CourseCreate,
    CourseDraftData,
    CourseDraftRequest,
    CourseDraftResponse,
    DraftStatus,
    CourseEnrichRequest,
    CourseListResponse,
    CourseOut,
    CourseUpdate,
)
from .tasks import (
    add_course_task,
    enrich_course_task,
    process_course_draft_sync,
    process_course_draft_task,
    update_course_task,
)

setup_logging()

app = FastAPI(title="Training Processing API", version="0.1.0")

logger = logging.getLogger(__name__)

CONFLICT_DETAIL = "Course link must be unique"

MAX_PAGE_SIZE = 100


def _get_timeout() -> int:
    return int(getattr(get_settings(), "task_timeout", None) or 10)


def _get_repo() -> CourseRepository:
    settings = get_settings()
    return CourseRepository(
        settings.sqlite_path,
        settings.courses_path,
        redis_url=settings.redis_url,
    )


def _validate_course_payload(payload: dict[str, str]) -> CourseOut:
    return CourseOut.model_validate(payload)


def _fallback_list(options: Dict[str, Any]) -> CourseListResponse:
    repo = _get_repo()
    result = repo.query_courses(**options)
    return CourseListResponse.model_validate(result.as_dict())


def _normalise_filters(**raw_filters: list[str]) -> dict[str, list[str]]:
    filtered: dict[str, list[str]] = {}
    for field, values in raw_filters.items():
        if not values:
            continue
        cleaned = [value.strip() for value in values if value and value.strip()]
        if cleaned:
            filtered[field] = cleaned
    return filtered


def _fallback_create(payload: dict[str, str]) -> CourseOut:
    repo = _get_repo()
    course = repo.add_course(payload)
    repo.export_to_json(get_settings().courses_path)
    return CourseOut.model_validate(course.model_dump())


def _fallback_update(course_id: str, payload: dict[str, Any], *, version: int) -> CourseOut:
    repo = _get_repo()
    print(f"DEBUG FALLBACK: Updating course_id='{course_id}' with version={version}")
    try:
        course = repo.update_course(course_id, payload, expected_version=version)
    except KeyError as exc:
        print(f"DEBUG FALLBACK: KeyError: {exc}")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VersionConflictError as exc:
        print(f"DEBUG FALLBACK: Version conflict: {exc}")
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        print(f"DEBUG FALLBACK: Integrity error: {exc}")
        raise HTTPException(status_code=409, detail=CONFLICT_DETAIL) from exc
    repo.export_to_json(get_settings().courses_path)
    return CourseOut.model_validate(course.model_dump())


def _fallback_enrich(payload: dict[str, str]) -> CourseOut:
    try:
        enricher = CourseEnricher()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    metadata = enricher.enrich(
        link=payload["link"],
        provider=payload.get("provider"),
        course_name=payload.get("course_name"),
    )
    repo = _get_repo()
    data = metadata.to_dict()
    course: CourseOut
    for attempt in range(2):
        existing = repo.get_course_by_link(data["link"])
        if existing is None:
            course_model = repo.add_course(data)
            course = CourseOut.model_validate(course_model.model_dump())
            break
        try:
            course_model = repo.update_course(
                existing.id,
                data,
                expected_version=existing.version,
            )
            course = CourseOut.model_validate(course_model.model_dump())
            break
        except VersionConflictError as exc:
            if attempt == 1:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            continue
    else:  # pragma: no cover - defensive
        raise HTTPException(status_code=409, detail="Failed to update course due to concurrent modification")
    repo.export_to_json(get_settings().courses_path)
    return course


def _draft_to_response(draft: CourseDraft) -> CourseDraftResponse:
    draft_data = CourseDraftData.model_validate(draft.course_payload())
    return CourseDraftResponse(
        id=draft.id,
        status=cast("DraftStatus", draft.status),
        message=draft.status_message or None,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
        task_id=draft.task_id,
        draft=draft_data,
        error=draft.error,
    )


def _process_draft_inline(draft_id: str) -> None:
    try:
        process_course_draft_sync(draft_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Inline draft processing failed", exc_info=exc)


def _remove_draft(draft_id: str | None) -> None:
    if not draft_id:
        return
    repo = _get_repo()
    try:
        repo.delete_draft(draft_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to delete draft %s: %s", draft_id, exc)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/courses", response_model=CourseListResponse)
def list_courses(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = Query(None, min_length=1),
    provider: list[str] = Query(default_factory=list),
    platform: list[str] = Query(default_factory=list),
    difficulty: list[str] = Query(default_factory=list),
    skill_level: list[str] = Query(default_factory=list),
    hands_on: list[str] = Query(default_factory=list),
    track: list[str] = Query(default_factory=list),
) -> CourseListResponse:
    options: Dict[str, Any] = {
        "page": page,
        "page_size": min(page_size, MAX_PAGE_SIZE),
        "search": search,
        "filters": _normalise_filters(
            provider=provider,
            platform=platform,
            difficulty=difficulty,
            skill_level=skill_level,
            hands_on=hands_on,
            track=track,
        ),
    }

    # Directly query SQLite for read-only requests so course listings return quickly.
    return _fallback_list(options)


@app.post("/courses", response_model=CourseOut, status_code=201)
def create_course(course: CourseCreate, draft_id: str | None = Query(None, alias="draft_id")) -> CourseOut:
    payload = course.model_dump()
    result: CourseOut
    try:
        async_result = add_course_task.delay(payload)
    except OperationalError as exc:  # Broker unavailable
        logger.warning("Celery broker unreachable, falling back to direct create", exc_info=exc)
        result = _fallback_create(payload)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Celery dispatch failed, falling back to direct create", exc_info=exc)
        result = _fallback_create(payload)
    else:
        try:
            data = async_result.get(timeout=_get_timeout())
        except TimeoutError:  # pragma: no cover - defensive
            result = _fallback_create(payload)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail=CONFLICT_DETAIL) from exc
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Celery task failed, falling back to direct create", exc_info=exc)
            result = _fallback_create(payload)
        else:
            result = _validate_course_payload(data)

    _remove_draft(draft_id)
    return result


@app.put("/courses/{course_id}", response_model=CourseOut)
def update_course(course_id: str, update: CourseUpdate) -> CourseOut:
    """Update a course by its unique identifier using optimistic concurrency control."""

    data = update.model_dump(exclude_unset=True)
    version = data.pop("version", None)
    if version is None:
        raise HTTPException(status_code=400, detail="Version is required for updates")
    if not data:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    try:
        async_result = update_course_task.delay(course_id, version, data)
    except OperationalError as exc:  # Broker unavailable
        logger.warning("Celery broker unreachable, falling back to direct update", exc_info=exc)
        return _fallback_update(course_id, data, version=version)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Celery dispatch failed, falling back to direct update", exc_info=exc)
        return _fallback_update(course_id, data, version=version)
    try:
        payload = async_result.get(timeout=_get_timeout())
    except TimeoutError:  # pragma: no cover - defensive
        print("DEBUG API: Celery timeout, using fallback")
        return _fallback_update(course_id, data, version=version)
    except KeyError as exc:
        print(f"DEBUG API: KeyError from Celery: {exc}")
        raise HTTPException(status_code=404, detail=f"Course not found: {str(exc)}") from exc
    except VersionConflictError as exc:
        print(f"DEBUG API: Version conflict from Celery: {exc}")
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=CONFLICT_DETAIL) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Celery task failed, falling back to direct update", exc_info=exc)
        return _fallback_update(course_id, data, version=version)

    return _validate_course_payload(payload)


@app.post("/courses/draft", response_model=CourseDraftResponse, status_code=202)
def create_course_draft(request: CourseDraftRequest) -> CourseDraftResponse:
    repo = _get_repo()
    link = str(request.link)

    try:
        draft = repo.create_or_reset_draft(
            link=link,
            provider=request.provider or "",
            course_name=request.course_name or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("Dispatching draft processing for %s (draft_id=%s)", link, draft.id)
    try:
        async_result = process_course_draft_task.delay(draft.id)
    except OperationalError as exc:  # Broker unavailable
        logger.warning("Celery broker unreachable, processing draft inline", exc_info=exc)
        _process_draft_inline(draft.id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Celery dispatch failed, processing draft inline", exc_info=exc)
        _process_draft_inline(draft.id)
    else:
        logger.info("Draft %s queued to Celery task %s", draft.id, async_result.id)
        repo.update_draft(
            draft.id,
            task_id=async_result.id,
            message="Draft queued for background processing",
        )

    refreshed = repo.get_draft(draft.id)
    if refreshed is None:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail="Draft not found")
    return _draft_to_response(refreshed)


@app.get("/courses/draft/{draft_id}", response_model=CourseDraftResponse)
def get_course_draft(draft_id: str) -> CourseDraftResponse:
    repo = _get_repo()
    draft = repo.get_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return _draft_to_response(draft)


@app.post("/courses/enrich", response_model=CourseOut, status_code=202)
def enrich_course(request: CourseEnrichRequest) -> CourseOut:
    data = request.model_dump()
    data["link"] = str(data["link"])
    try:
        async_result = enrich_course_task.delay(data)
    except OperationalError as exc:  # Broker unavailable
        logger.warning("Celery broker unreachable, falling back to direct enrich", exc_info=exc)
        return _fallback_enrich(data)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Celery dispatch failed, falling back to direct enrich", exc_info=exc)
        return _fallback_enrich(data)
    try:
        payload = async_result.get(timeout=_get_timeout())
    except TimeoutError:  # pragma: no cover - defensive
        return _fallback_enrich(data)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=CONFLICT_DETAIL) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Celery task failed, falling back to direct enrich", exc_info=exc)
        return _fallback_enrich(data)
    return _validate_course_payload(payload)
