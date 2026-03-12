"""
Response schema for Gemini-backed intent parsing.

This module centralizes the dictionary used as `response_schema` when calling
the Google Gen AI SDK. It mirrors the fields of `CommuteIntent` plus a small
number of ambiguity flags, using the SDK's expected schema format
(`type` = STRING/BOOLEAN/ARRAY/OBJECT, with `nullable` for optional fields).
"""

from __future__ import annotations

from typing import Any, Dict


INTENT_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "intent": {
            "type": "STRING",
            "enum": ["commute_plan", "clarification_request"],
            "description": "High-level intent kind.",
        },
        "origin_source": {
            "type": "STRING",
            "enum": ["home", "office", "explicit"],
            "description": "Where the origin comes from.",
        },
        "destination_source": {
            "type": "STRING",
            "enum": ["home", "office", "calendar_event", "explicit"],
            "description": "Where the destination comes from.",
        },
        "origin_text": {
            "type": "STRING",
            "nullable": True,
            "description": "Explicit origin text when origin_source is explicit.",
        },
        "destination_text": {
            "type": "STRING",
            "nullable": True,
            "description": "Explicit destination when destination_source is explicit.",
        },
        "event_query": {
            "type": "STRING",
            "nullable": True,
            "description": "Free-text reference to a calendar event.",
        },
        "arrival_time": {
            "type": "STRING",
            "nullable": True,
            "description": "ISO-8601 timestamp for exact arrival deadline, or null.",
        },
        "arrival_window_start": {
            "type": "STRING",
            "nullable": True,
            "description": "ISO-8601 timestamp for start of arrival window, or null.",
        },
        "arrival_window_end": {
            "type": "STRING",
            "nullable": True,
            "description": "ISO-8601 timestamp for end of arrival window, or null.",
        },
        "risk_mode": {
            "type": "STRING",
            "enum": ["aggressive", "balanced", "safest"],
            "description": "Risk preference.",
        },
        "missing_fields": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Names of missing or ambiguous fields.",
        },
        "destination_ambiguous": {
            "type": "BOOLEAN",
            "description": "True if the destination reference appears ambiguous.",
        },
        "time_ambiguous": {
            "type": "BOOLEAN",
            "description": "True if the time constraint appears ambiguous.",
        },
    },
    "required": ["intent", "origin_source", "destination_source", "risk_mode"],
}

