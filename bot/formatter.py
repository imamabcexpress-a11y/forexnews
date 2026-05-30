"""
bot/formatter.py - Telegram message formatters
"""
from datetime import datetime
from typing import Optional
import pytz

from analysis.signal_engine import SignalResult
from data.news_fetcher import get_affected_pairs

WIB = pytz.timezone("Asia/Jakarta")


def fmt_price(price: Optional[float], symbol: str = "") -> str:
    if price is None:
        return "N/A"
    decimals = 2 if "XAU" in symbol or "XAG" in symbol or "BTC" in symbol else 5
    return f"{price:.{decimals}f}"


def format_signal_message(signal: SignalResult) -> str:
    sym = signal.symbol
    fp = lambda p: fmt_price(p, sym)

    direction_emoji = "📈" if signal.direction == "BUY" else "📉"
    strength_map = {"STRONG": "💪 STRONG", "NORMAL": "", "WEAK": "⚠️ WEAK"}
    label = f"{strength_map.get(signal.strength, '')} {signal.direction}".strip()

    now_wib = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")

    trend_emoji = lambda t: "🟢" if t == "BULLISH" else "🔴" if t == "BEARISH" else "⚪"
    news_status = "✅ Safe" if signal.news_safe else "⚠️ News Active"

    score = signal.score
    conf = signal.confidence

    msg = f"""
{direction_emoji} <b>SIGNAL {sym}</b>

━━━━━━━━━━━━━━━━━━━━
<b>Direction:</b> {label}
<b>Entry:</b> {fp(signal.entry)}
<b>SL:</b> {fp(signal.sl)}
<b>TP1:</b> {fp(signal.tp1)}
<b>TP2:</b> {fp(signal.tp2)}
<b>TP3:</b> {fp(signal.tp3)}
<b>Risk Reward:</b> 1:{signal.risk_reward}
<b>Confidence:</b> {conf}%
━━━━━━━━━━━━━━━━━━━━

<b>🕯 Trend Analysis</b>
D1: {trend_emoji(signal.trend_d1)} {signal.trend_d1}
H4: {trend_emoji(signal.trend_h4)} {signal.trend_h4}
H1: {trend_emoji(signal.trend_h1)} {signal.trend_h1}
M15: {trend_emoji(signal.trend_m15)} {signal.trend_m15}

<b>📊 Score Breakdown</b>
Trend:       {score.trend}/20
S/R:         {score.sr}/20
RSI:         {score.rsi}/10
Volume:      {score.volume}/10
VWAP:        {score.vwap}/10
Structure:   {score.structure}/15
OrderBlock:  {score.orderblock}/15
<b>Total: {conf}/100</b>

<b>📰 News:</b> {news_status}
<b>🕒 Time:</b> {now_wib}
━━━━━━━━━━━━━━━━━━━━
⚠️ <i>Gunakan manajemen risiko. Ini bukan financial advice.</i>
""".strip()
    return msg


def format_news_alert(event: dict, minutes_before: Optional[int] = None) -> str:
    currency = event.get("currency", "")
    affected = get_affected_pairs(currency)
    pairs_str = "\n".join(f"• {p}" for p in affected)

    release_wib = event.get("release_time_wib")
    if release_wib:
        time_str = release_wib.strftime("%H:%M WIB")
    else:
        time_str = "N/A"

    if minutes_before:
        header = f"⏰ <b>NEWS REMINDER — {minutes_before} menit lagi</b>"
    else:
        header = "🔔 <b>NEWS RILIS SEKARANG</b>"

    forecast = event.get("forecast") or "–"
    previous = event.get("previous") or "–"
    actual = event.get("actual") or "–"
    actual_line = f"\n<b>Actual:</b> {actual}" if minutes_before is None else ""

    msg = f"""
🟠 <b>HIGH IMPACT NEWS</b>
{header}
━━━━━━━━━━━━━━━━━━━━
<b>Event:</b> {event.get("title", "Unknown")}
<b>Country:</b> {event.get("country", "–")} ({currency})
<b>Forecast:</b> {forecast}
<b>Previous:</b> {previous}{actual_line}
<b>Release:</b> {time_str}
━━━━━━━━━━━━━━━━━━━━
<b>Affected Pairs:</b>
{pairs_str}
━━━━━━━━━━━━━━━━━━━━
⚠️ <i>Hindari entry baru 30 menit sebelum dan 15 menit setelah rilis.</i>
""".strip()
    return msg


def format_breakout_alert(
    symbol: str,
    level_name: str,
    level_price: float,
    direction: str,
    volume_high: bool,
    probability: int,
) -> str:
    dir_emoji = "🚀" if "Bullish" in direction else "💣"
    vol_str = "🔥 High" if volume_high else "Normal"
    now_wib = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
    msg = f"""
🚨 <b>BREAKOUT ALERT</b>
{dir_emoji} {direction.upper()}
━━━━━━━━━━━━━━━━━━━━
<b>Pair:</b> {symbol}
<b>Level:</b> {level_name} @ {fmt_price(level_price, symbol)}
<b>Direction:</b> {direction}
<b>Volume:</b> {vol_str}
<b>Probability:</b> {probability}%
<b>Time:</b> {now_wib}
━━━━━━━━━━━━━━━━━━━━
""".strip()
    return msg


def format_status_message(bot_uptime: str, signals_today: int, news_today: int) -> str:
    now_wib = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
    return f"""
✅ <b>BOT STATUS</b>
━━━━━━━━━━━━━━━━━━━━
<b>Status:</b> 🟢 Online
<b>Time:</b> {now_wib}
<b>Uptime:</b> {bot_uptime}
<b>Signals Today:</b> {signals_today}
<b>News Alerts Today:</b> {news_today}
━━━━━━━━━━━━━━━━━━━━
""".strip()
