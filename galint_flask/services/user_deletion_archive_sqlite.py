"""Arquivo morto SQLite para exclusao de colaboradores."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import current_app, has_app_context

_LOCK = threading.Lock()
_DB_FILENAME = "deleted_users_archive.sqlite"
_DB_DIRNAME = "audit"


def _base_dir() -> Path:
    if has_app_context():
        return Path(current_app.instance_path)
    return Path(__file__).resolve().parents[2] / "instance"


def get_archive_db_path() -> Path:
    archive_dir = _base_dir() / _DB_DIRNAME
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir / _DB_FILENAME


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS deleted_user_archives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_at TEXT NOT NULL,
            action_type TEXT NOT NULL,
            matricula TEXT NOT NULL,
            nome TEXT,
            deleted_by TEXT,
            deleted_by_name TEXT,
            total_records INTEGER NOT NULL DEFAULT 0,
            counts_json TEXT,
            payload_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_deleted_user_archives_occurred_at ON deleted_user_archives(occurred_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_deleted_user_archives_matricula ON deleted_user_archives(matricula, occurred_at DESC)"
    )


def archive_deleted_user_snapshot(*, details: dict[str, Any]) -> Path:
    """Persiste em SQLite o snapshot completo do colaborador antes da exclusao."""
    payload = details or {}
    counts = payload.get("counts") or {}
    total_records = sum(int(value or 0) for value in counts.values())
    parameters: tuple[Any, ...] = (
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "user_deletion_archive",
        str(payload.get("user", {}).get("matricula") or ""),
        str(payload.get("user", {}).get("nome") or ""),
        payload.get("deleted_by", {}).get("matricula"),
        payload.get("deleted_by", {}).get("nome"),
        total_records,
        json.dumps(counts, ensure_ascii=False, default=str),
        json.dumps(payload, ensure_ascii=False, default=str),
    )

    with _LOCK:
        db_path = get_archive_db_path()
        with sqlite3.connect(db_path) as connection:
            _ensure_schema(connection)
            connection.execute(
                """
                INSERT INTO deleted_user_archives (
                    occurred_at,
                    action_type,
                    matricula,
                    nome,
                    deleted_by,
                    deleted_by_name,
                    total_records,
                    counts_json,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                parameters,
            )
            connection.commit()
        return db_path