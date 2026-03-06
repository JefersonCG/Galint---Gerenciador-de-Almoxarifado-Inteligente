"""Diagnóstico rápido: mostra pg_stat_activity do banco configurado no GALINT.

Uso:
  python scripts/diag_pg_activity.py

Não imprime a DATABASE_URL completa (evita vazar senha).
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from galint_flask import create_app
from galint_flask.extensions import db


def main() -> None:
    app = create_app()
    with app.app_context():
        db.session.execute(text("select 1"))
        sql = """
        select pid,
               usename,
               application_name,
               client_addr,
               state,
               wait_event_type,
               wait_event,
               now() - query_start as age,
               left(replace(query, E'\n', ' '), 220) as query
        from pg_stat_activity
        where datname = current_database()
        order by query_start desc nulls last
        limit 25
        """
        rows = db.session.execute(text(sql)).fetchall()

    print("pg_stat_activity (top 25):")
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
