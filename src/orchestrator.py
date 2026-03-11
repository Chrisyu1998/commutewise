"""
Orchestrator.

Wires planner → providers → recommendation → validation → response generation.
Mock-first and CLI-first for Week 1.

The concrete implementation will:
- Accept configuration (e.g. an `AppConfig` from `src.config`) in its
  constructor so that office/home defaults and timezone are explicit.
- Use helpers from `src.time_utils` to normalize all planner-produced
  datetimes into timezone-aware values.

No implementation is included in the scaffold.
"""

from __future__ import annotations

from typing import Protocol

from src.schemas import CommuteRequest, Recommendation


class Orchestrator(Protocol):
    """End-to-end entrypoint from request to recommendation."""

    def run(self, request: CommuteRequest) -> Recommendation:
        """Return a final, validated recommendation for a request."""

