"""Valida um backup PostgreSQL restaurando-o em um banco temporário isolado.

Uso:
  python scripts/validate_backup_restore.py [--backup-name NOME]

Comportamento:
- escolhe o backup SQL mais recente por padrão
- cria um banco temporário no mesmo servidor PostgreSQL
- restaura o backup nesse banco temporário
- executa uma checagem simples de conectividade/tabelas
- remove o banco temporário ao final

Esse utilitário é para homologação técnica, não para produção.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from galint_flask import create_app
from galint_flask.services.backup import BackupService


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _latest_sql_backup(service: BackupService) -> str:
    backups = service.list_backups()
    for backup in backups:
        if backup.get("kind") == BackupService.DATABASE_BACKUP_KIND and str(backup.get("name") or "").endswith(".sql"):
            return str(backup["name"])
    raise ValueError("Nenhum backup SQL encontrado para homologação.")


def _maintenance_uri(original_uri: str, maintenance_db: str) -> str:
    url = make_url(original_uri)
    return url.set(database=maintenance_db).render_as_string(hide_password=False)


def _base_database_name(original_uri: str) -> str:
    url = make_url(original_uri)
    if not url.database:
        raise ValueError("URI PostgreSQL sem nome de banco.")
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", url.database).strip("_") or "galint"
    return base[:48]


def main() -> int:
    parser = argparse.ArgumentParser(description="Homologa backup restaurando em banco temporário.")
    parser.add_argument("--backup-name", help="Nome do backup SQL a validar. Se omitido, usa o mais recente.")
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Mantém o banco temporário ao final para inspeção manual.",
    )
    args = parser.parse_args()

    os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

    app = create_app()
    with app.app_context():
        service = BackupService(app)
        backup_name = args.backup_name or _latest_sql_backup(service)
        backup_path = service._safe_backup_path(backup_name)
        if not backup_path.exists():
            raise ValueError(f"Backup não encontrado: {backup_name}")

        original_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        url = make_url(original_uri)
        maintenance_db = (os.environ.get("GALINT_RESTORE_MAINTENANCE_DB") or "postgres").strip() or "postgres"
        temp_db_name = f"{_base_database_name(original_uri)}_restore_test_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        maintenance_uri = _maintenance_uri(original_uri, maintenance_db)
        maintenance_engine = create_engine(maintenance_uri, future=True)

        print(f"Backup selecionado: {backup_name}")
        print(f"Banco temporário: {temp_db_name}")

        try:
            with maintenance_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS {_quote_identifier(temp_db_name)}'))
                conn.execute(text(f'CREATE DATABASE {_quote_identifier(temp_db_name)} TEMPLATE template0'))

            temp_uri = url.set(database=temp_db_name).render_as_string(hide_password=False)
            app.config["SQLALCHEMY_DATABASE_URI"] = temp_uri
            temp_service = BackupService(app)
            temp_service.restore_backup_with_progress(backup_name, capture_delta=False)

            temp_engine = create_engine(temp_uri, future=True)
            try:
                with temp_engine.connect() as conn:
                    table_count = conn.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM information_schema.tables
                            WHERE table_schema = 'public'
                            """
                        )
                    ).scalar_one()
                    conn.execute(text("SELECT 1"))
                print(f"Restore homologado com sucesso. Tabelas em public: {table_count}")
            finally:
                temp_engine.dispose()

            print("Homologação concluída com sucesso.")
            return 0
        finally:
            app.config["SQLALCHEMY_DATABASE_URI"] = original_uri
            try:
                with maintenance_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                    if not args.keep_db:
                        conn.execute(text(f'DROP DATABASE IF EXISTS {_quote_identifier(temp_db_name)}'))
                        print("Banco temporário removido.")
                    else:
                        print("Banco temporário preservado por solicitação.")
            finally:
                maintenance_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())