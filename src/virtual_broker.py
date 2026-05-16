from __future__ import annotations

import uuid
from typing import Any

from src.database import (
    delete_position,
    get_all_positions,
    get_config,
    get_position,
    get_session,
    log_trade,
    set_config,
    upsert_position,
)
from src.market_data import get_quote

DEFAULT_CASH = 100_000.0


# ---------------------------------------------------------------------------
# Account state (stored in portfolio_config)
# ---------------------------------------------------------------------------

def _load_cash() -> float:
    val = get_config("cash")
    if val is None:
        _seed_defaults()
        return DEFAULT_CASH
    return float(val)


def _save_cash(amount: float) -> None:
    set_config("cash", f"{amount:.2f}")


def _load_initial_balance() -> float:
    val = get_config("initial_balance")
    if val is None:
        return DEFAULT_CASH
    return float(val)


def _seed_defaults() -> None:
    set_config("cash", f"{DEFAULT_CASH:.2f}")
    set_config("initial_balance", f"{DEFAULT_CASH:.2f}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_account() -> dict[str, Any]:
    cash = _load_cash()
    positions = get_all_positions()
    positions_value = 0.0
    for p in positions:
        try:
            quote = get_quote(p.symbol)
            price = float(quote.get("price") or 0)
        except Exception:
            price = p.avg_entry_price
        positions_value += p.quantity * price

    equity = cash + positions_value
    return {
        "cash": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "equity": round(equity, 2),
        "initial_balance": round(_load_initial_balance(), 2),
        "pnl": round(equity - _load_initial_balance(), 2),
        "pnl_pct": round((equity / _load_initial_balance() - 1) * 100, 2),
    }


def get_positions() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for p in get_all_positions():
        try:
            quote = get_quote(p.symbol)
            current_price = float(quote.get("price") or 0)
        except Exception:
            current_price = p.avg_entry_price
        results.append({
            "symbol": p.symbol,
            "quantity": p.quantity,
            "avg_entry_price": p.avg_entry_price,
            "current_price": current_price,
            "market_value": round(p.quantity * current_price, 2),
            "unrealized_pl": round(p.quantity * (current_price - p.avg_entry_price), 2),
            "unrealized_plpc": round((current_price / p.avg_entry_price - 1) * 100, 2) if p.avg_entry_price else 0,
        })
    return results


def submit_order(
    symbol: str,
    qty: float,
    side: str,
    reason: str = "",
    price: float | None = None,
) -> dict[str, Any]:
    """Simulate a market order against the virtual portfolio."""
    side = side.upper()
    order_id = str(uuid.uuid4())[:8]
    cash = _load_cash()

    if price is None:
        quote = get_quote(symbol)
        price = float(quote.get("price") or 0)
    if price <= 0:
        raise ValueError(f"Could not fetch price for {symbol}")

    if side == "BUY":
        cost = qty * price
        if cost > cash:
            raise ValueError(
                f"Insufficient cash: need ${cost:,.2f}, have ${cash:,.2f}"
            )
        current_pos = get_position(symbol)
        if current_pos:
            new_qty = current_pos.quantity + qty
            new_avg = ((current_pos.avg_entry_price * current_pos.quantity) + cost) / new_qty
            upsert_position(symbol, new_qty, round(new_avg, 4))
        else:
            upsert_position(symbol, qty, price)
        _save_cash(cash - cost)

    elif side == "SELL":
        current_pos = get_position(symbol)
        if not current_pos or current_pos.quantity < qty:
            raise ValueError(
                f"Insufficient shares: have {current_pos.quantity if current_pos else 0}, need {qty}"
            )
        revenue = qty * price
        remaining_qty = current_pos.quantity - qty
        if remaining_qty <= 0:
            delete_position(symbol)
        else:
            upsert_position(symbol, remaining_qty, current_pos.avg_entry_price)
        _save_cash(cash + revenue)

    else:
        raise ValueError(f"Unknown side: {side}")

    trade = log_trade(
        symbol=symbol,
        side=side,
        quantity=qty,
        price=price,
        order_id=order_id,
        status="filled",
        reason=reason,
    )
    return {
        "id": trade.order_id,
        "symbol": symbol,
        "qty": qty,
        "side": side,
        "price": price,
        "status": "filled",
    }


def reset_portfolio(cash: float = DEFAULT_CASH) -> dict[str, Any]:
    """Reset the virtual portfolio to a clean state."""
    with get_session() as session:
        from sqlmodel import delete as sql_delete
        from src.database import Position

        session.exec(sql_delete(Position))
        session.commit()
    _save_cash(cash)
    set_config("initial_balance", f"{cash:.2f}")
    return get_account()
