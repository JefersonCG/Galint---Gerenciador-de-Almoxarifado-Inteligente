"""Script auxiliar para adicionar colunas `celular` em telegram_users
e `celular_informado` em telegram_conversations caso não existam.

Execute em ambiente onde o banco está configurado:
    python scripts/add_telegram_celular_column.py
"""
from sqlalchemy import text
from galint_flask import create_app


def main() -> int:
    app = create_app()
    with app.app_context():
        engine = app.extensions["sqlalchemy"].db.get_engine(app)

        dialect = engine.dialect.name
        with engine.connect() as conn:
            # Postgres / others support ADD COLUMN IF NOT EXISTS
            if dialect in ("postgresql", "psycopg2"):
                stm_user = "ALTER TABLE telegram_users ADD COLUMN IF NOT EXISTS celular VARCHAR"
                stm_conv = "ALTER TABLE telegram_conversations ADD COLUMN IF NOT EXISTS celular_informado VARCHAR"
            else:
                # Tenta adicionar a coluna e ignora se já existir
                stm_user = "ALTER TABLE telegram_users ADD COLUMN celular VARCHAR"
                stm_conv = "ALTER TABLE telegram_conversations ADD COLUMN celular_informado VARCHAR"

            try:
                conn.execute(text(stm_user))
                print("OK: coluna 'celular' em 'telegram_users' verificada/criada")
            except Exception as e:
                print("Aviso: falha ao criar/verificar coluna 'celular' (ignorado):", e)

            try:
                conn.execute(text(stm_conv))
                print("OK: coluna 'celular_informado' em 'telegram_conversations' verificada/criada")
            except Exception as e:
                print("Aviso: falha ao criar/verificar coluna 'celular_informado' (ignorado):", e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
