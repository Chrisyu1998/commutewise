"""
Calendar provider interface and mock implementation.

Week 1 uses MockCalendarProvider with local fixture data shaped like the
Google Calendar API response (see Events resource and events.list response).
Real API integration can use the same normalizer and return CalendarEvent.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Protocol, Sequence

from src.schemas import CalendarEvent, EventResolutionResult
from src.time_utils import ensure_timezone

from src.providers.calendar.event_resolver import EventResolver


def _parse_google_start_end(
    obj: dict,
    *,
    default_timezone: str = "America/Los_Angeles",
    end_of_day: bool = False,
) -> datetime:
    """
    Parse a Google Calendar API start/end object into a timezone-aware datetime.

    API shape: { "dateTime": "RFC3339" } or { "date": "yyyy-mm-dd", "timeZone": "IANA" }.
    For all-day events, date is used; end_of_day=True interprets as 23:59:59.999999.
    """
    tz_name = obj.get("timeZone") or default_timezone
    if "dateTime" in obj:
        parsed = datetime.fromisoformat(obj["dateTime"].replace("Z", "+00:00"))
        return ensure_timezone(parsed, tz_name)
    if "date" in obj:
        from datetime import date as date_type

        d = datetime.strptime(obj["date"], "%Y-%m-%d").date()
        if end_of_day:
            dt = datetime.combine(d, datetime.max.time())
        else:
            dt = datetime.combine(d, datetime.min.time())
        return ensure_timezone(dt, tz_name)
    raise ValueError("start/end must have dateTime or date")


def normalize_google_event(raw: dict[str, Any]) -> CalendarEvent:
    """
    Convert a Google Calendar API event resource to our CalendarEvent schema.

    Maps API fields: summary → title, start/end objects → timezone-aware datetimes.
    Skips validation of optional API fields (creator, organizer, etc.); only
    id, summary, start, end are required for normalization. Location and
    timeZone are optional. Events with status "cancelled" should be filtered
    out by the caller before normalizing if desired.
    """
    event_id = raw.get("id") or ""
    title = raw.get("summary") or ""
    start_obj = raw.get("start") or {}
    end_obj = raw.get("end") or {}
    tz_name = (
        (start_obj.get("timeZone") or end_obj.get("timeZone"))
        or "America/Los_Angeles"
    )
    start_dt = _parse_google_start_end(start_obj, default_timezone=tz_name, end_of_day=False)
    # For "date" (all-day), API end is exclusive = start of end date (midnight). For dateTime, use as-is.
    end_dt = _parse_google_start_end(end_obj, default_timezone=tz_name, end_of_day=False)
    if "dateTime" in end_obj:
        parsed_end = datetime.fromisoformat(end_obj["dateTime"].replace("Z", "+00:00"))
        end_dt = ensure_timezone(parsed_end, tz_name)
    location = raw.get("location")
    return CalendarEvent(
        id=event_id,
        title=title,
        start=start_dt,
        end=end_dt,
        location=location if location else None,
        timezone=tz_name,
    )


class CalendarProvider(Protocol):
    """
    Interface for fetching and resolving calendar events.

    Implementations: MockCalendarProvider (fixture/JSON), GoogleCalendarProvider (future).
    """

    def get_events(self, start: datetime, end: datetime) -> List[CalendarEvent]:
        """Return normalized events in the given time range."""

    def resolve_event(
        self, query: str, events: Sequence[CalendarEvent]
    ) -> EventResolutionResult:
        """
        Return candidate events and scores matching a user query.

        When result.needs_clarification is True, the orchestrator can ask the user
        "Do you mean X or Y?" (using result.candidates' titles), then call
        resolve_event again with the user's reply to get a single event.
        """



class MockCalendarProvider:
    """
    Calendar provider backed by local fixture data (JSON or in-memory list).

    - get_events(start, end): returns events that overlap [start, end].
    - resolve_event(query, events): delegates to EventResolver; returns
      EventResolutionResult (candidates + scores). When needs_clarification,
      caller can ask "Do you mean X or Y?" and re-call with user's reply.
    """

    def __init__(
        self,
        *,
        events_path: Optional[Path] = None,
        events: Optional[List[CalendarEvent]] = None,
        resolver: Optional[EventResolver] = None,
    ) -> None:
        """
        Initialize from a JSON file and/or an explicit events list.

        - If events is set, those events are used (overrides path; useful for tests).
        - If events is not set and events_path is set, events are loaded from that file.
        - If neither is set, use default path: data/calendar_events.json relative to
          the package root (parent of src/).
        - resolver: optional EventResolver for resolve_event; defaults to a new
          EventResolver() so mock and real providers share the same resolution logic.
        """
        if events is not None:
            self._events = list(events)
        else:
            # Project root: src/providers/calendar/calendar.py -> 4 levels up
            path = events_path or Path(__file__).resolve().parent.parent.parent.parent / "data" / "calendar_events.json"
            self._events = self._load_from_path(path)
        self._resolver = resolver if resolver is not None else EventResolver()

    def _load_from_path(self, path: Path) -> List[CalendarEvent]:
        """
        Load events from a JSON file in Google Calendar API list response shape.

        Expects either:
        - A dict with "items" (calendar#events list response); each item is
          an event resource. Events with status "cancelled" are skipped.
        - A list of event resources (same shape as items[]).
        """
        if not path.exists():
            return []
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "items" in data:
            raw_list = data["items"]
        elif isinstance(data, list):
            raw_list = data
        else:
            return []
        result = []
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue
            if raw.get("status") == "cancelled":
                continue
            try:
                result.append(normalize_google_event(raw))
            except (ValueError, KeyError):
                continue
        return result

    def get_events(self, start: datetime, end: datetime) -> List[CalendarEvent]:
        """
        Return normalized events that overlap the given [start, end] window.

        An event overlaps if event.start < end and event.end > start.
        """
        result = []
        for ev in self._events:
            if ev.start < end and ev.end > start:
                result.append(ev)
        result.sort(key=lambda e: e.start)
        return result

    def resolve_event(
        self, query: str, events: Sequence[CalendarEvent]
    ) -> EventResolutionResult:
        """
        Return candidate events and scores via the shared EventResolver.

        When result.needs_clarification is True, the caller can prompt the user
        e.g. "Do you mean {candidate titles}?" and call resolve_event again with
        the user's reply to get a single event.
        """
        return self._resolver.resolve(query, events)
