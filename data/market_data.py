"""
data/market_data.py - Fetch OHLCV price data from Twelve Data & Alpha Vantage
"""
import asyncio
from datetime import datetime
from typing import Optional, List
import httpx
import pandas as pd
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import settings

TIMEFRAME_MAP_TD = {
    "M1": "1min", "M5": "5min", "M15": "15min",
    "H1": "1h", "H4": "4h", "D1": "1day"
}

# Twelve Data uses different symbols for metals/crypto
SYMBOL_MAP = {
    "XAUUSD": "XAU/USD",
    "XAGUSD": "XAG/USD",
    "BTCUSD": "BTC/USD",
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
}


class TwelveDataClient:
    BASE_URL = "https://api.twelvedata.com"

    def __init__(self, api_key: str):
        self.api_key = api_key

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        outputsize: int = 200,
    ) -> Optional[pd.DataFrame]:
        if not self.api_key:
            logger.warning("TwelveData API key not set")
            return None

        td_symbol = SYMBOL_MAP.get(symbol, symbol)
        td_interval = TIMEFRAME_MAP_TD.get(timeframe, "1h")

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{self.BASE_URL}/time_series",
                params={
                    "symbol": td_symbol,
                    "interval": td_interval,
                    "outputsize": outputsize,
                    "apikey": self.api_key,
                    "format": "JSON",
                    "order": "ASC",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") == "error":
            logger.error(f"TwelveData error for {symbol}/{timeframe}: {data.get('message')}")
            return None

        values = data.get("values", [])
        if not values:
            return None

        df = pd.DataFrame(values)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime").sort_index()
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                                  "close": "Close", "volume": "Volume"})
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
    async def get_price(self, symbol: str) -> Optional[float]:
        if not self.api_key:
            return None
        td_symbol = SYMBOL_MAP.get(symbol, symbol)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.BASE_URL}/price",
                params={"symbol": td_symbol, "apikey": self.api_key},
            )
            resp.raise_for_status()
            data = resp.json()
        price = data.get("price")
        return float(price) if price else None


class AlphaVantageClient:
    BASE_URL = "https://www.alphavantage.co/query"

    AV_FUNCTION_MAP = {
        "M1": "FX_INTRADAY",
        "M5": "FX_INTRADAY",
        "M15": "FX_INTRADAY",
        "H1": "FX_INTRADAY",
        "D1": "FX_DAILY",
    }
    AV_INTERVAL_MAP = {
        "M1": "1min", "M5": "5min", "M15": "15min", "H1": "60min"
    }

    def __init__(self, api_key: str):
        self.api_key = api_key

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        outputsize: str = "compact",
    ) -> Optional[pd.DataFrame]:
        if not self.api_key or "/" not in SYMBOL_MAP.get(symbol, "/"):
            return None

        td_sym = SYMBOL_MAP.get(symbol, symbol)
        if "/" not in td_sym:
            return None
        from_sym, to_sym = td_sym.split("/")

        func = self.AV_FUNCTION_MAP.get(timeframe, "FX_DAILY")
        params = {
            "function": func,
            "from_symbol": from_sym,
            "to_symbol": to_sym,
            "outputsize": outputsize,
            "apikey": self.api_key,
        }
        if timeframe in self.AV_INTERVAL_MAP:
            params["interval"] = self.AV_INTERVAL_MAP[timeframe]

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(self.BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        key = next((k for k in data if "Time Series" in k), None)
        if not key:
            logger.warning(f"AlphaVantage no data for {symbol}/{timeframe}")
            return None

        ts = data[key]
        rows = []
        for dt_str, vals in ts.items():
            rows.append({
                "datetime": pd.to_datetime(dt_str),
                "Open": float(vals.get("1. open", 0)),
                "High": float(vals.get("2. high", 0)),
                "Low": float(vals.get("3. low", 0)),
                "Close": float(vals.get("4. close", 0)),
                "Volume": float(vals.get("5. volume", 0)),
            })

        if not rows:
            return None

        df = pd.DataFrame(rows).set_index("datetime").sort_index()
        return df


class MarketDataService:
    """Primary market data service with fallback"""

    def __init__(self):
        self.td = TwelveDataClient(settings.TWELVE_DATA_API_KEY)
        self.av = AlphaVantageClient(settings.ALPHA_VANTAGE_API_KEY)

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        outputsize: int = 200,
    ) -> Optional[pd.DataFrame]:
        # Try Twelve Data first
        df = await self.td.get_ohlcv(symbol, timeframe, outputsize)
        if df is not None and len(df) >= 50:
            return df

        # Fallback to Alpha Vantage
        logger.warning(f"TwelveData failed for {symbol}/{timeframe}, trying AlphaVantage")
        df = await self.av.get_ohlcv(symbol, timeframe)
        if df is not None:
            return df

        logger.error(f"All data sources failed for {symbol}/{timeframe}")
        return None

    async def get_multi_timeframe(
        self,
        symbol: str,
        timeframes: List[str] = None,
    ) -> dict:
        if timeframes is None:
            timeframes = ["D1", "H4", "H1", "M15", "M5", "M1"]

        tasks = {tf: self.get_ohlcv(symbol, tf) for tf in timeframes}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        mtf_data = {}
        for tf, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"MTF fetch error {symbol}/{tf}: {result}")
                mtf_data[tf] = None
            else:
                mtf_data[tf] = result

        return mtf_data

    async def get_current_price(self, symbol: str) -> Optional[float]:
        price = await self.td.get_price(symbol)
        if price:
            return price
        # Fallback: get last close from D1
        df = await self.get_ohlcv(symbol, "D1", outputsize=5)
        if df is not None and not df.empty:
            return float(df["Close"].iloc[-1])
        return None
