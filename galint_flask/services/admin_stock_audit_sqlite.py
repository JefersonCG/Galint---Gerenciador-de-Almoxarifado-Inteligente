"""Auditoria SQLite para ajustes administrativos de estoque."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import current_app, has_app_context

_LOCK = threading.Lock()
_DB_FILENAME = "admin_stock_adjustments.sqlite"
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
        CREATE TABLE IF NOT EXISTS admin_stock_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_at TEXT NOT NULL,
            action_type TEXT NOT NULL,
            action_result TEXT NOT NULL,
            codigo_item TEXT,
            descricao_item TEXT,
            target_balance REAL,
            reason TEXT,
            user_id TEXT,
            user_name TEXT,
            route TEXT,
            ip_address TEXT,
            user_agent TEXT,
            displayed_balance_before REAL,
            displayed_balance_after REAL,
            legacy_balance_before REAL,
            legacy_balance_after REAL,
            ledger_balance_before REAL,
            ledger_balance_after REAL,
            stock_balance_before REAL,
            stock_balance_after REAL,
            daily_limit INTEGER,
            daily_used INTEGER,
            daily_remaining INTEGER,
            event_id INTEGER,
            movement_id INTEGER,
            operation_log_id INTEGER,
            error_message TEXT,
            details_json TEXT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_stock_adjustments_occurred_at ON admin_stock_adjustments(occurred_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_stock_adjustments_item ON admin_stock_adjustments(codigo_item, occurred_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_stock_adjustments_result ON admin_stock_adjustments(action_type, action_result)"
    )


def log_admin_stock_adjustment(*, action_type: str, action_result: str = "success", details: dict[str, Any] | None = None) -> None:
    """Registra ajustes administrativos em um SQLite local para auditoria."""
    payload = details or {}
    occurred_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    parameters: tuple[Any, ...] = (
        occurred_at,
        str(action_type or "admin_stock_adjustment"),
        str(action_result or "success"),
        payload.get("codigo_item"),
        payload.get("descricao_item"),
        payload.get("target_balance"),
        payload.get("reason"),
        payload.get("user_id"),
        payload.get("user_name"),
        payload.get("route"),
        payload.get("ip_address"),
        payload.get("user_agent"),
        payload.get("displayed_balance_before"),
        payload.get("displayed_balance_after"),
        payload.get("legacy_balance_before"),
        payload.get("legacy_balance_after"),
        payload.get("ledger_balance_before"),
        payload.get("ledger_balance_after"),
        payload.get("stock_balance_before"),
        payload.get("stock_balance_after"),
        payload.get("daily_limit"),
        payload.get("daily_used"),
        payload.get("daily_remaining"),
        payload.get("event_id"),
        payload.get("movement_id"),
        payload.get("operation_log_id"),
        payload.get("error_message"),
        json.dumps(payload, ensure_ascii=False, default=str),
    )

    try:
        with _LOCK:
            db_path = get_audit_db_path()
            with sqlite3.connect(db_path) as connection:
                _ensure_schema(connection)
                connection.execute(
                    """
                    INSERT INTO admin_stock_adjustments (
                        occurred_at,
                        action_type,
                        action_result,
                        codigo_item,
                        descricao_item,
                        target_balance,
                        reason,
                        user_id,
                        user_name,
                        route,
                        ip_address,
                        user_agent,
                        displayed_balance_before,
                        displayed_balance_after,
                        legacy_balance_before,
                        legacy_balance_after,
                        ledger_balance_before,
                        ledger_balance_after,
                        stock_balance_before,
                        stock_balance_after,
                        daily_limit,
                        daily_used,
                        daily_remaining,
                        event_id,
                        movement_id,
                        operation_log_id,
                        error_message,
                        details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    parameters,
                )
                connection.commit()
    except Exception:
        pass