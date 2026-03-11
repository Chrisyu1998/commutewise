"""
Maps provider interface.

Week 1 uses a mock implementation; real API integration comes later.
"""

from __future__ import annotations

from typing import Protocol

from src.schemas import PlaceRef, RouteEstimate


class MapsProvider(Protocol):
    """Fetch live route estimates between two places."""

    def get_eta(self, origin: PlaceRef, destination: PlaceRef) -> RouteEstimate:
        """Return a live route estimate for origin → destination."""

