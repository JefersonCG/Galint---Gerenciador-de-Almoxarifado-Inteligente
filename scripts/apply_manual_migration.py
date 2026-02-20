"""Script para aplicar alterações manuais no esquema quando Alembic falhar.

Ele adiciona as colunas `low_stock_enabled`, `low_stock_weekly_count` e
`low_stock_daily_count` na tabela `telegram_config` com valores default seguros.

Uso:
    python scripts/apply_manual_migration.py
"""
import sys
from pathlib import Path

# Garantir que a raiz do projeto está no PYTHONPATH quando o script é executado
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from galint_flask import create_app
from galint_flask.extensions import db
from sqlalchemy import text

app = create_app()

with app.app_context():
    # obter engine a partir da sessão para compatibilidade com Flask-SQLAlchemy
    engine = db.session.get_bind()
    try:
        print("Aplicando alterações manuais no esquema: adicionando colunas...")
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE telegram_config ADD COLUMN IF NOT EXISTS low_stock_enabled boolean NOT NULL DEFAULT false;"
            ))
            conn.execute(text(
                "ALTER TABLE telegram_config ADD COLUMN IF NOT EXISTS low_stock_weekly_count integer NOT NULL DEFAULT 3;"
            ))
            conn.execute(text(
                "ALTER TABLE telegram_config ADD COLUMN IF NOT EXISTS low_stock_daily_count integer NOT NULL DEFAULT 3;"
            ))

        print("Colunas adicionadas (ou já existiam).")
    except Exception as e:
        print("Erro ao aplicar alterações manuais:", e)
