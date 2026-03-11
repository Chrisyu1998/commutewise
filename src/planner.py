"""
Planner / intent parser.

Week 1: a rule-based parser can implement this interface.
Later: swap in an LLM-based parser that returns `CommuteIntent`.
"""

from __future__ import annotations

from typing import Protocol

from src.schemas import CommuteIntent, CommuteRequest


class Planner(Protocol):
    """Parse raw user input into a structured `CommuteIntent`."""

    def parse(self, request: CommuteRequest) -> CommuteIntent:
        """Return a schema-validated parsed intent."""

