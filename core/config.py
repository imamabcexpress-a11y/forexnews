"""
core/config.py - Central configuration management
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List

load_dotenv()

class Settings(BaseModel):
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_GROUP_ID: str = os.getenv("TELEGRAM_GROUP_ID", "")
    TELEGRAM_CHANNEL_ID: str = os.getenv("TELEGRAM_CHANNEL_ID", "")
    TELEGRAM_ADMIN_ID: int = int(os.getenv("TELEGRAM_ADMIN_ID", "0"))

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/forex_bot")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # APIs
    TWELVE_DATA_API_KEY: str = os.getenv("TWELVE_DATA_API_KEY", "")
    ALPHA_VANTAGE_API_KEY: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    POLYGON_API_KEY: str = os.getenv("POLYGON_API_KEY", "")
    TRADING_ECONOMICS_API_KEY: str = os.getenv("TRADING_ECONOMICS_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Bot
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Jakarta")
    SIGNAL_MIN_CONFIDENCE: int = int(os.getenv("SIGNAL_MIN_CONFIDENCE", "80"))
    NEWS_FETCH_INTERVAL: int = int(os.getenv("NEWS_FETCH_INTERVAL", "300"))
    SIGNAL_CHECK_INTERVAL: int = int(os.getenv("SIGNAL_CHECK_INTERVAL", "300"))
    PRICE_UPDATE_INTERVAL: int = int(os.getenv("PRICE_UPDATE_INTERVAL", "60"))
    ENABLE_AI_ANALYSIS: bool = os.getenv("ENABLE_AI_ANALYSIS", "true").lower() == "true"
    ENABLE_DASHBOARD: bool = os.getenv("ENABLE_DASHBOARD", "true").lower() == "true"
    ENABLE_BREAKOUT_ALERTS: bool = os.getenv("ENABLE_BREAKOUT_ALERTS", "true").lower() == "true"

    # Dashboard
    DASHBOARD_SECRET_KEY: str = os.getenv("DASHBOARD_SECRET_KEY", "changeme")
    DASHBOARD_HOST: str = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "8000"))

    @property
    def WATCHLIST(self) -> List[str]:
        raw = os.getenv("WATCHLIST", "XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,BTCUSD")
        return [s.strip() for s in raw.split(",")]

    @property
    def HIGH_IMPACT_KEYWORDS(self) -> List[str]:
        return [
            "NFP", "Non-Farm", "CPI", "Core CPI", "PPI", "Core PPI",
            "PCE", "Core PCE", "FOMC", "Fed Interest Rate", "Federal Reserve",
            "ECB Rate", "ECB Interest Rate", "BOE Rate", "Bank of England",
            "Unemployment Rate", "GDP", "Retail Sales", "ISM PMI",
            "Initial Jobless Claims", "Durable Goods"
        ]

    class Config:
        env_file = ".env"

settings = Settings()
