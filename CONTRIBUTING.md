# Contributing to Telegram Bot Studio

Thanks for helping improve Telegram Bot Studio. Contributions of code,
documentation, tests, bug reports, and UX feedback are welcome.

## Development setup

Requirements:

- Python 3.12+
- PostgreSQL 16+, or Docker with Docker Compose
- A Telegram bot token from `@BotFather`

Create your local configuration:

```bash
cp .env.example .env
```

Set at least `BOT_TOKEN`, `DATABASE_URL`, and `PANEL_PASSWORD` in `.env`. Never
commit this file.

To run the complete stack with Docker:

```bash
docker compose up --build
```

To run Python directly:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m bot.main
```

## Making changes

1. Fork the repository and create a focused branch from `main`.
2. Keep changes scoped to one concern.
3. Add or update tests for changed behavior.
4. Update documentation and `.env.example` for configuration changes.
5. Do not commit credentials, database dumps, local logs, or generated caches.

Use clear branch names, such as:

```text
feature/button-search
fix/keyboard-refresh-message
docs/docker-setup
```

## Validation

Run the test suite and static checks before opening a pull request:

```bash
python -m unittest discover -s tests -v
python -m compileall -q bot migrations tests
alembic history
git diff --check
```

For UI changes, check both desktop and mobile layouts. For database changes,
add an Alembic revision and verify both a fresh database and an existing one.

## Pull requests

Include:

- A concise explanation of the problem and solution.
- Testing performed.
- Screenshots for visible UI changes.
- Migration and deployment notes when applicable.

Avoid mixing formatting-only changes with functional changes. Maintainers may
request revisions before merging.

## Reporting security issues

Do not open a public issue for vulnerabilities or exposed credentials. Follow
the private reporting process in [SECURITY.md](SECURITY.md).

