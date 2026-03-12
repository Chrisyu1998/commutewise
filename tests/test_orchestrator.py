"""
Tests for the minimal Week 1 orchestrator.

Covers: office commute (run_with_intent), calendar single match, clarification
path, and run(request) with RuleBasedPlanner.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from zoneinfo import ZoneInfo

from src.config import DEFAULT_TIMEZONE, default_app_config
from src.orchestrator import (
    NEEDS_ARRIVAL_INFO_MESSAGE,
    NO_EVENT_FOUND_MESSAGE,
    OrchestratorResult,
    SimpleOrchestrator,
)
from src.planner import RuleBasedPlanner
from src.providers import MockCalendarProvider
from src.schemas import CommuteIntent, CommuteRequest
from src.time_utils import ensure_timezone


def _tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo(DEFAULT_TIMEZONE))
    return dt


def test_orchestrator_result_requires_exactly_one_field() -> None:
    with pytest.raises(ValueError):
        OrchestratorResult(kind="recommendation", recommendation=None)
    with pytest.raises(ValueError):
        OrchestratorResult(kind="clarification", clarification_candidates=[], clarification_message=None)
    with pytest.raises(ValueError):
        OrchestratorResult(kind="no_event_found", message=None)
    with pytest.raises(ValueError):
        OrchestratorResult(kind="needs_arrival_info", message=None)


def test_office_commute_run_with_intent_returns_recommendation() -> None:
    """Office destination + arrival window -> recommendation."""
    now = _tz(datetime(2026, 3, 11, 7, 0))
    window_start = _tz(datetime(2026, 3, 11, 10, 0))
    window_end = _tz(datetime(2026, 3, 11, 11, 0))
    intent = CommuteIntent(
        intent="commute_plan",
        origin_source="home",
        destination_source="office",
        destination_text=None,
        event_query=None,
        origin_text=None,
        arrival_time=None,
        arrival_window_start=window_start,
        arrival_window_end=window_end,
        risk_mode="balanced",
        missing_fields=[],
    )
    orchestrator = SimpleOrchestrator(now_provider=lambda: now)
    result = orchestrator.run_with_intent(intent)

    assert result.kind == "recommendation"
    assert result.recommendation is not None
    rec = result.recommendation
    assert rec.departure_time is not None
    # ETA 35 min (fixture), balanced buffer 10; balanced targets middle of window (10:30) -> leave 09:45
    assert rec.departure_time.hour == 9
    assert rec.departure_time.minute == 45


def test_calendar_single_match_returns_recommendation() -> None:
    """Event query that matches exactly one event (e.g. 'dentist') -> recommendation."""
    now = _tz(datetime(2026, 3, 12, 8, 0))
    window_start = _tz(datetime(2026, 3, 12, 10, 0))
    window_end = _tz(datetime(2026, 3, 12, 11, 0))
    intent = CommuteIntent(
        intent="commute_plan",
        origin_source="home",
        destination_source="calendar_event",
        destination_text=None,
        event_query="dentist",
        origin_text=None,
        arrival_time=None,
        arrival_window_start=window_start,
        arrival_window_end=window_end,
        risk_mode="balanced",
        missing_fields=[],
    )
    orchestrator = SimpleOrchestrator(now_provider=lambda: now)
    result = orchestrator.run_with_intent(intent)

    assert result.kind == "recommendation"
    assert result.recommendation is not None
    rec = result.recommendation
    assert rec.departure_time is not None


def test_calendar_ambiguous_returns_clarification_candidates() -> None:
    """Event query matching multiple events (e.g. 'lunch') -> clarification_candidates."""
    now = _tz(datetime(2026, 3, 11, 9, 0))
    intent = CommuteIntent(
        intent="commute_plan",
        origin_source="home",
        destination_source="calendar_event",
        destination_text=None,
        event_query="lunch",
        origin_text=None,
        arrival_time=None,
        arrival_window_start=None,
        arrival_window_end=None,
        risk_mode="balanced",
        missing_fields=[],
    )
    orchestrator = SimpleOrchestrator(now_provider=lambda: now)
    # No arrival window -> recommendation engine would raise; but we never get there
    # because resolve_event returns multiple candidates first.
    result = orchestrator.run_with_intent(intent)

    assert result.kind == "clarification"
    assert result.clarification_candidates is not None
    titles = [e.title for e in result.clarification_candidates]
    assert "Lunch with Sarah" in titles
    assert "Lunch with Alex" in titles
    assert "Do you mean" in result.clarification_message
    assert "Lunch with Sarah" in result.clarification_message
    assert "Lunch with Alex" in result.clarification_message


def test_run_with_planner_office_between_10_and_11() -> None:
    """run(request) with RuleBasedPlanner parses 'office between 10 and 11' and returns recommendation."""
    now = _tz(datetime(2026, 3, 11, 7, 0))
    from datetime import date

    planner = RuleBasedPlanner(
        timezone=DEFAULT_TIMEZONE,
        reference_date=date(2026, 3, 11),
    )
    orchestrator = SimpleOrchestrator(
        planner=planner,
        now_provider=lambda: now,
    )
    request = CommuteRequest(
        query="When should I leave for the office between 10 and 11?"
    )
    result = orchestrator.run(request)

    assert result.kind == "recommendation"
    assert result.recommendation is not None
    assert result.recommendation.departure_time.hour == 9
    assert result.recommendation.departure_time.minute == 45


def test_run_without_planner_raises() -> None:
    """run(request) without injecting a planner raises."""
    orchestrator = SimpleOrchestrator(planner=None)
    with pytest.raises(ValueError, match="planner"):
        orchestrator.run(CommuteRequest(query="office between 10 and 11"))


def test_office_no_arrival_returns_needs_arrival_info_message() -> None:
    """Office destination with no arrival time/window -> ask user for arrival."""
    now = _tz(datetime(2026, 3, 11, 7, 0))
    intent = CommuteIntent(
        intent="commute_plan",
        origin_source="home",
        destination_source="office",
        destination_text=None,
        event_query=None,
        origin_text=None,
        arrival_time=None,
        arrival_window_start=None,
        arrival_window_end=None,
        risk_mode="balanced",
        missing_fields=[],
    )
    orchestrator = SimpleOrchestrator(now_provider=lambda: now)
    result = orchestrator.run_with_intent(intent)

    assert result.kind == "needs_arrival_info"
    assert result.message == NEEDS_ARRIVAL_INFO_MESSAGE
    assert "What time do you wish to arrive" in result.message


def test_calendar_zero_candidates_returns_no_event_found_message() -> None:
    """Event query matching no events returns no_event_found_message."""
    calendar = MockCalendarProvider(events=[])
    now = _tz(datetime(2026, 3, 11, 9, 0))
    intent = CommuteIntent(
        intent="commute_plan",
        origin_source="home",
        destination_source="calendar_event",
        destination_text=None,
        event_query="nonexistent meeting",
        origin_text=None,
        arrival_time=None,
        arrival_window_start=None,
        arrival_window_end=None,
        risk_mode="balanced",
        missing_fields=[],
    )
    orchestrator = SimpleOrchestrator(
        calendar_provider=calendar,
        now_provider=lambda: now,
    )
    result = orchestrator.run_with_intent(intent)

    assert result.kind == "no_event_found"
    assert result.message is not None
    assert NO_EVENT_FOUND_MESSAGE in result.message
    assert "date and location" in result.message
    assert "Searched" in result.message
    assert "2026-03-11" in result.message
    assert "2026-03-18" in result.message
