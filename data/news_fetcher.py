"""
data/news_fetcher.py - Fetch economic calendar from multiple APIs (no HTML scraping)
"""
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import List, Optional
import httpx
import pytz
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import settings

WIB = pytz.timezone("Asia/Jakarta")
UTC = pytz.utc

HIGH_IMPACT_KEYWORDS = settings.HIGH_IMPACT_KEYWORDS


def _make_event_id(title: str, release_utc: datetime) -> str:
    raw = f"{title}_{release_utc.isoformat()}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _to_wib(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = UTC.localize(dt)
    return dt.astimezone(WIB)


# ─────────────────────────────────────────
# Trading Economics Calendar
# ─────────────────────────────────────────
class TradingEconomicsClient:
    BASE_URL = "https://api.tradingeconomics.com/calendar"

    def __init__(self, api_key: str):
        self.api_key = api_key

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_calendar(self, days_ahead: int = 7) -> List[dict]:
        if not self.api_key:
            logger.warning("TradingEconomics API key not set")
            return []

        start = datetime.utcnow().strftime("%Y-%m-%d")
        end = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        url = f"{self.BASE_URL}/country/all/{start}/{end}"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params={"c": self.api_key, "f": "json"})
            resp.raise_for_status()
            data = resp.json()

        events = []
        for item in data:
            try:
                release_utc = datetime.fromisoformat(
                    item.get("Date", "").replace("Z", "+00:00")
                )
                impact = self._map_impact(item.get("Importance", 0))
                event = {
                    "event_id": _make_event_id(item.get("Event", ""), release_utc),
                    "title": item.get("Event", "Unknown"),
                    "country": item.get("Country", ""),
                    "currency": item.get("Currency", ""),
                    "impact": impact,
                    "forecast": str(item.get("Forecast", "") or ""),
                    "previous": str(item.get("Previous", "") or ""),
                    "actual": str(item.get("Actual", "") or ""),
                    "release_time_utc": release_utc.replace(tzinfo=UTC) if release_utc.tzinfo is None else release_utc,
                    "release_time_wib": _to_wib(release_utc),
                    "source": "trading_economics",
                }
                events.append(event)
            except Exception as e:
                logger.debug(f"Skipped TE event: {e}")
        return events

    def _map_impact(self, importance: int) -> str:
        if importance >= 3:
            return "HIGH"
        elif importance == 2:
            return "MEDIUM"
        return "LOW"


# ─────────────────────────────────────────
# Twelve Data Economic Calendar
# ─────────────────────────────────────────
class TwelveDataCalendarClient:
    BASE_URL = "https://api.twelvedata.com/economic_calendar"

    def __init__(self, api_key: str):
        self.api_key = api_key

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_calendar(self, days_ahead: int = 7) -> List[dict]:
        if not self.api_key:
            logger.warning("TwelveData API key not set")
            return []

        start = datetime.utcnow().strftime("%Y-%m-%d")
        end = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                self.BASE_URL,
                params={
                    "apikey": self.api_key,
                    "start_date": start,
                    "end_date": end,
                    "importance": "high",
                    "outputsize": 200,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        events = []
        for item in data.get("result", {}).get("list", []):
            try:
                release_utc = datetime.fromisoformat(item.get("datetime", ""))
                if release_utc.tzinfo is None:
                    release_utc = UTC.localize(release_utc)
                impact = "HIGH" if item.get("importance", "") == "High" else "MEDIUM"
                event = {
                    "event_id": _make_event_id(item.get("event", ""), release_utc),
                    "title": item.get("event", "Unknown"),
                    "country": item.get("country", ""),
                    "currency": item.get("currency", ""),
                    "impact": impact,
                    "forecast": str(item.get("forecast", "") or ""),
                    "previous": str(item.get("prev", "") or ""),
                    "actual": str(item.get("actual", "") or ""),
                    "release_time_utc": release_utc,
                    "release_time_wib": _to_wib(release_utc),
                    "source": "twelve_data",
                }
                events.append(event)
            except Exception as e:
                logger.debug(f"Skipped TD event: {e}")
        return events


# ─────────────────────────────────────────
# News Filter
# ─────────────────────────────────────────
def is_high_impact(event: dict) -> bool:
    if event.get("impact") != "HIGH":
        return False
    title = event.get("title", "").upper()
    return any(kw.upper() in title for kw in HIGH_IMPACT_KEYWORDS)


def get_affected_pairs(currency: str) -> List[str]:
    mapping = {
        "USD": ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "XAGUSD"],
        "EUR": ["EURUSD", "XAUUSD"],
        "GBP": ["GBPUSD", "XAUUSD"],
        "JPY": ["USDJPY"],
        "XAU": ["XAUUSD"],
    }
    return mapping.get(currency.upper(), [currency])


# ─────────────────────────────────────────
# Aggregated Fetcher
# ─────────────────────────────────────────
class NewsAggregator:
    def __init__(self):
        self.te_client = TradingEconomicsClient(settings.TRADING_ECONOMICS_API_KEY)
        self.td_client = TwelveDataCalendarClient(settings.TWELVE_DATA_API_KEY)

    async def fetch_all(self, days_ahead: int = 7) -> List[dict]:
        results = await asyncio.gather(
            self.te_client.fetch_calendar(days_ahead),
            self.td_client.fetch_calendar(days_ahead),
            return_exceptions=True,
        )

        seen_ids = set()
        merged = []
        for batch in results:
            if isinstance(batch, Exception):
                logger.error(f"News fetch error: {batch}")
                continue
            for event in batch:
                eid = event["event_id"]
                if eid not in seen_ids:
                    seen_ids.add(eid)
                    merged.append(event)

        logger.info(f"Fetched {len(merged)} total news events")
        return merged

    async def fetch_high_impact_only(self, days_ahead: int = 3) -> List[dict]:
        all_events = await self.fetch_all(days_ahead)
        filtered = [e for e in all_events if is_high_impact(e)]
        logger.info(f"Filtered to {len(filtered)} HIGH IMPACT events")
        return filtered
