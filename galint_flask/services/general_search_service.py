from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from flask import current_app, has_request_context, url_for
from sqlalchemy import func, or_

from ..extensions import db
from ..models import InventarioEvento, Item, Saida, Usuario
from ..utils.time_service import TimeService


def _format_code(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "N/D"
    return text[-4:] if len(text) >= 4 else text


def _photo_url(photo_path: str | None) -> str | None:
    normalized = str(photo_path or "").strip()
    if not normalized:
        return None
    return _safe_url_for("static", filename=normalized)


def _safe_url_for(endpoint: str, **values: Any) -> str:
    if has_request_context():
        return url_for(endpoint, **values)
    with current_app.test_request_context("/"):
        return url_for(endpoint, **values)


def _is_tool_category(category: object) -> bool:
    return "ferrament" in str(category or "").strip().lower()


def _safe_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class GeneralSearchService:
    def search_employees(self, query: str, *, limit: int = 12) -> list[dict[str, Any]]:
        search_term = str(query or "").strip()
        if not search_term:
            return []

        users = (
            Usuario.query.filter(
                or_(
                    Usuario.nome.ilike(f"%{search_term}%"),
                    Usuario.matricula.ilike(f"%{search_term}%"),
                )
            )
            .order_by(Usuario.nome.asc(), Usuario.matricula.asc())
            .limit(max(int(limit or 0), 1))
            .all()
        )

        results: list[dict[str, Any]] = []
        for user in users:
            role_label = str(user.setor or user.cargo or "N/D").strip() or "N/D"
            results.append(
                {
                    "entity_type": "funcionario",
                    "id": user.matricula,
                    "matricula": user.matricula,
                    "title": user.nome,
                    "subtitle": f"Matricula {user.matricula} • {role_label}",
                    "badge": role_label,
                }
            )
        return results

    def search_items(self, query: str, *, limit: int = 12) -> list[dict[str, Any]]:
        search_term = str(query or "").strip()
        if not search_term:
            return []

        items = (
            Item.query.filter(
                or_(
                    Item.descricao.ilike(f"%{search_term}%"),
                    Item.codigo_item.ilike(f"%{search_term}%"),
                )
            )
            .order_by(func.lower(Item.descricao).asc(), Item.codigo_item.asc())
            .limit(max(int(limit or 0), 1))
            .all()
        )

        results: list[dict[str, Any]] = []
        for item in items:
            category = str(item.categoria or "Sem categoria").strip() or "Sem categoria"
            brand = str(item.marca or "").strip()
            subtitle = f"Codigo {_format_code(item.codigo_item)} • {category}"
            if brand:
                subtitle += f" • {brand}"
            results.append(
                {
                    "entity_type": "item",
                    "id": item.codigo_item,
                    "codigo_item": item.codigo_item,
                    "title": item.descricao,
                    "subtitle": subtitle,
                    "badge": category,
                    "photo_url": _photo_url(item.foto_path),
                }
            )
        return results

    def build_employee_payload(self, matricula: str) -> dict[str, Any]:
        employee_id = str(matricula or "").strip()
        if not employee_id:
            raise ValueError("Funcionario nao informado")

        employee = Usuario.query.filter_by(matricula=employee_id).first()
        if employee is None:
            raise ValueError("Funcionario nao encontrado")

        withdrawals = (
            db.session.query(
                Saida.id_saida,
                Saida.quantidade,
                Saida.data_saida,
                Saida.observacao,
                Saida.local_servico,
                Saida.codigo_item,
                Item.descricao.label("item_descricao"),
                Item.categoria.label("item_categoria"),
                Item.marca.label("item_marca"),
            )
            .join(Item, Saida.codigo_item == Item.codigo_item, isouter=True)
            .filter(Saida.matricula == employee_id)
            .order_by(Saida.data_saida.desc(), Saida.id_saida.desc())
            .all()
        )

        returns = (
            db.session.query(
                InventarioEvento.id_evento,
                InventarioEvento.quantidade,
                InventarioEvento.data_evento,
                InventarioEvento.descricao,
                InventarioEvento.codigo_item,
                InventarioEvento.tipo,
                Item.descricao.label("item_descricao"),
                Item.categoria.label("item_categoria"),
                Item.marca.label("item_marca"),
            )
            .join(Item, InventarioEvento.codigo_item == Item.codigo_item, isouter=True)
            .filter(InventarioEvento.matricula == employee_id)
            .filter(InventarioEvento.tipo.in_(["devolucao_ferramenta", "devolucao_material", "devolucao"]))
            .order_by(InventarioEvento.data_evento.desc(), InventarioEvento.id_evento.desc())
            .all()
        )

        return_dates_by_item: dict[str, list[datetime]] = defaultdict(list)
        timeline: list[dict[str, Any]] = []
        for row in returns:
            item_code = str(row.codigo_item or "").strip()
            if item_code and row.data_evento:
                return_dates_by_item[item_code].append(row.data_evento)
            timeline.append(
                {
                    "entry_id": f"return-{row.id_evento}",
                    "type_label": "Devolucao",
                    "type_kind": "return",
                    "date_label": TimeService.format_local(row.data_evento, "%d/%m/%Y"),
                    "time_label": TimeService.format_local(row.data_evento, "%H:%M"),
                    "item_description": row.item_descricao or "Item removido",
                    "item_code": _format_code(row.codigo_item),
                    "quantity": _safe_float(row.quantidade),
                    "context": str(row.descricao or "").strip() or "Retorno registrado no estoque",
                    "period_label": TimeService.get_business_day_tag(row.data_evento) or "Expediente",
                    "sort_value": row.data_evento,
                }
            )

        materials: list[dict[str, Any]] = []
        tools: list[dict[str, Any]] = []
        total_withdrawn_quantity = 0.0
        for row in withdrawals:
            category = row.item_categoria or ""
            is_tool = _is_tool_category(category)
            local_info = str(row.local_servico or "").strip() or "Sem local informado"
            observation = str(row.observacao or "").strip()
            if observation:
                local_info = f"{local_info} | {observation}"

            status_kind = "resolved"
            status_label = "Devolvido ao estoque"
            if is_tool:
                matching_return = any(returned_at >= row.data_saida for returned_at in return_dates_by_item.get(str(row.codigo_item or "").strip(), []))
                if not matching_return:
                    status_kind = "pending"
                    status_label = "Pendencia de devolucao"

            payload = {
                "entry_id": f"withdraw-{row.id_saida}",
                "date_label": TimeService.format_local(row.data_saida, "%d/%m/%Y"),
                "time_label": TimeService.format_local(row.data_saida, "%H:%M"),
                "item_description": row.item_descricao or "Item removido",
                "item_code": _format_code(row.codigo_item),
                "quantity": _safe_float(row.quantidade),
                "local": str(row.local_servico or "").strip() or "N/D",
                "observation": observation,
                "context": local_info,
                "status_kind": status_kind,
                "status_label": status_label,
                "period_label": TimeService.get_business_day_tag(row.data_saida) or "Expediente",
            }
            if is_tool:
                tools.append(payload)
            else:
                materials.append(payload)

            timeline.append(
                {
                    "entry_id": payload["entry_id"],
                    "type_label": "Retirada",
                    "type_kind": "withdraw",
                    "date_label": payload["date_label"],
                    "time_label": payload["time_label"],
                    "item_description": payload["item_description"],
                    "item_code": payload["item_code"],
                    "quantity": payload["quantity"],
                    "context": payload["context"],
                    "period_label": payload["period_label"],
                    "sort_value": row.data_saida,
                }
            )
            total_withdrawn_quantity += payload["quantity"]

        timeline.sort(key=lambda row: row.get("sort_value") or datetime.min, reverse=True)
        for row in timeline:
            row.pop("sort_value", None)

        local_now = TimeService.now_local()
        local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        local_end = local_start + timedelta(days=1)
        start_utc = local_start.astimezone(timezone.utc).replace(tzinfo=None)
        end_utc = local_end.astimezone(timezone.utc).replace(tzinfo=None)

        today_rows = (
            db.session.query(
                Saida.codigo_item,
                Item.descricao.label("item_descricao"),
                db.func.sum(Saida.quantidade).label("total_quantity"),
            )
            .join(Item, Saida.codigo_item == Item.codigo_item, isouter=True)
            .filter(
                Saida.matricula == employee_id,
                Saida.data_saida >= start_utc,
                Saida.data_saida < end_utc,
            )
            .group_by(Saida.codigo_item, Item.descricao)
            .order_by(Item.descricao.asc())
            .all()
        )

        today_checklist = [
            {
                "item_description": row.item_descricao or "Item removido",
                "item_code": _format_code(row.codigo_item),
                "quantity": _safe_float(row.total_quantity),
            }
            for row in today_rows
        ]

        return {
            "scope": "funcionario",
            "employee": {
                "matricula": employee.matricula,
                "name": employee.nome,
                "role": str(employee.setor or employee.cargo or "N/D").strip() or "N/D",
                "sector": str(employee.setor or "N/D").strip() or "N/D",
            },
            "summary": {
                "materials_count": len(materials),
                "tools_count": len(tools),
                "returns_count": len(returns),
                "timeline_count": len(timeline),
                "today_count": len(today_checklist),
                "pending_tools_count": sum(1 for tool in tools if tool.get("status_kind") == "pending"),
                "total_withdrawn_quantity": round(total_withdrawn_quantity, 3),
            },
            "today_checklist": today_checklist,
            "materials": materials,
            "tools": tools,
            "timeline": timeline,
            "download_url": _safe_url_for("reports.by_item_download", search=employee.matricula, type="usuario", period=0),
        }

    def build_item_payload(self, codigo_item: str, *, period_days: int = 0) -> dict[str, Any]:
        item_code = str(codigo_item or "").strip()
        if not item_code:
            raise ValueError("Item nao informado")

        item = Item.query.get(item_code)
        if item is None:
            raise ValueError("Item nao encontrado")

        query = (
            db.session.query(
                Saida.id_saida,
                Saida.quantidade,
                Saida.data_saida,
                Saida.observacao,
                Saida.local_servico,
                Saida.matricula.label("user_matricula"),
                Usuario.nome.label("user_name"),
            )
            .join(Usuario, Saida.matricula == Usuario.matricula, isouter=True)
            .filter(Saida.codigo_item == item_code)
        )

        normalized_period = int(period_days or 0)
        if normalized_period > 0:
            cutoff = datetime.utcnow() - timedelta(days=normalized_period)
            query = query.filter(Saida.data_saida >= cutoff)

        rows = query.order_by(Saida.data_saida.desc(), Saida.id_saida.desc()).all()

        movements: list[dict[str, Any]] = []
        unique_users: set[str] = set()
        daily_totals_map: dict[str, dict[str, Any]] = {}
        total_quantity = 0.0

        for row in rows:
            local_info = str(row.local_servico or "").strip() or "Sem local informado"
            observation = str(row.observacao or "").strip()
            if observation:
                local_info = f"{local_info} | {observation}"

            day_key = TimeService.format_local(row.data_saida, "%Y-%m-%d")
            day_bucket = daily_totals_map.setdefault(
                day_key,
                {
                    "date_label": TimeService.format_local(row.data_saida, "%d/%m/%Y"),
                    "movement_count": 0,
                    "total_quantity": 0.0,
                    "users": set(),
                },
            )
            quantity = _safe_float(row.quantidade)
            day_bucket["movement_count"] += 1
            day_bucket["total_quantity"] += quantity
            if row.user_matricula:
                day_bucket["users"].add(row.user_matricula)

            movements.append(
                {
                    "entry_id": row.id_saida,
                    "date_label": TimeService.format_local(row.data_saida, "%d/%m/%Y"),
                    "time_label": TimeService.format_local(row.data_saida, "%H:%M"),
                    "user_name": row.user_name or (f"Matricula {row.user_matricula}" if row.user_matricula else "N/D"),
                    "user_matricula": row.user_matricula or "N/D",
                    "quantity": quantity,
                    "local_info": local_info,
                    "period_label": TimeService.get_business_day_tag(row.data_saida) or "Expediente",
                }
            )
            total_quantity += quantity
            if row.user_matricula:
                unique_users.add(row.user_matricula)

        daily_totals = []
        for _, bucket in sorted(daily_totals_map.items(), reverse=True):
            users = bucket.pop("users", set())
            bucket["users_count"] = len(users)
            bucket["total_quantity"] = round(_safe_float(bucket.get("total_quantity")), 3)
            daily_totals.append(bucket)

        try:
            current_balance = _safe_float(item.get_saldo_fisico_total())
        except Exception:
            current_balance = 0.0

        return {
            "scope": "item",
            "item": {
                "codigo": item.codigo_item,
                "codigo_curto": _format_code(item.codigo_item),
                "descricao": item.descricao or item.codigo_item,
                "categoria": item.categoria or "Sem categoria",
                "marca": item.marca or "Sem marca",
                "saldo_atual": current_balance,
                "photo_url": _photo_url(item.foto_path),
            },
            "summary": {
                "movement_count": len(movements),
                "total_quantity": round(total_quantity, 3),
                "users_count": len(unique_users),
                "days_count": len(daily_totals),
                "period_days": normalized_period,
            },
            "movements": movements,
            "daily_totals": daily_totals,
            "download_url": _safe_url_for("reports.by_item_download", search=item.codigo_item, type="item", period=normalized_period),
        }

    def build_daily_payload(self, *, selected_date: date, search_term: str = "") -> dict[str, Any]:
        local_now = TimeService.now_local()
        local_start = local_now.replace(
            year=selected_date.year,
            month=selected_date.month,
            day=selected_date.day,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        local_end = local_start + timedelta(days=1)
        start_utc = local_start.astimezone(timezone.utc).replace(tzinfo=None)
        end_utc = local_end.astimezone(timezone.utc).replace(tzinfo=None)

        query = (
            db.session.query(
                Saida.id_saida,
                Saida.quantidade,
                Saida.data_saida,
                Saida.observacao,
                Saida.local_servico,
                Saida.tipo_custodia,
                Saida.codigo_item,
                Saida.matricula,
                Item.descricao.label("item_descricao"),
                Item.categoria.label("item_categoria"),
                Item.marca.label("item_marca"),
                Item.foto_path.label("item_foto_path"),
                Usuario.nome.label("usuario_nome"),
            )
            .join(Item, Saida.codigo_item == Item.codigo_item, isouter=True)
            .join(Usuario, Saida.matricula == Usuario.matricula, isouter=True)
            .filter(
                Saida.data_saida >= start_utc,
                Saida.data_saida < end_utc,
            )
        )

        normalized_search = str(search_term or "").strip()
        if normalized_search:
            like_term = f"%{normalized_search}%"
            query = query.filter(
                or_(
                    Item.descricao.ilike(like_term),
                    Item.codigo_item.ilike(like_term),
                    Usuario.nome.ilike(like_term),
                    Usuario.matricula.ilike(like_term),
                    Saida.local_servico.ilike(like_term),
                    Saida.observacao.ilike(like_term),
                )
            )

        rows = query.order_by(Saida.data_saida.asc(), Saida.id_saida.asc()).all()

        grouped_items_map: dict[str, dict[str, Any]] = {}
        total_quantity = 0.0

        for row in rows:
            item_key = str(row.codigo_item or "").strip() or f"sem-codigo-{row.id_saida}"
            item_group = grouped_items_map.get(item_key)
            if item_group is None:
                item_group = {
                    "codigo": row.codigo_item or "N/D",
                    "codigo_curto": _format_code(row.codigo_item),
                    "descricao": row.item_descricao or "Item removido",
                    "categoria": row.item_categoria or "Sem categoria",
                    "marca": row.item_marca or "Sem marca",
                    "foto_url": _photo_url(row.item_foto_path),
                    "total_quantity": 0.0,
                    "movement_count": 0,
                    "unique_users": set(),
                    "movements": [],
                }
                grouped_items_map[item_key] = item_group

            local_info = str(row.local_servico or "").strip() or "Sem local informado"
            observation = str(row.observacao or "").strip()
            if observation:
                local_info = f"{local_info} | {observation}"

            quantity = _safe_float(row.quantidade)
            item_group["total_quantity"] += quantity
            item_group["movement_count"] += 1
            if row.matricula:
                item_group["unique_users"].add(row.matricula)

            item_group["movements"].append(
                {
                    "entry_id": row.id_saida,
                    "time_label": TimeService.format_local(row.data_saida, "%H:%M"),
                    "user_name": row.usuario_nome or (f"Matricula {row.matricula}" if row.matricula else "N/D"),
                    "user_matricula": row.matricula or "N/D",
                    "quantity": quantity,
                    "local_info": local_info,
                    "period_label": TimeService.get_business_day_tag(row.data_saida) or "Expediente",
                    "custody_kind": str(row.tipo_custodia or "temporaria").strip().lower() or "temporaria",
                    "custody_label": "Permanente" if str(row.tipo_custodia or "").strip().lower() == "permanente" else "Temporaria",
                }
            )
            total_quantity += quantity

        grouped_items = list(grouped_items_map.values())
        grouped_items.sort(key=lambda item: (str(item.get("descricao") or "").lower(), str(item.get("codigo") or "")))
        for item_group in grouped_items:
            unique_users = item_group.pop("unique_users", set())
            item_group["unique_user_count"] = len(unique_users)
            item_group["total_quantity"] = round(_safe_float(item_group.get("total_quantity")), 3)

        return {
            "scope": "diario",
            "selected_date": selected_date.isoformat(),
            "selected_date_label": selected_date.strftime("%d/%m/%Y"),
            "search_term": normalized_search,
            "summary": {
                "total_items": len(grouped_items),
                "total_movements": len(rows),
                "total_quantity": round(total_quantity, 3),
                "items_with_photo": sum(1 for item in grouped_items if item.get("foto_url")),
            },
            "grouped_items": grouped_items,
        }


general_search_service = GeneralSearchService()