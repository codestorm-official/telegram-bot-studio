"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    redis_url: str
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
            raise RuntimeError(
                "BOT_TOKEN is not set. Add it to your local .env file or Railway variables."
            )

        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL is not set. Add a PostgreSQL connection string to your "
                ".env file or Railway variables."
            )

        redis_url = os.getenv("REDIS_URL", "").strip()
        if not redis_url:
            raise RuntimeError(
                "REDIS_URL is not set. Add a Redis connection string to your "
                ".env file or Railway variables."
            )

        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
        return cls(
            bot_token=bot_token,
            database_url=database_url,
            redis_url=redis_url,
            log_level=log_level,
        )
