"""SQLAlchemy ORM models the dashboard reads and run_dashboard_feed.py writes.

These mirror data structures that already exist elsewhere in the platform
(DecisionReport, AccountState, Trade) rather than inventing a parallel
schema: a RecordedSignal is a DecisionReport plus the strategy that
produced it, persisted so the read-only Streamlit UI can query it without
holding a live connection of its own.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RecordedBar(Base):
    __tablename__ = "recorded_bars"
    __table_args__ = (UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_recorded_bar"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    timeframe: Mapped[str] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)


class RecordedSignal(Base):
    __tablename__ = "recorded_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    direction: Mapped[str] = mapped_column(String)
    strategy_name: Mapped[str] = mapped_column(String)
    entry_price: Mapped[float | None] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float)
    take_profit: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    uncertainty: Mapped[str] = mapped_column(String)
    atr: Mapped[float | None] = mapped_column(Float)
    evidence_json: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)


class RecordedAccountSnapshot(Base):
    __tablename__ = "recorded_account_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    balance: Mapped[float] = mapped_column(Float)
    equity: Mapped[float] = mapped_column(Float)
    margin: Mapped[float] = mapped_column(Float)
    free_margin: Mapped[float] = mapped_column(Float)
    margin_level: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)


class RecordedTrade(Base):
    __tablename__ = "recorded_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[str] = mapped_column(String, unique=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    side: Mapped[str] = mapped_column(String)
    volume: Mapped[float] = mapped_column(Float)
    open_price: Mapped[float] = mapped_column(Float)
    close_price: Mapped[float] = mapped_column(Float)
    open_time: Mapped[datetime] = mapped_column(DateTime)
    close_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    profit: Mapped[float] = mapped_column(Float)


__all__ = ["Base", "RecordedAccountSnapshot", "RecordedBar", "RecordedSignal", "RecordedTrade"]
