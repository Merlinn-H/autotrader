"""Unit tests for decision_engine — zero real API calls."""

from __future__ import annotations

import datetime as dt
from collections import deque
from unittest.mock import patch, MagicMock

from src.decision_engine import (
    DeepSeekRateLimiter,
    MarketSnapshot,
    build_prompt,
    validate_decision,
    _count_daily_trades,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_snapshot(**overrides: object) -> MarketSnapshot:
    defaults = {
        "symbol": "AAPL",
        "current_price": 213.40,
        "open_price": 211.00,
        "day_high": 215.00,
        "day_low": 210.50,
        "volume": 55_000_000,
        "vwap": 213.00,
        "pct_change_today": 1.2,
        "current_position_qty": 0.0,
        "current_position_avg_cost": 0.0,
        "virtual_cash": 8_500.0,
        "virtual_portfolio_value": 10_000.0,
        "risk_tolerance": "medium",
        "stop_loss_pct": 0.05,
    }
    defaults.update(overrides)
    return MarketSnapshot(**{k: v for k, v in defaults.items() if k in MarketSnapshot.__dataclass_fields__})


def make_decision(**overrides: object) -> dict:
    d = {"action": "BUY", "quantity": 10, "confidence": 0.80, "reasoning": "test"}
    d.update(overrides)
    return d


# ---------------------------------------------------------------------------
# Test 1: Low confidence BUY is overridden to HOLD
# ---------------------------------------------------------------------------

def test_low_confidence_buy_overridden():
    snap = make_snapshot()
    decision = make_decision(action="BUY", confidence=0.55)
    result = validate_decision(decision, snap)
    assert result["action"] == "HOLD"
    assert result["quantity"] == 0
    assert "confidence below" in result["reasoning"]


# ---------------------------------------------------------------------------
# Test 2: BUY exceeding max_position_size_pct is overridden to HOLD
# ---------------------------------------------------------------------------

def test_buy_exceeds_max_position_size_pct():
    snap = make_snapshot(
        current_price=500.0,
        virtual_portfolio_value=10_000.0,
        virtual_cash=10_000.0,
    )
    # max_position_size_pct = 0.20 -> max $2,000 per position
    # BUY 10 shares at $500 = $5,000 -> exceeds 20% of $10,000
    decision = make_decision(action="BUY", quantity=10, confidence=0.90)
    result = validate_decision(decision, snap, {"max_position_size_pct": 0.20})
    assert result["action"] == "HOLD"
    assert "exceeds" in result["reasoning"]


# ---------------------------------------------------------------------------
# Test 3: DeepSeekRateLimiter blocks calls correctly after cap is reached
# ---------------------------------------------------------------------------

def test_rate_limiter_blocks_at_cap():
    limiter = DeepSeekRateLimiter()
    limiter._max_calls = 3

    # Clear existing timestamps and inject a full window
    limiter._timestamps = deque()
    now = dt.datetime.now(dt.UTC).timestamp()
    for _ in range(3):
        limiter._timestamps.append(now)

    # Should block the 4th call
    assert limiter.allow_call() is False

    # With old timestamps (expired), should allow again
    limiter._timestamps = deque([now - 3601])  # older than 1 hour
    assert limiter.allow_call() is True


# ---------------------------------------------------------------------------
# Bonus: SELL without position is overridden
# ---------------------------------------------------------------------------

def test_sell_without_position_overridden():
    snap = make_snapshot(current_position_qty=0.0)
    decision = make_decision(action="SELL", quantity=5, confidence=0.90)
    result = validate_decision(decision, snap)
    assert result["action"] == "HOLD"
    assert "no position" in result["reasoning"]


# ---------------------------------------------------------------------------
# Bonus: valid BUY passes all checks
# ---------------------------------------------------------------------------

@patch("src.decision_engine._count_daily_trades", return_value=0)
def test_valid_buy_passes(_mock_count):
    snap = make_snapshot(
        current_price=100.0,
        virtual_portfolio_value=10_000.0,
        virtual_cash=10_000.0,
    )
    # 10 shares at $100 = $1,000, which is 10% of $10,000 (max 20%)
    decision = make_decision(action="BUY", quantity=10, confidence=0.85)
    result = validate_decision(decision, snap)
    assert result["action"] == "BUY"
    assert result["quantity"] == 10
