"""Helpers to enrich course metadata using OpenAI."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup
from openai import OpenAI

from .config import get_settings
from .logging_config import setup_logging


setup_logging()

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CourseMetadata:
    provider: str
    link: str
    course_name: str
    summary: str
    track: str
    platform: str
    hands_on: str
    skill_level: str
    difficulty: str
    length: str
    evidence_of_completion: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CourseMetadata":
        """Create a :class:`CourseMetadata` ensuring all fields exist."""

        defaults = {
            "provider": "",
            "link": "",
            "course_name": "Unknown",
            "summary": "Unknown",
            "track": "",
            "platform": "",
            "hands_on": "Unknown",
            "skill_level": "Unknown",
            "difficulty": "Unknown",
            "length": "0 Hours",
            "evidence_of_completion": "Unknown",
        }
        data = {**defaults, **payload}
        return cls(**data)

    def to_dict(self) -> dict[str, str]:
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


class CourseEnricher:
    """Fetch course context and call OpenAI to synthesise metadata."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            msg = "OPENAI_API_KEY is not configured"
            raise RuntimeError(msg)
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.timeout = settings.openai_request_timeout
        self.max_chars = settings.openai_context_chars

    def enrich(
        self,
        *,
        link: str,
        provider: Optional[str] = None,
        course_name: Optional[str] = None,
    ) -> CourseMetadata:
        logger.info("Starting enrichment for %s", link)
        page_text = self._fetch_text(link)
        payload = self._call_openai(
            link=link,
            provider=provider,
            course_name=course_name,
            page_text=page_text,
        )
        payload.setdefault("link", link)
        if provider:
            payload.setdefault("provider", provider)
        if course_name:
            payload.setdefault("course_name", course_name)
        logger.info("Completed enrichment for %s", link)
        return CourseMetadata.from_dict(payload)

    def _fetch_text(self, link: str) -> str:
        """Fetch and condense the course page for prompting."""

        try:
            logger.debug("Fetching course page %s", link)
            response = httpx.get(link, follow_redirects=True, timeout=self.timeout)
            response.raise_for_status()
        except Exception as exc:  # pragma: no cover - network variability
            logger.error("Failed to fetch course page %s: %s", link, exc)
            raise RuntimeError(f"Failed to fetch course page: {exc}") from exc

        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        text = " ".join(text.split())
        if len(text) > self.max_chars:
            text = text[: self.max_chars]
        return text

    def _call_openai(
        self,
        *,
        link: str,
        provider: Optional[str],
        course_name: Optional[str],
        page_text: str,
    ) -> dict[str, Any]:
        system_prompt = (
            "You extract structured metadata for online training courses. "
            "Use only the information provided. When unsure, respond with "
            "'Unknown' for the respective field. Return concise values."
        )
        user_prompt = (
            "Generate course metadata with the following JSON keys: "
            "provider, link, course_name, summary, track, platform, hands_on, "
            "skill_level, difficulty, length, evidence_of_completion."
            f"\nCourse link: {link}\n"
            f"Provider (may be missing): {provider or 'Unknown'}\n"
            f"Course name (may be missing): {course_name or 'Unknown'}\n"
            "Course page content (truncated):\n" + page_text
        )
        result = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        content = result.choices[0].message.content
        try:
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            return data
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to parse OpenAI response for %s: %s", link, exc)
            raise RuntimeError(f"Failed to parse OpenAI response: {exc}") from exc
