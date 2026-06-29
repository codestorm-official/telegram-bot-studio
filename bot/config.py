"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    log_level: str = "INFO"
    port: int = 8080
    panel_username: str = "admin"
    panel_password: str = ""
    panel_secret_key: str = ""
    panel_secure_cookie: bool = False

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

        # The database remains optional for a bot-only process, but the admin
        # panel cannot work without its command store.
        database_url = os.getenv("DATABASE_URL", "").strip()

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
        secure_cookie_value = os.getenv("PANEL_SECURE_COOKIE", "").strip().lower()
        panel_secure_cookie = (
            secure_cookie_value in {"1", "true", "yes", "on"}
            if secure_cookie_value
            else bool(os.getenv("RAILWAY_ENVIRONMENT"))
        )
        if panel_password and not database_url:
            raise RuntimeError(
                "DATABASE_URL is required when PANEL_PASSWORD enables the admin panel. "
                "On Railway, add DATABASE_URL=${{ Postgres.DATABASE_URL }} to the "
                "bot service variables."
            )

        return cls(
            bot_token=bot_token,
            database_url=database_url,
            log_level=log_level,
            port=port,
            panel_username=panel_username,
            panel_password=panel_password,
            panel_secret_key=panel_secret_key,
            panel_secure_cookie=panel_secure_cookie,
        )
