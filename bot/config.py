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
    port: int = 8080
    panel_username: str = "admin"
    panel_password: str = ""
    panel_secret_key: str = ""

    @property
    def panel_enabled(self) -> bool:
        """The admin panel is served only when a password is configured."""
        return bool(self.panel_password)

    @classmethod
    def from_env(cls) -> "Settings":
        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
            raise RuntimeError(
                "BOT_TOKEN is not set. Add it to your local .env file or Railway variables."
            )

        # DATABASE_URL / REDIS_URL are optional: when absent or empty the bot
        # still starts and simply runs without persistence / caching. This keeps
        # local testing easy; on Railway the linked services fill these in.
        database_url = os.getenv("DATABASE_URL", "").strip()
        redis_url = os.getenv("REDIS_URL", "").strip()

        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"

        # Railway injects PORT; default keeps local runs predictable.
        try:
            port = int(os.getenv("PORT", "8080").strip() or "8080")
        except ValueError:
            port = 8080

        # Admin panel: served only when PANEL_PASSWORD is set (see panel_enabled).
        panel_username = os.getenv("PANEL_USERNAME", "admin").strip() or "admin"
        panel_password = os.getenv("PANEL_PASSWORD", "").strip()
        panel_secret_key = os.getenv("PANEL_SECRET_KEY", "").strip()

        return cls(
            bot_token=bot_token,
            database_url=database_url,
            redis_url=redis_url,
            log_level=log_level,
            port=port,
            panel_username=panel_username,
            panel_password=panel_password,
            panel_secret_key=panel_secret_key,
        )
