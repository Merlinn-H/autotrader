"""Smoke test for market data (yfinance) + rate limiter."""

import time

from src.market_data import get_quote, get_historical, get_batch_quotes


def main() -> None:
    print("Testing Yahoo Finance market data (rate-limited)...")
    print()

    # 1. Single quote
    t0 = time.perf_counter()
    quote = get_quote("AAPL")
    elapsed = time.perf_counter() - t0
    print(f"[OK] AAPL quote ({elapsed:.2f}s)")
    print(f"     price={quote['price']}, bid={quote['bid']}, ask={quote['ask']}")
    print()

    # 2. Cache hit — should be instant, no rate-limit wait
    t0 = time.perf_counter()
    quote2 = get_quote("AAPL")
    elapsed = time.perf_counter() - t0
    print(f"[OK] AAPL quote cached ({elapsed:.4f}s) — same price: {quote['price'] == quote2['price']}")
    print()

    # 3. Historical
    t0 = time.perf_counter()
    hist = get_historical("SPY", period="5d", interval="1d")
    elapsed = time.perf_counter() - t0
    print(f"[OK] SPY 5d history ({elapsed:.2f}s) — {len(hist['data'])} candles")
    print()

    # 4. Batch quotes (will rate-limit between each)
    t0 = time.perf_counter()
    quotes = get_batch_quotes(["MSFT", "GOOGL"])
    elapsed = time.perf_counter() - t0
    print(f"[OK] Batch quotes for MSFT, GOOGL ({elapsed:.2f}s)")
    for q in quotes:
        print(f"     {q['symbol']}: price={q['price']}")
    print()

    print("Market data smoke test complete.")


if __name__ == "__main__":
    main()
