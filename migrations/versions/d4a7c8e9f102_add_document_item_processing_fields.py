"""add document item processing fields

Revision ID: d4a7c8e9f102
Revises: c3f9a6e1b2d4
Create Date: 2026-03-24
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "d4a7c8e9f102"
down_revision = "c3f9a6e1b2d4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
DO $$
BEGIN
  ALTER TABLE entrada_documento_itens
    ADD COLUMN IF NOT EXISTS status_processamento varchar(30) NOT NULL DEFAULT 'pendente',
    ADD COLUMN IF NOT EXISTS processado_em timestamp NULL,
    ADD COLUMN IF NOT EXISTS erro_processamento text NULL,
    ADD COLUMN IF NOT EXISTS stock_movement_id integer NULL REFERENCES stock_movements(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS operation_log_id integer NULL REFERENCES operation_logs(id) ON DELETE SET NULL;

  CREATE INDEX IF NOT EXISTS ix_entrada_documento_itens_status_processamento
    ON entrada_documento_itens(status_processamento);
  CREATE INDEX IF NOT EXISTS ix_entrada_documento_itens_stock_movement_id
    ON entrada_documento_itens(stock_movement_id);
  CREATE INDEX IF NOT EXISTS ix_entrada_documento_itens_operation_log_id
    ON entrada_documento_itens(operation_log_id);

  UPDATE entrada_documento_itens
     SET status_processamento = 'processado',
         processado_em = COALESCE(processado_em, criado_em, now()),
         erro_processamento = NULL
   WHERE entrada_id IS NOT NULL;
END $$;
"""
    )


def downgrade():
    op.execute(
        """
DO $$
BEGIN
  DROP INDEX IF EXISTS ix_entrada_documento_itens_operation_log_id;
  DROP INDEX IF EXISTS ix_entrada_documento_itens_stock_movement_id;
  DROP INDEX IF EXISTS ix_entrada_documento_itens_status_processamento;

  ALTER TABLE entrada_documento_itens
    DROP COLUMN IF EXISTS operation_log_id,
    DROP COLUMN IF EXISTS stock_movement_id,
    DROP COLUMN IF EXISTS erro_processamento,
    DROP COLUMN IF EXISTS processado_em,
    DROP COLUMN IF EXISTS status_processamento;
END $$;
"""
    )