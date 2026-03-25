from __future__ import annotations

from collections import defaultdict
import json

from flask import Blueprint, abort, render_template, request
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from ..models import OperationLog
from ..services.operation_log_service import operation_log_service


blueprint = Blueprint("operations", __name__, url_prefix="/estoque")


def _is_admin(user) -> bool:
    if not user:
        return False
    value = getattr(user, "is_admin", False)
    if isinstance(value, str):
        return value.strip() in {"1", "true", "True", "TRUE"}
    return bool(value)


def _is_supervisor(user) -> bool:
    if not user:
        return False
    setor = (getattr(user, "setor", "") or "").strip().lower()
    cargo = (getattr(user, "cargo", "") or "").strip().lower()
    return "supervisor" in setor or "supervisor" in cargo


def _require_admin_or_supervisor() -> None:
    if not (_is_admin(current_user) or _is_supervisor(current_user)):
        abort(403)


def _format_quantity(value: float | None, unit: str | None = None) -> str:
    if value is None:
        return "—"
    formatted = f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if formatted.endswith(",00"):
        formatted = formatted[:-3]
    suffix = (unit or "").strip()
    return f"{formatted} {suffix}".strip()


@blueprint.get("/central-operacoes")
@login_required
def central_operations():
    _require_admin_or_supervisor()
    try:
        limit = max(50, min(int(request.args.get("limit", 200)), 1000))
    except (TypeError, ValueError):
        limit = 200

    logs = (
        OperationLog.query
        .options(joinedload(OperationLog.item), joinedload(OperationLog.user))
        .order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
        .limit(limit)
        .all()
    )

    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    counts = {"entrada": 0, "saida": 0, "devolucao": 0, "erro": 0}
    status_badges = {
        "success": "bg-secondary",
        "telegram_ok": "bg-success",
        "telegram_fail": "bg-warning text-dark",
        "error": "bg-danger",
    }

    for log in logs:
        payload = dict(log.payload_json or {})
        operation_key = log.operation_type if log.operation_type in {"entrada", "saida", "devolucao", "erro"} else "erro"
        counts[operation_key] = counts.get(operation_key, 0) + 1
        groups[operation_key].append(
            {
                "id": log.id,
                "product_label": log.item.descricao if log.item else (log.product_id or "—"),
                "product_code": log.product_id or "—",
                "quantity_input": _format_quantity(log.quantity_input, log.unit_input),
                "quantity_base": _format_quantity(log.quantity_base, payload.get("unit_base") if isinstance(payload, dict) else None),
                "user_label": log.user.nome if log.user else (log.user_id or "Sistema"),
                "source": (log.source or "web").strip().lower() or "web",
                "status": log.status,
                "status_badge": status_badges.get(log.status, "bg-secondary"),
                "created_at": log.created_at,
                "error_message": log.error_message or "—",
                "payload_preview": operation_log_service.payload_preview(payload),
                "payload_pretty": json.dumps(payload, ensure_ascii=True, indent=2, default=str) if payload else "{}",
            }
        )

    return render_template(
        "inventory/central_operations.html",
        logs_by_tab=groups,
        counts=counts,
        limit=limit,
    )