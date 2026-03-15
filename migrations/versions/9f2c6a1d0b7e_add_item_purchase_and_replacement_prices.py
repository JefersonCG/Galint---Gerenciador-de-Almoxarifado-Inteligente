"""Add item purchase and replacement prices (merge heads)

Revision ID: 9f2c6a1d0b7e
Revises: 07f4c54a93e9, 8b3d1a2c4e10
Create Date: 2026-03-14

Objetivo:
- Adicionar campos financeiros no cadastro de itens para:
  - Preço de compra (investido) por unidade/embalagem
  - Preço de reposição (referência de mercado) por unidade/embalagem
- Guardar metadados (fonte, documento, UF, query e link) para auditoria.
- Este arquivo também faz merge dos dois heads existentes.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "9f2c6a1d0b7e"
down_revision = ("07f4c54a93e9", "8b3d1a2c4e10")
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
DO $$
BEGIN
  -- Preço de compra
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_unitario'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_compra_unitario double precision;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_fonte'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_compra_fonte varchar(50);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_documento'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_compra_documento varchar(120);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_atualizado_em'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_compra_atualizado_em timestamp;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_atualizado_por'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_compra_atualizado_por varchar(100);
  END IF;

  -- Preço de reposição
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_reposicao_unitario'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_reposicao_unitario double precision;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_reposicao_fonte'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_reposicao_fonte varchar(50);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_reposicao_uf'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_reposicao_uf varchar(2);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_reposicao_query'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_reposicao_query text;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_reposicao_url'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_reposicao_url text;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_reposicao_atualizado_em'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_reposicao_atualizado_em timestamp;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_reposicao_atualizado_por'
  ) THEN
    ALTER TABLE itens ADD COLUMN preco_reposicao_atualizado_por varchar(100);
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
    WHERE table_name='itens' AND column_name='preco_reposicao_atualizado_por'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_reposicao_atualizado_por;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_reposicao_atualizado_em'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_reposicao_atualizado_em;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_reposicao_url'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_reposicao_url;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_reposicao_query'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_reposicao_query;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_reposicao_uf'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_reposicao_uf;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_reposicao_fonte'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_reposicao_fonte;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_reposicao_unitario'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_reposicao_unitario;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_atualizado_por'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_compra_atualizado_por;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_atualizado_em'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_compra_atualizado_em;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_documento'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_compra_documento;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_fonte'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_compra_fonte;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='preco_compra_unitario'
  ) THEN
    ALTER TABLE itens DROP COLUMN preco_compra_unitario;
  END IF;
END $$;
"""
    )

