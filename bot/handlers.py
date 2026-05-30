"""
bot/handlers.py - Telegram bot command handlers
"""
import asyncio
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from loguru import logger

from core.config import settings
from data.market_data import MarketDataService
from data.news_fetcher import NewsAggregator
from analysis.signal_engine import SignalEngine
from bot.formatter import (
    format_signal_message,
    format_news_alert,
    format_status_message,
)

WIB = pytz.timezone("Asia/Jakarta")
_start_time = datetime.now(WIB)

market_svc = MarketDataService()
news_agg = NewsAggregator()
signal_engine = SignalEngine()


def uptime_str() -> str:
    delta = datetime.now(WIB) - _start_time
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s"


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 <b>Forex News & Signal Bot</b>\n\n"
        "Bot aktif dan siap mengirim notifikasi berita dan sinyal trading.\n\n"
        "Ketik /help untuk daftar perintah."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 <b>Daftar Command</b>\n\n"
        "/start — Mulai bot\n"
        "/status — Status bot\n"
        "/news — Berita high impact hari ini\n"
        "/gold — Analisa XAUUSD\n"
        "/signal [PAIR] — Generate sinyal (default: XAUUSD)\n"
        "/calendar — Kalender ekonomi 7 hari\n"
        "/impact — Berita high impact berikutnya\n"
        "/help — Bantuan\n\n"
        "⚠️ <i>Bukan financial advice. Selalu gunakan manajemen risiko.</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # TODO: query DB for today's counts
    text = format_status_message(uptime_str(), 0, 0)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Mengambil data berita...", parse_mode=ParseMode.HTML)
    try:
        events = await news_agg.fetch_high_impact_only(days_ahead=1)
        if not events:
            await update.message.reply_text("Tidak ada berita high impact hari ini.")
            return
        for event in events[:10]:
            msg = format_news_alert(event)
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"cmd_news error: {e}")
        await update.message.reply_text("❌ Gagal mengambil data berita.")


async def cmd_calendar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Mengambil kalender ekonomi...", parse_mode=ParseMode.HTML)
    try:
        events = await news_agg.fetch_high_impact_only(days_ahead=7)
        if not events:
            await update.message.reply_text("Tidak ada berita high impact minggu ini.")
            return

        lines = ["📅 <b>Kalender Ekonomi (7 Hari)</b>\n"]
        for e in events[:20]:
            t = e["release_time_wib"].strftime("%d/%m %H:%M")
            lines.append(f"• {t} WIB — {e['title']} [{e['currency']}]")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"cmd_calendar error: {e}")
        await update.message.reply_text("❌ Gagal mengambil kalender.")


async def cmd_impact(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Mencari berita berikutnya...", parse_mode=ParseMode.HTML)
    try:
        events = await news_agg.fetch_high_impact_only(days_ahead=3)
        now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
        upcoming = [e for e in events if e["release_time_utc"] > now_utc]
        upcoming.sort(key=lambda x: x["release_time_utc"])
        if not upcoming:
            await update.message.reply_text("Tidak ada berita high impact dalam 3 hari ke depan.")
            return
        msg = format_news_alert(upcoming[0])
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"cmd_impact error: {e}")
        await update.message.reply_text("❌ Gagal mengambil berita berikutnya.")


async def _generate_and_send_signal(symbol: str, update: Update):
    await update.message.reply_text(f"⏳ Menganalisa {symbol}...", parse_mode=ParseMode.HTML)
    try:
        mtf_data = await market_svc.get_multi_timeframe(symbol)
        price = await market_svc.get_current_price(symbol)

        if not price:
            await update.message.reply_text(f"❌ Tidak bisa mengambil harga {symbol}.")
            return

        # Check news safety (simplified: always safe for manual command)
        signal = signal_engine.generate(symbol, mtf_data, price, news_safe=True)

        if signal.direction == "NO_TRADE":
            await update.message.reply_text(
                f"⚪ <b>NO TRADE — {symbol}</b>\n\nAlasan: {signal.reason}",
                parse_mode=ParseMode.HTML,
            )
            return

        if signal.confidence < settings.SIGNAL_MIN_CONFIDENCE:
            await update.message.reply_text(
                f"⚠️ Confidence terlalu rendah ({signal.confidence}%). Signal tidak dikirim.",
                parse_mode=ParseMode.HTML,
            )
            return

        msg = format_signal_message(signal)
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Signal generation error {symbol}: {e}")
        await update.message.reply_text("❌ Gagal generate sinyal.")


async def cmd_gold(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _generate_and_send_signal("XAUUSD", update)


async def cmd_signal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    symbol = args[0].upper() if args else "XAUUSD"
    if symbol not in settings.WATCHLIST:
        await update.message.reply_text(
            f"⚠️ Pair tidak dikenal: {symbol}\nWatchlist: {', '.join(settings.WATCHLIST)}"
        )
        return
    await _generate_and_send_signal(symbol, update)


# ─────────────────────────────────────────
# APPLICATION BUILDER
# ─────────────────────────────────────────
def build_application() -> Application:
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("calendar", cmd_calendar))
    app.add_handler(CommandHandler("impact", cmd_impact))
    app.add_handler(CommandHandler("gold", cmd_gold))
    app.add_handler(CommandHandler("signal", cmd_signal))
    return app
