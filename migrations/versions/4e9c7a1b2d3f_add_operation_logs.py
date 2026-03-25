"""Add operation logs table

Revision ID: 4e9c7a1b2d3f
Revises: b1a4d2f9c8e7
Create Date: 2026-03-24 10:05:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "4e9c7a1b2d3f"
down_revision = "b1a4d2f9c8e7"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("operation_logs"):
        return

    op.create_table(
        "operation_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("operation_type", sa.String(length=20), nullable=False),
        sa.Column("product_id", sa.String(), nullable=True),
        sa.Column("quantity_input", sa.Float(), nullable=True),
        sa.Column("quantity_base", sa.Float(), nullable=True),
        sa.Column("unit_input", sa.String(length=30), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["product_id"], ["itens.codigo_item"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["usuarios.matricula"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_operation_logs_created_at"), "operation_logs", ["created_at"], unique=False)
    op.create_index(op.f("ix_operation_logs_operation_type"), "operation_logs", ["operation_type"], unique=False)
    op.create_index(op.f("ix_operation_logs_product_id"), "operation_logs", ["product_id"], unique=False)
    op.create_index(op.f("ix_operation_logs_source"), "operation_logs", ["source"], unique=False)
    op.create_index(op.f("ix_operation_logs_status"), "operation_logs", ["status"], unique=False)
    op.create_index(op.f("ix_operation_logs_user_id"), "operation_logs", ["user_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("operation_logs"):
        return

    op.drop_index(op.f("ix_operation_logs_user_id"), table_name="operation_logs")
    op.drop_index(op.f("ix_operation_logs_status"), table_name="operation_logs")
    op.drop_index(op.f("ix_operation_logs_source"), table_name="operation_logs")
    op.drop_index(op.f("ix_operation_logs_product_id"), table_name="operation_logs")
    op.drop_index(op.f("ix_operation_logs_operation_type"), table_name="operation_logs")
    op.drop_index(op.f("ix_operation_logs_created_at"), table_name="operation_logs")
    op.drop_table("operation_logs")