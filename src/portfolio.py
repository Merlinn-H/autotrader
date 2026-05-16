from __future__ import annotations

from dataclasses import dataclass, field

from src.database import get_all_positions, get_config, set_config
from src.virtual_broker import submit_order
from src.market_data import get_quote


@dataclass
class Portfolio:
    watchlist: list[str] = field(default_factory=lambda: ["AAPL", "MSFT", "GOOGL"])
    max_position_size_pct: float = 0.20
    max_daily_trades: int = 10
    risk_tolerance: str = "medium"  # low / medium / high
    stop_loss_pct: float = 0.05

    def save(self) -> None:
        set_config("watchlist", ",".join(self.watchlist))
        set_config("max_position_size_pct", str(self.max_position_size_pct))
        set_config("max_daily_trades", str(self.max_daily_trades))
        set_config("risk_tolerance", self.risk_tolerance)
        set_config("stop_loss_pct", str(self.stop_loss_pct))

    @classmethod
    def load(cls) -> Portfolio:
        p = cls()
        wl = get_config("watchlist")
        if wl:
            p.watchlist = [s.strip() for s in wl.split(",") if s.strip()]
        mp = get_config("max_position_size_pct")
        if mp:
            p.max_position_size_pct = float(mp)
        mt = get_config("max_daily_trades")
        if mt:
            p.max_daily_trades = int(mt)
        rt = get_config("risk_tolerance")
        if rt:
            p.risk_tolerance = rt
        sl = get_config("stop_loss_pct")
        if sl:
            p.stop_loss_pct = float(sl)
        return p

    # -- Trading wrappers (delegate to virtual_broker) --

    def apply_buy(self, symbol: str, qty: int, price: float, reason: str = "") -> dict:
        return submit_order(symbol, float(qty), "BUY", reason=reason, price=price)

    def apply_sell(self, symbol: str, qty: int, price: float, reason: str = "") -> dict:
        return submit_order(symbol, float(qty), "SELL", reason=reason, price=price)

    @staticmethod
    def get_positions() -> list[dict]:
        results = []
        for p in get_all_positions():
            try:
                q = get_quote(p.symbol)
                cur = float(q.get("price") or p.avg_entry_price)
            except Exception:
                cur = p.avg_entry_price
            results.append({
                "symbol": p.symbol,
                "quantity": p.quantity,
                "avg_entry_price": p.avg_entry_price,
                "current_price": cur,
                "market_value": round(p.quantity * cur, 2),
                "unrealized_pl": round(p.quantity * (cur - p.avg_entry_price), 2),
                "unrealized_plpc": round((cur / p.avg_entry_price - 1) * 100, 2) if p.avg_entry_price else 0,
            })
        return results
