"""
Deterministic recommendation engine (departure-time computation).

This module will contain pure, deterministic logic in Week 1+.
No implementation is included in the scaffold.
"""

from __future__ import annotations

from typing import Protocol

from src.schemas import Recommendation, ResolvedCommute


class RecommendationEngine(Protocol):
    """Compute a final recommendation from a grounded commute."""

    def recommend(self, commute: ResolvedCommute) -> Recommendation:
        """Return the final departure recommendation."""

