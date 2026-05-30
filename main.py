"""
main.py - Entry point for Forex News & Signal Bot
"""
import asyncio
import signal
import sys
from loguru import logger

from core.config import settings
from core.database import init_db
from bot.handlers import build_application
from bot.scheduler import build_scheduler
from dashboard.backend.app import create_dashboard


# ─────────────────────────────────────────
# LOGGING SETUP
# ─────────────────────────────────────────
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - {message}",
    level="INFO",
)
logger.add(
    "logs/bot_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="30 days",
    level="DEBUG",
    encoding="utf-8",
)


async def main():
    logger.info("🚀 Starting Forex News & Signal Bot")
    logger.info(f"Watchlist: {settings.WATCHLIST}")
    logger.info(f"Timezone: {settings.TIMEZONE}")
    logger.info(f"Min Confidence: {settings.SIGNAL_MIN_CONFIDENCE}%")

    # Init database
    logger.info("Initializing database...")
    await init_db()

    # Build Telegram application
    app = build_application()

    # Build scheduler
    scheduler, news_sched, signal_sched = build_scheduler(app.bot)

    # Initial news fetch
    await news_sched.refresh_news()

    # Start scheduler
    scheduler.start()
    logger.info("✅ Scheduler started")

    # Start dashboard (optional)
    dashboard_task = None
    if settings.ENABLE_DASHBOARD:
        import uvicorn
        dashboard_app = create_dashboard()
        config = uvicorn.Config(
            dashboard_app,
            host=settings.DASHBOARD_HOST,
            port=settings.DASHBOARD_PORT,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        dashboard_task = asyncio.create_task(server.serve())
        logger.info(f"✅ Dashboard running on http://{settings.DASHBOARD_HOST}:{settings.DASHBOARD_PORT}")

    # Start Telegram bot (polling)
    logger.info("✅ Starting Telegram bot polling...")
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        # Keep running
        stop_event = asyncio.Event()

        def _handle_stop(signum, frame):
            logger.info("Shutdown signal received")
            stop_event.set()

        signal.signal(signal.SIGINT, _handle_stop)
        signal.signal(signal.SIGTERM, _handle_stop)

        logger.info("✅ Bot is running. Press Ctrl+C to stop.")
        await stop_event.wait()

        # Graceful shutdown
        logger.info("Shutting down...")
        scheduler.shutdown(wait=False)
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        if dashboard_task:
            dashboard_task.cancel()

    logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
