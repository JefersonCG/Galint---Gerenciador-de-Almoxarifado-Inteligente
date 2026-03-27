"""Auditoria SQLite para exclusoes de itens de documentos fiscais."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import current_app, has_app_context

_LOCK = threading.Lock()
_DB_FILENAME = "nf_document_item_deletions.sqlite"
_DB_DIRNAME = "audit"


def _base_dir() -> Path:
    if has_app_context():
        return Path(current_app.instance_path)
    return Path(__file__).resolve().parents[2] / "instance"


def get_audit_db_path() -> Path:
    audit_dir = _base_dir() / _DB_DIRNAME
    audit_dir.mkdir(parents=True, exist_ok=True)
    return audit_dir / _DB_FILENAME


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS nf_document_item_deletions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_at TEXT NOT NULL,
            action_type TEXT NOT NULL,
            action_result TEXT NOT NULL,
            document_id INTEGER,
            document_item_id INTEGER,
            numero_documento TEXT,
            codigo_item TEXT,
            status_processamento TEXT,
            reason TEXT,
            user_id TEXT,
            route TEXT,
            ip_address TEXT,
            user_agent TEXT,
            stock_movement_id INTEGER,
            balance_before REAL,
            balance_after REAL,
            details_json TEXT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_nf_document_item_deletions_occurred_at ON nf_document_item_deletions(occurred_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_nf_document_item_deletions_document ON nf_document_item_deletions(document_id, document_item_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_nf_document_item_deletions_action ON nf_document_item_deletions(action_type, action_result)"
    )


def log_document_item_deletion(*, action_type: str, action_result: str = "success", details: dict[str, Any] | None = None) -> None:
    """Registra a exclusao de um item de documento fiscal em um SQLite local."""
    payload = details or {}
    occurred_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    parameters: tuple[Any, ...] = (
        occurred_at,
        str(action_type or "nf.document_item.deletion"),
        str(action_result or "success"),
        payload.get("document_id"),
        payload.get("document_item_id"),
        payload.get("numero_documento"),
        payload.get("codigo_item"),
        payload.get("status_processamento"),
        payload.get("reason"),
        payload.get("user_id"),
        payload.get("route"),
        payload.get("ip_address"),
        payload.get("user_agent"),
        payload.get("stock_movement_id"),
        payload.get("balance_before"),
        payload.get("balance_after"),
        json.dumps(payload, ensure_ascii=False, default=str),
    )

    try:
        with _LOCK:
            db_path = get_audit_db_path()
            with sqlite3.connect(db_path) as connection:
                _ensure_schema(connection)
                connection.execute(
                    """
                    INSERT INTO nf_document_item_deletions (
                        occurred_at,
                        action_type,
                        action_result,
                        document_id,
                        document_item_id,
                        numero_documento,
                        codigo_item,
                        status_processamento,
                        reason,
                        user_id,
                        route,
                        ip_address,
                        user_agent,
                        stock_movement_id,
                        balance_before,
                        balance_after,
                        details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    parameters,
                )
                connection.commit()
    except Exception:
        # Auditoria nunca deve bloquear a operação principal.
        pass
