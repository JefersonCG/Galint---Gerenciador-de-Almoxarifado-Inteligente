"""add service company documents json

Revision ID: f6a1b2c3d4e5
Revises: e2f4b6c8d9a1
Create Date: 2026-05-18
"""

from alembic import op


revision = "f6a1b2c3d4e5"
down_revision = "e2f4b6c8d9a1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE service_companies ADD COLUMN IF NOT EXISTS documents_json jsonb")


def downgrade():
    op.execute("ALTER TABLE service_companies DROP COLUMN IF EXISTS documents_json")