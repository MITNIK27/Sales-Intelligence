"""Public job boards. Many companies publish their openings through Greenhouse, Lever or Ashby,
which expose them as open JSON. This module finds which board a company uses (from links on its
own careers page, never by guessing a name) and turns each board's response into plain postings.
Pure functions: fetching lives in `sources.py`.

Dates are only as good as the board gives. Greenhouse states when a posting was last updated and
Ashby when it was published; Lever's documented response has no date, so its postings are
undated here rather than given an invented one."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.modules.opportunity.research.types import Posting

_MAX_EXCERPT = 400
_NOT_A_BOARD = {"embed", "jobs", "careers", "job_board", "boards", "v1", "api"}

_BOARD_LINKS = (
    (
        "greenhouse",
        re.compile(
            r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?"
            r"([A-Za-z0-9_-]+)",
            re.IGNORECASE,
        ),
    ),
    ("lever", re.compile(r"jobs(?:\.eu)?\.lever\.co/([A-Za-z0-9_.-]+)", re.IGNORECASE)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)", re.IGNORECASE)),
)


@dataclass(frozen=True)
class Board:
    kind: str  # greenhouse | lever | ashby
    token: str

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.token}"

    @property
    def url(self) -> str:
        if self.kind == "greenhouse":
            return f"https://boards-api.greenhouse.io/v1/boards/{self.token}/jobs?content=true"
        if self.kind == "lever":
            return f"https://api.lever.co/v0/postings/{self.token}?mode=json"
        return f"https://api.ashbyhq.com/posting-api/job-board/{self.token}"


def find_board(page_text: str) -> Board | None:
    """The first supported job board a careers page links to."""
    for kind, pattern in _BOARD_LINKS:
        for match in pattern.finditer(page_text):
            token = match.group(1).strip(".")
            if token and token.lower() not in _NOT_A_BOARD:
                return Board(kind, token)
    return None


def _excerpt(text: Any) -> str:
    return " ".join(str(text or "").split())[:_MAX_EXCERPT]


def _clean(value: Any) -> str | None:
    text = " ".join(str(value).split()) if value else ""
    return text or None


def _epoch_ms_to_iso(value: Any) -> str | None:
    if isinstance(value, int | float) and value > 0:
        return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()
    return None


def parse_greenhouse(body: Any) -> list[Posting]:
    jobs = body.get("jobs") if isinstance(body, dict) else None
    postings: list[Posting] = []
    for job in jobs or []:
        if not isinstance(job, dict) or not _clean(job.get("title")):
            continue
        departments = job.get("departments") or []
        department = _clean(departments[0].get("name")) if departments else None
        location = job.get("location")
        postings.append(
            Posting(
                title=_clean(job["title"]) or "",
                url=job.get("absolute_url"),
                department=department,
                location=_clean(location.get("name")) if isinstance(location, dict) else None,
                posted=_clean(job.get("updated_at")),
                excerpt=_excerpt(job.get("content")),
            )
        )
    return postings


def parse_lever(body: Any) -> list[Posting]:
    postings: list[Posting] = []
    for job in body if isinstance(body, list) else []:
        if not isinstance(job, dict) or not _clean(job.get("text")):
            continue
        raw_categories = job.get("categories")
        categories: dict[str, Any] = raw_categories if isinstance(raw_categories, dict) else {}
        postings.append(
            Posting(
                title=_clean(job["text"]) or "",
                url=job.get("hostedUrl"),
                department=_clean(categories.get("department") or categories.get("team")),
                location=_clean(categories.get("location")),
                posted=_epoch_ms_to_iso(job.get("createdAt")),  # not documented; used if present
                excerpt=_excerpt(job.get("descriptionPlain")),
            )
        )
    return postings


def parse_ashby(body: Any) -> list[Posting]:
    jobs = body.get("jobs") if isinstance(body, dict) else None
    postings: list[Posting] = []
    for job in jobs or []:
        if not isinstance(job, dict) or not _clean(job.get("title")):
            continue
        if job.get("isListed") is False:
            continue
        postings.append(
            Posting(
                title=_clean(job["title"]) or "",
                url=job.get("jobUrl"),
                department=_clean(job.get("department") or job.get("team")),
                location=_clean(job.get("location")),
                posted=_clean(job.get("publishedAt")),
                excerpt=_excerpt(job.get("descriptionPlain")),
            )
        )
    return postings


_PARSERS = {"greenhouse": parse_greenhouse, "lever": parse_lever, "ashby": parse_ashby}


def parse_board(board: Board, body: Any) -> list[Posting]:
    return _PARSERS[board.kind](body)
