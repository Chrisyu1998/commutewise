"""
Deterministic guardrails / validation.

This module will validate that recommendations are feasible and consistent.
No implementation is included in the scaffold.
"""

from __future__ import annotations

from typing import Protocol

from src.schemas import Recommendation, ResolvedCommute, ValidationResult


class Validator(Protocol):
    """Validate a recommendation against a grounded commute."""

    def validate(self, commute: ResolvedCommute, recommendation: Recommendation) -> ValidationResult:
        """Return a structured validation result."""

