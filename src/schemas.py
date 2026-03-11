"""
Core typed schemas for CommuteWise.

Data models only; no business logic. Used across planner, providers,
recommendation engine, orchestrator, and validator.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# -----------------------------------------------------------------------------
# Enums (as Literal types for clarity and validation)
# -----------------------------------------------------------------------------

OriginSource = Literal["home", "office", "explicit"]
DestinationSource = Literal["home", "office", "calendar_event", "explicit"]
RiskMode = Literal["aggressive", "balanced", "safest"]
CommuteIntentKind = Literal["commute_plan", "clarification_request"]
ConfidenceLevel = Literal["low", "medium", "high"]

def _require_timezone(dt: datetime) -> datetime:
    """
    Ensure a datetime has timezone information.

    CommuteWise treats all timestamps as timezone-aware to avoid ambiguity across
    calendar events, history records, and evaluation replays.
    """

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("datetime must be timezone-aware")
    return dt


# -----------------------------------------------------------------------------
# User input
# -----------------------------------------------------------------------------


class CommuteRequest(BaseModel):
    """
    Raw user commute request (input to the system).

    Wraps the natural-language query for tracing and optional metadata later.
    """

    query: str = Field(..., description="Natural-language question, e.g. 'When should I leave for the office?'")


# -----------------------------------------------------------------------------
# Parsed intent (planner output)
# -----------------------------------------------------------------------------


class CommuteIntent(BaseModel):
    """
    Structured representation of the user's commute request after parsing.

    Produced by the planner / intent parser from a CommuteRequest.
    """

    intent: CommuteIntentKind = Field(
        default="commute_plan",
        description="Type of intent: commute_plan or clarification_request.",
    )
    origin_source: OriginSource = Field(
        default="home",
        description="Where the origin comes from: home, office, or explicit.",
    )
    destination_source: DestinationSource = Field(
        ...,
        description="Where the destination comes from: home, office, calendar_event, or explicit.",
    )
    destination_text: Optional[str] = Field(
        default=None,
        description="Explicit destination address or label when destination_source is 'explicit'.",
    )
    event_query: Optional[str] = Field(
        default=None,
        description="Free-text event reference when destination_source is 'calendar_event', e.g. 'dinner with Mom'.",
    )
    origin_text: Optional[str] = Field(
        default=None,
        description="Explicit origin address or label when origin_source is 'explicit'.",
    )
    arrival_time: Optional[datetime] = Field(
        default=None,
        description="Exact target arrival time when user specifies a single time.",
    )
    arrival_window_start: Optional[datetime] = Field(
        default=None,
        description="Start of acceptable arrival window, e.g. 'arrive between 10 and 11'.",
    )
    arrival_window_end: Optional[datetime] = Field(
        default=None,
        description="End of acceptable arrival window.",
    )
    risk_mode: RiskMode = Field(
        default="balanced",
        description="User preference: aggressive, balanced, or safest.",
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Fields that could not be inferred and may require clarification.",
    )

    @field_validator("arrival_time", "arrival_window_start", "arrival_window_end")
    @classmethod
    def _validate_timezone_aware_intent_times(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return None
        return _require_timezone(v)


# -----------------------------------------------------------------------------
# Calendar (provider output)
# -----------------------------------------------------------------------------


class CalendarEvent(BaseModel):
    """
    Normalized calendar event used for destination and deadline resolution.

    Returned by the calendar provider; may be matched from event_query.
    """

    id: str = Field(..., description="Stable event identifier.")
    title: str = Field(..., description="Event title.")
    start: datetime = Field(..., description="Event start time.")
    end: datetime = Field(..., description="Event end time.")
    location: Optional[str] = Field(default=None, description="Event location or address.")
    timezone: Optional[str] = Field(
        default=None,
        description="Event timezone (IANA), e.g. 'America/Los_Angeles'.",
    )

    @field_validator("start", "end")
    @classmethod
    def _validate_timezone_aware_event_times(cls, v: datetime) -> datetime:
        return _require_timezone(v)


class EventResolutionResult(BaseModel):
    """
    Result of resolving a user query to calendar event(s).

    When multiple candidates match (e.g. "lunch" → Lunch with Sarah, Lunch with Alex),
    the orchestrator can ask the user: "Do you mean X or Y?" using candidate titles,
    then call resolve_event again with the user's reply to get a single event.
    """

    candidates: list[CalendarEvent] = Field(
        default_factory=list,
        description="Matching events, sorted by score descending then start.",
    )
    scores: list[float] = Field(
        default_factory=list,
        description="Match score for each candidate (same order as candidates).",
    )

    @property
    def needs_clarification(self) -> bool:
        """True when there is more than one candidate; caller should ask user to disambiguate."""
        return len(self.candidates) > 1


# -----------------------------------------------------------------------------
# Maps (provider output)
# -----------------------------------------------------------------------------

class PlaceRef(BaseModel):
    """
    Reference to a real-world place.

    Use this across providers and history records to keep place identity stable
    for retrieval (Week 2) and evaluation. Office and home locations in
    configuration (see `src.config`) are typically expressed as `PlaceRef`
    instances. Time-related fields that reference these places should be
    constructed via helpers in `src.time_utils` to ensure timezone-awareness.
    """

    label: Optional[str] = Field(
        default=None,
        description="Human-friendly label, e.g. 'Home' or 'Sunnyvale Office'.",
    )
    address: Optional[str] = Field(
        default=None,
        description="Normalized address string, if known.",
    )
    provider_place_id: Optional[str] = Field(
        default=None,
        description="Stable provider-specific identifier (e.g. Google Place ID) if available.",
    )


class RouteEstimate(BaseModel):
    """
    Live route ETA from origin to destination.

    Returned by the maps provider; used as input to the recommendation engine.
    """

    origin: PlaceRef = Field(..., description="Origin place reference.")
    destination: PlaceRef = Field(..., description="Destination place reference.")
    duration_minutes: float = Field(..., ge=0, description="Estimated travel time in minutes.")


# -----------------------------------------------------------------------------
# Resolved commute (post-orchestration, grounded state)
# -----------------------------------------------------------------------------


class ResolvedCommute(BaseModel):
    """
    Grounded, fully-resolved commute ready for deterministic recommendation.

    This is produced after orchestration: destinations/origins are resolved to
    concrete PlaceRef objects, and calendar/maps context is attached as needed.
    """

    origin: PlaceRef = Field(..., description="Resolved origin place.")
    destination: PlaceRef = Field(..., description="Resolved destination place.")
    event: Optional[CalendarEvent] = Field(
        default=None,
        description="Resolved calendar event when destination is event-derived.",
    )
    route: Optional[RouteEstimate] = Field(
        default=None,
        description="Live route estimate when available.",
    )
    arrival_time: Optional[datetime] = Field(
        default=None,
        description="Exact target arrival time (timezone-aware).",
    )
    arrival_window_start: Optional[datetime] = Field(
        default=None,
        description="Start of acceptable arrival window (timezone-aware).",
    )
    arrival_window_end: Optional[datetime] = Field(
        default=None,
        description="End of acceptable arrival window (timezone-aware).",
    )
    risk_mode: RiskMode = Field(
        default="balanced",
        description="Risk preference used by the recommendation engine.",
    )

    @field_validator("arrival_time", "arrival_window_start", "arrival_window_end")
    @classmethod
    def _validate_timezone_aware_resolved_times(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return None
        return _require_timezone(v)


# -----------------------------------------------------------------------------
# Commute history (retrieval / RAG)
# -----------------------------------------------------------------------------


class CommuteHistoryRecord(BaseModel):
    """
    One past commute episode for retrieval and similarity comparison.

    Stored in the history store; retrieved by the history retriever. Timestamps
    should be timezone-aware, typically created via helpers in `src.time_utils`.
    """

    origin: PlaceRef = Field(..., description="Origin place reference.")
    destination: PlaceRef = Field(..., description="Destination place reference.")
    event_type: str = Field(..., description="Category, e.g. 'office_commute'.")
    planned_arrival_time: Optional[datetime] = Field(
        default=None,
        description=(
            "Planned/target arrival time for this commute (timezone-aware, "
            "see `time_utils` for construction/parsing)."
        ),
    )
    departure_time: datetime = Field(
        ...,
        description="Actual departure timestamp (timezone-aware).",
    )
    arrival_time: Optional[datetime] = Field(
        default=None,
        description=(
            "Actual arrival timestamp when known (timezone-aware, built via "
            "`time_utils`)."
        ),
    )
    actual_duration_min: int = Field(..., ge=0, description="Actual travel duration in minutes.")
    late: bool = Field(..., description="Whether the user arrived late.")
    condition_tags: list[str] = Field(
        default_factory=list,
        description="Tags describing conditions, e.g. ['rush_hour', 'light_rain'].",
    )
    notes: Optional[str] = Field(default=None, description="Optional free-text notes.")

    @field_validator("planned_arrival_time", "departure_time", "arrival_time")
    @classmethod
    def _validate_timezone_aware_history_times(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return None
        return _require_timezone(v)


# -----------------------------------------------------------------------------
# Recommendation (engine output)
# -----------------------------------------------------------------------------


class RecommendationCandidate(BaseModel):
    """
    One candidate departure recommendation before final selection.

    The recommendation engine may produce multiple candidates (e.g. by risk mode);
    the orchestrator or ranking step selects one as the final recommendation.
    """

    departure_time: datetime = Field(..., description="Recommended departure time.")
    buffer_minutes: float = Field(..., ge=0, description="Buffer included in this candidate.")
    strategy: RiskMode = Field(..., description="Risk strategy this candidate follows.")
    explanation_snippet: Optional[str] = Field(
        default=None,
        description="Optional short rationale for this candidate.",
    )

    @field_validator("departure_time")
    @classmethod
    def _validate_timezone_aware_candidate_times(cls, v: datetime) -> datetime:
        return _require_timezone(v)


class Recommendation(BaseModel):
    """
    Final recommendation returned to the user.

    Produced after selecting (or computing) the chosen candidate; includes
    user-facing explanation and optional backup.
    """

    departure_time: datetime = Field(..., description="Recommended departure time.")
    buffer_minutes: float = Field(..., ge=0, description="Buffer included in the recommendation.")
    explanation: str = Field(..., description="User-facing explanation of the recommendation.")
    confidence: ConfidenceLevel = Field(
        default="medium",
        description="Confidence in the recommendation: low, medium, or high.",
    )
    backup_departure_time: Optional[datetime] = Field(
        default=None,
        description="Optional earlier departure for lower lateness risk.",
    )

    @field_validator("departure_time", "backup_departure_time")
    @classmethod
    def _validate_timezone_aware_recommendation_times(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return None
        return _require_timezone(v)


# -----------------------------------------------------------------------------
# Validation (guardrail output)
# -----------------------------------------------------------------------------


class ValidationResult(BaseModel):
    """
    Result of guardrail / validator checks on a recommendation.

    Used to decide whether to surface the recommendation or request clarification.
    """

    valid: bool = Field(..., description="True if all checks passed.")
    passed_checks: list[str] = Field(
        default_factory=list,
        description="Names of checks that passed.",
    )
    failed_checks: list[str] = Field(
        default_factory=list,
        description="Names of checks that failed.",
    )
    message: Optional[str] = Field(
        default=None,
        description="Optional human-readable summary for debugging or user feedback.",
    )
