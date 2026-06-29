"""Entrypoint for the Telegram bot (and the optional admin panel)."""

import asyncio
import logging

import uvicorn
from telegram import Update
from telegram.ext import Application, ApplicationBuilder

from bot import commands, db
from bot.config import Settings
from bot.handlers import (
    DB_KEY,
    error_handler,
    register_handlers,
    set_bot_commands,
)
from bot.panel.app import create_app


logger = logging.getLogger(__name__)


def configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
        level=level,
    )


async def _connect_database(url: str, *, required: bool):
    """Connect to Postgres, only degrading gracefully for a bot-only process.

    A panel with no database is unusable, so fail startup instead of serving a
    permanently disconnected UI after a transient or configuration error.
    """
    if not url:
        logger.warning("DATABASE_URL not set - running without PostgreSQL persistence.")
        return None
    try:
        return await db.create_pool(url)
    except Exception as exc:
        if required:
            raise RuntimeError(
                "PostgreSQL connection failed. Check DATABASE_URL in the bot "
                "service and confirm the Railway Postgres service is running."
            ) from exc
        logger.exception("PostgreSQL unavailable - running without persistence.")
        return None


def build_application(settings: Settings) -> Application:
    async def on_startup(application: Application) -> None:
        application.bot_data[DB_KEY] = await _connect_database(
            settings.database_url, required=settings.panel_enabled
        )
        # Load panel-managed commands before publishing the Telegram menu.
        await commands.reload(application.bot_data[DB_KEY])
        try:
            await set_bot_commands(application)
        except Exception:
            # A rejected menu must not stop the bot from starting.
            logger.exception("Failed to publish command menu on startup.")

    async def on_shutdown(application: Application) -> None:
        pool = application.bot_data.get(DB_KEY)
        if pool is not None:
            await db.close_pool(pool)

    application = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )
    register_handlers(application)
    application.add_error_handler(error_handler)
    return application


async def _run_with_panel(application: Application, settings: Settings) -> None:
    """Run Telegram polling and the admin panel together in one event loop."""
    await application.initialize()  # triggers on_startup (connect + load commands)
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot polling started; admin panel listening on port %d.", settings.port)

    web = create_app(application, settings)
    config = uvicorn.Config(
        web,
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)
    try:
        await server.serve()  # blocks until SIGTERM/SIGINT
    finally:
        if application.updater is not None and application.updater.running:
            await application.updater.stop()
        await application.stop()
        await application.shutdown()  # triggers on_shutdown (close pool)


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    application = build_application(settings)

    if settings.panel_enabled:
        asyncio.run(_run_with_panel(application, settings))
    else:
        logger.info(
            "Bot is running with polling (admin panel disabled: PANEL_PASSWORD not set)."
        )
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
