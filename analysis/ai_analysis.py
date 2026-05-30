"""
analysis/ai_analysis.py - AI-powered market summary using Bluesminds API
"""
import asyncio
from datetime import datetime
from typing import Optional
import httpx
import pytz
from loguru import logger
from core.config import settings

WIB = pytz.timezone("Asia/Jakarta")

class AIAnalysisService:
    """Generates natural language market summaries using Bluesminds API"""

    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.base_url = "https://api.bluesminds.com/v1/chat/completions"
        self.model = "claude-sonnet-4-6"
        self.enabled = settings.ENABLE_AI_ANALYSIS and bool(self.api_key)
        if not self.enabled:
            logger.warning("AI Analysis disabled (no OPENAI_API_KEY or feature disabled)")

    async def generate_market_summary(
        self,
        symbol: str,
        analyses: dict,
        levels: dict,
        news_events: list,
        current_price: float,
    ) -> Optional[str]:
        if not self.enabled:
            return None

        # Build context for AI
        trend_summary = "\n".join(
            f"- {tf}: {a.get('trend','?')} | RSI {a.get('rsi',0):.1f} | ADX {a.get('adx',0):.1f}"
            for tf, a in analyses.items() if a
        )
        news_summary = "\n".join(
            f"- {e.get('title','?')} [{e.get('currency','?')}] @ {e.get('release_time_wib','').strftime('%H:%M WIB') if e.get('release_time_wib') else '?'}"
            for e in news_events[:5]
        )
        level_summary = "\n".join(f"- {k}: {v:.5f}" for k, v in levels.items() if v)

        prompt = f"""You are a professional forex market analyst. Analyze {symbol} and provide a concise summary in Bahasa Indonesia.

Current Price: {current_price:.5f}
Time: {datetime.now(WIB).strftime('%Y-%m-%d %H:%M WIB')}

Multi-Timeframe Analysis:
{trend_summary}

Key Levels:
{level_summary}

Upcoming High Impact News:
{news_summary if news_summary else '- None'}

Provide analysis covering:
1. Kondisi market saat ini (2-3 kalimat)
2. Risiko news hari ini (1-2 kalimat)
3. Skenario bullish (1-2 kalimat)
4. Skenario bearish (1-2 kalimat)
5. Area entry terbaik (1-2 kalimat)

Format with emoji. Keep it concise. End with disclaimer singkat."""

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 600,
                        "temperature": 0.3,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return None

    def format_ai_message(self, symbol: str, summary: str) -> str:
        now = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
        return (
            f"🧠 <b>AI MARKET ANALYSIS — {symbol}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{summary}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 {now}"
        )