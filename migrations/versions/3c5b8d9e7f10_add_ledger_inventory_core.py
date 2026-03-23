"""add_ledger_inventory_core

Revision ID: 3c5b8d9e7f10
Revises: f8b1d9c2a6e4
Create Date: 2026-03-23 12:30:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "3c5b8d9e7f10"
down_revision = "f8b1d9c2a6e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("movement_type", sa.String(length=30), nullable=False),
        sa.Column("quantity_base", sa.Float(), nullable=False),
        sa.Column("unit_base", sa.String(length=30), nullable=False),
        sa.Column("reference_type", sa.String(length=50), nullable=True),
        sa.Column("reference_id", sa.String(length=100), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["product_id"], ["itens.codigo_item"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stock_movements_created_at"), "stock_movements", ["created_at"], unique=False)
    op.create_index(op.f("ix_stock_movements_movement_type"), "stock_movements", ["movement_type"], unique=False)
    op.create_index(op.f("ix_stock_movements_product_id"), "stock_movements", ["product_id"], unique=False)
    op.create_index(op.f("ix_stock_movements_reference_id"), "stock_movements", ["reference_id"], unique=False)
    op.create_index(op.f("ix_stock_movements_reference_type"), "stock_movements", ["reference_type"], unique=False)

    op.create_table(
        "stock_balances",
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("quantity_base", sa.Float(), nullable=False, server_default="0"),
        sa.Column("read_model_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["product_id"], ["itens.codigo_item"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("product_id"),
    )

    op.create_table(
        "product_dimensions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("dimension", sa.String(length=30), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["product_id"], ["itens.codigo_item"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "dimension", name="uq_product_dimensions_product_dimension"),
    )
    op.create_index(op.f("ix_product_dimensions_product_id"), "product_dimensions", ["product_id"], unique=False)

    op.create_table(
        "product_units",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("unit_code", sa.String(length=30), nullable=False),
        sa.Column("unit_label", sa.String(length=80), nullable=False),
        sa.Column("dimension", sa.String(length=30), nullable=True),
        sa.Column("is_base", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["product_id"], ["itens.codigo_item"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "unit_code", name="uq_product_units_product_unit_code"),
    )
    op.create_index(op.f("ix_product_units_product_id"), "product_units", ["product_id"], unique=False)

    op.create_table(
        "product_unit_conversions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("from_unit", sa.String(length=30), nullable=False),
        sa.Column("to_unit", sa.String(length=30), nullable=False),
        sa.Column("factor", sa.Float(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["product_id"], ["itens.codigo_item"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id",
            "from_unit",
            "to_unit",
            name="uq_product_unit_conversions_product_from_to",
        ),
    )
    op.create_index(op.f("ix_product_unit_conversions_product_id"), "product_unit_conversions", ["product_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_product_unit_conversions_product_id"), table_name="product_unit_conversions")
    op.drop_table("product_unit_conversions")

    op.drop_index(op.f("ix_product_units_product_id"), table_name="product_units")
    op.drop_table("product_units")

    op.drop_index(op.f("ix_product_dimensions_product_id"), table_name="product_dimensions")
    op.drop_table("product_dimensions")

    op.drop_table("stock_balances")

    op.drop_index(op.f("ix_stock_movements_reference_type"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_reference_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_product_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_movement_type"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_created_at"), table_name="stock_movements")
    op.drop_table("stock_movements")