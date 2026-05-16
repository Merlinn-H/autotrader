from __future__ import annotations

import logging
import signal
import sys
import traceback
from types import FrameType
from typing import Any

from src.database import init_db, log_decision
from src.market_data import get_quote
from src.market_status import get_market_status
from src.portfolio import Portfolio
from src.decision_engine import (
    MarketSnapshot,
    build_prompt,
    query_deepseek,
    validate_decision,
)
from src.virtual_broker import get_account

logger = logging.getLogger("trader")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(handler)

_shutdown_requested = False


def _handle_shutdown(signum: int, frame: FrameType | None) -> None:
    global _shutdown_requested
    logger.info("Received signal %d, shutting down gracefully...", signum)
    _shutdown_requested = True


signal.signal(signal.SIGINT, _handle_shutdown)
signal.signal(signal.SIGTERM, _handle_shutdown)


def run_cycle() -> dict[str, Any]:
    """Run one full trading cycle. Returns cycle summary dict."""
    if _shutdown_requested:
        return {"status": "shutdown"}

    # 1. Market hours check
    status = get_market_status()
    if not status["is_open"]:
        logger.info("Market closed — skipping cycle (ET: %s)", status["timestamp_et"])
        return {"status": "skipped", "reason": "market_closed"}

    # 2. Load portfolio config
    portfolio = Portfolio.load()
    account = get_account()
    positions = Portfolio.get_positions()
    positions_map = {p["symbol"]: p for p in positions}

    results: list[dict[str, Any]] = []

    for symbol in portfolio.watchlist:
        if _shutdown_requested:
            break

        try:
            result = _process_ticker(symbol, portfolio, account, positions_map)
            results.append(result)
        except Exception:
            logger.error("Unhandled error for %s:\n%s", symbol, traceback.format_exc())
            log_decision(
                symbol=symbol,
                decision="hold",
                confidence=0.0,
                reasoning="exception_in_loop",
                executed=False,
            )
            results.append({"symbol": symbol, "action": "ERROR", "error": True})

    buys = sum(1 for r in results if r.get("action") == "BUY")
    sells = sum(1 for r in results if r.get("action") == "SELL")
    holds = sum(1 for r in results if r.get("action") == "HOLD")
    errors = sum(1 for r in results if r.get("error"))

    logger.info(
        "Cycle complete — %d BUY, %d SELL, %d HOLD, %d errors across %d tickers",
        buys, sells, holds, errors, len(portfolio.watchlist),
    )
    return {
        "status": "completed",
        "buys": buys,
        "sells": sells,
        "holds": holds,
        "errors": errors,
        "results": results,
    }


def _process_ticker(
    symbol: str,
    portfolio: Portfolio,
    account: dict[str, Any],
    positions_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    logger.info("--- Processing %s ---", symbol)

    # Step 1: Get quote (rate-limited internally)
    quote = get_quote(symbol)
    price = float(quote.get("price") or 0)
    if price <= 0:
        logger.warning("Zero/empty price for %s — skipping", symbol)
        return {"symbol": symbol, "action": "HOLD", "reason": "bad_price"}

    logger.info("Quote: $%.2f", price)

    # Step 2: Build snapshot
    pos = positions_map.get(symbol, {})
    snapshot = MarketSnapshot.build(
        symbol=symbol,
        quote=quote,
        position_qty=float(pos.get("quantity", 0)),
        position_avg_cost=float(pos.get("avg_entry_price", 0)),
        virtual_cash=float(account["cash"]),
        virtual_portfolio_value=float(account["equity"]),
        risk_tolerance=portfolio.risk_tolerance,
        stop_loss_pct=portfolio.stop_loss_pct,
    )

    # Step 3: Query AI (rate limiter enforced inside)
    prompt = build_prompt(snapshot)
    decision = query_deepseek(prompt)

    action = str(decision.get("action", "HOLD")).upper()
    logger.info("Raw AI decision: %s x%d (confidence=%.2f)", action, decision.get("quantity", 0), decision.get("confidence", 0.0))

    # Step 4: Validate
    config = {
        "max_position_size_pct": portfolio.max_position_size_pct,
        "max_daily_trades": portfolio.max_daily_trades,
    }
    safe = validate_decision(decision, snapshot, config)
    safe_action = str(safe.get("action", "HOLD")).upper()
    logger.info("Validated: %s x%d (confidence=%.2f)", safe_action, safe.get("quantity", 0), safe.get("confidence", 0.0))

    # Step 5: Execute
    if safe_action == "BUY":
        qty = int(safe.get("quantity", 0))
        reason = str(safe.get("reasoning", ""))
        portfolio.apply_buy(symbol, qty, price, reason=reason)
        log_decision(
            symbol=symbol,
            decision="buy",
            confidence=float(safe.get("confidence", 0)),
            reasoning=reason,
            executed=True,
        )
        logger.info("EXECUTED BUY %d %s @ $%.2f", qty, symbol, price)

    elif safe_action == "SELL":
        qty = int(safe.get("quantity", 0))
        reason = str(safe.get("reasoning", ""))
        portfolio.apply_sell(symbol, qty, price, reason=reason)
        log_decision(
            symbol=symbol,
            decision="sell",
            confidence=float(safe.get("confidence", 0)),
            reasoning=reason,
            executed=True,
        )
        logger.info("EXECUTED SELL %d %s @ $%.2f", qty, symbol, price)

    else:
        log_decision(
            symbol=symbol,
            decision="hold",
            confidence=float(safe.get("confidence", 0)),
            reasoning=str(safe.get("reasoning", "")),
            executed=False,
        )
        logger.info("HOLD %s", symbol)

    return {"symbol": symbol, "action": safe_action}


if __name__ == "__main__":
    init_db()
    summary = run_cycle()
    print()
    print("Cycle summary:", summary["status"])
    for r in summary.get("results", []):
        print(f"  {r['symbol']}: {r.get('action', '?')}")
