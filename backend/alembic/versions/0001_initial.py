"""initial schema — all tables + postgis/pg_trgm extensions

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-16

Enables the PostGIS + pg_trgm extensions (required by the geometry column and the trigram
address search), then creates every table registered on ``Base.metadata``. We import the
models so the metadata is fully populated, then emit ``create_all`` against the migration
connection — a single source of truth shared with the local ``create_all`` path.
"""
from __future__ import annotations

from alembic import op

# Import the app models so Base.metadata carries every table before we create_all.
from app.core.db import Base
import app.models.entities  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pg_trgm for fuzzy address search (ships with standard Postgres).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
    # Leave extensions in place — other schemas/databases may depend on them.
