"""Background scheduler — triggers the trading loop on weekdays during market hours."""

from __future__ import annotations

import datetime as dt
import logging
import signal
import sys
import time
from types import FrameType
from typing import Any

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

from src.database import get_config, init_db, set_config
from src.market_status import EASTERN, get_market_status
from src.trader import run_cycle

logger = logging.getLogger("scheduler")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(handler)

DEFAULT_LOOP_INTERVAL = 15  # minutes
_shutdown_requested = False


def _load_interval() -> int:
    val = get_config("loop_interval_minutes")
    return int(val) if val else DEFAULT_LOOP_INTERVAL


def _handle_shutdown(signum: int, frame: FrameType | None) -> None:
    global _shutdown_requested
    logger.info("Shutdown signal received, stopping scheduler...")
    _shutdown_requested = True


def trading_job() -> None:
    """Called by APScheduler each interval. Skips if market closed."""
    now_et = dt.datetime.now(dt.UTC).astimezone(EASTERN)
    status = get_market_status()
    if not status["is_open"]:
        logger.info(
            "Trigger at %s ET — market closed, skipping",
            now_et.strftime("%H:%M"),
        )
        return
    logger.info("Trigger at %s ET — running trading cycle", now_et.strftime("%H:%M"))
    try:
        summary = run_cycle()
        logger.info(
            "Cycle done: %d buys, %d sells, %d holds, %d errors",
            summary.get("buys", 0),
            summary.get("sells", 0),
            summary.get("holds", 0),
            summary.get("errors", 0),
        )
    except Exception:
        logger.exception("Trading cycle crashed — will retry next interval")


def main() -> None:
    init_db()

    interval = _load_interval()
    if get_config("loop_interval_minutes") is None:
        set_config("loop_interval_minutes", str(interval))

    logger.info("Starting scheduler — interval=%dmin, timezone=US/Eastern", interval)
    logger.info("Market hours: 9:30–16:00 ET, weekdays only")

    scheduler = BackgroundScheduler(timezone=EASTERN)
    scheduler.add_job(
        trading_job,
        trigger="interval",
        minutes=interval,
        id="trading_cycle",
        replace_existing=True,
    )
    scheduler.start()

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    logger.info("Scheduler running. Press Ctrl+C to stop.")

    try:
        while not _shutdown_requested:
            time.sleep(1)
    finally:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
