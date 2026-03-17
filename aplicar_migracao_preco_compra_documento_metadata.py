"""Aplica migração idempotente para metadados de documento financeiro.

Motivo:
- Alguns ambientes não conseguem rodar o Alembic/Flask-Migrate automaticamente.
- Esta migração cria colunas faltantes usadas pelo modelo `Item` e pelo financeiro.

O script é seguro para reexecução (usa IF NOT EXISTS).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


DDL = """
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


def _resolve_db_url() -> str:
    load_dotenv(override=False)
    db_url = os.environ.get("GALINT_DATABASE_URI") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit(
            "Banco não configurado. Defina GALINT_DATABASE_URI (ou DATABASE_URL) em .env ou no ambiente."
        )
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[len("postgres://") :]
    return db_url


def main() -> None:
    db_url = _resolve_db_url()
    print("Conectando em:", db_url)

    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(DDL))

        has = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema='public'
                  AND table_name='itens'
                  AND column_name='preco_compra_chave_acesso'
                """
            )
        ).scalar()

    print("OK. preco_compra_chave_acesso existe?", bool(has))


if __name__ == "__main__":
    main()
