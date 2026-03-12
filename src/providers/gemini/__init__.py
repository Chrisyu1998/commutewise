"""
Gemini provider package.

Contains thin, testable client wrappers around the Gemini API that are used by
Gemini-backed components such as the planner / intent parser.

This package intentionally exposes a small surface area so the rest of the
codebase depends only on stable interfaces, not on a specific SDK.
"""

from __future__ import annotations

from .client import GeminiClient, GeminiClientProtocol

__all__ = ["GeminiClient", "GeminiClientProtocol"]

