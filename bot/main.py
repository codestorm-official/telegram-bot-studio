"""Entrypoint for the Telegram bot."""

import logging

from telegram import Update
from telegram.ext import Application, ApplicationBuilder

from bot import cache, db
from bot.config import Settings
from bot.handlers import (
    DB_KEY,
    REDIS_KEY,
    error_handler,
    register_handlers,
    set_bot_commands,
)


logger = logging.getLogger(__name__)


def configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
        level=level,
    )


def build_application(settings: Settings) -> Application:
    async def on_startup(application: Application) -> None:
        # Fail fast: if either backend is unreachable the bot must not start.
        application.bot_data[DB_KEY] = await db.create_pool(settings.database_url)
        application.bot_data[REDIS_KEY] = await cache.create_client(settings.redis_url)
        await set_bot_commands(application)

    async def on_shutdown(application: Application) -> None:
        pool = application.bot_data.get(DB_KEY)
        if pool is not None:
            await db.close_pool(pool)

        client = application.bot_data.get(REDIS_KEY)
        if client is not None:
            await cache.close_client(client)

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


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    application = build_application(settings)
    logger.info("Bot is running with polling.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
