"""Add potential suppliers and item market quotes."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b7c2d4e9a1f6"
down_revision = "a9d4e6f2c1b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "potential_suppliers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("legal_name", sa.String(length=180), nullable=True),
        sa.Column("cnpj", sa.String(length=18), nullable=True),
        sa.Column("source_name", sa.String(length=80), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("marketplace_seller_id", sa.String(length=120), nullable=True),
        sa.Column("address_line", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=40), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("phone", sa.String(length=60), nullable=True),
        sa.Column("email", sa.String(length=160), nullable=True),
        sa.Column("contact_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="capturado"),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_matricula", sa.String(length=100), nullable=True),
        sa.Column("updated_by_matricula", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["created_by_matricula"], ["usuarios.matricula"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_matricula"], ["usuarios.matricula"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_name", "marketplace_seller_id", name="uq_potential_suppliers_source_seller"),
    )
    op.create_index("ix_potential_suppliers_cnpj", "potential_suppliers", ["cnpj"], unique=False)
    op.create_index("ix_potential_suppliers_display_name", "potential_suppliers", ["display_name"], unique=False)
    op.create_index("ix_potential_suppliers_source_name", "potential_suppliers", ["source_name"], unique=False)
    op.create_index("ix_potential_suppliers_status", "potential_suppliers", ["status"], unique=False)

    op.create_table(
        "item_potential_supplier_quotes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("codigo_item", sa.String(), nullable=False),
        sa.Column("potential_supplier_id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=80), nullable=True),
        sa.Column("offer_title", sa.String(length=255), nullable=True),
        sa.Column("product_url", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="BRL"),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("price_unit", sa.String(length=40), nullable=True),
        sa.Column("unit_price_base", sa.Float(), nullable=True),
        sa.Column("factor_to_base", sa.Float(), nullable=True),
        sa.Column("uf", sa.String(length=2), nullable=True),
        sa.Column("freight_value", sa.Float(), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("quote_status", sa.String(length=30), nullable=False, server_default="capturada"),
        sa.Column("capture_query", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("captured_by_matricula", sa.String(length=100), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["captured_by_matricula"], ["usuarios.matricula"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["codigo_item"], ["itens.codigo_item"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["potential_supplier_id"], ["potential_suppliers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo_item", "product_url", name="uq_item_potential_quote_item_url"),
    )
    op.create_index("ix_item_potential_supplier_quotes_captured_at", "item_potential_supplier_quotes", ["captured_at"], unique=False)
    op.create_index("ix_item_potential_supplier_quotes_codigo_item", "item_potential_supplier_quotes", ["codigo_item"], unique=False)
    op.create_index("ix_item_potential_supplier_quotes_potential_supplier_id", "item_potential_supplier_quotes", ["potential_supplier_id"], unique=False)
    op.create_index("ix_item_potential_supplier_quotes_quote_status", "item_potential_supplier_quotes", ["quote_status"], unique=False)
    op.create_index("ix_item_potential_supplier_quotes_source_name", "item_potential_supplier_quotes", ["source_name"], unique=False)
    op.create_index("ix_item_potential_supplier_quotes_unit_price_base", "item_potential_supplier_quotes", ["unit_price_base"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_item_potential_supplier_quotes_unit_price_base", table_name="item_potential_supplier_quotes")
    op.drop_index("ix_item_potential_supplier_quotes_source_name", table_name="item_potential_supplier_quotes")
    op.drop_index("ix_item_potential_supplier_quotes_quote_status", table_name="item_potential_supplier_quotes")
    op.drop_index("ix_item_potential_supplier_quotes_potential_supplier_id", table_name="item_potential_supplier_quotes")
    op.drop_index("ix_item_potential_supplier_quotes_codigo_item", table_name="item_potential_supplier_quotes")
    op.drop_index("ix_item_potential_supplier_quotes_captured_at", table_name="item_potential_supplier_quotes")
    op.drop_table("item_potential_supplier_quotes")
    op.drop_index("ix_potential_suppliers_status", table_name="potential_suppliers")
    op.drop_index("ix_potential_suppliers_source_name", table_name="potential_suppliers")
    op.drop_index("ix_potential_suppliers_display_name", table_name="potential_suppliers")
    op.drop_index("ix_potential_suppliers_cnpj", table_name="potential_suppliers")
    op.drop_table("potential_suppliers")