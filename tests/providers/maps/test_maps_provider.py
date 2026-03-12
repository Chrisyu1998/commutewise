"""Tests for MockMapsProvider: known routes, unknown routes, and key resolution."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from src.schemas import PlaceRef, RouteEstimate
from src.providers.maps import (
    MockMapsProvider,
    UnknownRouteError,
    _load_routes_fixture,
    _place_key,
)


# -----------------------------------------------------------------------------
# _place_key
# -----------------------------------------------------------------------------


def test_place_key_prefers_provider_place_id() -> None:
    assert _place_key(PlaceRef(provider_place_id="ChIJabc", address="123 Main", label="Home")) == "ChIJabc"


def test_place_key_uses_address_when_no_place_id() -> None:
    assert _place_key(PlaceRef(address="123 Main St", label="Home")) == "123 Main St"


def test_place_key_uses_label_when_only_label() -> None:
    assert _place_key(PlaceRef(label="Office")) == "Office"


def test_place_key_empty_when_all_none() -> None:
    assert _place_key(PlaceRef()) == ""


# -----------------------------------------------------------------------------
# MockMapsProvider — known routes
# -----------------------------------------------------------------------------


def test_get_eta_known_route_returns_route_estimate() -> None:
    """Default fixture has Home → Office and Office → Home."""
    provider = MockMapsProvider()
    home = PlaceRef(
        label="Home",
        address="45271 Electric Ter Unit 101, Fremont, CA 94539",
        provider_place_id="ChIJk1UlJffGj4AR-7kpSYyI4Ag",
    )
    office = PlaceRef(
        label="Office",
        address="Google CL5, 1600 Amphitheatre Pkwy, Mountain View, CA 94043",
        provider_place_id="ChIJwVpbIqK5j4ARTSu3RuPzCAk",
    )
    out = provider.get_eta(home, office)
    assert isinstance(out, RouteEstimate)
    assert out.origin == home
    assert out.destination == office
    assert out.duration_minutes == 35.0

    back = provider.get_eta(office, home)
    assert back.duration_minutes == 40.0


def test_get_eta_accepts_optional_context() -> None:
    """Context is accepted for interface compatibility and ignored by mock."""
    provider = MockMapsProvider()
    home = PlaceRef(label="Home", provider_place_id="ChIJk1UlJffGj4AR-7kpSYyI4Ag")
    office = PlaceRef(label="Office", provider_place_id="ChIJwVpbIqK5j4ARTSu3RuPzCAk")
    out = provider.get_eta(home, office, context={"departure_time": "2026-03-11T08:00:00-07:00"})
    assert out.duration_minutes == 35.0


def test_get_eta_custom_fixture_known_route() -> None:
    """Custom fixture path: known route returns correct duration."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            {"routes": [{"origin_key": "A", "destination_key": "B", "duration_minutes": 12.5}]},
            f,
        )
        path = Path(f.name)
    try:
        provider = MockMapsProvider(fixture_path=path)
        origin = PlaceRef(provider_place_id="A")
        dest = PlaceRef(provider_place_id="B")
        out = provider.get_eta(origin, dest)
        assert out.duration_minutes == 12.5
    finally:
        path.unlink(missing_ok=True)


def test_get_eta_calendar_derived_destination_via_address() -> None:
    """Calendar-derived PlaceRef (address from event.location) resolves via default fixture."""
    provider = MockMapsProvider()
    home = PlaceRef(label="Home", provider_place_id="ChIJk1UlJffGj4AR-7kpSYyI4Ag")
    # As from event_to_place_ref: label=event.title, address=event.location, provider_place_id=None
    dinner_dest = PlaceRef(
        label="Dinner with Mom",
        address="Olive Garden, 456 El Camino Real, Palo Alto",
        provider_place_id=None,
    )
    out = provider.get_eta(home, dinner_dest)
    assert out.duration_minutes == 32.0
    assert out.destination.label == "Dinner with Mom"


def test_get_eta_calendar_derived_destination_via_label_when_no_location() -> None:
    """Calendar-derived PlaceRef with no location uses label (event title) as key."""
    provider = MockMapsProvider()
    home = PlaceRef(label="Home", provider_place_id="ChIJk1UlJffGj4AR-7kpSYyI4Ag")
    standup_dest = PlaceRef(label="Team standup", address=None, provider_place_id=None)
    out = provider.get_eta(home, standup_dest)
    assert out.duration_minutes == 35.0


# -----------------------------------------------------------------------------
# MockMapsProvider — unknown routes
# -----------------------------------------------------------------------------


def test_get_eta_unknown_route_raises_unknown_route_error() -> None:
    provider = MockMapsProvider()
    origin = PlaceRef(label="Mars", provider_place_id="place_mars")
    dest = PlaceRef(label="Venus", provider_place_id="place_venus")
    with pytest.raises(UnknownRouteError) as exc_info:
        provider.get_eta(origin, dest)
    assert exc_info.value.origin == origin
    assert exc_info.value.destination == dest
    assert "place_mars" in str(exc_info.value) and "place_venus" in str(exc_info.value)


def test_get_eta_empty_place_key_raises_unknown_route_error() -> None:
    provider = MockMapsProvider()
    origin = PlaceRef(provider_place_id="ChIJk1UlJffGj4AR-7kpSYyI4Ag")
    dest = PlaceRef()  # no id, address, or label
    with pytest.raises(UnknownRouteError):
        provider.get_eta(origin, dest)


# -----------------------------------------------------------------------------
# Fixture loading
# -----------------------------------------------------------------------------


def test_load_routes_fixture_dict_with_routes_key() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            {
                "routes": [
                    {"origin_key": "X", "destination_key": "Y", "duration_minutes": 5.0},
                ]
            },
            f,
        )
        path = Path(f.name)
    try:
        out = _load_routes_fixture(path)
        assert out == {("X", "Y"): 5.0}
    finally:
        path.unlink(missing_ok=True)


def test_load_routes_fixture_list_top_level() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            [{"origin_key": "P", "destination_key": "Q", "duration_minutes": 10}],
            f,
        )
        path = Path(f.name)
    try:
        out = _load_routes_fixture(path)
        assert out == {("P", "Q"): 10.0}
    finally:
        path.unlink(missing_ok=True)


def test_load_routes_fixture_skips_invalid_entries() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            {
                "routes": [
                    {"origin_key": "A", "destination_key": "B", "duration_minutes": 1.0},
                    {"origin_key": "C"},  # missing destination_key, duration
                    {"destination_key": "D", "duration_minutes": 2.0},  # missing origin_key
                    {"origin_key": "E", "destination_key": "F", "duration_minutes": "not_a_number"},
                ]
            },
            f,
        )
        path = Path(f.name)
    try:
        out = _load_routes_fixture(path)
        assert out == {("A", "B"): 1.0}
    finally:
        path.unlink(missing_ok=True)
