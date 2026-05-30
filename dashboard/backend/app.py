"""
dashboard/backend/app.py - FastAPI dashboard for signal history and analytics
"""
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from pydantic import BaseModel
import pytz

from core.database import get_session, TradingSignal, NewsEvent, BotLog
from core.config import settings

WIB = pytz.timezone("Asia/Jakarta")


# ─────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────
class SignalOut(BaseModel):
    id: int
    symbol: str
    direction: str
    strength: Optional[str]
    entry_price: Optional[float]
    sl_price: Optional[float]
    tp1_price: Optional[float]
    confidence_score: Optional[int]
    trend_d1: Optional[str]
    news_safe: Optional[bool]
    outcome: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class NewsOut(BaseModel):
    id: int
    title: str
    country: Optional[str]
    currency: Optional[str]
    impact: str
    forecast: Optional[str]
    previous: Optional[str]
    actual: Optional[str]
    release_time_wib: datetime

    class Config:
        from_attributes = True


class StatsOut(BaseModel):
    total_signals: int
    signals_today: int
    win_rate: float
    avg_confidence: float
    total_news: int
    news_today: int


# ─────────────────────────────────────────
# APP FACTORY
# ─────────────────────────────────────────
def create_dashboard() -> FastAPI:
    app = FastAPI(
        title="Forex Bot Dashboard",
        description="Signal history, news calendar, and analytics",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─── SIGNALS ───────────────────────────
    @app.get("/api/signals", response_model=List[SignalOut])
    async def get_signals(
        symbol: Optional[str] = None,
        limit: int = 50,
        db: AsyncSession = Depends(get_session),
    ):
        q = select(TradingSignal).order_by(desc(TradingSignal.created_at)).limit(limit)
        if symbol:
            q = q.where(TradingSignal.symbol == symbol.upper())
        result = await db.execute(q)
        return result.scalars().all()

    @app.get("/api/signals/{signal_id}", response_model=SignalOut)
    async def get_signal(signal_id: int, db: AsyncSession = Depends(get_session)):
        result = await db.execute(
            select(TradingSignal).where(TradingSignal.id == signal_id)
        )
        sig = result.scalar_one_or_none()
        if not sig:
            raise HTTPException(404, "Signal not found")
        return sig

    # ─── NEWS ──────────────────────────────
    @app.get("/api/news", response_model=List[NewsOut])
    async def get_news(
        impact: Optional[str] = "HIGH",
        days: int = 7,
        db: AsyncSession = Depends(get_session),
    ):
        since = datetime.utcnow() - timedelta(days=1)
        until = datetime.utcnow() + timedelta(days=days)
        q = (
            select(NewsEvent)
            .where(NewsEvent.release_time_utc >= since)
            .where(NewsEvent.release_time_utc <= until)
            .order_by(NewsEvent.release_time_utc)
        )
        if impact:
            q = q.where(NewsEvent.impact == impact)
        result = await db.execute(q)
        return result.scalars().all()

    # ─── STATS ─────────────────────────────
    @app.get("/api/stats", response_model=StatsOut)
    async def get_stats(db: AsyncSession = Depends(get_session)):
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)

        total_sigs = (await db.execute(func.count(TradingSignal.id))).scalar() or 0
        sigs_today = (
            await db.execute(
                func.count(TradingSignal.id).where(TradingSignal.created_at >= today_start)
            )
        ).scalar() or 0

        # Win rate
        wins = (
            await db.execute(
                func.count(TradingSignal.id).where(TradingSignal.outcome == "WIN")
            )
        ).scalar() or 0
        losses = (
            await db.execute(
                func.count(TradingSignal.id).where(TradingSignal.outcome == "LOSS")
            )
        ).scalar() or 0
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0

        avg_conf = (
            await db.execute(func.avg(TradingSignal.confidence_score))
        ).scalar() or 0.0

        total_news = (await db.execute(func.count(NewsEvent.id))).scalar() or 0
        news_today = (
            await db.execute(
                func.count(NewsEvent.id).where(NewsEvent.release_time_utc >= today_start)
            )
        ).scalar() or 0

        return StatsOut(
            total_signals=total_sigs,
            signals_today=sigs_today,
            win_rate=round(win_rate, 2),
            avg_confidence=round(float(avg_conf), 2),
            total_news=total_news,
            news_today=news_today,
        )

    # ─── HEALTH ────────────────────────────
    @app.get("/health")
    async def health():
        return {"status": "ok", "time": datetime.now(WIB).isoformat()}

    return app
