from __future__ import annotations

import yfinance as yf

from src.rate_limiter import cached_call


@cached_call(ttl=30.0)
def get_quote(symbol: str) -> dict[str, object]:
    """Fetch a single real-time quote. Cached for 30 s."""
    ticker = yf.Ticker(symbol)
    info = ticker.info
    fast = ticker.fast_info
    return {
        "symbol": symbol,
        "price": getattr(fast, "last_price", None),
        "bid": info.get("bid"),
        "ask": info.get("ask"),
        "previous_close": info.get("previousClose"),
        "open": info.get("open"),
        "day_high": info.get("dayHigh"),
        "day_low": info.get("dayLow"),
        "volume": info.get("volume"),
        "market_cap": info.get("marketCap"),
        "currency": info.get("currency", "USD"),
    }


@cached_call(ttl=300.0)
def get_historical(
    symbol: str,
    period: str = "6mo",
    interval: str = "1d",
) -> dict[str, object]:
    """Fetch OHLCV history. Cached for 5 min."""
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)
    if df.empty:
        return {"symbol": symbol, "period": period, "interval": interval, "data": []}
    records = []
    for idx, row in df.iterrows():
        records.append({
            "date": str(idx.date()),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        })
    return {
        "symbol": symbol,
        "period": period,
        "interval": interval,
        "data": records,
    }


def get_batch_quotes(symbols: list[str]) -> list[dict[str, object]]:
    """Fetch quotes for multiple symbols sequentially (rate-limited internally)."""
    results: list[dict[str, object]] = []
    for sym in symbols:
        results.append(get_quote(sym))
    return results
