"""Adopt existing bot schema and add audit history.

Revision ID: 20260629_01
"""
from alembic import op


revision = "20260629_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            telegram_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS commands (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            reply_type TEXT NOT NULL DEFAULT 'text',
            reply_text TEXT NOT NULL DEFAULT '',
            media_url TEXT NOT NULL DEFAULT '',
            keyboard JSONB,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            show_in_menu BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS menu_buttons (
            id SERIAL PRIMARY KEY,
            label TEXT NOT NULL UNIQUE,
            command_name TEXT NOT NULL,
            row_index INTEGER NOT NULL DEFAULT 0 CHECK (row_index >= 0),
            sort_order INTEGER NOT NULL DEFAULT 0,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id BIGSERIAL PRIMARY KEY,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_name TEXT NOT NULL,
            details JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS audit_log_created_at_idx
            ON audit_log (created_at DESC);
        """
    )


def downgrade():
    op.execute(
        """
        DROP TABLE IF EXISTS audit_log;
        DROP TABLE IF EXISTS menu_buttons;
        DROP TABLE IF EXISTS commands;
        DROP TABLE IF EXISTS users;
        """
    )
