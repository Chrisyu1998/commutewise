"""
Orchestrator: minimal Week 1 implementation.

Takes a parsed or simple input (CommuteIntent), resolves office or calendar
destination, calls mock calendar/maps providers, runs the recommendation engine,
and returns a structured result (Recommendation or clarification needed).

No graph framework; linear flow. No LLM; intent is supplied by caller or a
rule-based planner. Readable and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, List, Literal, Optional, Protocol

from src.config import AppConfig, default_app_config
from src.destination import event_to_place_ref
from src.schemas import (
    CalendarEvent,
    CommuteIntent,
    CommuteRequest,
    PlaceRef,
    Recommendation,
    ResolvedCommute,
)
from src.time_utils import ensure_timezone

from src.providers.maps import MapsProvider


def _format_clarification_message(candidates: list[CalendarEvent]) -> str:
    """Build user-facing 'Do you mean X or Y?' message from candidate event titles."""
    titles = [e.title for e in candidates]
    if len(titles) == 1:
        return f"Do you mean {titles[0]}?"
    if len(titles) == 2:
        return f"Do you mean {titles[0]} or {titles[1]}?"
    # "Do you mean A, B, or C?"
    return "Do you mean " + ", ".join(titles[:-1]) + ", or " + titles[-1] + "?"

def _format_date_window(start: datetime, end: datetime) -> str:
    """Format a searched datetime window for user-facing messages."""
    return f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"


NO_EVENT_FOUND_MESSAGE = (
    "We cannot find a related calendar event. You can let me know the date and location."
)

NEEDS_ARRIVAL_INFO_MESSAGE = (
    "What time do you wish to arrive? (e.g. 'by 10:00' or 'between 10 and 11')"
)


OrchestratorResultKind = Literal[
    "recommendation",
    "clarification",
    "no_event_found",
    "needs_arrival_info",
]


@dataclass(frozen=True)
class OrchestratorResult:
    """
    Tagged result from the orchestrator.

    This replaces the "exactly one of N optional fields" pattern with an
    explicit `kind`, which is easier to extend safely as the orchestration
    workflow grows.
    """

    kind: OrchestratorResultKind
    recommendation: Optional[Recommendation] = None
    clarification_candidates: Optional[list[CalendarEvent]] = None
    clarification_message: Optional[str] = None
    message: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind == "recommendation":
            if self.recommendation is None:
                raise ValueError("recommendation result requires recommendation")
            return

        if self.kind == "clarification":
            if not self.clarification_candidates:
                raise ValueError("clarification result requires clarification_candidates")
            if not self.clarification_message:
                raise ValueError("clarification result requires clarification_message")
            return

        if self.kind in ("no_event_found", "needs_arrival_info"):
            if not self.message:
                raise ValueError(f"{self.kind} result requires message")
            return

        raise ValueError(f"Unknown OrchestratorResult kind: {self.kind}")


class Orchestrator(Protocol):
    """End-to-end entrypoint from request to structured result."""

    def run(self, request: CommuteRequest) -> OrchestratorResult:
        """Parse request, resolve destination, recommend; return result or clarification needed."""

    def run_with_intent(self, intent: CommuteIntent) -> OrchestratorResult:
        """Run with an already-parsed intent (e.g. from tests or a planner)."""


def _default_now() -> datetime:
    """Current time in default timezone (for event window and tests)."""
    from src.config import DEFAULT_TIMEZONE

    return ensure_timezone(datetime.now(), DEFAULT_TIMEZONE)


class SimpleOrchestrator:
    """
    Minimal Week 1 orchestrator: linear flow, no graph, no LLM.

    - Resolves origin (home from config) and destination (office config or
      calendar event or explicit text).
    - Calls calendar provider for get_events + resolve_event when destination
      is calendar_event.
    - Calls maps provider for ETA.
    - Calls recommendation engine; returns Recommendation or clarification.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        *,
        calendar_provider: Optional["CalendarProvider"] = None,
        maps_provider: Optional[MapsProvider] = None,
        recommendation_engine: Optional["RecommendationEngine"] = None,
        now_provider: Optional[Callable[[], datetime]] = None,
        planner: Optional["Planner"] = None,
    ) -> None:
        from src.providers import MockCalendarProvider, MockMapsProvider
        from src.recommendation import SimpleRecommendationEngine

        self._config = config or default_app_config()
        self._calendar = calendar_provider or MockCalendarProvider()
        self._maps = maps_provider or MockMapsProvider()
        self._engine = recommendation_engine or SimpleRecommendationEngine(
            now_provider=now_provider
        )
        self._now = now_provider or _default_now
        self._planner = planner  # Optional: for run(request)

    def run(self, request: CommuteRequest) -> OrchestratorResult:
        """Parse request with planner (if set), then run with intent."""
        if self._planner is None:
            raise ValueError(
                "SimpleOrchestrator.run(request) requires a planner; "
                "use run_with_intent(intent) for pre-parsed input, or inject a planner."
            )
        intent = self._planner.parse(request)
        return self.run_with_intent(intent)

    def run_with_intent(self, intent: CommuteIntent) -> OrchestratorResult:
        """
        Resolve destination, get ETA, run recommendation engine; return result.

        - Office: use config.office.place.
        - Calendar event: get_events(start, end), resolve_event(query, events);
          if one candidate → use it; if multiple → return clarification_candidates.
        - Explicit: PlaceRef from intent.destination_text.
        """
        origin = self._resolve_origin(intent)
        destination, event, calendar_window = self._resolve_destination(intent)
        if destination is None:
            # No candidates or multiple candidates (calendar only)
            if isinstance(event, list):
                if len(event) == 0:
                    window_suffix = ""
                    if calendar_window is not None:
                        start, end = calendar_window
                        window_suffix = f" (Searched { _format_date_window(start, end) })"
                    return OrchestratorResult(
                        kind="no_event_found",
                        message=NO_EVENT_FOUND_MESSAGE + window_suffix,
                    )
                return OrchestratorResult(
                    kind="clarification",
                    clarification_candidates=event,
                    clarification_message=_format_clarification_message(event),
                )
            raise AssertionError("destination None but event is not a list")

        chosen_event: Optional[CalendarEvent] = (
            event if isinstance(event, CalendarEvent) else None
        )

        # If arrival time/window is missing:
        # - For calendar-event destinations, default to arriving by event start time.
        # - Otherwise, ask the user instead of calling the recommendation engine.
        has_arrival_time = intent.arrival_time is not None
        has_arrival_window = (
            intent.arrival_window_start is not None
            and intent.arrival_window_end is not None
        )
        inferred_arrival_time: Optional[datetime] = None
        if not has_arrival_time and not has_arrival_window:
            if chosen_event is not None:
                inferred_arrival_time = chosen_event.start
                has_arrival_time = True
            else:
                return OrchestratorResult(
                    kind="needs_arrival_info",
                    message=NEEDS_ARRIVAL_INFO_MESSAGE,
                )

        route = self._get_route(origin, destination)
        commute = ResolvedCommute(
            origin=origin,
            destination=destination,
            event=chosen_event,
            route=route,
            arrival_time=intent.arrival_time or inferred_arrival_time,
            arrival_window_start=intent.arrival_window_start,
            arrival_window_end=intent.arrival_window_end,
            risk_mode=intent.risk_mode,
        )
        recommendation = self._engine.recommend(commute)
        return OrchestratorResult(kind="recommendation", recommendation=recommendation)

    def _resolve_origin(self, intent: CommuteIntent) -> PlaceRef:
        """Resolve origin to a PlaceRef; Week 1 defaults to home."""
        if intent.origin_source == "home":
            return self._config.home.place
        if intent.origin_source == "office":
            return self._config.office.place
        # explicit: use origin_text as label/address
        return PlaceRef(
            label=intent.origin_text,
            address=intent.origin_text,
            provider_place_id=None,
        )

    def _resolve_destination(
        self, intent: CommuteIntent
    ) -> tuple[
        Optional[PlaceRef],
        Optional[CalendarEvent] | List[CalendarEvent],
        Optional[tuple[datetime, datetime]],
    ]:
        """
        Resolve destination from intent.

        Returns (PlaceRef, event_or_none, None) or (None, list[CalendarEvent], window).
        When calendar has multiple candidates, returns (None, candidates)
        for clarification.
        """
        if intent.destination_source == "office":
            return (self._config.office.place, None, None)
        if intent.destination_source == "explicit":
            return (
                PlaceRef(
                    label=intent.destination_text,
                    address=intent.destination_text,
                    provider_place_id=None,
                ),
                None,
                None,
            )
        if intent.destination_source != "calendar_event" or not intent.event_query:
            raise ValueError(
                "Intent destination_source is calendar_event but event_query is missing."
            )

        now = self._now()
        start = now
        end = now + timedelta(days=7)
        events = self._calendar.get_events(start, end)
        result = self._calendar.resolve_event(intent.event_query, events)

        if not result.candidates:
            return (None, [], (start, end))
        if result.needs_clarification:
            return (None, result.candidates, (start, end))

        chosen = result.candidates[0]
        return (event_to_place_ref(chosen), chosen, None)

    def _get_route(self, origin: PlaceRef, destination: PlaceRef):
        """Get route ETA from maps provider."""
        return self._maps.get_eta(origin, destination)


# Optional type-only imports to avoid circular imports at runtime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.planner import Planner
    from src.providers.calendar import CalendarProvider
    from src.recommendation import RecommendationEngine
