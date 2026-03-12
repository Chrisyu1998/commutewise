"""
Deterministic recommendation engine (departure-time computation).

This module contains pure, deterministic logic only:
- No LLM calls
- No hidden state beyond an injectable "now" provider and optional history input
- Explicit, documented formulas for buffers and selection

**Timezone:** All datetimes (now, arrival_time, window, route context) are assumed
to be comparable; the engine does not convert timezones. Callers should normalize
to a single effective timezone (e.g. user's local or DEFAULT_TIMEZONE) before
calling recommend().

**History:** When history_adjustments is not passed, the engine uses zero overrun
(no historical adjustment). Pass HistoryAdjustments from retrieval to inject
history; this keeps the engine pure and testable without I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Protocol

from src.config import DEFAULT_TIMEZONE
from src.schemas import (
    ConfidenceLevel,
    Recommendation,
    RecommendationCandidate,
    ResolvedCommute,
    RiskMode,
)
from src.time_utils import ensure_timezone, format_hh_mm


class RecommendationError(RuntimeError):
    """
    Structured error when no feasible recommendation can be produced.

    Callers should use .code for branching and .message for logging or display.
    Error codes and when they are raised:

    - missing_route: ResolvedCommute.route is None.
    - invalid_route_duration: route.duration_minutes < 0.
    - route_mismatch: route origin/destination do not match commute origin/destination.
    - conflicting_constraints: Both arrival_time and arrival_window are set.
    - missing_constraints: Neither arrival_time nor a full arrival window is set.
    - incomplete_window: Only one of arrival_window_start / arrival_window_end is set.
    - invalid_window: arrival_window_start >= arrival_window_end.
    - unknown_risk_mode: risk_mode is not aggressive | balanced | safest.
    - no_feasible_recommendation: No candidate is valid (e.g. all departures in the past).
    - no_primary_candidate: Valid candidates exist but none match the desired risk mode (should not occur in practice).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RecommendationEngine(Protocol):
    """Compute a final recommendation from a grounded commute."""

    def recommend(self, commute: ResolvedCommute) -> Recommendation:
        """Return the final departure recommendation or raise RecommendationError."""


@dataclass(frozen=True)
class HistoryAdjustments:
    """
    Summary of historical traffic overrun for a route, used to adjust buffers.

    Pass into recommend(commute, history_adjustments=...) when you have
    retrieval results; otherwise the engine uses zero overrun. Overrun is
    relative to the live ETA at planning time (e.g. actual_duration - planned_eta).
    """

    mean_overrun_minutes: float = 0.0
    p90_overrun_minutes: float = 0.0


# Formula constants (single place for tuning / evaluation).
# Base buffer = max(MIN_BASE_*, FRACTION * duration); then add history adjustment and clamp.
_BUFFER_MIN_MINUTES = 5.0
_BUFFER_MAX_MINUTES = 60.0
_AGGRESSIVE_BASE_MIN = 5.0
_AGGRESSIVE_FRACTION = 0.10
_BALANCED_BASE_MIN = 10.0
_BALANCED_FRACTION = 0.20
_SAFEST_BASE_MIN = 15.0
_SAFEST_FRACTION = 0.30
_AGGRESSIVE_WINDOW_OFFSET_MINUTES = 5.0  # Target = window_end - this
_MIN_BACKUP_GAP_MINUTES = 5.0


class SimpleRecommendationEngine:
    """
    Deterministic implementation of the RecommendationEngine protocol.

    The engine:
    - Validates that the commute is sufficiently specified and route matches commute OD
    - Computes buffers using explicit, risk-mode-based formulas (see module constants)
    - Computes departure candidates and selects a final recommendation
    - Never calls an LLM or performs any non-deterministic operations

    **Past check:** A candidate is invalid if departure_time < now (strict, no tolerance).
    """

    def __init__(self, now_provider: Callable[[], datetime] | None = None) -> None:
        """
        Create a SimpleRecommendationEngine.

        - now_provider: injectable clock function returning the current datetime.
          If it returns a naive datetime, the DEFAULT_TIMEZONE will be attached.
          This is primarily for testability; production can use the default.
        """

        if now_provider is None:
            self._now_provider = lambda: ensure_timezone(datetime.now(), DEFAULT_TIMEZONE)
        else:
            self._now_provider = lambda: ensure_timezone(now_provider(), DEFAULT_TIMEZONE)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def recommend(
        self,
        commute: ResolvedCommute,
        history_adjustments: HistoryAdjustments | None = None,
    ) -> Recommendation:
        """
        Return the final departure recommendation for a resolved commute.

        When history_adjustments is None, the engine uses zero overrun (no
        historical adjustment). Pass a HistoryAdjustments instance from
        retrieval to inject history without the engine performing I/O.
        """
        self._validate_commute(commute)

        now = self._now_provider()
        route = commute.route
        assert route is not None  # for type checkers; validated above

        duration_minutes = float(route.duration_minutes)
        history = (
            history_adjustments
            if history_adjustments is not None
            else self._summarize_history(commute)
        )

        candidates = self._build_candidates(
            commute=commute,
            duration_minutes=duration_minutes,
            history=history,
        )

        # Filter candidates that are feasible given "now" and arrival constraints.
        valid_candidates = [
            c for c in candidates if self._is_candidate_valid(c, commute, duration_minutes, now)
        ]

        if not valid_candidates:
            raise RecommendationError(
                code="no_feasible_recommendation",
                message="No departure time satisfies the arrival constraints with the configured buffers.",
            )

        primary = self._select_primary_candidate(commute.risk_mode, valid_candidates)
        if primary is None:
            raise RecommendationError(
                code="no_primary_candidate",
                message="Could not select a primary recommendation for the given risk mode.",
            )

        backup = self._select_backup_candidate(primary, valid_candidates)

        explanation = self._build_explanation(primary, commute, duration_minutes)
        confidence = self._derive_confidence(primary)

        return Recommendation(
            departure_time=primary.departure_time,
            buffer_minutes=primary.buffer_minutes,
            explanation=explanation,
            confidence=confidence,
            backup_departure_time=backup.departure_time if backup is not None else None,
        )

    # -------------------------------------------------------------------------
    # Validation and helpers
    # -------------------------------------------------------------------------

    def _validate_commute(self, commute: ResolvedCommute) -> None:
        """
        Ensure the commute has the required fields for deterministic recommendation.

        Preconditions:
        - origin and destination are present (schema-enforced)
        - route with non-negative duration is present
        - exactly one of:
          * arrival_time
          * (arrival_window_start and arrival_window_end with start < end)
        """

        if commute.route is None:
            raise RecommendationError(
                code="missing_route",
                message="ResolvedCommute.route must be present with a live duration estimate.",
            )

        if commute.route.duration_minutes < 0:
            raise RecommendationError(
                code="invalid_route_duration",
                message="Route duration_minutes must be non-negative.",
            )

        if commute.route.origin != commute.origin or commute.route.destination != commute.destination:
            raise RecommendationError(
                code="route_mismatch",
                message="Route origin/destination must match commute origin/destination.",
            )

        arrival_time = commute.arrival_time
        window_start = commute.arrival_window_start
        window_end = commute.arrival_window_end

        has_fixed = arrival_time is not None
        has_window = window_start is not None or window_end is not None

        if has_fixed and has_window:
            raise RecommendationError(
                code="conflicting_constraints",
                message="Both arrival_time and arrival_window are set; only one constraint type is allowed.",
            )

        if not has_fixed and not has_window:
            raise RecommendationError(
                code="missing_constraints",
                message="Either arrival_time or an arrival window must be provided.",
            )

        if has_window:
            if window_start is None or window_end is None:
                raise RecommendationError(
                    code="incomplete_window",
                    message="Both arrival_window_start and arrival_window_end must be provided for a window.",
                )
            if not window_start < window_end:
                raise RecommendationError(
                    code="invalid_window",
                    message="arrival_window_start must be strictly earlier than arrival_window_end.",
                )

    def _summarize_history(self, commute: ResolvedCommute) -> HistoryAdjustments:
        """
        Return simple historical overrun adjustments for this commute.

        MVP implementation returns zero adjustments. Week 2+ can replace this
        with logic that:
        - Retrieves similar CommuteHistoryRecord entries
        - Computes mean and p90 ETA overruns
        - Populates HistoryAdjustments accordingly
        """

        return HistoryAdjustments()

    # -------------------------------------------------------------------------
    # Candidate construction
    # -------------------------------------------------------------------------

    def _build_candidates(
        self,
        *,
        commute: ResolvedCommute,
        duration_minutes: float,
        history: HistoryAdjustments,
    ) -> list[RecommendationCandidate]:
        """
        Build recommendation candidates for each risk mode.

        Even if we ultimately return only the candidate matching commute.risk_mode,
        computing all three (aggressive, balanced, safest) makes it easy to
        surface a safer backup option.
        """

        risk_modes: list[RiskMode] = ["aggressive", "balanced", "safest"]
        candidates: list[RecommendationCandidate] = []

        for mode in risk_modes:
            buffer = self._compute_buffer_minutes(
                risk_mode=mode,
                duration_minutes=duration_minutes,
                history=history,
            )

            if commute.arrival_time is not None:
                departure_time = self._departure_for_fixed_arrival(
                    arrival_time=commute.arrival_time,
                    duration_minutes=duration_minutes,
                    buffer_minutes=buffer,
                )
            else:
                assert commute.arrival_window_start is not None
                assert commute.arrival_window_end is not None
                departure_time = self._departure_for_arrival_window(
                    risk_mode=mode,
                    window_start=commute.arrival_window_start,
                    window_end=commute.arrival_window_end,
                    duration_minutes=duration_minutes,
                    buffer_minutes=buffer,
                )

            candidates.append(
                RecommendationCandidate(
                    departure_time=departure_time,
                    buffer_minutes=buffer,
                    strategy=mode,
                    explanation_snippet=None,
                )
            )

        return candidates

    def _compute_buffer_minutes(
        self,
        *,
        risk_mode: RiskMode,
        duration_minutes: float,
        history: HistoryAdjustments,
    ) -> float:
        """
        Compute a buffer in minutes using explicit, risk-mode-based formulas.

        Base buffers (see module constants): aggressive max(5, 0.10*d), balanced
        max(10, 0.20*d), safest max(15, 0.30*d). Then add history adjustment
        and clamp to [_BUFFER_MIN_MINUTES, _BUFFER_MAX_MINUTES].
        """
        d = max(0.0, duration_minutes)

        if risk_mode == "aggressive":
            base = max(_AGGRESSIVE_BASE_MIN, _AGGRESSIVE_FRACTION * d)
            adjusted = base + 0.5 * max(0.0, history.mean_overrun_minutes)
        elif risk_mode == "balanced":
            base = max(_BALANCED_BASE_MIN, _BALANCED_FRACTION * d)
            adjusted = base + 1.0 * max(0.0, history.mean_overrun_minutes)
        elif risk_mode == "safest":
            base = max(_SAFEST_BASE_MIN, _SAFEST_FRACTION * d)
            adjusted = base + 1.0 * max(0.0, history.p90_overrun_minutes)
        else:
            raise RecommendationError(
                code="unknown_risk_mode",
                message=f"Unknown risk mode: {risk_mode}",
            )

        return float(
            min(_BUFFER_MAX_MINUTES, max(_BUFFER_MIN_MINUTES, adjusted))
        )

    @staticmethod
    def _departure_for_fixed_arrival(
        *,
        arrival_time: datetime,
        duration_minutes: float,
        buffer_minutes: float,
    ) -> datetime:
        """Compute departure time for a fixed target arrival."""

        total_travel_minutes = duration_minutes + buffer_minutes
        return arrival_time - timedelta(minutes=total_travel_minutes)

    @staticmethod
    def _departure_for_arrival_window(
        *,
        risk_mode: RiskMode,
        window_start: datetime,
        window_end: datetime,
        duration_minutes: float,
        buffer_minutes: float,
    ) -> datetime:
        """
        Compute departure time for an arrival window.

        Mode-specific target arrival within [window_start, window_end]:
        - aggressive: near the end (window_end - 5 min), clamped to >= window_start if window is short
        - balanced:  middle of the window
        - safest:    at the start of the window
        """
        window_span = window_end - window_start

        if risk_mode == "aggressive":
            target_arrival = window_end - timedelta(minutes=_AGGRESSIVE_WINDOW_OFFSET_MINUTES)
            target_arrival = max(window_start, target_arrival)
        elif risk_mode == "balanced":
            target_arrival = window_start + window_span / 2
        elif risk_mode == "safest":
            target_arrival = window_start
        else:
            raise RecommendationError(
                code="unknown_risk_mode",
                message=f"Unknown risk mode: {risk_mode}",
            )

        total_travel_minutes = duration_minutes + buffer_minutes
        return target_arrival - timedelta(minutes=total_travel_minutes)

    # -------------------------------------------------------------------------
    # Candidate validation and selection
    # -------------------------------------------------------------------------

    @staticmethod
    def _is_candidate_valid(
        candidate: RecommendationCandidate,
        commute: ResolvedCommute,
        duration_minutes: float,
        now: datetime,
    ) -> bool:
        """
        Check whether a candidate is feasible.

        Rules:
        - Departure must not be in the past (strict comparison).
        - For fixed arrival:
          * arrival_time must be >= candidate departure + duration
        - For window (asymmetric): implied arrival must be in
          [window_start - buffer, window_end]. We allow up to buffer_minutes
          early so the safest candidate (targeting window_start, arriving at
          window_start - buffer) is valid; we never allow arrival after window_end.
        """

        if candidate.departure_time < now:
            return False

        travel_duration = timedelta(minutes=duration_minutes)
        implied_arrival = candidate.departure_time + travel_duration

        if commute.arrival_time is not None:
            # Require that we do not arrive after the target.
            return implied_arrival <= commute.arrival_time

        assert commute.arrival_window_start is not None
        assert commute.arrival_window_end is not None
        earliest_ok = commute.arrival_window_start - timedelta(minutes=candidate.buffer_minutes)
        return earliest_ok <= implied_arrival <= commute.arrival_window_end

    @staticmethod
    def _select_primary_candidate(
        desired_mode: RiskMode,
        candidates: list[RecommendationCandidate],
    ) -> RecommendationCandidate | None:
        """
        Select the primary candidate based on the desired risk mode.

        Fallback order:
        - aggressive: aggressive → balanced → safest
        - balanced:  balanced → safest
        - safest:    safest only
        """

        mode_priority: dict[RiskMode, list[RiskMode]] = {
            "aggressive": ["aggressive", "balanced", "safest"],
            "balanced": ["balanced", "safest"],
            "safest": ["safest"],
        }

        for mode in mode_priority[desired_mode]:
            for c in candidates:
                if c.strategy == mode:
                    return c
        return None

    def _select_backup_candidate(
        self,
        primary: RecommendationCandidate,
        candidates: list[RecommendationCandidate],
    ) -> RecommendationCandidate | None:
        """
        Optionally select a safer backup departure time.

        - Backup must use a strictly safer strategy than primary.
        - Backup must leave at least _MIN_BACKUP_GAP_MINUTES earlier than primary.
        - If multiple candidates qualify, choose the earliest departure.
        """

        risk_rank: dict[RiskMode, int] = {
            "aggressive": 0,
            "balanced": 1,
            "safest": 2,
        }

        primary_rank = risk_rank[primary.strategy]
        earliest_backup: RecommendationCandidate | None = None

        for c in candidates:
            if risk_rank[c.strategy] <= primary_rank:
                continue
            # Require that backup is meaningfully earlier.
            if (
                primary.departure_time - c.departure_time
                < timedelta(minutes=_MIN_BACKUP_GAP_MINUTES)
            ):
                continue
            if earliest_backup is None or c.departure_time < earliest_backup.departure_time:
                earliest_backup = c

        return earliest_backup

    # -------------------------------------------------------------------------
    # Explanation and confidence
    # -------------------------------------------------------------------------

    @staticmethod
    def _derive_confidence(candidate: RecommendationCandidate) -> ConfidenceLevel:
        """
        Map risk mode to a coarse confidence level.

        Safest -> high, balanced -> medium, aggressive -> low.
        """
        if candidate.strategy == "safest":
            return "high"
        if candidate.strategy == "balanced":
            return "medium"
        return "low"

    def _build_explanation(
        self,
        candidate: RecommendationCandidate,
        commute: ResolvedCommute,
        duration_minutes: float,
    ) -> str:
        """
        Build a deterministic, human-readable explanation string.

        This explanation is intentionally plain and formula-based. The separate
        response generator component can later refine user-facing wording.
        """

        arrival_phrase: str
        if commute.arrival_time is not None:
            arrival_phrase = f"by {format_hh_mm(commute.arrival_time)}"
        else:
            assert commute.arrival_window_start is not None
            assert commute.arrival_window_end is not None
            arrival_phrase = (
                f"between {format_hh_mm(commute.arrival_window_start)} "
                f"and {format_hh_mm(commute.arrival_window_end)}"
            )

        return (
            f"Using the {candidate.strategy} risk mode, current ETA is "
            f"{duration_minutes:.1f} minutes and the buffer is "
            f"{candidate.buffer_minutes:.1f} minutes. "
            f"Leave at {format_hh_mm(candidate.departure_time)} to arrive {arrival_phrase}."
        )


