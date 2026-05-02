"""Add purchase projection summary history tables

Revision ID: a9d4e6f2c1b8
Revises: 4f1c9e2a7b6d
Create Date: 2026-05-02 11:45:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a9d4e6f2c1b8"
down_revision = "4f1c9e2a7b6d"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("inventory_purchase_projection_summaries"):
        op.create_table(
            "inventory_purchase_projection_summaries",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("title", sa.String(length=160), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
            sa.Column("filters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("cart_state_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("cart_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("revision_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by_matricula", sa.String(), nullable=True),
            sa.Column("updated_by_matricula", sa.String(), nullable=True),
            sa.Column("source_summary_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["created_by_matricula"], ["usuarios.matricula"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_matricula"], ["usuarios.matricula"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["source_summary_id"], ["inventory_purchase_projection_summaries.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_inventory_purchase_projection_summaries_status"), "inventory_purchase_projection_summaries", ["status"], unique=False)
        op.create_index(op.f("ix_inventory_purchase_projection_summaries_created_by_matricula"), "inventory_purchase_projection_summaries", ["created_by_matricula"], unique=False)
        op.create_index(op.f("ix_inventory_purchase_projection_summaries_updated_by_matricula"), "inventory_purchase_projection_summaries", ["updated_by_matricula"], unique=False)
        op.create_index(op.f("ix_inventory_purchase_projection_summaries_source_summary_id"), "inventory_purchase_projection_summaries", ["source_summary_id"], unique=False)
        op.create_index(op.f("ix_inventory_purchase_projection_summaries_created_at"), "inventory_purchase_projection_summaries", ["created_at"], unique=False)
        op.create_index(op.f("ix_inventory_purchase_projection_summaries_updated_at"), "inventory_purchase_projection_summaries", ["updated_at"], unique=False)

    if not inspector.has_table("inventory_purchase_projection_summary_revisions"):
        op.create_table(
            "inventory_purchase_projection_summary_revisions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("summary_id", sa.Integer(), nullable=False),
            sa.Column("revision_number", sa.Integer(), nullable=False),
            sa.Column("action", sa.String(length=20), nullable=False, server_default="save"),
            sa.Column("title_snapshot", sa.String(length=160), nullable=False),
            sa.Column("filters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("cart_state_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("cart_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("created_by_matricula", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["summary_id"], ["inventory_purchase_projection_summaries.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_matricula"], ["usuarios.matricula"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("summary_id", "revision_number", name="uq_purchase_projection_summary_revision"),
        )
        op.create_index(op.f("ix_inventory_purchase_projection_summary_revisions_summary_id"), "inventory_purchase_projection_summary_revisions", ["summary_id"], unique=False)
        op.create_index(op.f("ix_inventory_purchase_projection_summary_revisions_created_by_matricula"), "inventory_purchase_projection_summary_revisions", ["created_by_matricula"], unique=False)
        op.create_index(op.f("ix_inventory_purchase_projection_summary_revisions_created_at"), "inventory_purchase_projection_summary_revisions", ["created_at"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("inventory_purchase_projection_summary_revisions"):
        op.drop_index(op.f("ix_inventory_purchase_projection_summary_revisions_created_at"), table_name="inventory_purchase_projection_summary_revisions")
        op.drop_index(op.f("ix_inventory_purchase_projection_summary_revisions_created_by_matricula"), table_name="inventory_purchase_projection_summary_revisions")
        op.drop_index(op.f("ix_inventory_purchase_projection_summary_revisions_summary_id"), table_name="inventory_purchase_projection_summary_revisions")
        op.drop_table("inventory_purchase_projection_summary_revisions")

    if inspector.has_table("inventory_purchase_projection_summaries"):
        op.drop_index(op.f("ix_inventory_purchase_projection_summaries_updated_at"), table_name="inventory_purchase_projection_summaries")
        op.drop_index(op.f("ix_inventory_purchase_projection_summaries_created_at"), table_name="inventory_purchase_projection_summaries")
        op.drop_index(op.f("ix_inventory_purchase_projection_summaries_source_summary_id"), table_name="inventory_purchase_projection_summaries")
        op.drop_index(op.f("ix_inventory_purchase_projection_summaries_updated_by_matricula"), table_name="inventory_purchase_projection_summaries")
        op.drop_index(op.f("ix_inventory_purchase_projection_summaries_created_by_matricula"), table_name="inventory_purchase_projection_summaries")
        op.drop_index(op.f("ix_inventory_purchase_projection_summaries_status"), table_name="inventory_purchase_projection_summaries")
        op.drop_table("inventory_purchase_projection_summaries")