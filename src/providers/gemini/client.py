"""
Gemini client wrapper used by Gemini-backed components (e.g. planner).

This module intentionally keeps the interface small and testable. The default
implementation does not perform real network calls yet; tests inject a fake
client that implements the same protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol

import json
import os

from google import genai


class GeminiClientProtocol(Protocol):
    """
    Minimal protocol for a Gemini client used by the planner.

    Concrete implementations may wrap an HTTP client or official SDK, but the
    rest of the codebase should depend only on this interface.
    """

    def generate_structured_intent(
        self,
        *,
        system_prompt: str,
        user_query: str,
        json_schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Run a Gemini call that returns a JSON object following `json_schema`.

        The planner expects the returned dict to be immediately consumable as
        keyword arguments to the `CommuteIntent` schema after light
        post-processing (timezone normalization, ambiguity mapping, etc.).
        """


@dataclass
class GeminiClient(GeminiClientProtocol):
    """
    Placeholder Gemini client.

    This implementation uses the official Google Gen AI SDK (`google-genai`)
    and reads the API key from the environment. Tests can still inject a fake
    client by implementing `GeminiClientProtocol`.
    """

    # Default Gemini model used for structured intent parsing. `gemini-2.0-flash`
    # is widely available and supports JSON-mode responses.
    model: str = "gemini-2.5-flash"
    _client: genai.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Gemini API key not found. Set GEMINI_API_KEY or GOOGLE_API_KEY "
                "in your environment before using GeminiClient."
            )
        self._client = genai.Client(api_key=api_key)

    def generate_structured_intent(
        self,
        *,
        system_prompt: str,
        user_query: str,
        json_schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Call the Gemini API with a schema-constrained JSON response.

        The planner passes in a JSON schema that mirrors `CommuteIntent`. This
        method requests `application/json` output and parses it into a Python
        dict for further normalization and Pydantic validation.
        """

        response = self._client.models.generate_content(
            model=self.model,
            contents=[
                {"role": "user", "parts": [{"text": user_query}]},
            ],
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "response_schema": json_schema,
            },
        )

        # The SDK returns JSON as a string in response.text when using
        # response_mime_type="application/json".
        try:
            return json.loads(response.text)
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Failed to parse Gemini JSON response: {exc}") from exc

