"""Script para ajustar colunas booleanas em entradas_registro_30_dias."""
import os
import sys

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Desabilitar serviços em background
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

from galint_flask import create_app
from galint_flask.extensions import db


def alter_columns_to_boolean():
    app = create_app()

    with app.app_context():
        dialect = db.engine.dialect.name
        print(f"🔧 Dialeto do banco: {dialect}")

        if dialect != "postgresql":
            print("ℹ️  Nenhuma alteração aplicada (apenas PostgreSQL).")
            return True

        sql = """
        ALTER TABLE entradas_registro_30_dias
            ALTER COLUMN pdf_gerado DROP DEFAULT,
            ALTER COLUMN pdf_gerado TYPE BOOLEAN USING (pdf_gerado::int = 1),
            ALTER COLUMN pdf_gerado SET DEFAULT FALSE,
            ALTER COLUMN ativo DROP DEFAULT,
            ALTER COLUMN ativo TYPE BOOLEAN USING (ativo::int = 1),
            ALTER COLUMN ativo SET DEFAULT TRUE;
        """

        try:
            db.session.execute(db.text(sql))
            db.session.commit()
            print("✅ Colunas ajustadas para BOOLEAN com sucesso!")
            return True
        except Exception as exc:
            db.session.rollback()
            print(f"❌ Erro ao alterar colunas: {exc}")
            return False


if __name__ == "__main__":
    ok = alter_columns_to_boolean()
    sys.exit(0 if ok else 1)
