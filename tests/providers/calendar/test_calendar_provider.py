"""Tests for MockCalendarProvider: get_events, resolve_event, and fixture loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from src.schemas import CalendarEvent, EventResolutionResult
from src.time_utils import parse_iso
from src.providers.calendar import (
    EventResolver,
    MockCalendarProvider,
    match_score,
    normalize_google_event,
    tokenize,
)


def _evt(
    id: str,
    title: str,
    start: str,
    end: str,
    location: str | None = None,
) -> CalendarEvent:
    return CalendarEvent(
        id=id,
        title=title,
        start=parse_iso(start),
        end=parse_iso(end),
        location=location,
        timezone="America/Los_Angeles",
    )


@pytest.fixture
def sample_events() -> list[CalendarEvent]:
    """Nine events over a few days for testing get_events and resolve_event."""
    return [
        _evt("1", "Team standup", "2026-03-11T09:00:00-07:00", "2026-03-11T09:15:00-07:00"),
        _evt("2", "Lunch with Sarah", "2026-03-11T12:30:00-07:00", "2026-03-11T13:30:00-07:00", "Sushi House"),
        _evt("3", "Dinner with Mom", "2026-03-11T18:30:00-07:00", "2026-03-11T20:30:00-07:00", "Olive Garden"),
        _evt("4", "Lunch with Alex", "2026-03-12T12:00:00-07:00", "2026-03-12T13:00:00-07:00", "In-N-Out"),
        _evt("5", "Dentist appointment", "2026-03-12T10:00:00-07:00", "2026-03-12T11:00:00-07:00", "Smile Dental"),
        _evt("6", "1:1 with Manager", "2026-03-12T14:00:00-07:00", "2026-03-12T14:30:00-07:00"),
        _evt("7", "Doctor appointment", "2026-03-13T08:30:00-07:00", "2026-03-13T09:15:00-07:00", "Kaiser"),
        _evt("8", "Yoga class", "2026-03-13T17:30:00-07:00", "2026-03-13T18:30:00-07:00", "CorePower"),
        _evt("9", "Coffee with Jen", "2026-03-14T10:00:00-07:00", "2026-03-14T10:45:00-07:00", "Philz"),
    ]


# -----------------------------------------------------------------------------
# get_events
# -----------------------------------------------------------------------------


def test_get_events_returns_events_overlapping_window(sample_events: list[CalendarEvent]) -> None:
    provider = MockCalendarProvider(events=sample_events)
    start = parse_iso("2026-03-11T00:00:00-07:00")
    end = parse_iso("2026-03-12T00:00:00-07:00")
    out = provider.get_events(start, end)
    assert len(out) == 3  # standup, lunch sarah, dinner mom
    assert [e.id for e in out] == ["1", "2", "3"]
    assert out[0].title == "Team standup"
    assert out[-1].title == "Dinner with Mom"


def test_get_events_sorted_by_start(sample_events: list[CalendarEvent]) -> None:
    provider = MockCalendarProvider(events=sample_events)
    start = parse_iso("2026-03-12T00:00:00-07:00")
    end = parse_iso("2026-03-14T00:00:00-07:00")
    out = provider.get_events(start, end)
    # Dentist (5) 10:00, Lunch Alex (4) 12:00, 1:1 (6) 14:00, Doctor (7) next day, Yoga (8)
    assert [e.id for e in out] == ["5", "4", "6", "7", "8"]
    for i in range(len(out) - 1):
        assert out[i].start <= out[i + 1].start


def test_get_events_empty_window_returns_empty(sample_events: list[CalendarEvent]) -> None:
    provider = MockCalendarProvider(events=sample_events)
    start = parse_iso("2026-03-15T00:00:00-07:00")
    end = parse_iso("2026-03-16T00:00:00-07:00")
    assert provider.get_events(start, end) == []


def test_get_events_event_straddling_boundary_included(sample_events: list[CalendarEvent]) -> None:
    provider = MockCalendarProvider(events=sample_events)
    # Window 11th 10:00–12:00: standup (9–9:15) ends before 10, so excluded; lunch (12:30–13:30) starts after 12
    # So only events that start before 12 and end after 10: dentist on 12th is not in this window.
    # Standup 9–9:15: overlap with 10–12? 9:15 > 10 no. Lunch 12:30–13:30: 12:30 < 12 no.
    start = parse_iso("2026-03-11T10:00:00-07:00")
    end = parse_iso("2026-03-11T12:00:00-07:00")
    out = provider.get_events(start, end)
    assert len(out) == 0
    # Window that catches lunch: 12:00–14:00 on 11th
    start2 = parse_iso("2026-03-11T12:00:00-07:00")
    end2 = parse_iso("2026-03-11T14:00:00-07:00")
    out2 = provider.get_events(start2, end2)
    assert len(out2) == 1 and out2[0].title == "Lunch with Sarah"


# -----------------------------------------------------------------------------
# resolve_event
# -----------------------------------------------------------------------------


def test_resolve_event_single_match(sample_events: list[CalendarEvent]) -> None:
    provider = MockCalendarProvider(events=sample_events)
    candidates = provider.get_events(
        parse_iso("2026-03-11T00:00:00-07:00"),
        parse_iso("2026-03-14T00:00:00-07:00"),
    )
    result = provider.resolve_event("dinner mom", candidates)
    assert isinstance(result, EventResolutionResult)
    assert len(result.candidates) == 1
    assert result.candidates[0].title == "Dinner with Mom" and result.candidates[0].id == "3"
    assert result.scores == [2.0]
    assert result.needs_clarification is False


def test_resolve_event_multiple_candidates_when_ambiguous(sample_events: list[CalendarEvent]) -> None:
    provider = MockCalendarProvider(events=sample_events)
    candidates = provider.get_events(
        parse_iso("2026-03-11T00:00:00-07:00"),
        parse_iso("2026-03-14T00:00:00-07:00"),
    )
    result = provider.resolve_event("lunch", candidates)
    assert len(result.candidates) == 2
    titles = {e.title for e in result.candidates}
    assert titles == {"Lunch with Sarah", "Lunch with Alex"}
    assert result.needs_clarification is True
    assert len(result.scores) == 2


def test_resolve_event_clarification_flow_user_reply_narrows(sample_events: list[CalendarEvent]) -> None:
    """After asking 'Do you mean X or Y?', user reply can be re-resolved to a single event."""
    provider = MockCalendarProvider(events=sample_events)
    candidates = provider.get_events(
        parse_iso("2026-03-11T00:00:00-07:00"),
        parse_iso("2026-03-14T00:00:00-07:00"),
    )
    result = provider.resolve_event("lunch", candidates)
    assert result.needs_clarification is True
    # User says "Sarah" (or "the first one" parsed as "Sarah"); re-resolve to get single event
    result2 = provider.resolve_event("Sarah", candidates)
    assert result2.needs_clarification is False
    assert len(result2.candidates) == 1 and result2.candidates[0].title == "Lunch with Sarah"


def test_resolve_event_fuzzy_partial_match(sample_events: list[CalendarEvent]) -> None:
    provider = MockCalendarProvider(events=sample_events)
    candidates = provider.get_events(
        parse_iso("2026-03-11T00:00:00-07:00"),
        parse_iso("2026-03-14T00:00:00-07:00"),
    )
    result = provider.resolve_event("dentist", candidates)
    assert len(result.candidates) == 1 and result.candidates[0].title == "Dentist appointment"
    result2 = provider.resolve_event("doctor", candidates)
    assert len(result2.candidates) == 1 and result2.candidates[0].title == "Doctor appointment"


def test_resolve_event_sorted_by_score_then_start(sample_events: list[CalendarEvent]) -> None:
    provider = MockCalendarProvider(events=sample_events)
    candidates = provider.get_events(
        parse_iso("2026-03-11T00:00:00-07:00"),
        parse_iso("2026-03-14T00:00:00-07:00"),
    )
    result = provider.resolve_event("dinner mom", candidates)
    assert len(result.candidates) >= 1 and result.candidates[0].title == "Dinner with Mom"


def test_resolve_event_empty_query_returns_empty(sample_events: list[CalendarEvent]) -> None:
    provider = MockCalendarProvider(events=sample_events)
    candidates = provider.get_events(
        parse_iso("2026-03-11T00:00:00-07:00"),
        parse_iso("2026-03-12T00:00:00-07:00"),
    )
    result = provider.resolve_event("", candidates)
    assert result.candidates == [] and result.scores == []
    result2 = provider.resolve_event("   ", candidates)
    assert result2.candidates == [] and result2.scores == []


def test_resolve_event_no_match_returns_empty(sample_events: list[CalendarEvent]) -> None:
    provider = MockCalendarProvider(events=sample_events)
    candidates = provider.get_events(
        parse_iso("2026-03-11T00:00:00-07:00"),
        parse_iso("2026-03-12T00:00:00-07:00"),
    )
    result = provider.resolve_event("nonexistent meeting", candidates)
    assert result.candidates == [] and result.scores == []


def test_resolve_event_empty_events_returns_empty() -> None:
    provider = MockCalendarProvider(events=[])
    result = provider.resolve_event("lunch", [])
    assert result.candidates == [] and result.scores == []


# -----------------------------------------------------------------------------
# fixture loading
# -----------------------------------------------------------------------------


def test_load_from_fixture_json() -> None:
    """Default provider loads data/calendar_events.json and returns normalized events."""
    # tests/providers/calendar/test_calendar_provider.py -> 4 levels up to project root
    path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "calendar_events.json"
    if not path.exists():
        pytest.skip("data/calendar_events.json not found (run from repo root)")
    provider = MockCalendarProvider(events_path=path)
    start = parse_iso("2026-03-11T00:00:00-07:00")
    end = parse_iso("2026-03-15T00:00:00-07:00")
    events = provider.get_events(start, end)
    assert len(events) >= 8
    for e in events:
        assert e.id and e.title and e.start.tzinfo and e.end.tzinfo


def test_normalize_google_event() -> None:
    """Normalize a Google Calendar API event resource into CalendarEvent."""
    raw = {
        "id": "x",
        "summary": "Test",
        "start": {"dateTime": "2026-03-11T09:00:00-07:00", "timeZone": "America/Los_Angeles"},
        "end": {"dateTime": "2026-03-11T10:00:00-07:00", "timeZone": "America/Los_Angeles"},
        "location": "Somewhere",
        "status": "confirmed",
    }
    ev = normalize_google_event(raw)
    assert ev.id == "x" and ev.title == "Test" and ev.location == "Somewhere"
    assert ev.start.tzinfo is not None and ev.end.tzinfo is not None


def test_normalize_google_event_all_day() -> None:
    """All-day events use start.date and end.date (end is exclusive)."""
    raw = {
        "id": "allday-1",
        "summary": "Conference",
        "start": {"date": "2026-03-12", "timeZone": "America/Los_Angeles"},
        "end": {"date": "2026-03-13", "timeZone": "America/Los_Angeles"},
        "status": "confirmed",
    }
    ev = normalize_google_event(raw)
    assert ev.title == "Conference"
    assert ev.start.tzinfo is not None
    assert ev.end.tzinfo is not None
    # Start = midnight 2026-03-12, end = midnight 2026-03-13 (exclusive)
    assert ev.start.hour == 0 and ev.start.minute == 0
    assert ev.end.hour == 0 and ev.end.minute == 0


def test_load_skips_cancelled_events(tmp_path: Path) -> None:
    """When loading API-shaped JSON, events with status cancelled are skipped."""
    api_response = {
        "kind": "calendar#events",
        "items": [
            {
                "id": "evt-1",
                "summary": "Kept",
                "status": "confirmed",
                "start": {"dateTime": "2026-03-11T09:00:00-07:00", "timeZone": "America/Los_Angeles"},
                "end": {"dateTime": "2026-03-11T10:00:00-07:00", "timeZone": "America/Los_Angeles"},
            },
            {
                "id": "evt-2",
                "summary": "Cancelled",
                "status": "cancelled",
                "start": {"dateTime": "2026-03-11T11:00:00-07:00", "timeZone": "America/Los_Angeles"},
                "end": {"dateTime": "2026-03-11T12:00:00-07:00", "timeZone": "America/Los_Angeles"},
            },
        ],
    }
    path = tmp_path / "cal.json"
    path.write_text(json.dumps(api_response), encoding="utf-8")
    provider = MockCalendarProvider(events_path=path)
    start = parse_iso("2026-03-11T00:00:00-07:00")
    end = parse_iso("2026-03-12T00:00:00-07:00")
    events = provider.get_events(start, end)
    assert len(events) == 1 and events[0].title == "Kept"


def test_tokenize() -> None:
    assert tokenize("dinner with Mom") == ["dinner", "mom"]
    assert tokenize("  lunch  ") == ["lunch"]
    assert tokenize("") == []
    assert tokenize("1:1") == ["11"]  # non-alphanumeric stripped


def test_match_score() -> None:
    ev = _evt("1", "Dinner with Mom", "2026-03-11T18:00:00-07:00", "2026-03-11T19:00:00-07:00", "Olive Garden")
    assert match_score(["dinner", "mom"], ev) == 2
    assert match_score(["lunch"], ev) == 0
    assert match_score(["olive"], ev) == 1
    assert match_score(["garden"], ev) == 1


def test_event_resolver_standalone(sample_events: list[CalendarEvent]) -> None:
    """EventResolver can be used directly (e.g. by future GoogleCalendarProvider)."""
    resolver = EventResolver()
    result = resolver.resolve("dinner mom", sample_events)
    assert len(result.candidates) == 1 and result.candidates[0].title == "Dinner with Mom"
    result2 = resolver.resolve("lunch", sample_events)
    assert result2.needs_clarification is True and len(result2.candidates) == 2


def test_mock_provider_accepts_custom_resolver(sample_events: list[CalendarEvent]) -> None:
    """MockCalendarProvider can be given a custom EventResolver (e.g. for testing)."""
    resolver = EventResolver()
    provider = MockCalendarProvider(events=sample_events, resolver=resolver)
    events = provider.get_events(parse_iso("2026-03-11T00:00:00-07:00"), parse_iso("2026-03-14T00:00:00-07:00"))
    result = provider.resolve_event("dentist", events)
    assert len(result.candidates) == 1 and result.candidates[0].title == "Dentist appointment"
