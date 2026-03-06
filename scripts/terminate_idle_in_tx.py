"""Encerra sessões 'idle in transaction' no banco atual.

Útil quando uma sessão esquecida segura locks e impede restore/migrations.

Uso:
  python scripts/terminate_idle_in_tx.py

Observação: precisa de permissão para pg_terminate_backend.
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
        rows = db.session.execute(
            text(
                """
                select pid,
                       usename,
                       application_name,
                       client_addr,
                       now() - xact_start as age,
                       left(replace(query, E'\n', ' '), 200) as query
                from pg_stat_activity
                where datname = current_database()
                  and state = 'idle in transaction'
                  and pid <> pg_backend_pid()
                order by xact_start asc nulls last
                """
            )
        ).fetchall()

        if not rows:
            print("Nenhuma sessão 'idle in transaction' encontrada.")
            return

        print("Sessões idle in transaction encontradas:")
        for r in rows:
            print(r)

        pids = [r[0] for r in rows]
        print("\nTentando encerrar pids:", pids)

        results = db.session.execute(
            text(
                """
                select pid, pg_terminate_backend(pid) as terminated
                from pg_stat_activity
                where datname = current_database()
                  and state = 'idle in transaction'
                  and pid <> pg_backend_pid()
                """
            )
        ).fetchall()

    print("Resultados:")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
