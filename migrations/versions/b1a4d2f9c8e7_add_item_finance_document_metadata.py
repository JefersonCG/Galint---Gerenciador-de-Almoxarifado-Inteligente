"""Add item and finance ledger document metadata

Revision ID: b1a4d2f9c8e7
Revises: c3f9a6e1b2d4
Create Date: 2026-03-16
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "b1a4d2f9c8e7"
down_revision = "c3f9a6e1b2d4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_chave_acesso'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_compra_chave_acesso varchar(64);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_data_emissao'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_compra_data_emissao date;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_data_recebimento'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_compra_data_recebimento date;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='finance_lancamentos' AND column_name='chave_acesso'
  ) THEN
    ALTER TABLE finance_lancamentos ADD COLUMN chave_acesso varchar(64);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='finance_lancamentos' AND column_name='data_emissao_documento'
  ) THEN
    ALTER TABLE finance_lancamentos ADD COLUMN data_emissao_documento date;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='finance_lancamentos' AND column_name='data_recebimento_documento'
  ) THEN
    ALTER TABLE finance_lancamentos ADD COLUMN data_recebimento_documento date;
  END IF;
END $$;
"""
    )


def downgrade():
    op.execute(
        """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='finance_lancamentos' AND column_name='data_recebimento_documento'
  ) THEN
    ALTER TABLE finance_lancamentos DROP COLUMN data_recebimento_documento;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='finance_lancamentos' AND column_name='data_emissao_documento'
  ) THEN
    ALTER TABLE finance_lancamentos DROP COLUMN data_emissao_documento;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='finance_lancamentos' AND column_name='chave_acesso'
  ) THEN
    ALTER TABLE finance_lancamentos DROP COLUMN chave_acesso;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_data_recebimento'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_compra_data_recebimento;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_data_emissao'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_compra_data_emissao;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_chave_acesso'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_compra_chave_acesso;
  END IF;
END $$;
"""
    )