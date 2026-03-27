"""add movimenta_estoque to entrada_documentos

Revision ID: e8a1f3c4d2b7
Revises: 07f4c54a93e9
Create Date: 2026-03-27 00:00:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "e8a1f3c4d2b7"
down_revision = "07f4c54a93e9"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
DO $$
BEGIN
  ALTER TABLE entrada_documentos
    ADD COLUMN IF NOT EXISTS movimenta_estoque boolean NOT NULL DEFAULT true;

  UPDATE entrada_documentos
     SET movimenta_estoque = COALESCE(movimenta_estoque, true);
END $$;
"""
    )


def downgrade():
    op.execute(
        """
DO $$
BEGIN
  ALTER TABLE entrada_documentos
    DROP COLUMN IF EXISTS movimenta_estoque;
END $$;
"""
    )
