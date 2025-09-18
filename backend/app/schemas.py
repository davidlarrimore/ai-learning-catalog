"""Pydantic models for API requests/responses."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CourseBase(BaseModel):
    provider: str = ""
    link: str = Field(default="", examples=["https://example.com/course"])
    course_name: str = ""
    summary: str = ""
    track: str = ""
    platform: str = ""
    hands_on: str = "Unknown"
    skill_level: str = "Unknown"
    difficulty: str = "Unknown"
    length: str = "0 Hours"
    evidence_of_completion: str = "Unknown"

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class CourseCreate(CourseBase):
    ...


class CourseUpdate(BaseModel):
    provider: Optional[str] = None
    link: Optional[str] = None
    course_name: Optional[str] = None
    summary: Optional[str] = None
    track: Optional[str] = None
    platform: Optional[str] = None
    hands_on: Optional[str] = None
    skill_level: Optional[str] = None
    difficulty: Optional[str] = None
    length: Optional[str] = None
    evidence_of_completion: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class CourseOut(CourseBase):
    ...


class CourseFilters(BaseModel):
    provider: list[str] = Field(default_factory=list)
    platform: list[str] = Field(default_factory=list)
    difficulty: list[str] = Field(default_factory=list)
    skill_level: list[str] = Field(default_factory=list, alias="skillLevel")
    hands_on: list[str] = Field(default_factory=list, alias="handsOn")
    track: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class CourseListResponse(BaseModel):
    items: list[CourseOut]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")
    total_pages: int = Field(alias="totalPages")
    available_filters: CourseFilters = Field(default_factory=CourseFilters, alias="availableFilters")

    model_config = ConfigDict(populate_by_name=True)


class CourseEnrichRequest(BaseModel):
    link: HttpUrl
    provider: Optional[str] = None
    course_name: Optional[str] = Field(default=None, alias="courseName")

    model_config = ConfigDict(populate_by_name=True, extra="ignore")
