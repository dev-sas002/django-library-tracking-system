"""
Utilities for generating commit messages and timestamps that follow this
project's guidelines.

These helpers are intentionally framework-agnostic so they can be imported
from automation scripts (for example, a time-travel commit generator) without
depending on Django.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import os
import random
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Mapping, Optional, Sequence


class TaskType(str, Enum):
    """Supported Task labels for commit messages."""

    REFACTOR = "Refactor"
    BUGFIX = "BugFix"
    TEST = "Test"
    DOCS = "Docs"
    CHORE = "Chore"
    INFRA = "Infra"


@dataclass(frozen=True)
class CommitTemplate:
    task: TaskType
    description: str


_TEMPLATES: Sequence[CommitTemplate] = (
    # Refactors
    CommitTemplate(
        TaskType.REFACTOR,
        "Simplify book search filters",
    ),
    CommitTemplate(
        TaskType.REFACTOR,
        "Extract loan validation into service layer",
    ),
    CommitTemplate(
        TaskType.REFACTOR,
        "Clean up serializer field definitions",
    ),
    # Bug fixes
    CommitTemplate(
        TaskType.BUGFIX,
        "Fix overdue loan calculation for edge dates",
    ),
    CommitTemplate(
        TaskType.BUGFIX,
        "Handle missing member records in loans API",
    ),
    CommitTemplate(
        TaskType.BUGFIX,
        "Prevent duplicate book entries on import",
    ),
    # Tests
    CommitTemplate(
        TaskType.TEST,
        "Add tests for loans API endpoint",
    ),
    CommitTemplate(
        TaskType.TEST,
        "Increase coverage for book search filters",
    ),
    CommitTemplate(
        TaskType.TEST,
        "Add regression tests for overdue loans",
    ),
    # Docs
    CommitTemplate(
        TaskType.DOCS,
        "Document library sync management command",
    ),
    CommitTemplate(
        TaskType.DOCS,
        "Clarify environment variables in README",
    ),
    # Chores / infra
    CommitTemplate(
        TaskType.CHORE,
        "Update development dependencies",
    ),
    CommitTemplate(
        TaskType.INFRA,
        "Add CI job for Django test suite",
    ),
)


def generate_commit_message(
    task: Optional[TaskType] = None,
    *,
    rng: Optional[random.Random] = None,
) -> str:
    """
    Generate a commit message in the form:

        Feature::Task::Task Description

    If ``task`` is provided, a template for that TaskType is chosen; otherwise
    a random TaskType is selected based on the available templates.
    """
    if rng is None:
        rng = random

    candidates: List[CommitTemplate]
    if task is None:
        candidates = list(_TEMPLATES)
    else:
        candidates = [t for t in _TEMPLATES if t.task is task]
        if not candidates:
            raise ValueError(f"No templates registered for task {task!r}")

    template = rng.choice(candidates)
    return f"Feature::{template.task.value}::{template.description}"


def parse_yyyy_mm_dd(value: str) -> dt.date:
    """Parse a YYYY-MM-DD date string into a date object."""
    return dt.datetime.strptime(value.strip(), "%Y-%m-%d").date()


def _daterange_inclusive(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    current = start
    one_day = dt.timedelta(days=1)
    while current <= end:
        yield current
        current += one_day


def generate_commit_timestamps(
    start_date: dt.date,
    end_date: dt.date,
    commit_count: int,
    *,
    skip_weekends: bool = True,
    seed: Optional[int] = None,
) -> List[dt.datetime]:
    """
    Generate ``commit_count`` UTC datetimes between ``start_date`` and
    ``end_date`` (inclusive).

    - All timestamps are timezone-aware and in UTC.
    - Timestamps are sorted in non-decreasing order.
    - Optionally skips weekends entirely.
    """
    if commit_count <= 0:
        return []
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")

    rng = random.Random(seed)
    available_days: List[dt.date] = []
    for day in _daterange_inclusive(start_date, end_date):
        if skip_weekends and day.weekday() >= 5:
            continue
        available_days.append(day)

    if not available_days:
        raise ValueError("No available days in range after applying filters")

    timestamps: List[dt.datetime] = []
    for _ in range(commit_count):
        day = rng.choice(available_days)
        # Random time during working hours (08:00–18:00)
        hour = rng.randint(8, 18)
        minute = rng.randint(0, 59)
        second = rng.randint(0, 59)
        ts = dt.datetime(
            day.year,
            day.month,
            day.day,
            hour,
            minute,
            second,
            tzinfo=dt.timezone.utc,
        )
        timestamps.append(ts)

    timestamps.sort()
    return timestamps


def build_git_date_env(
    commit_ts: dt.datetime,
    base_env: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """
    Return a copy of ``base_env`` updated with GIT_AUTHOR_DATE and
    GIT_COMMITTER_DATE derived from ``commit_ts``.

    The timestamp is rendered in ISO 8601 with a trailing ``Z`` to make the
    UTC timezone explicit, for example: ``2023-10-03T10:30:00Z``.
    """
    if commit_ts.tzinfo is None:
        # Treat naive datetimes as UTC.
        commit_ts = commit_ts.replace(tzinfo=dt.timezone.utc)
    commit_ts = commit_ts.astimezone(dt.timezone.utc).replace(microsecond=0)
    iso_value = commit_ts.isoformat().replace("+00:00", "Z")

    env: Dict[str, str] = dict(base_env or os.environ)
    env["GIT_AUTHOR_DATE"] = iso_value
    env["GIT_COMMITTER_DATE"] = iso_value
    return env


__all__ = [
    "TaskType",
    "CommitTemplate",
    "generate_commit_message",
    "parse_yyyy_mm_dd",
    "generate_commit_timestamps",
    "build_git_date_env",
]

