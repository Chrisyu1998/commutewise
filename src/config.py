"""
Application configuration for CommuteWise.

Week 1 focuses on a simple, in-memory configuration that defines:
- Home and office locations
- Default timezone
- Default risk mode

This module intentionally avoids I/O and external dependencies so it stays
interview-friendly and easy to test. Real config loading (env files, flags,
etc.) can be layered on later if needed.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.schemas import PlaceRef, RiskMode


# Central defaults for local development / tests.
DEFAULT_TIMEZONE: str = "America/Los_Angeles"
DEFAULT_RISK_MODE: RiskMode = "balanced"


@dataclass(frozen=True)
class PlaceConfig:
    """Configuration for a named place such as Home or Office."""

    name: str
    place: PlaceRef


@dataclass(frozen=True)
class AppConfig:
    """
    Top-level application configuration.

    This struct is passed into orchestrator / providers so configuration
    remains explicit and easy to mock in tests.
    """

    default_timezone: str
    home: PlaceConfig
    office: PlaceConfig
    default_risk_mode: RiskMode = DEFAULT_RISK_MODE


def get_default_home_config() -> PlaceConfig:
    """Return the default Home configuration."""

    return PlaceConfig(
        name="Home",
        place=PlaceRef(
            label="Home",
            address="45271 Electric Ter Unit 101, Fremont, CA 94539",
            provider_place_id="ChIJk1UlJffGj4AR-7kpSYyI4Ag",
        ),
    )


def get_default_office_config() -> PlaceConfig:
    """Return the default Office configuration."""

    return PlaceConfig(
        name="Office",
        place=PlaceRef(
            label="Office",
            address="Google CL5, 1600 Amphitheatre Pkwy, Mountain View, CA 94043",
            provider_place_id="ChIJwVpbIqK5j4ARTSu3RuPzCAk",
        ),
    )


def default_app_config() -> AppConfig:
    """
    Return the built-in default configuration for local development.

    These defaults are intentionally simple and not personalized. They should
    be overridden by tests and by any future real configuration mechanism.
    """

    return AppConfig(
        default_timezone=DEFAULT_TIMEZONE,
        home=get_default_home_config(),
        office=get_default_office_config(),
        default_risk_mode=DEFAULT_RISK_MODE,
    )

