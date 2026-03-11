from datetime import date, datetime, time, timezone

from zoneinfo import ZoneInfo

from src.config import DEFAULT_TIMEZONE
from src import time_utils


def test_ensure_timezone_attaches_default_tz() -> None:
    naive = datetime(2026, 3, 10, 9, 30)

    aware = time_utils.ensure_timezone(naive)

    assert aware.tzinfo is not None
    assert aware.tzinfo == ZoneInfo(DEFAULT_TIMEZONE)


def test_parse_iso_and_format_iso_round_trip() -> None:
    original = datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc)

    iso_str = time_utils.format_iso(original)
    parsed = time_utils.parse_iso(iso_str)

    # Round-trip should preserve the instant in time.
    assert parsed == original


def test_combine_date_time_and_extract_features() -> None:
    d = date(2026, 3, 10)  # This is a Tuesday.
    t = time(8, 45)

    dt = time_utils.combine_date_time(d, t)

    features = time_utils.extract_features(dt)

    assert 0 <= features.weekday <= 6
    assert features.hour == 8


def test_parse_and_format_hh_mm() -> None:
    dt = time_utils.parse_hh_mm("07:15", timezone=DEFAULT_TIMEZONE)
    hh_mm = time_utils.format_hh_mm(dt)

    assert hh_mm == "07:15"

