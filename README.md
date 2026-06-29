# Telegram Bot with python-telegram-bot

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/python-telegram-bot?referralCode=asepsp&utm_medium=integration&utm_source=template&utm_campaign=generic)

A starter Telegram bot project built with [`python-telegram-bot`](https://python-telegram-bot.org/), environment-based configuration, Docker support, and Railway deployment setup.

![Telegram Bot Demo](img/bot.png)

## Features

- Persistent chat menu buttons after `/start`
- `/start`, `/help`, `/about`, and `/ping` commands
- Echo replies for normal text messages
- Fallback handler for unknown commands
- Error logging
- **PostgreSQL persistence** (asyncpg): users are stored/updated on `/start`
- Per-process message counter for echoed messages
- **Telegram Bot Studio**: a password-protected web dashboard to add/edit/delete dynamic
  commands (text, photo/document, and reply keyboards) without redeploying
- Configuration loaded from a local `.env` file or Railway variables
- Ready to run with Docker and Railway

## Data Store

PostgreSQL is optional when the bot runs without the admin panel. When
`DATABASE_URL` is set, the bot connects on startup and creates its tables
automatically. When `PANEL_PASSWORD` enables the panel, a working
`DATABASE_URL` is required and startup fails with a clear error if it is missing
or unreachable. This prevents the panel from silently running without its
command store.

- **PostgreSQL** — a `users` table is created automatically on first run. `/start` inserts
  a new user or refreshes `username`, `first_name`, and `last_seen` for an existing one.
  Without a database, `/start` still greets the user but nothing is persisted.

Connections are pooled with asyncpg, reused across updates, and closed cleanly
on shutdown.

## Chat Menu Buttons

The bot shows a persistent reply keyboard after `/start` with these buttons:

| Button  | Action                           |
| ------- | -------------------------------- |
| `Help`  | Show available commands          |
| `About` | Show short bot information       |
| `Ping`  | Check whether the bot is running |

Telegram bots cannot display custom buttons before a user starts or messages the bot. The keyboard appears after the bot replies, then stays available in supported Telegram clients.

## Bot Commands

| Command  | Description                      |
| -------- | -------------------------------- |
| `/start` | Show the welcome message         |
| `/help`  | Show available commands          |
| `/about` | Show short bot information       |
| `/ping`  | Check whether the bot is running |

The built-in commands above always take precedence. Any other `/command` is
resolved dynamically from commands you create in Telegram Bot Studio.

## Telegram Bot Studio

A lightweight web dashboard (FastAPI) runs **in the same process** as the bot —
no extra service required. Use it to manage dynamic commands at runtime:

- Add, edit, enable/disable, and delete commands without redeploying.
- Reply types: **text**, **photo**, or **document** (media via URL or a Telegram
  `file_id`), each with an optional **reply keyboard**.
- Changes apply immediately: the in-process registry and the Telegram command
  menu are refreshed on every save.
- Reply-keyboard changes appear after the user runs `/start` again; Telegram
  clients do not expose a remote keyboard-refresh API.
- Schema changes are managed with Alembic and applied automatically on startup.

**Enabling it:** the panel is served only when `PANEL_PASSWORD` is set, and it
requires `DATABASE_URL` (Postgres is the command store). Without `PANEL_PASSWORD`
the bot runs as a plain poller. Once enabled, open your Railway service URL (or
`http://localhost:8080` locally) and sign in with `PANEL_USERNAME` / `PANEL_PASSWORD`.

Security: credentials are checked in constant time, sessions use signed cookies,
and all state-changing forms are CSRF-protected. Always use a strong
`PANEL_PASSWORD` since the panel is reachable on your public Railway domain.

## Project Structure

```text
.
├── bot/
│   ├── __init__.py
│   ├── commands.py     # In-process registry for dynamic commands
│   ├── config.py
│   ├── db.py           # PostgreSQL pool and queries
│   ├── handlers.py
│   ├── main.py
│   └── panel/          # Telegram Bot Studio (FastAPI: app, auth, templates, static)
│       ├── app.py
│       ├── auth.py
│       ├── templates/
│       └── static/
├── .env
├── .env.example
├── .dockerignore
├── .gitignore
├── Dockerfile
├── LICENSE
├── railway.json
├── README.md
└── requirements.txt
```

## Set Up the Bot Token

1. Create a bot with Telegram `@BotFather`.
2. Copy the bot token.
3. Add the token to `.env`:

## Environment Variables

| Name           | Required | Default | Description                                        |
| -------------- | -------- | ------- | -------------------------------------------------- |
| `BOT_TOKEN`        | Yes | -       | Bot token from `@BotFather`                                   |
| `DATABASE_URL`     | For panel | -  | PostgreSQL connection string; required when `PANEL_PASSWORD` is set |
| `PANEL_PASSWORD`   | No  | -       | Enables Telegram Bot Studio when set; password to sign in     |
| `PANEL_USERNAME`   | No  | `admin` | Username for Telegram Bot Studio                              |
| `PANEL_SECRET_KEY` | No  | derived | Secret for signing panel session cookies (derived from password if empty) |
| `PANEL_SECURE_COOKIE` | No | Railway: `true` | Require HTTPS for panel session cookies |
| `PORT`             | No  | `8080`  | Port the panel binds to (Railway injects this automatically)  |
| `LOG_LEVEL`        | No  | `INFO`  | Logging level, such as `DEBUG`, `INFO`, or `ERROR`            |

On Railway, add a **PostgreSQL** service and reference its connection string
from the bot service:

```text
DATABASE_URL=${{ Postgres.DATABASE_URL }}
```

The service name in the expression is case-sensitive. If your Railway database
service has a different name, replace `Postgres` with that exact name. After
changing variables, redeploy the bot service.

For local development you can run PostgreSQL with Docker:

```bash
docker run -d --name pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16
```

## Install and Run Locally

Make sure Python 3.10 or newer is installed.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m bot.main
```

For Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m bot.main
```

## Run with Docker

```bash
docker build -t telegram-bot .
docker run --env-file .env telegram-bot
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
