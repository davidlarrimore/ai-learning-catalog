"""FastAPI application for managing training courses."""
from __future__ import annotations

from celery.exceptions import TimeoutError
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .course_model import ensure_store

from .config import get_settings
from .enrichment import CourseEnricher
from .repository import CourseRepository
from .schemas import CourseCreate, CourseEnrichRequest, CourseOut, CourseUpdate
from .tasks import (
    add_course_task,
    enrich_course_task,
    list_courses_task,
    update_course_task,
)

app = FastAPI(title="Training Processing API", version="0.1.0")


def _get_timeout() -> int:
    return int(getattr(get_settings(), "task_timeout", None) or 10)


def _get_repo() -> CourseRepository:
    settings = get_settings()
    ensure_store(settings.courses_path)
    return CourseRepository(settings.courses_path)


def _validate_course_payload(payload: dict[str, str]) -> CourseOut:
    return CourseOut.model_validate(payload)


def _fallback_list() -> list[CourseOut]:
    repo = _get_repo()
    return [
        CourseOut.model_validate(course.model_dump())
        for course in repo.list_courses()
    ]


def _fallback_create(payload: dict[str, str]) -> CourseOut:
    repo = _get_repo()
    course = repo.add_course(payload)
    return CourseOut.model_validate(course.model_dump())


def _fallback_update(link: str, payload: dict[str, str]) -> CourseOut:
    repo = _get_repo()
    try:
        course = repo.update_course("link", link, payload)
    except KeyError as exc:
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


@app.get("/courses", response_model=list[CourseOut])
def list_courses() -> list[CourseOut]:
    async_result = list_courses_task.delay()
    try:
        payload = async_result.get(timeout=_get_timeout())
    except TimeoutError:  # pragma: no cover - defensive
        return _fallback_list()
    return [CourseOut.model_validate(course) for course in payload]


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
    data = update.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields provided for update")
    async_result = update_course_task.delay(course_link, data)
    try:
        payload = async_result.get(timeout=_get_timeout())
    except TimeoutError:  # pragma: no cover - defensive
        return _fallback_update(course_link, data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
