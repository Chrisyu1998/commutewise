from __future__ import annotations

from datetime import datetime

import pytest

from src.config import DEFAULT_TIMEZONE
from src.planner import GeminiPlanner, PlannerModelError
from src.schemas import CommuteIntent, CommuteRequest
from src.time_utils import ensure_timezone


class FakeGeminiClient:
    """
    Test double for GeminiClientProtocol.

    Returns canned structured outputs based on the user query so tests are
    deterministic and offline.
    """

    def generate_structured_intent(self, *, system_prompt, user_query, json_schema):
        q = user_query.lower()

        if "office" in q and "arrive by" in q:
            # Office commute with single arrival-by time.
            base = datetime(2026, 3, 12)
            arrive = ensure_timezone(base.replace(hour=10, minute=0), DEFAULT_TIMEZONE)
            return {
                "intent": "commute_plan",
                "origin_source": "home",
                "destination_source": "office",
                "origin_text": None,
                "destination_text": None,
                "event_query": None,
                "arrival_time": arrive.isoformat(),
                "arrival_window_start": None,
                "arrival_window_end": None,
                "risk_mode": "balanced",
                "missing_fields": [],
                "destination_ambiguous": False,
                "time_ambiguous": False,
            }

        if "office" in q and "between 10 and 11" in q:
            # Office commute with arrival window.
            base = datetime(2026, 3, 12)
            start = ensure_timezone(base.replace(hour=10, minute=0), DEFAULT_TIMEZONE)
            end = ensure_timezone(base.replace(hour=11, minute=0), DEFAULT_TIMEZONE)
            return {
                "intent": "commute_plan",
                "origin_source": "home",
                "destination_source": "office",
                "origin_text": None,
                "destination_text": None,
                "event_query": None,
                "arrival_time": None,
                "arrival_window_start": start.isoformat(),
                "arrival_window_end": end.isoformat(),
                "risk_mode": "balanced",
                "missing_fields": [],
                "destination_ambiguous": False,
                "time_ambiguous": False,
            }

        if "dinner with mom" in q:
            # Event-based query without explicit arrival time.
            return {
                "intent": "commute_plan",
                "origin_source": "home",
                "destination_source": "calendar_event",
                "origin_text": None,
                "destination_text": None,
                "event_query": "dinner with Mom",
                "arrival_time": None,
                "arrival_window_start": None,
                "arrival_window_end": None,
                "risk_mode": "balanced",
                "missing_fields": [],
                "destination_ambiguous": False,
                "time_ambiguous": True,
            }

        if "lunch" in q:
            # Ambiguous destination; should surface ambiguity in missing_fields.
            return {
                "intent": "commute_plan",
                "origin_source": "home",
                "destination_source": "calendar_event",
                "origin_text": None,
                "destination_text": None,
                "event_query": "lunch",
                "arrival_time": None,
                "arrival_window_start": None,
                "arrival_window_end": None,
                "risk_mode": "balanced",
                "missing_fields": ["arrival_time_or_window"],
                "destination_ambiguous": True,
                "time_ambiguous": False,
            }

        if "leave for the office now" in q or "leave now for the office" in q:
            # Leave-now style query; destination is office but timing is fuzzy.
            return {
                "intent": "commute_plan",
                "origin_source": "home",
                "destination_source": "office",
                "origin_text": None,
                "destination_text": None,
                "event_query": None,
                "arrival_time": None,
                "arrival_window_start": None,
                "arrival_window_end": None,
                "risk_mode": "balanced",
                "missing_fields": ["arrival_time_or_window", "ambiguous_time"],
                "destination_ambiguous": False,
                "time_ambiguous": True,
            }

        # Default: minimal structured output with missing destination/time.
        return {
            "intent": "commute_plan",
            "origin_source": "home",
            "destination_source": "home",
            "origin_text": None,
            "destination_text": None,
            "event_query": None,
            "arrival_time": None,
            "arrival_window_start": None,
            "arrival_window_end": None,
            "risk_mode": "balanced",
            "missing_fields": ["destination", "arrival_time_or_window"],
            "destination_ambiguous": False,
            "time_ambiguous": False,
        }


def _make_planner() -> GeminiPlanner:
    client = FakeGeminiClient()
    return GeminiPlanner(gemini_client=client, timezone=DEFAULT_TIMEZONE)


def test_gemini_planner_office_commute_window():
    planner = _make_planner()
    intent: CommuteIntent = planner.parse(
        CommuteRequest(
            query="When should I leave for the office if I want to arrive between 10 and 11?"
        )
    )

    assert intent.destination_source == "office"
    assert intent.event_query is None
    assert intent.arrival_time is None
    assert intent.arrival_window_start is not None
    assert intent.arrival_window_end is not None
    assert intent.arrival_window_start.tzinfo is not None
    assert intent.arrival_window_end.tzinfo is not None
    assert intent.missing_fields == []


def test_gemini_planner_office_arrival_by_query():
    planner = _make_planner()
    intent = planner.parse(
        CommuteRequest(query="When should I leave for the office to arrive by 10?")
    )

    assert intent.destination_source == "office"
    assert intent.arrival_time is not None
    assert intent.arrival_window_start is None
    assert intent.arrival_window_end is None
    # Timestamp should be timezone-aware and roughly at 10:00.
    assert intent.arrival_time.tzinfo is not None
    assert intent.arrival_time.hour == 10
    assert intent.arrival_time.minute == 0


def test_gemini_planner_event_based_query_without_time():
    planner = _make_planner()
    intent = planner.parse(
        CommuteRequest(query="When should I leave for dinner with Mom?")
    )

    assert intent.destination_source == "calendar_event"
    assert intent.event_query == "dinner with Mom"
    assert intent.arrival_time is None
    assert intent.arrival_window_start is None
    assert intent.arrival_window_end is None
    # Time ambiguity should be surfaced via missing_fields.
    assert "ambiguous_time" in intent.missing_fields


def test_gemini_planner_ambiguous_destination_adds_missing_field():
    planner = _make_planner()
    intent = planner.parse(CommuteRequest(query="When should I leave for lunch?"))

    assert intent.destination_source == "calendar_event"
    assert intent.event_query == "lunch"
    assert "ambiguous_destination" in intent.missing_fields
    assert "arrival_time_or_window" in intent.missing_fields


def test_gemini_planner_leave_now_query_marks_time_ambiguous():
    planner = _make_planner()
    intent = planner.parse(
        CommuteRequest(query="Should I leave for the office now or wait?")
    )

    assert intent.destination_source == "office"
    # No explicit arrival constraint parsed.
    assert intent.arrival_time is None
    assert intent.arrival_window_start is None
    assert intent.arrival_window_end is None
    # Time ambiguity should be surfaced.
    assert "ambiguous_time" in intent.missing_fields
    assert "arrival_time_or_window" in intent.missing_fields


def test_gemini_planner_under_specified_query_missing_fields():
    planner = _make_planner()
    intent = planner.parse(CommuteRequest(query="When should I leave?"))

    # Default behavior: treat as under-specified, keep origin/home, no dest.
    assert intent.origin_source == "home"
    # Destination is not resolved; destination_source stays home and fields are missing.
    assert "destination" in intent.missing_fields
    assert "arrival_time_or_window" in intent.missing_fields


def test_gemini_planner_raises_model_error_on_non_dict_response():
    class BadClient(FakeGeminiClient):
        def generate_structured_intent(self, *, system_prompt, user_query, json_schema):
            # Simulate a bug where the client returns a non-dict JSON value.
            return "not-a-dict"  # type: ignore[return-value]

    planner = GeminiPlanner(gemini_client=BadClient(), timezone=DEFAULT_TIMEZONE)

    with pytest.raises(PlannerModelError):
        planner.parse(CommuteRequest(query="When should I leave for the office?"))

