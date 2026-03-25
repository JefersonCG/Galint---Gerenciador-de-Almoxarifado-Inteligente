from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..extensions import db
from ..models import OperationLog


class OperationLogService:
    @staticmethod
    def normalize_operation_type(operation_type: str | None, *, quantity_base: float | None = None) -> str:
        raw = (operation_type or "").strip().lower()
        if raw in {"entrada", "saida", "devolucao", "erro"}:
            return raw
        if raw == "ajuste":
            return "entrada" if float(quantity_base or 0.0) >= 0 else "saida"
        return "erro"

    @staticmethod
    def create_success_log(
        *,
        operation_type: str,
        product_id: str | None,
        quantity_input: float | None,
        quantity_base: float | None,
        unit_input: str | None,
        user_id: str | None,
        source: str | None,
        payload_json: dict[str, Any] | None,
        created_at: datetime | None = None,
        commit: bool = False,
    ) -> OperationLog:
        log = OperationLog(
            operation_type=OperationLogService.normalize_operation_type(operation_type, quantity_base=quantity_base),
            product_id=(product_id or "").strip() or None,
            quantity_input=quantity_input,
            quantity_base=quantity_base,
            unit_input=(unit_input or "").strip() or None,
            user_id=(user_id or "").strip() or None,
            source=(source or "").strip() or None,
            status="success",
            payload_json=payload_json or {},
            created_at=created_at or datetime.utcnow(),
        )
        db.session.add(log)
        db.session.flush()
        if commit:
            db.session.commit()
        return log

    @staticmethod
    def create_error_log(
        *,
        requested_operation_type: str | None,
        product_id: str | None,
        quantity_input: float | None,
        unit_input: str | None,
        user_id: str | None,
        source: str | None,
        payload_json: dict[str, Any] | None,
        error_message: str,
        commit: bool = True,
    ) -> OperationLog:
        log = OperationLog(
            operation_type="erro",
            product_id=(product_id or "").strip() or None,
            quantity_input=quantity_input,
            quantity_base=None,
            unit_input=(unit_input or "").strip() or None,
            user_id=(user_id or "").strip() or None,
            source=(source or "").strip() or None,
            status="error",
            error_message=(error_message or "Erro operacional")[:4000],
            payload_json={
                "requested_operation_type": (requested_operation_type or "").strip().lower() or None,
                **(payload_json or {}),
            },
            created_at=datetime.utcnow(),
        )
        db.session.add(log)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return log

    @staticmethod
    def attach_audit_metadata(operation_log_id: int | None, audit_payload: dict[str, Any]) -> None:
        if not operation_log_id:
            return
        log = db.session.get(OperationLog, operation_log_id)
        if log is None:
            return
        current_payload = dict(log.payload_json or {})
        current_payload.update(audit_payload or {})
        log.payload_json = current_payload
        db.session.commit()

    @staticmethod
    def mark_telegram_result(operation_log_id: int | None, result: dict[str, Any] | None) -> None:
        if not operation_log_id:
            return
        log = db.session.get(OperationLog, operation_log_id)
        if log is None:
            return
        payload = dict(log.payload_json or {})
        payload["telegram_result"] = result or {}
        if result and result.get("success"):
            log.status = "telegram_ok"
        else:
            log.status = "telegram_fail"
            if result and result.get("error"):
                log.error_message = str(result.get("error"))[:4000]
        log.payload_json = payload
        db.session.commit()

    @staticmethod
    def notify_telegram(operation_log_id: int | None) -> dict[str, Any]:
        if not operation_log_id:
            return {"success": False, "error": "OperationLog não informado."}
        from .telegram_service import TelegramService

        result = TelegramService.notify_operation_log(operation_log_id)
        OperationLogService.mark_telegram_result(operation_log_id, result)
        return result

    @staticmethod
    def payload_preview(payload: dict[str, Any] | None, *, limit: int = 180) -> str:
        if not payload:
            return "—"
        compact = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), default=str)
        if len(compact) <= limit:
            return compact
        return f"{compact[: limit - 3]}..."


operation_log_service = OperationLogService()