"""
Destination resolution helpers.

When the destination is calendar-derived, the orchestrator uses this module
to turn a CalendarEvent into a PlaceRef for ResolvedCommute and downstream
(Maps, recommendation engine). Option A: orchestrator owns the decision to
call this when building ResolvedCommute; implementation lives here for reuse.
"""

from __future__ import annotations

from src.schemas import CalendarEvent, PlaceRef


def event_to_place_ref(event: CalendarEvent) -> PlaceRef:
    """
    Convert a calendar event to a PlaceRef for use as destination.

    Uses event title as the label and event location as the address.
    provider_place_id is left None until Maps/Geocoding integration can
    resolve the address to a stable place ID (Week 2+).
    """
    return PlaceRef(
        label=event.title or None,
        address=event.location,
        provider_place_id=None,
    )
