# AI Trader — Virtual Portfolio

**This tool simulates trading using virtual funds. No real money is involved.**

## Setup

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt   # Windows
# source venv/bin/pip install -r requirements.txt  # macOS/Linux
```

Create a `.env` file from `.env.template`:

```
DEEPSEEK_API_KEY=sk-your-key-here
```

## How to run

Terminal 1 — background scheduler:
```bash
venv\Scripts\python scheduler.py
```

Terminal 2 — dashboard:
```bash
venv\Scripts\python -m streamlit run dashboard.py
```

## Rate limits

- **`max_ai_calls_per_hour`** — Maximum DeepSeek API calls per rolling 60-minute window. Set in `portfolio_config` via the dashboard or directly in SQLite. Default: 50.
- **`loop_interval_minutes`** — How often the scheduler triggers a full watchlist scan. Set in `portfolio_config`. Default: 15.

### Yahoo Finance rate limiter

The market data module enforces ~1 request/second with a 1900 req/hour cap. Identical symbol queries are cached (30s for quotes, 5min for historical data) to avoid wasting quota.

## Architecture

| Module | Role |
|---|---|
| `src/config.py` | Loads `.env` |
| `src/database.py` | SQLite tables: `portfolio_config`, `trade_log`, `decision_log`, `positions` |
| `src/market_data.py` | yfinance wrapper with rate limiting + caching |
| `src/market_status.py` | US market hours check (9:30–16:00 ET, weekdays) |
| `src/portfolio.py` | Portfolio settings + apply_buy/apply_sell wrappers |
| `src/virtual_broker.py` | Simulated order execution, positions, cash tracking |
| `src/decision_engine.py` | DeepSeekRateLimiter, MarketSnapshot, prompt builder, query + validate |
| `src/trader.py` | Main trading loop: quote → snapshot → AI → validate → execute |
| `scheduler.py` | APScheduler background process |
| `dashboard.py` | Streamlit 4-page dashboard |

## System flow

1. **Scheduler** fires every `loop_interval_minutes` on weekdays between 9:30 AM and 4:00 PM ET
2. **Trader** iterates over the watchlist, fetches a quote for each ticker via Yahoo Finance
3. **Decision Engine** builds a MarketSnapshot, sends it to DeepSeek for analysis
4. DeepSeek returns a JSON decision (BUY/SELL/HOLD + quantity + confidence + reasoning)
5. **validate_decision()** enforces safety rules: confidence floor, position size limits, cash constraints, daily trade cap
6. Valid BUY/SELL decisions are executed against the **virtual portfolio** (SQLite)
7. All decisions are logged to `decision_log`, all trades to `trade_log`
8. **Dashboard** displays portfolio state, trade history, decision history, and settings
