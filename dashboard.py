"""Streamlit dashboard — 4 pages for the virtual trading system."""

from __future__ import annotations

import datetime as dt

import streamlit as st

from src.database import (
    DecisionLog,
    TradeLog,
    get_all_positions,
    get_config,
    get_session,
    init_db,
    set_config,
)
from src.market_data import get_quote
from src.virtual_broker import get_account, reset_portfolio

st.set_page_config(page_title="AI Trader — Virtual Portfolio", layout="wide")

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
st.sidebar.title("AI Trader")
st.sidebar.caption("Simulated trading — no real funds involved")
page = st.sidebar.radio(
    "Navigate",
    ["Portfolio Settings", "Trade Log", "Decision Log", "Virtual Portfolio"],
)

# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------
init_db()

# ---------------------------------------------------------------------------
# Page 1 — Portfolio Settings
# ---------------------------------------------------------------------------
if page == "Portfolio Settings":
    st.title("Portfolio Settings")

    # Load current values
    current_wl = get_config("watchlist") or "AAPL,MSFT,GOOGL"
    current_max_pos = float(get_config("max_position_size_pct") or 0.20)
    current_max_trades = int(get_config("max_daily_trades") or 10)
    current_risk = get_config("risk_tolerance") or "medium"
    current_stop = float(get_config("stop_loss_pct") or 0.05)

    max_ai = get_config("max_ai_calls_per_hour") or "50"
    loop_interval = get_config("loop_interval_minutes") or "15"

    with st.form("settings_form"):
        watchlist = st.text_input("Watchlist (comma-separated tickers)", value=current_wl)
        col1, col2 = st.columns(2)
        with col1:
            max_position = st.number_input(
                "Max position size (% of portfolio)",
                min_value=0.01,
                max_value=1.0,
                value=current_max_pos,
                step=0.05,
                format="%.2f",
            )
            max_trades = st.number_input(
                "Max daily trades",
                min_value=1,
                max_value=100,
                value=current_max_trades,
                step=1,
            )
        with col2:
            risk = st.selectbox(
                "Risk tolerance",
                options=["low", "medium", "high"],
                index=["low", "medium", "high"].index(current_risk),
            )
            stop_loss = st.number_input(
                "Stop loss (%)",
                min_value=0.01,
                max_value=0.50,
                value=current_stop,
                step=0.01,
                format="%.2f",
            )

        submitted = st.form_submit_button("Save Settings")
        if submitted:
            set_config("watchlist", watchlist)
            set_config("max_position_size_pct", str(max_position))
            set_config("max_daily_trades", str(max_trades))
            set_config("risk_tolerance", risk)
            set_config("stop_loss_pct", str(stop_loss))
            st.success("Settings saved.")
            st.rerun()

    st.divider()
    st.caption("System limits (read-only)")
    st.metric("Max AI calls / hour", max_ai)
    st.metric("Loop interval (minutes)", loop_interval)


# ---------------------------------------------------------------------------
# Page 2 — Trade Log
# ---------------------------------------------------------------------------
elif page == "Trade Log":
    st.title("Trade Log")
    st.caption("Simulated trades — no real funds involved")

    with get_session() as session:
        from sqlmodel import select as sql_select

        trades = list(session.exec(
            sql_select(TradeLog).order_by(TradeLog.timestamp.desc()).limit(200)
        ).all())

    if not trades:
        st.info("No trades yet.")
    else:
        rows = [
            {
                "Timestamp": t.timestamp,
                "Symbol": t.symbol,
                "Action": t.side,
                "Qty": t.quantity,
                "Price": f"${t.price:,.2f}",
                "Order ID": t.order_id,
                "Status": t.status,
                "Reason": t.reason[:80] if t.reason else "",
            }
            for t in trades
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Page 3 — Decision Log
# ---------------------------------------------------------------------------
elif page == "Decision Log":
    st.title("Decision Log")

    with get_session() as session:
        from sqlmodel import select as sql_select

        decisions = list(session.exec(
            sql_select(DecisionLog).order_by(DecisionLog.timestamp.desc()).limit(200)
        ).all())

    if not decisions:
        st.info("No decisions yet.")
    else:
        for d in decisions:
            action = d.decision.upper()
            color = {"BUY": "green", "SELL": "red", "HOLD": "gray"}.get(action, "gray")
            emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}.get(action, "⚪")

            col1, col2, col3, col4 = st.columns([1, 1, 1, 3])
            with col1:
                st.markdown(f"**{d.symbol or '—'}**  \n{d.timestamp[:19]}")
            with col2:
                st.markdown(f":{color}[{action}]")
            with col3:
                st.markdown(f"Confidence: **{d.confidence:.1%}**")
            with col4:
                st.caption(d.reasoning[:200] if d.reasoning else "—")
            st.divider()


# ---------------------------------------------------------------------------
# Page 4 — Virtual Portfolio
# ---------------------------------------------------------------------------
elif page == "Virtual Portfolio":
    st.title("Virtual Portfolio")
    st.caption("All values shown are (simulated)")

    account = get_account()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Cash (simulated)", f"${account['cash']:,.2f}")
    with col2:
        st.metric("Portfolio Value (simulated)", f"${account['positions_value']:,.2f}")
    with col3:
        delta = f"${account['pnl']:,.2f} ({account['pnl_pct']}%)"
        st.metric("Total P&L (simulated)", f"${account['equity']:,.2f}", delta=delta)

    st.divider()
    st.subheader("Open Positions")

    positions = get_all_positions()
    if not positions:
        st.info("No open positions.")
    else:
        rows = []
        for p in positions:
            try:
                q = get_quote(p.symbol)
                cur = float(q.get("price") or p.avg_entry_price)
            except Exception:
                cur = p.avg_entry_price
            pl = round(p.quantity * (cur - p.avg_entry_price), 2)
            pl_pct = round((cur / p.avg_entry_price - 1) * 100, 2) if p.avg_entry_price else 0
            rows.append({
                "Symbol": p.symbol,
                "Qty": p.quantity,
                "Avg Cost (simulated)": f"${p.avg_entry_price:,.2f}",
                "Current Price (simulated)": f"${cur:,.2f}",
                "Market Value (simulated)": f"${p.quantity * cur:,.2f}",
                "Unrealized P&L (simulated)": f"${pl:,.2f} ({pl_pct}%)",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Reset Portfolio")

    st.warning("This will liquidate all positions and reset cash to $100,000 (simulated).")
    confirm = st.checkbox("I confirm I want to reset the entire portfolio")
    if st.button("Reset Portfolio", type="secondary", disabled=not confirm):
        reset_portfolio()
        st.success("Portfolio reset — all positions cleared, cash restored.")
        st.rerun()
