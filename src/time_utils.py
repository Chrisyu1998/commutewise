"""
Time parsing and formatting helpers for CommuteWise.

These helpers are deliberately small and deterministic. They are intended to
support:
- Converting naive datetimes into timezone-aware datetimes
- Parsing simple "HH:MM" strings into datetimes
- Formatting recommendation times for display or logging
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time
from typing import Optional

from zoneinfo import ZoneInfo

from src.config import DEFAULT_TIMEZONE
from src.schemas import _require_timezone


TIME_FORMAT_HH_MM = "%H:%M"


def ensure_timezone(dt: datetime, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    """
    Ensure a datetime is timezone-aware in the given IANA timezone.

    If `dt` is naive, attach the provided timezone. If it is already aware,
    return it unchanged (after validating it has a tzinfo).
    """

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return datetime(
            year=dt.year,
            month=dt.month,
            day=dt.day,
            hour=dt.hour,
            minute=dt.minute,
            second=dt.second,
            microsecond=dt.microsecond,
            tzinfo=ZoneInfo(timezone),
        )
    return _require_timezone(dt)


def parse_hh_mm(
    value: str,
    *,
    timezone: str,
    reference_date: Optional[date] = None,
) -> datetime:
    """
    Parse a string like \"09:30\" into a timezone-aware datetime.

    - `timezone` must be an IANA name like \"America/Los_Angeles\".
    - `reference_date` defaults to today's date if not provided.
    """

    parsed_time = datetime.strptime(value, TIME_FORMAT_HH_MM).time()
    if reference_date is None:
        today = date.today()
    else:
        today = reference_date

    naive = datetime.combine(today, parsed_time)
    return ensure_timezone(naive, timezone)


def format_hh_mm(dt: datetime) -> str:
    """
    Format a timezone-aware datetime as \"HH:MM\" in its own timezone.
    """

    dt = _require_timezone(dt)
    local_dt = dt.astimezone(dt.tzinfo)
    return local_dt.strftime(TIME_FORMAT_HH_MM)


def parse_iso(dt_str: str, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    """
    Parse an ISO-8601 datetime string and ensure it is timezone-aware.

    If the parsed value is naive, attach the provided timezone.
    """

    parsed = datetime.fromisoformat(dt_str)
    return ensure_timezone(parsed, timezone)


def format_iso(dt: datetime) -> str:
    """
    Format a timezone-aware datetime as an ISO-8601 string with offset.
    """

    dt = _require_timezone(dt)
    return dt.isoformat()


def combine_date_time(
    d: date,
    t: time,
    timezone: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Combine a date and time into a timezone-aware datetime.
    """

    naive = datetime.combine(d, t)
    return ensure_timezone(naive, timezone)


@dataclass(frozen=True)
class TimeFeatures:
    """Derived temporal features for retrieval / analysis."""

    weekday: int  # Monday = 0 ... Sunday = 6
    hour: int     # 0-23


def extract_features(dt: datetime) -> TimeFeatures:
    """
    Extract simple time features (weekday, hour) from a timezone-aware datetime.
    """

    dt = _require_timezone(dt)
    local_dt = dt.astimezone(dt.tzinfo)
    return TimeFeatures(weekday=local_dt.weekday(), hour=local_dt.hour)

