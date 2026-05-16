from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlmodel import Field, Session, SQLModel, create_engine, select

DB_PATH = Path(__file__).resolve().parent.parent / "trader.db"
DB_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(DB_URL, echo=False)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

class PortfolioConfig(SQLModel, table=True):
    __tablename__ = "portfolio_config"
    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    value: str


class TradeLog(SQLModel, table=True):
    __tablename__ = "trade_log"
    id: int | None = Field(default=None, primary_key=True)
    timestamp: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    symbol: str
    side: str
    quantity: float
    price: float
    order_id: str
    status: str
    reason: str = ""


class Position(SQLModel, table=True):
    __tablename__ = "positions"
    id: int | None = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, unique=True)
    quantity: float
    avg_entry_price: float


class DecisionLog(SQLModel, table=True):
    __tablename__ = "decision_log"
    id: int | None = Field(default=None, primary_key=True)
    timestamp: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    symbol: str
    decision: str  # buy / sell / hold
    confidence: float
    reasoning: str = ""
    executed: bool = False


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def init_db() -> None:
    SQLModel.metadata.create_all(engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_session() -> Session:
    return Session(engine)


def get_config(key: str) -> str | None:
    with get_session() as session:
        row = session.exec(select(PortfolioConfig).where(PortfolioConfig.key == key)).first()
        return row.value if row else None


def set_config(key: str, value: str) -> None:
    with get_session() as session:
        existing = session.exec(select(PortfolioConfig).where(PortfolioConfig.key == key)).first()
        if existing:
            existing.value = value
        else:
            session.add(PortfolioConfig(key=key, value=value))
        session.commit()


def log_trade(**kwargs: object) -> TradeLog:
    trade = TradeLog(**{k: v for k, v in kwargs.items() if v is not None})  # type: ignore[arg-type]
    with get_session() as session:
        session.add(trade)
        session.commit()
        session.refresh(trade)
    return trade


def log_decision(**kwargs: object) -> DecisionLog:
    decision = DecisionLog(**{k: v for k, v in kwargs.items() if v is not None})  # type: ignore[arg-type]
    with get_session() as session:
        session.add(decision)
        session.commit()
        session.refresh(decision)
    return decision


def get_all_positions() -> list[Position]:
    with get_session() as session:
        return list(session.exec(select(Position)).all())


def get_position(symbol: str) -> Position | None:
    with get_session() as session:
        return session.exec(select(Position).where(Position.symbol == symbol)).first()


def upsert_position(symbol: str, quantity: float, avg_entry_price: float) -> Position:
    with get_session() as session:
        pos = session.exec(select(Position).where(Position.symbol == symbol)).first()
        if pos:
            pos.quantity = quantity
            pos.avg_entry_price = avg_entry_price
        else:
            pos = Position(symbol=symbol, quantity=quantity, avg_entry_price=avg_entry_price)
            session.add(pos)
        session.commit()
        session.refresh(pos)
        return pos  # type: ignore[return-value]


def delete_position(symbol: str) -> None:
    with get_session() as session:
        pos = session.exec(select(Position).where(Position.symbol == symbol)).first()
        if pos:
            session.delete(pos)
            session.commit()
