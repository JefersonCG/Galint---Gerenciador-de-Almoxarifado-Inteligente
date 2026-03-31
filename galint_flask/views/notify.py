from __future__ import annotations

from datetime import datetime
from functools import wraps
from pathlib import Path

import jwt
from flask import Blueprint, current_app, g, jsonify, request, send_file
from sqlalchemy import or_

from ..extensions import db
from ..models import Item, NotificationRouterConfig, Usuario
from ..services.auth import create_mobile_token, get_mobile_user
from ..services.galint_notify_service import GalintNotifyService
from ..services.notification_router import NotificationRouterService
from ..services.telegram_reports import TelegramReportService
from ..services.telegram_service import TelegramService
from ..services.unit_conversion_engine import UnitConversionError, unit_conversion_engine


blueprint = Blueprint("notify", __name__, url_prefix="/api/notify")


def _serialize_tool_item(item: Item) -> dict[str, object]:
    foto_path = (item.foto_path or "").strip() or None
    foto_url = None
    try:
        foto_url = (request.url_root.rstrip("/") + "/static/" + foto_path.lstrip("/")) if foto_path else None
    except Exception:
        foto_url = None

    return {
        "codigo_item": item.codigo_item,
        "descricao": item.descricao,
        "categoria": item.categoria,
        "unidade": item.unidade,
        "saldo": item.get_saldo_fisico_total(),
        "saldo_display": item.get_saldo_fisico_display(),
        "foto_path": foto_path,
        "foto_url": foto_url,
        "product_units": _resolve_active_units(item),
    }


def _resolve_active_units(item: Item) -> list[dict[str, object]]:
    active_units = [
        {
            "unit_code": unit.unit_code,
            "unit_label": unit.unit_label,
            "is_base": bool(unit.is_base),
        }
        for unit in sorted(item.product_units, key=lambda row: (not bool(row.is_base), (row.unit_code or ""), row.id or 0))
        if unit.active and (unit.unit_code or "").strip()
    ]
    if active_units:
        return active_units
    fallback_unit = ((item.unidade or "").strip() or "un")
    return [{
        "unit_code": fallback_unit,
        "unit_label": fallback_unit,
        "is_base": True,
    }]


def _convert_from_base(item: Item, quantity_base: float, unit_code: str) -> float:
    conversion = unit_conversion_engine.convert_item_to_base(item, 1.0, unit_code)
    factor = float(conversion.quantity_base or 0.0)
    if factor <= 0:
        raise UnitConversionError("Fator de conversão inválido")
    return float(quantity_base) / factor


def notify_login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.split(" ", 1)[1].strip() if auth_header.startswith("Bearer ") else request.args.get("token", "").strip()
        if not token:
            return jsonify({"success": False, "message": "Token ausente"}), 401

        user = None
        try:
            payload = jwt.decode(token, current_app.config.get("SECRET_KEY"), algorithms=["HS256"])
            matricula = (payload or {}).get("matricula")
            if matricula:
                user = Usuario.query.get(matricula)
        except Exception:
            user = None
        if not user:
            user = get_mobile_user(token)
        if not user:
            return jsonify({"success": False, "message": "Token inválido ou expirado"}), 401

        g.mobile_user = user
        return func(*args, **kwargs)

    return wrapper


@blueprint.post("/login")
def login():
    data = request.get_json() or {}
    matricula = str(data.get("matricula", "")).strip()
    senha = str(data.get("senha", "")).strip()
    if not matricula or not senha:
        return jsonify({"success": False, "message": "Matrícula e senha são obrigatórias"}), 400

    user = Usuario.query.get(matricula)
    if not user or not user.check_password(senha):
        return jsonify({"success": False, "message": "Credenciais inválidas"}), 401

    token = create_mobile_token(user)
    return jsonify(
        {
            "success": True,
            "token": token,
            "user": {
                "matricula": user.matricula,
                "nome": user.nome,
                "cargo": user.cargo,
                "setor": user.setor,
                "is_admin": bool(user.is_admin),
            },
        }
    )


@blueprint.post("/push/register")
@notify_login_required
def register_push():
    data = request.get_json() or {}
    device_uuid = str(data.get("device_uuid", "")).strip()
    token = str(data.get("token", "")).strip()
    provider = str(data.get("provider", "expo")).strip().lower() or "expo"
    if not device_uuid or not token:
        return jsonify({"success": False, "message": "device_uuid e token são obrigatórios"}), 400

    entry = GalintNotifyService.register_push_token(
        matricula=g.mobile_user.matricula,
        device_uuid=device_uuid,
        provider=provider,
        token=token,
    )
    return jsonify({"success": True, "id": entry.id, "provider": entry.provider})


@blueprint.get("/inbox")
@notify_login_required
def inbox():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    return jsonify({"success": True, **GalintNotifyService.list_inbox(matricula=g.mobile_user.matricula, page=page, per_page=per_page)})


@blueprint.post("/inbox/<int:message_id>/read")
@notify_login_required
def mark_read(message_id: int):
    recipient = GalintNotifyService.mark_read(matricula=g.mobile_user.matricula, message_id=message_id)
    if recipient is None:
        return jsonify({"success": False, "message": "Notificação não encontrada"}), 404
    return jsonify({"success": True, "message_id": message_id, "status": recipient.status})


@blueprint.get("/reports")
@notify_login_required
def reports():
    return jsonify({"success": True, "reports": GalintNotifyService.list_reports()})


@blueprint.get("/reports/<report_id>/download")
@notify_login_required
def download_report(report_id: str):
    fmt = (request.args.get("format") or "pdf").strip().lower()
    scope = (request.args.get("scope") or "all").strip().lower()
    if report_id == "daily":
        if fmt == "pdf":
            instance_path = Path(current_app.instance_path)
            reports_dir = instance_path / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            target = reports_dir / f"notify_daily_{scope}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
            TelegramService.generate_saidas_dia_pdf(str(target), scope=scope)
            return send_file(target, mimetype="application/pdf", as_attachment=True, download_name=target.name)
        target = TelegramReportService.generate_daily_xlsx(scope=scope)
        return send_file(target, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=Path(target).name)

    if report_id == "monthly":
        year = request.args.get("year", type=int)
        month = request.args.get("month", type=int)
        if not year or not month:
            return jsonify({"success": False, "message": "Ano e mês são obrigatórios"}), 400
        if fmt == "pdf":
            target = TelegramReportService.generate_monthly_pdf_report(year, month, scope=scope)
            return send_file(target, mimetype="application/pdf", as_attachment=True, download_name=Path(target).name)
        target = TelegramReportService.generate_monthly_xlsx_report(year, month, scope=scope)
        return send_file(target, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=Path(target).name)

    return jsonify({"success": False, "message": "Relatório não suportado"}), 404


@blueprint.get("/status")
@notify_login_required
def status():
    if not getattr(g.mobile_user, "is_admin", False):
        return jsonify({"success": False, "message": "Acesso negado"}), 403
    return jsonify({"success": True, "router": NotificationRouterService.status_payload()})


@blueprint.get("/tools/items/search")
@notify_login_required
def search_tool_items():
    query = str(request.args.get("q", "")).strip()
    limit = min(20, max(1, int(request.args.get("limit", 10) or 10)))
    if len(query) < 2:
        return jsonify({"success": True, "items": []})

    like = f"%{query}%"
    items = (
        Item.query.filter(
            or_(
                Item.codigo_item.ilike(like),
                Item.descricao.ilike(like),
                Item.categoria.ilike(like),
            )
        )
        .order_by(Item.descricao.asc(), Item.codigo_item.asc())
        .limit(limit)
        .all()
    )
    return jsonify({"success": True, "items": [_serialize_tool_item(item) for item in items]})


@blueprint.post("/tools/convert")
@notify_login_required
def convert_tool_units():
    data = request.get_json() or {}
    codigo_item = str(data.get("codigo_item", "")).strip()
    from_unit = str(data.get("from_unit", "")).strip()
    raw_quantity = data.get("quantity")

    if not codigo_item:
        return jsonify({"success": False, "message": "codigo_item é obrigatório"}), 400
    if not from_unit:
        return jsonify({"success": False, "message": "from_unit é obrigatório"}), 400
    try:
        quantity = float(raw_quantity)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "quantity inválida"}), 400

    item = Item.query.get(codigo_item)
    if item is None:
        return jsonify({"success": False, "message": "Item não encontrado"}), 404

    try:
        base_conversion = unit_conversion_engine.convert_item_to_base(item, quantity, from_unit)
    except UnitConversionError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    targets = []
    for unit in _resolve_active_units(item):
        unit_code = str(unit.get("unit_code") or "").strip()
        if not unit_code:
            continue
        try:
            converted_value = _convert_from_base(item, float(base_conversion.quantity_base or 0.0), unit_code)
        except UnitConversionError:
            continue
        targets.append(
            {
                "unit_code": unit_code,
                "unit_label": unit.get("unit_label") or unit_code,
                "is_base": bool(unit.get("is_base")),
                "quantity": converted_value,
                "display": f"{converted_value:g} {unit.get('unit_label') or unit_code}".strip(),
            }
        )

    return jsonify(
        {
            "success": True,
            "item": _serialize_tool_item(item),
            "input": {
                "quantity": quantity,
                "from_unit": from_unit,
                "display": f"{quantity:g} {from_unit}",
            },
            "base": {
                "quantity": float(base_conversion.quantity_base or 0.0),
                "unit": base_conversion.unit_base,
                "display": f"{float(base_conversion.quantity_base or 0.0):g} {base_conversion.unit_base}",
            },
            "targets": targets,
            "conversion_path": list(base_conversion.conversion_path or []),
            "factor_applied": float(base_conversion.factor_applied or 1.0),
        }
    )


@blueprint.post("/admin/test")
@notify_login_required
def admin_test():
    if not getattr(g.mobile_user, "is_admin", False):
        return jsonify({"success": False, "message": "Acesso negado"}), 403
    data = request.get_json() or {}
    matricula = str(data.get("matricula", "")).strip()
    title = str(data.get("title", "Teste GalintNotify")).strip() or "Teste GalintNotify"
    body = str(data.get("body", "Mensagem de teste do router de notificações.")).strip() or "Mensagem de teste do router de notificações."
    if not matricula:
        return jsonify({"success": False, "message": "Matrícula obrigatória"}), 400
    result = GalintNotifyService.deliver_message(
        recipient_ids=[matricula],
        title=title,
        body=body,
        category="test",
        message_type="manual_test",
        payload={"kind": "manual_test"},
    )
    return jsonify({"success": bool(result.get("success")), "result": result})
