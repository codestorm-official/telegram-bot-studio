#!/bin/sh
set -eu

if [ -n "${DATABASE_URL:-}" ]; then
  alembic upgrade head
fi

exec python -m bot.main
