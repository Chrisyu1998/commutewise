"""
Tests for the deterministic recommendation engine.

Covers: fixed arrival time, arrival window, each risk_mode, missing inputs,
and edge cases (short travel time, already too late).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from zoneinfo import ZoneInfo

from src.config import DEFAULT_TIMEZONE
from src.recommendation import (
    HistoryAdjustments,
    RecommendationError,
    SimpleRecommendationEngine,
)
from src.schemas import PlaceRef, ResolvedCommute, RiskMode, RouteEstimate


def _tz(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware in project default."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo(DEFAULT_TIMEZONE))
    return dt


def _make_commute(
    *,
    duration_minutes: float = 30.0,
    arrival_time: datetime | None = None,
    arrival_window_start: datetime | None = None,
    arrival_window_end: datetime | None = None,
    risk_mode: RiskMode = "balanced",
    origin: PlaceRef | None = None,
    destination: PlaceRef | None = None,
) -> ResolvedCommute:
    """Build a ResolvedCommute with optional arrival constraint and route."""
    origin = origin or PlaceRef(label="Home", address=None, provider_place_id=None)
    destination = destination or PlaceRef(label="Office", address=None, provider_place_id=None)
    route = RouteEstimate(
        origin=origin,
        destination=destination,
        duration_minutes=duration_minutes,
    )
    return ResolvedCommute(
        origin=origin,
        destination=destination,
        event=None,
        route=route,
        arrival_time=_tz(arrival_time) if arrival_time is not None else None,
        arrival_window_start=_tz(arrival_window_start) if arrival_window_start is not None else None,
        arrival_window_end=_tz(arrival_window_end) if arrival_window_end is not None else None,
        risk_mode=risk_mode,
    )


# -----------------------------------------------------------------------------
# Fixed arrival time
# -----------------------------------------------------------------------------


def test_fixed_arrival_balanced_returns_correct_departure() -> None:
    """Fixed arrival time with balanced risk: departure = arrival - (ETA + buffer)."""
    # ETA 30 min, balanced buffer = max(10, 0.2*30) = 10 → leave 40 min before
    now = _tz(datetime(2026, 3, 11, 7, 0))  # 7:00 AM
    arrival = _tz(datetime(2026, 3, 11, 10, 0))  # 10:00 AM
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(duration_minutes=30.0, arrival_time=arrival, risk_mode="balanced")

    rec = engine.recommend(commute)

    # 10:00 - 40 min = 09:20
    assert rec.departure_time.hour == 9
    assert rec.departure_time.minute == 20
    assert rec.buffer_minutes == 10.0
    assert rec.confidence == "medium"
    assert "10:00" in rec.explanation or "by" in rec.explanation


def test_fixed_arrival_aggressive_smaller_buffer() -> None:
    """Aggressive risk uses smaller buffer than balanced."""
    now = _tz(datetime(2026, 3, 11, 8, 0))
    arrival = _tz(datetime(2026, 3, 11, 9, 30))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(duration_minutes=30.0, arrival_time=arrival, risk_mode="aggressive")

    rec = engine.recommend(commute)

    # aggressive: max(5, 0.1*30)=5 → total 35 min → leave 8:55
    assert rec.buffer_minutes == 5.0
    assert rec.departure_time.hour == 8
    assert rec.departure_time.minute == 55
    assert rec.confidence == "low"


def test_fixed_arrival_safest_larger_buffer() -> None:
    """Safest risk uses larger buffer and higher confidence."""
    now = _tz(datetime(2026, 3, 11, 8, 0))
    arrival = _tz(datetime(2026, 3, 11, 10, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(duration_minutes=30.0, arrival_time=arrival, risk_mode="safest")

    rec = engine.recommend(commute)

    # safest: max(15, 0.3*30)=15 → total 45 min → leave 09:15
    assert rec.buffer_minutes == 15.0
    assert rec.departure_time.hour == 9
    assert rec.departure_time.minute == 15
    assert rec.confidence == "high"


# -----------------------------------------------------------------------------
# Arrival window
# -----------------------------------------------------------------------------


def test_arrival_window_balanced_aims_mid_window() -> None:
    """Arrival window with balanced risk targets middle of window."""
    now = _tz(datetime(2026, 3, 11, 9, 0))
    window_start = _tz(datetime(2026, 3, 11, 10, 0))
    window_end = _tz(datetime(2026, 3, 11, 11, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(
        duration_minutes=30.0,
        arrival_window_start=window_start,
        arrival_window_end=window_end,
        risk_mode="balanced",
    )

    rec = engine.recommend(commute)

    # Target arrival = 10:30. ETA 30 + buffer 10 = 40 min → leave 09:50
    assert rec.departure_time.hour == 9
    assert rec.departure_time.minute == 50
    assert "between" in rec.explanation


def test_arrival_window_aggressive_aims_near_end() -> None:
    """Arrival window aggressive aims near end of window (window_end - 5 min)."""
    now = _tz(datetime(2026, 3, 11, 17, 0))
    window_start = _tz(datetime(2026, 3, 11, 18, 0))
    window_end = _tz(datetime(2026, 3, 11, 19, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(
        duration_minutes=25.0,
        arrival_window_start=window_start,
        arrival_window_end=window_end,
        risk_mode="aggressive",
    )

    rec = engine.recommend(commute)

    # Target = 18:55. ETA 25 + buffer max(5, 2.5)=5 → leave 18:25
    assert rec.departure_time.hour == 18
    assert rec.departure_time.minute == 25
    # Implied arrival 18:25 + 25 = 18:50, in [18:00, 19:00]
    implied = rec.departure_time + timedelta(minutes=25)
    assert window_start <= implied <= window_end


def test_arrival_window_safest_aims_at_start() -> None:
    """Arrival window safest aims at window start."""
    now = _tz(datetime(2026, 3, 11, 8, 0))
    window_start = _tz(datetime(2026, 3, 11, 10, 0))
    window_end = _tz(datetime(2026, 3, 11, 11, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(
        duration_minutes=30.0,
        arrival_window_start=window_start,
        arrival_window_end=window_end,
        risk_mode="safest",
    )

    rec = engine.recommend(commute)

    # Target = 10:00. ETA 30 + buffer 15 = 45 min → leave 09:15
    assert rec.departure_time.hour == 9
    assert rec.departure_time.minute == 15
    assert rec.buffer_minutes == 15.0


def test_arrival_window_aggressive_narrow_window_clamped() -> None:
    """When window is shorter than 5 min, aggressive target is clamped to window_start."""
    now = _tz(datetime(2026, 3, 11, 9, 0))
    window_start = _tz(datetime(2026, 3, 11, 10, 0))
    window_end = _tz(datetime(2026, 3, 11, 10, 3))  # 3-minute window
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(
        duration_minutes=10.0,
        arrival_window_start=window_start,
        arrival_window_end=window_end,
        risk_mode="aggressive",
    )

    rec = engine.recommend(commute)

    # Target clamped to 10:00. ETA 10 + buffer 5 = 15 min → leave 09:45. Implied arrival 09:55.
    assert rec.departure_time.hour == 9
    assert rec.departure_time.minute == 45
    implied = rec.departure_time + timedelta(minutes=10)
    # Validity allows [window_start - buffer, window_end]; 09:55 is within that.
    assert window_start - timedelta(minutes=rec.buffer_minutes) <= implied <= window_end


# -----------------------------------------------------------------------------
# Risk modes (covered above; one explicit per-mode sanity check)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("risk_mode", ["aggressive", "balanced", "safest"])
def test_each_risk_mode_produces_valid_recommendation(risk_mode: RiskMode) -> None:
    """Each risk mode yields a feasible recommendation when now is early enough."""
    now = _tz(datetime(2026, 3, 11, 7, 0))
    arrival = _tz(datetime(2026, 3, 11, 10, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(duration_minutes=20.0, arrival_time=arrival, risk_mode=risk_mode)

    rec = engine.recommend(commute)

    assert rec.departure_time >= now
    assert rec.departure_time + timedelta(minutes=20) <= arrival
    assert rec.buffer_minutes >= 5.0
    assert rec.confidence in ("low", "medium", "high")


@pytest.mark.parametrize(
    "risk_mode,expected_confidence",
    [("aggressive", "low"), ("balanced", "medium"), ("safest", "high")],
)
def test_confidence_exact_per_risk_mode(
    risk_mode: RiskMode, expected_confidence: str
) -> None:
    """Confidence is low for aggressive, medium for balanced, high for safest."""
    now = _tz(datetime(2026, 3, 11, 7, 0))
    arrival = _tz(datetime(2026, 3, 11, 10, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(duration_minutes=20.0, arrival_time=arrival, risk_mode=risk_mode)

    rec = engine.recommend(commute)

    assert rec.confidence == expected_confidence


def test_explanation_contains_departure_time_and_buffer() -> None:
    """Explanation includes the recommended departure time and buffer amount."""
    now = _tz(datetime(2026, 3, 11, 7, 0))
    arrival = _tz(datetime(2026, 3, 11, 10, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(duration_minutes=30.0, arrival_time=arrival, risk_mode="balanced")

    rec = engine.recommend(commute)

    # Engine formats as HH:MM; 09:20 is the expected departure
    assert "09:20" in rec.explanation
    assert "10.0" in rec.explanation or "10" in rec.explanation


def test_invariant_departure_plus_duration_plus_buffer_before_arrival() -> None:
    """For fixed arrival, departure + ETA + buffer <= arrival (invariant)."""
    now = _tz(datetime(2026, 3, 11, 7, 0))
    arrival = _tz(datetime(2026, 3, 11, 10, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(duration_minutes=25.0, arrival_time=arrival, risk_mode="balanced")

    rec = engine.recommend(commute)

    total_minutes = 25.0 + rec.buffer_minutes
    expected_departure = arrival - timedelta(minutes=total_minutes)
    assert rec.departure_time == expected_departure
    assert rec.departure_time + timedelta(minutes=25.0) <= arrival


def test_backup_gap_boundary_exactly_five_minutes() -> None:
    """Backup exactly 5 minutes earlier than primary is accepted."""
    now = _tz(datetime(2026, 3, 11, 8, 0))
    arrival = _tz(datetime(2026, 3, 11, 10, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(duration_minutes=30.0, arrival_time=arrival, risk_mode="aggressive")

    rec = engine.recommend(commute)

    # Aggressive 09:25, balanced 09:20 (5 min earlier) → backup should be 09:20
    assert rec.backup_departure_time is not None
    assert (rec.departure_time - rec.backup_departure_time).total_seconds() >= 5 * 60


def test_history_adjustments_increase_buffer() -> None:
    """Passing non-zero HistoryAdjustments increases buffer vs zero history."""
    now = _tz(datetime(2026, 3, 11, 8, 0))
    arrival = _tz(datetime(2026, 3, 11, 10, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(duration_minutes=30.0, arrival_time=arrival, risk_mode="balanced")

    rec_zero = engine.recommend(commute)
    rec_with_history = engine.recommend(
        commute,
        history_adjustments=HistoryAdjustments(mean_overrun_minutes=10.0, p90_overrun_minutes=20.0),
    )

    assert rec_with_history.buffer_minutes > rec_zero.buffer_minutes
    assert rec_zero.buffer_minutes == 10.0
    assert rec_with_history.buffer_minutes == 20.0  # 10 + 1.0 * 10


# -----------------------------------------------------------------------------
# Missing / invalid inputs
# -----------------------------------------------------------------------------


def test_missing_route_raises() -> None:
    """Missing route raises RecommendationError with code missing_route."""
    commute = ResolvedCommute(
        origin=PlaceRef(label="A"),
        destination=PlaceRef(label="B"),
        route=None,
        arrival_time=_tz(datetime(2026, 3, 11, 10, 0)),
        risk_mode="balanced",
    )
    engine = SimpleRecommendationEngine()

    with pytest.raises(RecommendationError) as exc_info:
        engine.recommend(commute)

    assert exc_info.value.code == "missing_route"


def test_invalid_route_duration_raises() -> None:
    """Negative route duration raises invalid_route_duration."""
    origin = PlaceRef(label="A")
    destination = PlaceRef(label="B")
    # Bypass Pydantic validation to simulate bad data (e.g. from an API).
    route = RouteEstimate.model_construct(
        origin=origin,
        destination=destination,
        duration_minutes=-1.0,
    )
    commute = ResolvedCommute(
        origin=origin,
        destination=destination,
        route=route,
        arrival_time=_tz(datetime(2026, 3, 11, 10, 0)),
        risk_mode="balanced",
    )
    engine = SimpleRecommendationEngine()

    with pytest.raises(RecommendationError) as exc_info:
        engine.recommend(commute)

    assert exc_info.value.code == "invalid_route_duration"


def test_route_mismatch_raises() -> None:
    """Route origin/destination not matching commute raises route_mismatch."""
    origin = PlaceRef(label="Home")
    destination = PlaceRef(label="Office")
    other_place = PlaceRef(label="Other")
    route = RouteEstimate(
        origin=origin,
        destination=other_place,
        duration_minutes=30.0,
    )
    commute = ResolvedCommute(
        origin=origin,
        destination=destination,
        route=route,
        arrival_time=_tz(datetime(2026, 3, 11, 10, 0)),
        risk_mode="balanced",
    )
    engine = SimpleRecommendationEngine(now_provider=lambda: _tz(datetime(2026, 3, 11, 8, 0)))

    with pytest.raises(RecommendationError) as exc_info:
        engine.recommend(commute)

    assert exc_info.value.code == "route_mismatch"


def test_missing_constraints_raises() -> None:
    """Neither arrival_time nor window set raises missing_constraints."""
    engine = SimpleRecommendationEngine()
    commute = _make_commute(
        duration_minutes=30.0,
        arrival_time=None,
        arrival_window_start=None,
        arrival_window_end=None,
    )

    with pytest.raises(RecommendationError) as exc_info:
        engine.recommend(commute)

    assert exc_info.value.code == "missing_constraints"


def test_conflicting_constraints_raises() -> None:
    """Both arrival_time and arrival_window set raises conflicting_constraints."""
    now = _tz(datetime(2026, 3, 11, 8, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(
        duration_minutes=30.0,
        arrival_time=_tz(datetime(2026, 3, 11, 10, 0)),
        arrival_window_start=_tz(datetime(2026, 3, 11, 10, 0)),
        arrival_window_end=_tz(datetime(2026, 3, 11, 11, 0)),
    )

    with pytest.raises(RecommendationError) as exc_info:
        engine.recommend(commute)

    assert exc_info.value.code == "conflicting_constraints"


def test_incomplete_window_raises() -> None:
    """Window with only start or only end raises incomplete_window."""
    now = _tz(datetime(2026, 3, 11, 8, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(
        duration_minutes=30.0,
        arrival_time=None,
        arrival_window_start=_tz(datetime(2026, 3, 11, 10, 0)),
        arrival_window_end=None,
    )

    with pytest.raises(RecommendationError) as exc_info:
        engine.recommend(commute)

    assert exc_info.value.code == "incomplete_window"


def test_invalid_window_start_not_before_end_raises() -> None:
    """Window with start >= end raises invalid_window."""
    now = _tz(datetime(2026, 3, 11, 8, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(
        duration_minutes=30.0,
        arrival_time=None,
        arrival_window_start=_tz(datetime(2026, 3, 11, 11, 0)),
        arrival_window_end=_tz(datetime(2026, 3, 11, 10, 0)),
    )

    with pytest.raises(RecommendationError) as exc_info:
        engine.recommend(commute)

    assert exc_info.value.code == "invalid_window"


# -----------------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------------


def test_short_travel_time_buffer_floor() -> None:
    """Short ETA still gets minimum buffer (5 min), not proportionally tiny."""
    now = _tz(datetime(2026, 3, 11, 9, 0))
    arrival = _tz(datetime(2026, 3, 11, 9, 30))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(duration_minutes=3.0, arrival_time=arrival, risk_mode="aggressive")

    rec = engine.recommend(commute)

    # aggressive: max(5, 0.1*3) = 5
    assert rec.buffer_minutes == 5.0
    # 3 + 5 = 8 min before arrival → leave 09:22
    assert rec.departure_time.minute == 22


def test_already_too_late_raises_no_feasible() -> None:
    """When 'now' is after all feasible departure times, raise no_feasible_recommendation."""
    # Arrival 10:00, ETA 30 min, so we need to leave by 10:00 - (30 + buffer) ≈ 09:20 at latest for aggressive
    now = _tz(datetime(2026, 3, 11, 9, 50))  # already past any feasible departure
    arrival = _tz(datetime(2026, 3, 11, 10, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(duration_minutes=30.0, arrival_time=arrival, risk_mode="aggressive")
    # Latest leave = 10:00 - 35 = 09:25. Now is 09:50 → all candidates in past

    with pytest.raises(RecommendationError) as exc_info:
        engine.recommend(commute)

    assert exc_info.value.code == "no_feasible_recommendation"


def test_already_too_late_fallback_to_safest_still_fails() -> None:
    """Even with fallback to safest, if all departures are in the past we raise."""
    now = _tz(datetime(2026, 3, 11, 9, 55))
    arrival = _tz(datetime(2026, 3, 11, 10, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(duration_minutes=30.0, arrival_time=arrival, risk_mode="balanced")
    # Balanced: 30+10=40 → leave 09:20. Safest: 30+15=45 → leave 09:15. Now 09:55 → both in past

    with pytest.raises(RecommendationError) as exc_info:
        engine.recommend(commute)

    assert exc_info.value.code == "no_feasible_recommendation"


def test_backup_departure_when_aggressive_primary() -> None:
    """When primary is aggressive, backup can be balanced or safest (earlier)."""
    now = _tz(datetime(2026, 3, 11, 8, 0))
    arrival = _tz(datetime(2026, 3, 11, 10, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(duration_minutes=30.0, arrival_time=arrival, risk_mode="aggressive")

    rec = engine.recommend(commute)

    # aggressive: 10:00 - (30+5) = 09:25
    assert rec.departure_time.hour == 9
    assert rec.departure_time.minute == 25
    assert rec.backup_departure_time is not None
    assert rec.backup_departure_time < rec.departure_time
    assert (rec.departure_time - rec.backup_departure_time).total_seconds() >= 5 * 60


def test_no_backup_when_safest_primary() -> None:
    """When primary is safest, there is no safer backup."""
    now = _tz(datetime(2026, 3, 11, 8, 0))
    arrival = _tz(datetime(2026, 3, 11, 10, 0))
    engine = SimpleRecommendationEngine(now_provider=lambda: now)
    commute = _make_commute(duration_minutes=30.0, arrival_time=arrival, risk_mode="safest")

    rec = engine.recommend(commute)

    assert rec.backup_departure_time is None
