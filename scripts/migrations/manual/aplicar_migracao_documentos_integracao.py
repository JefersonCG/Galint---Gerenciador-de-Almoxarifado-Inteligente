"""Aplica migração idempotente para metadados de integração dos documentos fiscais.

Motivo:
- Permite deixar a NF visível e bloqueada no sistema antes da API/certificado digital.
- Alguns ambientes não executam o Alembic automático de forma confiável.

O script é seguro para reexecução e foca na tabela `entrada_documentos`.
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
    WHERE table_name='entrada_documentos' AND column_name='chave_acesso'
  ) THEN
    ALTER TABLE entrada_documentos ADD COLUMN chave_acesso varchar(64);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='entrada_documentos' AND column_name='status_integracao'
  ) THEN
    ALTER TABLE entrada_documentos ADD COLUMN status_integracao varchar(40) NOT NULL DEFAULT 'manual';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='entrada_documentos' AND column_name='mensagem_integracao'
  ) THEN
    ALTER TABLE entrada_documentos ADD COLUMN mensagem_integracao text;
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

        has_status = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema='public'
                  AND table_name='entrada_documentos'
                  AND column_name='status_integracao'
                """
            )
        ).scalar()

    print("OK. status_integracao existe?", bool(has_status))


if __name__ == "__main__":
    main()
