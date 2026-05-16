from __future__ import annotations

import datetime as dt
import json
import logging
import re
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Any

from openai import OpenAI

from src.config import DEEPSEEK_API_KEY
from src.database import get_config, log_decision, set_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter (DeepSeek API)
# ---------------------------------------------------------------------------

DEFAULT_MAX_CALLS_PER_HOUR = 50


class RateLimitExceeded(Exception):
    pass


class DeepSeekRateLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._timestamps: deque[float] = deque()
        self._max_calls: int = self._load_limit()

    @staticmethod
    def _load_limit() -> int:
        val = get_config("max_ai_calls_per_hour")
        return int(val) if val else DEFAULT_MAX_CALLS_PER_HOUR

    def allow_call(self) -> bool:
        now = dt.datetime.now(dt.UTC).timestamp()
        cutoff = now - 3600.0
        with self._lock:
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            used = len(self._timestamps)
            if used >= self._max_calls:
                return False
            remaining = self._max_calls - used
            if remaining <= 2:
                logger.warning(
                    "DeepSeek API quota low: %d call(s) remaining this hour", remaining - 1
                )
            self._timestamps.append(now)
            return True


# Lazy singleton (must not touch DB at import time)
_rate_limiter: DeepSeekRateLimiter | None = None


def _get_rate_limiter() -> DeepSeekRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = DeepSeekRateLimiter()
    return _rate_limiter


# ---------------------------------------------------------------------------
# Market snapshot
# ---------------------------------------------------------------------------

@dataclass
class MarketSnapshot:
    symbol: str
    current_price: float
    open_price: float
    day_high: float
    day_low: float
    volume: int
    vwap: float
    pct_change_today: float
    current_position_qty: float
    current_position_avg_cost: float
    virtual_cash: float
    virtual_portfolio_value: float
    risk_tolerance: str
    stop_loss_pct: float

    @classmethod
    def build(
        cls,
        symbol: str,
        quote: dict[str, object],
        position_qty: float = 0.0,
        position_avg_cost: float = 0.0,
        virtual_cash: float = 0.0,
        virtual_portfolio_value: float = 0.0,
        risk_tolerance: str = "medium",
        stop_loss_pct: float = 0.05,
    ) -> MarketSnapshot:
        price = float(quote.get("price") or 0)
        prev_close = float(quote.get("previous_close") or price)
        pct_change = ((price / prev_close) - 1) * 100 if prev_close else 0.0
        return cls(
            symbol=symbol,
            current_price=price,
            open_price=float(quote.get("open") or price),
            day_high=float(quote.get("day_high") or price),
            day_low=float(quote.get("day_low") or price),
            volume=int(quote.get("volume") or 0),
            vwap=float(quote.get("price") or price),  # yfinance has no vwap in quote; use price
            pct_change_today=round(pct_change, 2),
            current_position_qty=position_qty,
            current_position_avg_cost=position_avg_cost,
            virtual_cash=virtual_cash,
            virtual_portfolio_value=virtual_portfolio_value,
            risk_tolerance=risk_tolerance,
            stop_loss_pct=stop_loss_pct,
        )


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_prompt(snapshot: MarketSnapshot) -> str:
    risk_framing = {
        "low": (
            "Risk tolerance is LOW. Strongly prefer HOLD. "
            "Only act on BUY/SELL signals with confidence >= 0.85 and a very clear rationale."
        ),
        "medium": (
            "Risk tolerance is MEDIUM. Prefer HOLD unless there is a clear signal. "
            "BUY/SELL only with confidence >= 0.65 and a solid data-driven reason."
        ),
        "high": (
            "Risk tolerance is HIGH. You may act on signals with confidence >= 0.55. "
            "Do not over-trade — only act when there is a real edge."
        ),
    }.get(snapshot.risk_tolerance, "Risk tolerance is MEDIUM.")

    return f"""You are a disciplined stock trading AI. Analyze this market snapshot and decide: BUY, SELL, or HOLD.

**Market Snapshot**
symbol: {snapshot.symbol}
current_price: {snapshot.current_price:.2f}
open_price: {snapshot.open_price:.2f}
day_high: {snapshot.day_high:.2f}
day_low: {snapshot.day_low:.2f}
volume: {snapshot.volume}
vwap: {snapshot.vwap:.2f}
pct_change_today: {snapshot.pct_change_today:.2f}%
current_position_qty: {snapshot.current_position_qty}
current_position_avg_cost: {snapshot.current_position_avg_cost:.2f}
virtual_cash: ${snapshot.virtual_cash:,.2f}
virtual_portfolio_value: ${snapshot.virtual_portfolio_value:,.2f}
risk_tolerance: {snapshot.risk_tolerance}
stop_loss_pct: {snapshot.stop_loss_pct:.2f}

**Risk rules**
{risk_framing}
If the position is at a loss exceeding stop_loss_pct, SELL.

**Response format**
Return only a valid JSON object. No prose. No markdown fences. No text outside the JSON.
Schema:
{{"action": "BUY"|"SELL"|"HOLD", "quantity": int, "confidence": float between 0.0 and 1.0, "reasoning": string under 80 words}}"""


# ---------------------------------------------------------------------------
# DeepSeek query
# ---------------------------------------------------------------------------

_JSON_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json_strict(raw: str) -> dict[str, Any]:
    """Extract and parse JSON from a potentially noisy LLM response."""
    cleaned = raw.strip()
    match = _JSON_PATTERN.search(cleaned)
    if match:
        cleaned = match.group(0)
    result = json.loads(cleaned)
    action = str(result.get("action", "HOLD")).upper()
    if action not in ("BUY", "SELL", "HOLD"):
        action = "HOLD"
    return {
        "action": action,
        "quantity": max(0, int(result.get("quantity", 0))),
        "confidence": max(0.0, min(1.0, float(result.get("confidence", 0.0)))),
        "reasoning": str(result.get("reasoning", ""))[:200],
    }


FALLBACK_DECISION: dict[str, object] = {
    "action": "HOLD",
    "quantity": 0,
    "confidence": 0.0,
    "reasoning": "rate_limit_or_error",
}


def query_deepseek(prompt: str) -> dict[str, object]:
    limiter = _get_rate_limiter()
    if not limiter.allow_call():
        logger.warning("DeepSeek rate limit reached — returning HOLD for this cycle")
        log_decision(
            symbol="",
            decision="hold",
            confidence=0.0,
            reasoning="rate_limit_reached",
            executed=False,
        )
        return dict(FALLBACK_DECISION)

    client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3,
        )
        raw = response.choices[0].message.content or ""
        decision = _parse_json_strict(raw)
        log_decision(
            symbol=decision.get("symbol", ""),
            decision=decision["action"].lower(),
            confidence=float(decision["confidence"]),
            reasoning=str(decision.get("reasoning", ""))[:200],
            executed=False,
        )
        return decision

    except Exception as exc:
        logger.error("DeepSeek query failed: %s", exc)
        log_decision(
            symbol="",
            decision="hold",
            confidence=0.0,
            reasoning="parse_error",
            executed=False,
        )
        return dict(FALLBACK_DECISION)


# ---------------------------------------------------------------------------
# Validation gate (raw AI output never reaches portfolio directly)
# ---------------------------------------------------------------------------

def validate_decision(
    decision: dict[str, Any],
    snapshot: MarketSnapshot,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Apply safety rules. Returns a clean decision that is safe to execute.
    """
    if config is None:
        config = {}

    action = str(decision.get("action", "HOLD")).upper()
    quantity = int(decision.get("quantity", 0))
    confidence = float(decision.get("confidence", 0.0))
    reasoning = str(decision.get("reasoning", ""))

    # --- hard confidence floor ---
    if confidence < 0.65:
        return {
            "action": "HOLD",
            "quantity": 0,
            "confidence": confidence,
            "reasoning": "overridden: confidence below 0.65 threshold",
        }

    max_pos_pct = float(config.get("max_position_size_pct", 0.20))
    max_daily = int(config.get("max_daily_trades", 10))

    if action == "BUY":
        if quantity <= 0:
            return {
                "action": "HOLD",
                "quantity": 0,
                "confidence": confidence,
                "reasoning": "overridden: buy quantity must be > 0",
            }

        cost = quantity * snapshot.current_price
        max_allowed = snapshot.virtual_portfolio_value * max_pos_pct

        if cost > max_allowed:
            return {
                "action": "HOLD",
                "quantity": 0,
                "confidence": confidence,
                "reasoning": (
                    f"overridden: cost ${cost:,.2f} exceeds "
                    f"max_position_size_pct ({max_pos_pct*100:.0f}%) = ${max_allowed:,.2f}"
                ),
            }

        if cost > snapshot.virtual_cash:
            return {
                "action": "HOLD",
                "quantity": 0,
                "confidence": confidence,
                "reasoning": f"overridden: insufficient cash (need ${cost:,.2f}, have ${snapshot.virtual_cash:,.2f})",
            }

        # Daily trade count
        daily_count = _count_daily_trades()
        if daily_count >= max_daily:
            return {
                "action": "HOLD",
                "quantity": 0,
                "confidence": confidence,
                "reasoning": f"overridden: daily trade limit reached ({max_daily})",
            }

    elif action == "SELL":
        if quantity <= 0:
            return {
                "action": "HOLD",
                "quantity": 0,
                "confidence": confidence,
                "reasoning": "overridden: sell quantity must be > 0",
            }

        if snapshot.current_position_qty <= 0:
            return {
                "action": "HOLD",
                "quantity": 0,
                "confidence": confidence,
                "reasoning": "overridden: no position to sell",
            }

        if quantity > snapshot.current_position_qty:
            return {
                "action": "HOLD",
                "quantity": 0,
                "confidence": confidence,
                "reasoning": (
                    f"overridden: sell qty {quantity} exceeds held {snapshot.current_position_qty}"
                ),
            }

        daily_count = _count_daily_trades()
        if daily_count >= max_daily:
            return {
                "action": "HOLD",
                "quantity": 0,
                "confidence": confidence,
                "reasoning": f"overridden: daily trade limit reached ({max_daily})",
            }

    # --- passes all checks ---
    return {
        "action": action,
        "quantity": quantity,
        "confidence": confidence,
        "reasoning": reasoning,
    }


def _count_daily_trades() -> int:
    from src.database import get_session, TradeLog

    today = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    with get_session() as session:
        from sqlmodel import select as sql_select, func

        count = session.exec(
            sql_select(func.count()).where(TradeLog.timestamp.like(f"{today}%"))
        ).first()
        return int(count or 0)
