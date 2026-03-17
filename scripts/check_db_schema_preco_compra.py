from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def main() -> None:
    load_dotenv(override=False)

    db_url = os.environ.get("GALINT_DATABASE_URI") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("Sem GALINT_DATABASE_URI/DATABASE_URL.")

    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[len("postgres://") :]

    print("DB:", db_url)

    engine = create_engine(db_url)
    with engine.connect() as conn:
        try:
            alembic = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            print("Alembic version:", alembic)
        except Exception as exc:
            print("Alembic version: (falha ao ler)", exc)

        tables = [
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema='public'
                    ORDER BY table_name
                    """
                )
            )
        ]
        print("Tables:", tables)

        for table_name in ("itens", "items"):
            rows = conn.execute(
                text(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=:t
                    ORDER BY ordinal_position
                    """
                ),
                {"t": table_name},
            ).fetchall()
            if not rows:
                continue

            columns = [r[0] for r in rows]
            print(f"\n{table_name}: {len(columns)} colunas")
            print("tem preco_compra_chave_acesso?", "preco_compra_chave_acesso" in columns)
            for col, dtype in rows:
                if col.startswith("preco_") or col in ("codigo_item", "descricao"):
                    print(" ", col, dtype)


if __name__ == "__main__":
    main()
