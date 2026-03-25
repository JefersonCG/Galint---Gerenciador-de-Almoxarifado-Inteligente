"""add item pre registration flow

Revision ID: e6b7c8d9f103
Revises: 3c5b8d9e7f10, 4e9c7a1b2d3f, d4a7c8e9f102
Create Date: 2026-03-25
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "e6b7c8d9f103"
down_revision = ("3c5b8d9e7f10", "4e9c7a1b2d3f", "d4a7c8e9f102")
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='pre_cadastro_pendente'
  ) THEN
    ALTER TABLE itens ADD COLUMN pre_cadastro_pendente boolean NOT NULL DEFAULT false;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='pre_cadastro_origem'
  ) THEN
    ALTER TABLE itens ADD COLUMN pre_cadastro_origem varchar(40);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='pre_cadastro_documento_item_id'
  ) THEN
    ALTER TABLE itens ADD COLUMN pre_cadastro_documento_item_id integer NULL REFERENCES entrada_documento_itens(id_documento_item) ON DELETE SET NULL;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='pre_cadastro_criado_em'
  ) THEN
    ALTER TABLE itens ADD COLUMN pre_cadastro_criado_em timestamp NULL;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='itens' AND column_name='pre_cadastro_finalizado_em'
  ) THEN
    ALTER TABLE itens ADD COLUMN pre_cadastro_finalizado_em timestamp NULL;
  END IF;

  CREATE INDEX IF NOT EXISTS ix_itens_pre_cadastro_pendente ON itens(pre_cadastro_pendente);
  CREATE INDEX IF NOT EXISTS ix_itens_pre_cadastro_documento_item_id ON itens(pre_cadastro_documento_item_id);
END $$;
"""
    )


def downgrade():
    op.execute(
        """
DO $$
BEGIN
  DROP INDEX IF EXISTS ix_itens_pre_cadastro_documento_item_id;
  DROP INDEX IF EXISTS ix_itens_pre_cadastro_pendente;

  ALTER TABLE itens
    DROP COLUMN IF EXISTS pre_cadastro_finalizado_em,
    DROP COLUMN IF EXISTS pre_cadastro_criado_em,
    DROP COLUMN IF EXISTS pre_cadastro_documento_item_id,
    DROP COLUMN IF EXISTS pre_cadastro_origem,
    DROP COLUMN IF EXISTS pre_cadastro_pendente;
END $$;
"""
    )