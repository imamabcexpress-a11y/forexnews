"""
bot/scheduler.py - Background scheduler for news alerts and signal generation
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.constants import ParseMode
from loguru import logger

from core.config import settings
from core.database import AsyncSessionLocal, NewsEvent, TradingSignal
from data.market_data import MarketDataService
from data.news_fetcher import NewsAggregator, is_high_impact, get_affected_pairs
from analysis.signal_engine import SignalEngine
from analysis.technical import extract_key_levels
from bot.formatter import format_signal_message, format_news_alert, format_breakout_alert

UTC = pytz.utc
WIB = pytz.timezone("Asia/Jakarta")

market_svc = MarketDataService()
news_agg = NewsAggregator()
signal_engine = SignalEngine()


# ─────────────────────────────────────────
# HELPER: Send to configured channels
# ─────────────────────────────────────────
async def broadcast(bot: Bot, text: str):
    targets = [settings.TELEGRAM_GROUP_ID, settings.TELEGRAM_CHANNEL_ID]
    for chat_id in targets:
        if not chat_id:
            continue
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.warning(f"Broadcast failed to {chat_id}: {e}")


# ─────────────────────────────────────────
# NEWS SCHEDULER
# ─────────────────────────────────────────
class NewsScheduler:
    def __init__(self, bot: Bot):
        self.bot = bot
        self._news_cache: dict = {}  # event_id -> notified flags

    async def refresh_news(self):
        """Fetch and cache upcoming high impact news"""
        try:
            events = await news_agg.fetch_high_impact_only(days_ahead=3)
            for e in events:
                eid = e["event_id"]
                if eid not in self._news_cache:
                    self._news_cache[eid] = {
                        "event": e,
                        "notified_60m": False,
                        "notified_30m": False,
                        "notified_15m": False,
                        "notified_5m": False,
                        "notified_release": False,
                    }
            logger.info(f"News cache refreshed: {len(self._news_cache)} events")
        except Exception as e:
            logger.error(f"News refresh error: {e}")

    async def check_and_notify(self):
        """Check each cached event and send reminders at correct times"""
        now_utc = datetime.utcnow().replace(tzinfo=UTC)
        notif_windows = [
            (60, "notified_60m"),
            (30, "notified_30m"),
            (15, "notified_15m"),
            (5, "notified_5m"),
        ]

        for eid, entry in list(self._news_cache.items()):
            event = entry["event"]
            release = event["release_time_utc"]
            if release.tzinfo is None:
                release = UTC.localize(release)

            minutes_left = (release - now_utc).total_seconds() / 60

            # Send reminder notifications
            for mins, flag in notif_windows:
                if (mins - 1) <= minutes_left <= (mins + 1) and not entry[flag]:
                    logger.info(f"Sending {mins}m reminder: {event['title']}")
                    msg = format_news_alert(event, minutes_before=mins)
                    await broadcast(self.bot, msg)
                    entry[flag] = True

            # Send release notification (within 2 min after release)
            if -2 <= minutes_left <= 0 and not entry["notified_release"]:
                logger.info(f"Sending release notification: {event['title']}")
                msg = format_news_alert(event, minutes_before=None)
                await broadcast(self.bot, msg)
                entry["notified_release"] = True

            # Clean up old events (more than 2 hours after release)
            if minutes_left < -120:
                del self._news_cache[eid]

    def is_news_window(self, minutes_before: int = 30, minutes_after: int = 15) -> bool:
        """Check if currently within news blackout window"""
        now_utc = datetime.utcnow().replace(tzinfo=UTC)
        for entry in self._news_cache.values():
            release = entry["event"]["release_time_utc"]
            if release.tzinfo is None:
                release = UTC.localize(release)
            delta = (release - now_utc).total_seconds() / 60
            if -minutes_after <= delta <= minutes_before:
                return True
        return False


# ─────────────────────────────────────────
# SIGNAL SCHEDULER
# ─────────────────────────────────────────
class SignalScheduler:
    def __init__(self, bot: Bot, news_scheduler: NewsScheduler):
        self.bot = bot
        self.news_scheduler = news_scheduler
        self._last_signal: dict = {}  # symbol -> last signal timestamp

    async def check_signals(self):
        """Scan all watchlist symbols and send signals if conditions met"""
        news_safe = not self.news_scheduler.is_news_window()

        for symbol in settings.WATCHLIST:
            try:
                await self._check_symbol(symbol, news_safe)
                await asyncio.sleep(2)  # Rate limit API calls
            except Exception as e:
                logger.error(f"Signal check error {symbol}: {e}")

    async def _check_symbol(self, symbol: str, news_safe: bool):
        now = datetime.now(WIB)

        # Don't re-signal same symbol within 1 hour
        last = self._last_signal.get(symbol)
        if last and (now - last).total_seconds() < 3600:
            return

        mtf_data = await market_svc.get_multi_timeframe(symbol)
        price = await market_svc.get_current_price(symbol)
        if not price:
            return

        signal = signal_engine.generate(symbol, mtf_data, price, news_safe)

        if signal.direction == "NO_TRADE":
            logger.debug(f"No trade {symbol}: {signal.reason}")
            return

        if signal.confidence < settings.SIGNAL_MIN_CONFIDENCE:
            logger.debug(f"Low confidence {symbol}: {signal.confidence}")
            return

        logger.info(f"Signal generated: {symbol} {signal.direction} {signal.confidence}%")
        msg = format_signal_message(signal)
        await broadcast(self.bot, msg)
        self._last_signal[symbol] = now

        # Check breakout alerts
        if settings.ENABLE_BREAKOUT_ALERTS:
            await self._check_breakout(symbol, price, mtf_data)

    async def _check_breakout(self, symbol: str, price: float, mtf_data: dict):
        d1 = mtf_data.get("D1")
        if d1 is None or len(d1) < 5:
            return

        levels = extract_key_levels(d1, mtf_data.get("H4"))
        atr = float(d1["High"].iloc[-1] - d1["Low"].iloc[-1])
        threshold = atr * 0.1

        breakout_checks = [
            ("Daily High", levels.get("daily_high"), "Bullish"),
            ("Daily Low", levels.get("daily_low"), "Bearish"),
            ("Weekly High", levels.get("weekly_high"), "Bullish"),
            ("Weekly Low", levels.get("weekly_low"), "Bearish"),
        ]

        for name, level, direction in breakout_checks:
            if level is None:
                continue
            if direction == "Bullish" and price > level + threshold:
                msg = format_breakout_alert(symbol, name, level, f"Bullish Breakout", True, 80)
                await broadcast(self.bot, msg)
                break
            elif direction == "Bearish" and price < level - threshold:
                msg = format_breakout_alert(symbol, name, level, f"Bearish Breakout", True, 78)
                await broadcast(self.bot, msg)
                break


# ─────────────────────────────────────────
# SCHEDULER SETUP
# ─────────────────────────────────────────
def build_scheduler(bot: Bot) -> AsyncIOScheduler:
    news_sched = NewsScheduler(bot)
    signal_sched = SignalScheduler(bot, news_sched)

    scheduler = AsyncIOScheduler(timezone=WIB)

    # Refresh news every 5 minutes
    scheduler.add_job(
        news_sched.refresh_news,
        "interval",
        minutes=5,
        id="news_refresh",
        max_instances=1,
    )

    # Check and notify news every 1 minute
    scheduler.add_job(
        news_sched.check_and_notify,
        "interval",
        minutes=1,
        id="news_notify",
        max_instances=1,
    )

    # Check signals every 5 minutes
    scheduler.add_job(
        signal_sched.check_signals,
        "interval",
        minutes=5,
        id="signal_check",
        max_instances=1,
    )

    return scheduler, news_sched, signal_sched
