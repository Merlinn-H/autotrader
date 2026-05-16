from __future__ import annotations

import datetime as dt

import pytz

EASTERN = pytz.timezone("US/Eastern")

MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0


def get_market_status() -> dict[str, object]:
    now_utc = dt.datetime.now(dt.UTC)
    now_et = now_utc.astimezone(EASTERN)

    weekday = now_et.weekday()  # Monday=0 .. Sunday=6
    is_weekday = weekday < 5

    open_time = now_et.replace(
        hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0
    )
    close_time = now_et.replace(
        hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0, microsecond=0
    )

    is_open = is_weekday and open_time <= now_et < close_time

    return {
        "is_open": is_open,
        "timestamp_et": now_et.isoformat(),
        "weekday": is_weekday,
        "next_open": _next_open(now_et).isoformat() if not is_open else None,
    }


def _next_open(after: dt.datetime) -> dt.datetime:
    """Return the next market open datetime in ET."""
    candidate = after.replace(
        hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0
    )
    if candidate <= after:
        candidate += dt.timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += dt.timedelta(days=1)
    return candidate
