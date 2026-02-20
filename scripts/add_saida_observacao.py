"""Small helper to add the `observacao` column to the `saidas` table.

Run with the project environment active, e.g.:

    python scripts/add_saida_observacao.py

It will open the Flask app context and execute an ``ALTER TABLE`` if needed.
"""
from pathlib import Path
import sys

from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from galint_flask import create_app

SQL = """
ALTER TABLE saidas ADD COLUMN IF NOT EXISTS observacao TEXT;
"""


def main() -> None:
    app = create_app()
    with app.app_context():
        from galint_flask.extensions import db

        try:
            db.session.execute(text(SQL))
            db.session.commit()
            print(
                "Migration: coluna 'observacao' adicionada à tabela 'saidas' (ou já existia)."
            )
        except Exception as exc:
            db.session.rollback()
            print("Erro ao aplicar migração:", exc)
            raise


if __name__ == "__main__":
    main()
