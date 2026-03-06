"""Guard immutable fields and movement quantities

Revision ID: 8b3d1a2c4e10
Revises: 616036e9b6f8
Create Date: 2026-02-21

Objetivo:
- Saldo é derivado por movimentações (entradas/saidas/inventario_eventos).
- Blindar campos estruturais imutáveis no PostgreSQL.
- Manter compatibilidade com instalações antigas que possam ter coluna legada `itens.quantidade`.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "8b3d1a2c4e10"
down_revision = "616036e9b6f8"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Se existir coluna legada `itens.quantidade`, sincroniza uma vez com o saldo derivado.
    #    Isso evita discrepâncias históricas sem depender desse campo como fonte de verdade.
    op.execute(
        """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'itens'
      AND column_name = 'quantidade'
  ) THEN
    WITH
      e AS (
        SELECT codigo_item, COALESCE(SUM(quantidade), 0) AS total_entrada
        FROM entradas
        WHERE codigo_item IS NOT NULL
        GROUP BY codigo_item
      ),
      s AS (
        SELECT codigo_item, COALESCE(SUM(quantidade), 0) AS total_saida
        FROM saidas
        WHERE codigo_item IS NOT NULL
        GROUP BY codigo_item
      ),
      a AS (
        SELECT codigo_item, COALESCE(SUM(quantidade), 0) AS total_ajuste
        FROM inventario_eventos
        WHERE codigo_item IS NOT NULL
        GROUP BY codigo_item
      ),
      saldo AS (
        SELECT
          i.codigo_item,
          (COALESCE(e.total_entrada, 0) - COALESCE(s.total_saida, 0) + COALESCE(a.total_ajuste, 0))::double precision AS saldo
        FROM itens i
        LEFT JOIN e ON e.codigo_item = i.codigo_item
        LEFT JOIN s ON s.codigo_item = i.codigo_item
        LEFT JOIN a ON a.codigo_item = i.codigo_item
      )
    UPDATE itens i
    SET quantidade = saldo.saldo
    FROM saldo
    WHERE i.codigo_item = saldo.codigo_item
      AND i.quantidade IS DISTINCT FROM saldo.saldo;
  END IF;
END $$;
"""
    )

    # 2) Triggers para blindar campos imutáveis.
    op.execute(
        """
CREATE OR REPLACE FUNCTION galint_guard_itens_struct_fields()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  old_lote text;
  new_lote text;
BEGIN
  IF NEW.codigo_item IS DISTINCT FROM OLD.codigo_item THEN
    RAISE EXCEPTION 'Não é permitido alterar codigo_item após criação.';
  END IF;

  old_lote := NULLIF(BTRIM(COALESCE(OLD.lote, '')), '');
  new_lote := NULLIF(BTRIM(COALESCE(NEW.lote, '')), '');
  IF old_lote IS NOT NULL AND new_lote IS DISTINCT FROM old_lote THEN
    RAISE EXCEPTION 'Não é permitido alterar lote após definido.';
  END IF;

  IF OLD.data_validade IS NOT NULL AND NEW.data_validade IS DISTINCT FROM OLD.data_validade THEN
    RAISE EXCEPTION 'Não é permitido alterar data_validade após definida.';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_galint_guard_itens_struct_fields ON itens;
CREATE TRIGGER trg_galint_guard_itens_struct_fields
BEFORE UPDATE ON itens
FOR EACH ROW
EXECUTE FUNCTION galint_guard_itens_struct_fields();
"""
    )

    op.execute(
        """
CREATE OR REPLACE FUNCTION galint_guard_movement_quantidade_immutable()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.quantidade IS DISTINCT FROM OLD.quantidade THEN
    RAISE EXCEPTION 'Não é permitido alterar quantidade após criação. Registre um ajuste/estorno.';
  END IF;
  RETURN NEW;
END;
$$;
"""
    )

    for table_name in ("entradas", "saidas", "inventario_eventos"):
        op.execute(
            f"""
DROP TRIGGER IF EXISTS trg_galint_guard_{table_name}_quantidade ON {table_name};
CREATE TRIGGER trg_galint_guard_{table_name}_quantidade
BEFORE UPDATE ON {table_name}
FOR EACH ROW
EXECUTE FUNCTION galint_guard_movement_quantidade_immutable();
"""
        )


def downgrade():
    # Remover triggers (não apagar dados)
    for table_name in ("entradas", "saidas", "inventario_eventos"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_galint_guard_{table_name}_quantidade ON {table_name};")

    op.execute("DROP TRIGGER IF EXISTS trg_galint_guard_itens_struct_fields ON itens;")

    # Remover funções
    op.execute("DROP FUNCTION IF EXISTS galint_guard_movement_quantidade_immutable();")
    op.execute("DROP FUNCTION IF EXISTS galint_guard_itens_struct_fields();")
