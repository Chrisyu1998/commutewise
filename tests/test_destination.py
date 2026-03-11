"""Tests for destination helpers (event → PlaceRef)."""

from __future__ import annotations

from src.schemas import CalendarEvent
from src.time_utils import parse_iso
from src.destination import event_to_place_ref


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


def test_event_to_place_ref_uses_title_and_location() -> None:
    ev = _evt(
        "1", "Dinner with Mom",
        "2026-03-11T18:30:00-07:00", "2026-03-11T20:30:00-07:00",
        location="Olive Garden, Palo Alto",
    )
    place = event_to_place_ref(ev)
    assert place.label == "Dinner with Mom"
    assert place.address == "Olive Garden, Palo Alto"
    assert place.provider_place_id is None


def test_event_to_place_ref_no_location() -> None:
    ev = _evt("2", "Team standup", "2026-03-11T09:00:00-07:00", "2026-03-11T09:15:00-07:00")
    place = event_to_place_ref(ev)
    assert place.label == "Team standup"
    assert place.address is None
    assert place.provider_place_id is None
