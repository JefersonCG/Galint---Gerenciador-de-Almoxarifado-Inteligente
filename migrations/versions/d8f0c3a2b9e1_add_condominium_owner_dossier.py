"""add condominium owner dossier json

Revision ID: d8f0c3a2b9e1
Revises: c4f8a2b1d906, b7c2d4e9a1f6
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d8f0c3a2b9e1"
down_revision = ("c4f8a2b1d906", "b7c2d4e9a1f6")
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    columns = _column_names("condominium_owners")
    if not columns:
        return
    if "registry_data_json" not in columns:
        op.add_column("condominium_owners", sa.Column("registry_data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    if "attachment_checklist_json" not in columns:
        op.add_column("condominium_owners", sa.Column("attachment_checklist_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade():
    columns = _column_names("condominium_owners")
    if "attachment_checklist_json" in columns:
        op.drop_column("condominium_owners", "attachment_checklist_json")
    if "registry_data_json" in columns:
        op.drop_column("condominium_owners", "registry_data_json")