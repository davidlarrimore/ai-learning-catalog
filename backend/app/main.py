"""FastAPI application for managing training courses."""
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import unquote

from celery.exceptions import TimeoutError
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .course_model import ensure_store
from .config import get_settings
from .enrichment import CourseEnricher
from .repository import CourseRepository
from .schemas import (
    CourseCreate,
    CourseEnrichRequest,
    CourseListResponse,
    CourseOut,
    CourseUpdate,
)
from .tasks import (
    add_course_task,
    enrich_course_task,
    list_courses_task,
    update_course_task,
)

app = FastAPI(title="Training Processing API", version="0.1.0")

MAX_PAGE_SIZE = 100


def _get_timeout() -> int:
    return int(getattr(get_settings(), "task_timeout", None) or 10)


def _get_repo() -> CourseRepository:
    settings = get_settings()
    ensure_store(settings.courses_path)
    return CourseRepository(settings.courses_path)


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
    return CourseOut.model_validate(course.model_dump())


def _fallback_update(link: str, payload: dict[str, str]) -> CourseOut:
    repo = _get_repo()
    print(f"DEBUG FALLBACK: Updating with link='{link}'")
    try:
        course = repo.update_course("link", link, payload)
    except KeyError as exc:
        print(f"DEBUG FALLBACK: KeyError: {exc}")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
    try:
        course = repo.update_course("link", data["link"], data)
    except KeyError:
        course = repo.add_course(data)
    return CourseOut.model_validate(course.model_dump())


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

    async_result = list_courses_task.delay(options)
    try:
        payload = async_result.get(timeout=_get_timeout())
    except TimeoutError:  # pragma: no cover - defensive
        return _fallback_list(options)
    return CourseListResponse.model_validate(payload)


@app.post("/courses", response_model=CourseOut, status_code=201)
def create_course(course: CourseCreate) -> CourseOut:
    payload = course.model_dump()
    async_result = add_course_task.delay(payload)
    try:
        data = async_result.get(timeout=_get_timeout())
    except TimeoutError:  # pragma: no cover - defensive
        return _fallback_create(payload)
    return _validate_course_payload(data)


@app.put("/courses/{course_link:path}", response_model=CourseOut)
def update_course(course_link: str, update: CourseUpdate) -> CourseOut:
    """Update a course by its link (URL path parameter)."""
    data = update.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields provided for update")
    
    # FastAPI partially decodes path parameters, so we need to reconstruct the full URL
    # If we see 'https:/' it means 'https://' was sent as 'https%3A%2F%2F' but got partially decoded
    if course_link.startswith('https:/') and not course_link.startswith('https://'):
        # Reconstruct the proper URL - FastAPI decoded %2F to / but left %3A as :
        decoded_link = course_link.replace('https:/', 'https://')
        print(f"DEBUG API: Fixed partial decode: '{course_link}' -> '{decoded_link}'")
    elif course_link.startswith('http:/') and not course_link.startswith('http://'):
        # Handle http URLs too
        decoded_link = course_link.replace('http:/', 'http://')
        print(f"DEBUG API: Fixed partial decode: '{course_link}' -> '{decoded_link}'")
    else:
        # For other cases, try normal URL decoding
        decoded_link = unquote(course_link)
        print(f"DEBUG API: Standard decode: '{course_link}' -> '{decoded_link}'")
    
    print(f"DEBUG API: Final decoded link: '{decoded_link}'")
    
    async_result = update_course_task.delay(decoded_link, data)
    try:
        payload = async_result.get(timeout=_get_timeout())
    except TimeoutError:  # pragma: no cover - defensive
        print("DEBUG API: Celery timeout, using fallback")
        return _fallback_update(decoded_link, data)
    except KeyError as exc:
        print(f"DEBUG API: KeyError from Celery: {exc}")
        raise HTTPException(status_code=404, detail=f"Course not found: {str(exc)}") from exc
    
    return _validate_course_payload(payload)


@app.post("/courses/enrich", response_model=CourseOut, status_code=202)
def enrich_course(request: CourseEnrichRequest) -> CourseOut:
    data = request.model_dump()
    data["link"] = str(data["link"])
    async_result = enrich_course_task.delay(data)
    try:
        payload = async_result.get(timeout=_get_timeout())
    except TimeoutError:  # pragma: no cover - defensive
        return _fallback_enrich(data)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _validate_course_payload(payload)
