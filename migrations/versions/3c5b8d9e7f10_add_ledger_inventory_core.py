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
    bind = op.get_bind()

    def has_table(table_name):
        return sa.inspect(bind).has_table(table_name)

    def ensure_index(table_name, index_name, columns):
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}
        if index_name not in indexes:
            op.create_index(index_name, table_name, columns, unique=False)

    if not has_table("stock_movements"):
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
    ensure_index("stock_movements", op.f("ix_stock_movements_created_at"), ["created_at"])
    ensure_index("stock_movements", op.f("ix_stock_movements_movement_type"), ["movement_type"])
    ensure_index("stock_movements", op.f("ix_stock_movements_product_id"), ["product_id"])
    ensure_index("stock_movements", op.f("ix_stock_movements_reference_id"), ["reference_id"])
    ensure_index("stock_movements", op.f("ix_stock_movements_reference_type"), ["reference_type"])

    if not has_table("stock_balances"):
        op.create_table(
            "stock_balances",
            sa.Column("product_id", sa.String(), nullable=False),
            sa.Column("quantity_base", sa.Float(), nullable=False, server_default="0"),
            sa.Column("read_model_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["product_id"], ["itens.codigo_item"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("product_id"),
        )

    if not has_table("product_dimensions"):
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
    ensure_index("product_dimensions", op.f("ix_product_dimensions_product_id"), ["product_id"])

    if not has_table("product_units"):
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
    ensure_index("product_units", op.f("ix_product_units_product_id"), ["product_id"])

    if not has_table("product_unit_conversions"):
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
    ensure_index("product_unit_conversions", op.f("ix_product_unit_conversions_product_id"), ["product_id"])


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