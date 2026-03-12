"""
Planner / intent parser.

Week 1: a rule-based parser implements this interface (no LLM).
Later: swap in an LLM-based parser that returns `CommuteIntent`.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any, Dict, Optional, Protocol, Tuple

from src.config import DEFAULT_TIMEZONE
from src.schemas import CommuteIntent, CommuteRequest
from src.time_utils import combine_date_time, ensure_timezone


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


class PlannerError(Exception):
    """Base error for planner-related failures."""


class PlannerModelError(PlannerError):
    """Structured output from Gemini did not match the expected schema."""


class PlannerTransportError(PlannerError):
    """Transport or API-level error while calling Gemini."""


def _parse_iso_datetime(value: Optional[str], timezone: str) -> Optional[datetime]:
    """
    Parse an ISO-8601 datetime string and ensure it is timezone-aware.

    Gemini may return naive timestamps; we normalize them to the configured
    timezone to satisfy schema validators and avoid ambiguity.
    """

    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        # If the model returns something non-ISO, ignore it; downstream logic
        # will rely on missing_fields/clarification instead of a guessed time.
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = ensure_timezone(dt, timezone)
    return dt


class GeminiPlanner:
    """
    Planner implementation that uses Gemini for natural-language understanding.

    - Uses Gemini to classify intent and extract high-level slots.
    - Applies deterministic post-processing to normalize timestamps and
      ambiguity flags into a `CommuteIntent`.
    - Keeps downstream components unaware of Gemini-specific details: the
      public interface is still `Planner.parse(...) -> CommuteIntent`.
    """

    def __init__(
        self,
        *,
        gemini_client: "GeminiClientProtocol",
        timezone: str = DEFAULT_TIMEZONE,
        reference_date: date | None = None,
    ) -> None:
        self._client = gemini_client
        self._timezone = timezone
        self._reference_date = reference_date

    def _build_system_prompt(self) -> str:
        """
        System prompt describing the intent parsing task for Gemini.

        The prompt delegates natural-language understanding to the model while
        keeping all time arithmetic and safety checks in deterministic code.
        """

        ref = self._reference_date or date.today()
        ref_str = ref.isoformat()  # e.g. "2026-03-12"

        return (
            "You are an intent parser for a commute planning assistant called "
            "CommuteWise. Your job is to read a single user query about when "
            "they should leave for a trip and return a JSON object that fills "
            "in structured fields.\n\n"
            f"Today's date is {ref_str}. Use this date when constructing "
            "ISO-8601 timestamps for time references like 'between 10 and 11' "
            f"(e.g. arrival_window_start={ref_str}T10:00:00, "
            f"arrival_window_end={ref_str}T11:00:00).\n\n"
            "Use these rules:\n"
            "- Only use information stated or clearly implied in the query.\n"
            "- Do not invent calendar events or addresses.\n"
            "- If destination or time constraints are missing or ambiguous, "
            "leave the corresponding fields null and record the issue in "
            "`missing_fields`.\n"
            "- When a time window like 'between X and Y' is stated, populate "
            "arrival_window_start and arrival_window_end as full ISO-8601 "
            "timestamps using today's date. Do NOT add them to missing_fields.\n"
            "- Do not perform time arithmetic; only interpret the user's "
            "constraints.\n"
            "- Prefer office commutes when the query clearly references "
            "an office; otherwise, treat fuzzy event references as "
            "calendar_event destinations.\n"
        )

    def _build_json_schema(self) -> Dict[str, Any]:
        """
        JSON schema used to constrain Gemini's structured output.

        This mirrors the CommuteIntent fields plus a small number of helper
        flags for ambiguity; timestamps are represented as ISO-8601 strings or
        null and normalized to timezone-aware datetimes in Python.
        """

        from src.providers.gemini.intent_schema import INTENT_RESPONSE_SCHEMA

        # Return the shared schema so updates are centralized.
        return INTENT_RESPONSE_SCHEMA

    def parse(self, request: CommuteRequest) -> CommuteIntent:
        query = (request.query or "").strip()
        if not query:
            # Defer to downstream clarification instead of inventing structure.
            return CommuteIntent(
                intent="commute_plan",
                origin_source="home",
                destination_source="home",
                destination_text=None,
                event_query=None,
                origin_text=None,
                arrival_time=None,
                arrival_window_start=None,
                arrival_window_end=None,
                risk_mode="balanced",
                missing_fields=["destination", "arrival_time_or_window"],
            )

        system_prompt = self._build_system_prompt()
        schema = self._build_json_schema()

        try:
            raw = self._client.generate_structured_intent(
                system_prompt=system_prompt,
                user_query=query,
                json_schema=schema,
            )
        except Exception as exc:
            # Defer import so code paths that do not use Gemini do not require
            # the SDK at import time.
            from google.genai.errors import ClientError  # type: ignore[import]

            if isinstance(exc, ClientError):
                raise PlannerTransportError(
                    f"Gemini API error while parsing intent: {exc}"
                ) from exc
            # Anything else at this layer is treated as a model/schema-level
            # problem.
            raise PlannerModelError(
                f"Gemini intent parsing failed: {exc}"
            ) from exc

        if not isinstance(raw, dict):
            # The planner expects a JSON object matching the response schema.
            raise PlannerModelError(
                f"Gemini intent parsing failed: expected object, got {type(raw).__name__}"
            )

        intent_kind = raw.get("intent") or "commute_plan"
        origin_source = raw.get("origin_source") or "home"
        destination_source = raw.get("destination_source") or "home"
        origin_text = raw.get("origin_text")
        destination_text = raw.get("destination_text")
        event_query = raw.get("event_query")

        arrival_time = _parse_iso_datetime(
            raw.get("arrival_time"), self._timezone
        )
        arrival_window_start = _parse_iso_datetime(
            raw.get("arrival_window_start"), self._timezone
        )
        arrival_window_end = _parse_iso_datetime(
            raw.get("arrival_window_end"), self._timezone
        )

        risk_mode = raw.get("risk_mode") or "balanced"

        missing_fields = list(raw.get("missing_fields") or [])
        if raw.get("destination_ambiguous"):
            missing_fields.append("ambiguous_destination")
        if raw.get("time_ambiguous"):
            missing_fields.append("ambiguous_time")

        return CommuteIntent(
            intent=intent_kind,
            origin_source=origin_source,
            destination_source=destination_source,
            destination_text=destination_text,
            event_query=event_query,
            origin_text=origin_text,
            arrival_time=arrival_time,
            arrival_window_start=arrival_window_start,
            arrival_window_end=arrival_window_end,
            risk_mode=risk_mode,
            missing_fields=missing_fields,
        )


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.providers.gemini import GeminiClientProtocol


