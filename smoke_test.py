"""Smoke test — virtual broker with Yahoo Finance market data."""

from src.database import init_db
from src.portfolio import Portfolio
from src.virtual_broker import get_account, get_positions, reset_portfolio, submit_order


def main() -> None:
    # 1. Init DB + reset portfolio for a clean test
    init_db()
    print("[OK] SQLite database initialized")

    account = reset_portfolio(cash=100_000)
    print(f"[OK] Portfolio reset — ${account['equity']:,.2f} equity, ${account['cash']:,.2f} cash")
    print()

    # 2. Portfolio config
    portfolio = Portfolio.load()
    portfolio.save()
    print(f"[OK] Portfolio loaded — watchlist: {portfolio.watchlist}")
    print()

    # 3. Get account
    account = get_account()
    print("Virtual Account")
    print("---------------")
    print(f"  Cash:            ${account['cash']:,.2f}")
    print(f"  Equity:          ${account['equity']:,.2f}")
    print(f"  PnL:             ${account['pnl']:,.2f} ({account['pnl_pct']}%)")
    print()

    # 4. Buy 10 shares of AAPL
    print("BUY 10 AAPL")
    buy = submit_order("AAPL", 10, "buy", reason="smoke test")
    print(f"  Order: {buy['id']} — {buy['side']} {buy['qty']} {buy['symbol']} @ ${buy['price']:.2f}")
    print()

    # 5. Positions
    positions = get_positions()
    print("Positions:")
    for p in positions:
        print(f"  {p['symbol']}: {p['quantity']} shares @ avg ${p['avg_entry_price']:.2f} "
              f"(current ${p['current_price']:.2f}, PnL ${p['unrealized_pl']:.2f})")
    print()

    # 6. Account after trade
    account = get_account()
    print("Account after trade:")
    print(f"  Cash:   ${account['cash']:,.2f}")
    print(f"  Equity: ${account['equity']:,.2f}")
    print(f"  PnL:    ${account['pnl']:,.2f}")
    print()

    # 7. Sell half
    sell_qty = positions[0]["quantity"] / 2
    print(f"SELL {sell_qty} AAPL")
    sell = submit_order("AAPL", sell_qty, "sell", reason="smoke test")
    print(f"  Order: {sell['id']} — {sell['side']} {sell['qty']} {sell['symbol']} @ ${sell['price']:.2f}")
    print()

    positions = get_positions()
    for p in positions:
        print(f"  {p['symbol']}: {p['quantity']} shares remaining")
    print()

    account = get_account()
    print(f"Final equity: ${account['equity']:,.2f} | Cash: ${account['cash']:,.2f}")
    print("[OK] Smoke test passed")


if __name__ == "__main__":
    main()
