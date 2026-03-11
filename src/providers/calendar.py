"""
Calendar provider interface.

Week 1 uses a mock implementation; real API integration comes later.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Protocol, Sequence

from src.schemas import CalendarEvent


class CalendarProvider(Protocol):
    """Fetch and resolve calendar events."""

    def get_events(self, start: datetime, end: datetime) -> List[CalendarEvent]:
        """Return normalized events in the given time range."""

    def resolve_event(self, query: str, events: Sequence[CalendarEvent]) -> List[CalendarEvent]:
        """
        Return candidate events matching a user query.

        For MVP, returning multiple candidates supports an ambiguity/clarification flow.
        """

