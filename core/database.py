"""
core/database.py - Database models and connection management
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean,
    Text, Enum, Index
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
import enum
from core.config import settings

Base = declarative_base()

# ─────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────
class SignalDirection(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"

class SignalStrength(str, enum.Enum):
    STRONG = "STRONG"
    NORMAL = "NORMAL"
    WEAK = "WEAK"

class NewsImpact(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

# ─────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────
class NewsEvent(Base):
    __tablename__ = "news_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(100), unique=True, nullable=False)
    title = Column(String(300), nullable=False)
    country = Column(String(10))
    currency = Column(String(10))
    impact = Column(Enum(NewsImpact), default=NewsImpact.LOW)
    forecast = Column(String(50))
    previous = Column(String(50))
    actual = Column(String(50))
    release_time_utc = Column(DateTime, nullable=False)
    release_time_wib = Column(DateTime, nullable=False)
    notified_60m = Column(Boolean, default=False)
    notified_30m = Column(Boolean, default=False)
    notified_15m = Column(Boolean, default=False)
    notified_5m = Column(Boolean, default=False)
    notified_release = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_news_release_time", "release_time_utc"),
        Index("ix_news_impact", "impact"),
    )


class TradingSignal(Base):
    __tablename__ = "trading_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    direction = Column(Enum(SignalDirection), nullable=False)
    strength = Column(Enum(SignalStrength))
    entry_price = Column(Float)
    sl_price = Column(Float)
    tp1_price = Column(Float)
    tp2_price = Column(Float)
    tp3_price = Column(Float)
    risk_reward = Column(Float)
    confidence_score = Column(Integer)

    # Score breakdown
    score_trend = Column(Integer, default=0)
    score_sr = Column(Integer, default=0)
    score_rsi = Column(Integer, default=0)
    score_volume = Column(Integer, default=0)
    score_vwap = Column(Integer, default=0)
    score_structure = Column(Integer, default=0)
    score_orderblock = Column(Integer, default=0)

    trend_d1 = Column(String(20))
    trend_h4 = Column(String(20))
    trend_h1 = Column(String(20))
    trend_m15 = Column(String(20))
    news_safe = Column(Boolean, default=True)
    notes = Column(Text)

    sent_to_telegram = Column(Boolean, default=False)
    outcome = Column(String(20))  # WIN / LOSS / PENDING / CANCELLED
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_signal_symbol", "symbol"),
        Index("ix_signal_created", "created_at"),
    )


class PriceLevel(Base):
    __tablename__ = "price_levels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    level_type = Column(String(50))  # daily_high, weekly_low, supply_zone, etc.
    price = Column(Float, nullable=False)
    timeframe = Column(String(10))
    valid_from = Column(DateTime)
    valid_until = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BotLog(Base):
    __tablename__ = "bot_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(20))
    module = Column(String(100))
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# ENGINE & SESSION
# ─────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
