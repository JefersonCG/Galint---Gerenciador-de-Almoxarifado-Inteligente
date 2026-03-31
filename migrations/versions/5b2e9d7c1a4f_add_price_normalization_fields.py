"""Add normalized price and quantity fields.

Revision ID: 5b2e9d7c1a4f
Revises: e6b7c8d9f103
Create Date: 2026-03-31 13:40:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5b2e9d7c1a4f"
down_revision = "e6b7c8d9f103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("itens", sa.Column("preco_compra_unitario_base", sa.Float(), nullable=True))
    op.add_column("itens", sa.Column("preco_compra_unidade_preco", sa.String(length=30), nullable=True))
    op.add_column("itens", sa.Column("preco_compra_fator_base", sa.Float(), nullable=True))
    op.add_column("itens", sa.Column("preco_reposicao_unitario_base", sa.Float(), nullable=True))
    op.add_column("itens", sa.Column("preco_reposicao_unidade_preco", sa.String(length=30), nullable=True))
    op.add_column("itens", sa.Column("preco_reposicao_fator_base", sa.Float(), nullable=True))

    op.add_column("entrada_documento_itens", sa.Column("unidade_quantidade", sa.String(length=30), nullable=True))
    op.add_column("entrada_documento_itens", sa.Column("quantidade_base", sa.Float(), nullable=True))
    op.add_column("entrada_documento_itens", sa.Column("valor_unitario_base", sa.Float(), nullable=True))
    op.add_column("entrada_documento_itens", sa.Column("unidade_preco", sa.String(length=30), nullable=True))
    op.add_column("entrada_documento_itens", sa.Column("fator_preco_base", sa.Float(), nullable=True))

    op.add_column("finance_lancamentos", sa.Column("unidade_quantidade", sa.String(length=30), nullable=True))
    op.add_column("finance_lancamentos", sa.Column("quantidade_base", sa.Float(), nullable=True))
    op.add_column("finance_lancamentos", sa.Column("valor_unitario_base", sa.Float(), nullable=True))
    op.add_column("finance_lancamentos", sa.Column("unidade_preco", sa.String(length=30), nullable=True))
    op.add_column("finance_lancamentos", sa.Column("fator_preco_base", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("finance_lancamentos", "fator_preco_base")
    op.drop_column("finance_lancamentos", "unidade_preco")
    op.drop_column("finance_lancamentos", "valor_unitario_base")
    op.drop_column("finance_lancamentos", "quantidade_base")
    op.drop_column("finance_lancamentos", "unidade_quantidade")

    op.drop_column("entrada_documento_itens", "fator_preco_base")
    op.drop_column("entrada_documento_itens", "unidade_preco")
    op.drop_column("entrada_documento_itens", "valor_unitario_base")
    op.drop_column("entrada_documento_itens", "quantidade_base")
    op.drop_column("entrada_documento_itens", "unidade_quantidade")

    op.drop_column("itens", "preco_reposicao_fator_base")
    op.drop_column("itens", "preco_reposicao_unidade_preco")
    op.drop_column("itens", "preco_reposicao_unitario_base")
    op.drop_column("itens", "preco_compra_fator_base")
    op.drop_column("itens", "preco_compra_unidade_preco")
    op.drop_column("itens", "preco_compra_unitario_base")