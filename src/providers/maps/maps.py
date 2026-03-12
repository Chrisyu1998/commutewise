"""
Maps provider interface and mock implementation.

Week 1 uses MockMapsProvider with local fixture data. Input/output are compatible
with Google Routes API (computeRoutes): origin/destination as place references,
response as duration (we use minutes; Google returns seconds). A future
GoogleMapsProvider would call the API and map its response to RouteEstimate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Protocol

from src.schemas import PlaceRef, RouteEstimate


class UnknownRouteError(Exception):
    """Raised when the maps provider has no route for the given origin/destination."""

    def __init__(self, origin: PlaceRef, destination: PlaceRef) -> None:
        self.origin = origin
        self.destination = destination
        super().__init__(f"No route known for {_place_key(origin)} → {_place_key(destination)}")


def _place_key(place: PlaceRef) -> str:
    """
    Deterministic key for a place for route lookup.

    Prefer provider_place_id (Google Place ID), then address, then label.
    Matches how a real provider would identify places.
    """
    if place.provider_place_id:
        return place.provider_place_id
    if place.address:
        return place.address.strip()
    if place.label:
        return (place.label or "").strip()
    return ""


class MapsProvider(Protocol):
    """
    Fetch live route estimates between two places.

    A future GoogleMapsProvider would:
    - Map PlaceRef to API waypoints (provider_place_id → placeId, or address → latLng via Geocoding).
    - POST to routes.googleapis.com/directions/v2:computeRoutes with origin, destination, travelMode, etc.
    - Parse response: routes[0].duration (e.g. "165s") → duration_minutes; build RouteEstimate(origin, destination, duration_minutes).
    - Raise UnknownRouteError on API errors or zero routes (or map to a known-route failure).
    - Use context (e.g. departure_time, routing_preference) for traffic-aware requests if needed.
    """

    def get_eta(
        self,
        origin: PlaceRef,
        destination: PlaceRef,
        context: Optional[dict[str, Any]] = None,
    ) -> RouteEstimate:
        """
        Return a live route estimate for origin → destination.

        context: optional request context (e.g. departure_time, routing_preference).
        Mock ignores it; real provider may use it for traffic-aware routing.
        """
        ...


def _load_routes_fixture(fixture_path: Path) -> dict[tuple[str, str], float]:
    """
    Load route fixture: list of { origin_key, destination_key, duration_minutes }.
    Returns dict (origin_key, destination_key) -> duration_minutes.
    """
    raw = json.loads(fixture_path.read_text())
    routes = raw.get("routes") if isinstance(raw, dict) else raw
    if not isinstance(routes, list):
        return {}
    out: dict[tuple[str, str], float] = {}
    for r in routes:
        if isinstance(r, dict):
            ok = r.get("origin_key")
            dk = r.get("destination_key")
            dur = r.get("duration_minutes")
            if ok is not None and dk is not None and dur is not None:
                try:
                    out[(str(ok), str(dk))] = float(dur)
                except (TypeError, ValueError):
                    pass
    return out


class MockMapsProvider:
    """
    Deterministic maps provider using a local route fixture.

    Known routes: (origin_key, destination_key) from fixture. Keys are derived
    from PlaceRef via _place_key (provider_place_id > address > label).
    Unknown routes: get_eta raises UnknownRouteError.

    No external API calls; no traffic model. Optional context is accepted
    for interface compatibility but ignored.
    """

    def __init__(self, fixture_path: Optional[Path] = None) -> None:
        # Project root: src/providers/maps/maps.py -> 4 levels up
        if fixture_path is None:
            fixture_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "routes.json"
        self._routes = _load_routes_fixture(fixture_path)

    def get_eta(
        self,
        origin: PlaceRef,
        destination: PlaceRef,
        context: Optional[dict[str, Any]] = None,
    ) -> RouteEstimate:
        origin_key = _place_key(origin)
        destination_key = _place_key(destination)
        if not origin_key or not destination_key:
            raise UnknownRouteError(origin, destination)
        key = (origin_key, destination_key)
        if key not in self._routes:
            raise UnknownRouteError(origin, destination)
        return RouteEstimate(
            origin=origin,
            destination=destination,
            duration_minutes=self._routes[key],
        )
