"""
Planner / intent parser.

Week 1: a rule-based parser implements this interface (no LLM).
Later: swap in an LLM-based parser that returns `CommuteIntent`.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Optional, Protocol, Tuple

from src.config import DEFAULT_TIMEZONE
from src.schemas import CommuteIntent, CommuteRequest
from src.time_utils import combine_date_time


class Planner(Protocol):
    """Parse raw user input into a structured `CommuteIntent`."""

    def parse(self, request: CommuteRequest) -> CommuteIntent:
        """Return a schema-validated parsed intent."""


# Pattern for "arrive between 10 and 11" or "between 10:00 and 11:00"
_ARRIVAL_WINDOW_RE = re.compile(
    r"between\s+(\d{1,2})(?::(\d{2}))?\s+and\s+(\d{1,2})(?::(\d{2}))?",
    re.IGNORECASE,
)


def _parse_arrival_window(
    query: str, timezone: str, reference_date: Optional[date]
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    If query contains "between H and M" or "between H:MM and M", return
    (start_dt, end_dt) for today (or reference_date); else (None, None).
    """
    m = _ARRIVAL_WINDOW_RE.search(query)
    if not m:
        return (None, None)
    ref = reference_date or date.today()
    h1, m1, h2, m2 = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
    start_min = int(m1) if m1 else 0
    end_min = int(m2) if m2 else 0
    start_dt = combine_date_time(ref, time(hour=h1, minute=start_min), timezone)
    end_dt = combine_date_time(ref, time(hour=h2, minute=end_min), timezone)
    return (start_dt, end_dt)


class RuleBasedPlanner:
    """
    Minimal rule-based planner for Week 1 (no LLM).

    - "office" in query -> destination_source=office.
    - Otherwise -> destination_source=calendar_event, event_query=query
      (e.g. "dinner with mom").
    - "between X and Y" (e.g. "between 10 and 11") -> arrival window for today.
    - origin_source=home, risk_mode=balanced by default.
    """

    def __init__(
        self,
        *,
        timezone: str = DEFAULT_TIMEZONE,
        reference_date: date | None = None,
    ) -> None:
        self._timezone = timezone
        self._reference_date = reference_date

    def parse(self, request: CommuteRequest) -> CommuteIntent:
        query = (request.query or "").strip()
        # Destination: office vs calendar event
        if re.search(r"\boffice\b", query, re.IGNORECASE):
            destination_source = "office"
            event_query = None
            destination_text = None
        else:
            destination_source = "calendar_event"
            event_query = query if query else None
            destination_text = None

        # Arrival window
        arrival_window_start, arrival_window_end = _parse_arrival_window(
            query, self._timezone, self._reference_date
        )

        return CommuteIntent(
            intent="commute_plan",
            origin_source="home",
            destination_source=destination_source,
            destination_text=destination_text,
            event_query=event_query,
            origin_text=None,
            arrival_time=None,
            arrival_window_start=arrival_window_start,
            arrival_window_end=arrival_window_end,
            risk_mode="balanced",
            missing_fields=[],
        )

