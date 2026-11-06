from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from flask import current_app, has_request_context, url_for
from sqlalchemy import func, or_

from ..extensions import db
from ..models import EntradaFiscalHistorico, InventarioEvento, Item, Saida, Usuario
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

        archived = (
            EntradaFiscalHistorico.query.filter(
                or_(
                    EntradaFiscalHistorico.descricao_item.ilike(f"%{search_term}%"),
                    EntradaFiscalHistorico.codigo_item.ilike(f"%{search_term}%"),
                    EntradaFiscalHistorico.numero_documento.ilike(f"%{search_term}%"),
                    EntradaFiscalHistorico.chave_acesso.ilike(f"%{search_term}%"),
                )
            )
            .order_by(EntradaFiscalHistorico.ocorrido_em.desc(), EntradaFiscalHistorico.id.desc())
            .limit(max(int(limit or 0) * 2, 1))
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
        known_codes = {str(result.get("codigo_item") or "") for result in results}
        for record in archived:
            if record.codigo_item in known_codes:
                continue
            title = record.descricao_item or record.codigo_item
            results.append(
                {
                    "entity_type": "item_historico",
                    "id": record.codigo_item,
                    "codigo_item": record.codigo_item,
                    "title": title,
                    "subtitle": f"Codigo {_format_code(record.codigo_item)} • Documento {record.numero_documento}",
                    "badge": "Historico fiscal",
                    "photo_url": None,
                    "historical": True,
                }
            )
            known_codes.add(record.codigo_item)
            if len(results) >= max(int(limit or 0), 1):
                break
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
        fiscal_history = (
            EntradaFiscalHistorico.query
            .filter(EntradaFiscalHistorico.codigo_item == item_code)
            .order_by(EntradaFiscalHistorico.data_recebimento.desc().nullslast(), EntradaFiscalHistorico.id.desc())
            .all()
        )
        if item is None and not fiscal_history:
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
            cutoff = TimeService.now_db() - timedelta(days=normalized_period)
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

        reference = fiscal_history[0] if fiscal_history else None
        item_payload = {
            "codigo": item.codigo_item if item else item_code,
            "codigo_curto": _format_code(item.codigo_item if item else item_code),
            "descricao": (item.descricao if item else reference.descricao_item) or item_code,
            "categoria": (item.categoria if item else reference.categoria_item) or "Sem categoria",
            "marca": (item.marca if item else reference.marca_item) or "Sem marca",
            "saldo_atual": current_balance if item else 0.0,
            "photo_url": _photo_url(item.foto_path) if item else None,
            "historical_only": item is None,
        }
        return {
            "scope": "item",
            "item": item_payload,
            "summary": {
                "movement_count": len(movements),
                "total_quantity": round(total_quantity, 3),
                "users_count": len(unique_users),
                "days_count": len(daily_totals),
                "period_days": normalized_period,
            },
            "movements": movements,
            "daily_totals": daily_totals,
            "fiscal_history": [
                {
                    "evento": row.evento,
                    "documento": row.numero_documento,
                    "tipo_documento": row.tipo_documento,
                    "chave_acesso": row.chave_acesso,
                    "data_emissao": row.data_emissao.isoformat() if row.data_emissao else None,
                    "data_recebimento": row.data_recebimento.isoformat() if row.data_recebimento else None,
                    "quantidade": _safe_float(row.quantidade),
                    "valor_unitario": row.valor_unitario,
                    "valor_total": row.valor_total,
                    "status_processamento": row.status_processamento,
                    "motivo": row.motivo,
                    "ocorrido_em": TimeService.isoformat_utc(row.ocorrido_em),
                }
                for row in fiscal_history
            ],
            "download_url": _safe_url_for("reports.by_item_download", search=item_code, type="item", period=normalized_period),
        }

    def build_item_consumption_payload(self, codigo_item: str, *, period: str = "7d") -> dict[str, Any]:
        item_code = str(codigo_item or "").strip()
        if not item_code:
            raise ValueError("Material ou ferramenta não informado.")

        period = str(period or "7d").strip().lower()
        if period not in {"7d", "30d", "month", "3m", "6m", "12m"}:
            period = "7d"

        def subtract_months(value: date, months: int) -> date:
            month_index = value.year * 12 + value.month - 1 - months
            year, month_zero_based = divmod(month_index, 12)
            month = month_zero_based + 1
            day = min(value.day, calendar.monthrange(year, month)[1])
            return date(year, month, day)

        item = Item.query.get(item_code)
        history = None
        if item is None:
            history = (
                EntradaFiscalHistorico.query
                .filter(EntradaFiscalHistorico.codigo_item == item_code)
                .order_by(EntradaFiscalHistorico.ocorrido_em.desc(), EntradaFiscalHistorico.id.desc())
                .first()
            )
        if item is None and history is None:
            raise ValueError("Material ou ferramenta não encontrado.")

        today = TimeService.now_local().date()
        if period == "month":
            current_start = today.replace(day=1)
            current_days = (today - current_start).days + 1
            previous_start = subtract_months(current_start, 1)
            previous_end = min(
                previous_start + timedelta(days=current_days - 1),
                date(previous_start.year, previous_start.month, calendar.monthrange(previous_start.year, previous_start.month)[1]),
            )
            previous_end_exclusive = previous_end + timedelta(days=1)
            period_label = "Mês atual até hoje"
            previous_label = "Mesmo intervalo do mês anterior"
        elif period.endswith("m"):
            months = int(period[:-1])
            current_start = subtract_months(today + timedelta(days=1), months)
            previous_start = subtract_months(current_start, months)
            previous_end = current_start - timedelta(days=1)
            previous_end_exclusive = current_start
            period_label = f"Últimos {months} meses"
            previous_label = f"{months} meses anteriores"
        else:
            days = int(period[:-1])
            current_start = today - timedelta(days=days - 1)
            previous_start = current_start - timedelta(days=days)
            previous_end = current_start - timedelta(days=1)
            previous_end_exclusive = current_start
            period_label = f"Últimos {days} dias"
            previous_label = f"{days} dias anteriores"
        tomorrow = today + timedelta(days=1)
        current_start_dt = datetime.combine(current_start, time.min)
        previous_start_dt = datetime.combine(previous_start, time.min)
        tomorrow_dt = datetime.combine(tomorrow, time.min)
        previous_end_dt = datetime.combine(previous_end_exclusive, time.min)

        rows = (
            db.session.query(
                Saida.id_saida,
                Saida.quantidade,
                Saida.data_saida,
                Saida.local_servico,
                Saida.matricula.label("user_matricula"),
                Usuario.nome.label("user_name"),
            )
            .join(Usuario, Saida.matricula == Usuario.matricula, isouter=True)
            .filter(
                Saida.codigo_item == item_code,
                Saida.data_saida >= previous_start_dt,
                Saida.data_saida < tomorrow_dt,
            )
            .order_by(Saida.data_saida.desc(), Saida.id_saida.desc())
            .all()
        )

        current_totals: dict[str, dict[str, Any]] = {}
        previous_totals: dict[str, dict[str, Any]] = {}
        daily_totals: dict[date, dict[str, Any]] = {}
        current_quantity = previous_quantity = 0.0
        current_count = previous_count = 0
        movements: list[dict[str, Any]] = []

        period_span = (today - previous_start).days + 1
        for day_offset in range(period_span):
            bucket_date = previous_start + timedelta(days=day_offset)
            daily_totals[bucket_date] = {"date_label": bucket_date.strftime("%d/%m"), "quantity": 0.0, "count": 0}

        for row in rows:
            quantity = _safe_float(row.quantidade)
            movement_date = TimeService.to_local(row.data_saida).date()
            is_current = movement_date >= current_start_dt.date()
            if not is_current and movement_date >= previous_end_dt.date():
                continue
            totals = current_totals if is_current else previous_totals
            totals["all"] = totals.get("all", {"quantity": 0.0, "count": 0})
            totals["all"]["quantity"] += quantity
            totals["all"]["count"] += 1
            if is_current:
                current_quantity += quantity
                current_count += 1
            else:
                previous_quantity += quantity
                previous_count += 1

            bucket = daily_totals.get(movement_date)
            if bucket is not None:
                bucket["quantity"] += quantity
                bucket["count"] += 1

            employee_name = str(row.user_name or "").strip() or (
                f"Matrícula {row.user_matricula}" if row.user_matricula else "Não identificado"
            )
            employee_key = str(row.user_matricula or employee_name)
            employee_bucket = totals.setdefault(
                f"user:{employee_key}",
                {"name": employee_name, "quantity": 0.0, "count": 0},
            )
            employee_bucket["quantity"] += quantity
            employee_bucket["count"] += 1

            location_name = str(row.local_servico or "").strip() or "Sem local informado"
            location_bucket = totals.setdefault(
                f"local:{location_name}",
                {"name": location_name, "quantity": 0.0, "count": 0},
            )
            location_bucket["quantity"] += quantity
            location_bucket["count"] += 1

            movements.append(
                {
                    "date": TimeService.format_local(row.data_saida, "%d/%m/%Y %H:%M"),
                    "employee": employee_name,
                    "employee_id": row.user_matricula or "N/D",
                    "quantity": round(quantity, 3),
                    "location": location_name,
                }
            )

        percent_change = (
            round(((current_quantity - previous_quantity) / previous_quantity) * 100, 1)
            if previous_quantity > 0
            else None
        )
        if previous_quantity <= 0 < current_quantity:
            trend = "Novo consumo no período"
        elif percent_change is not None and percent_change > 0:
            trend = "Consumo em alta"
        elif percent_change is not None and percent_change < 0:
            trend = "Consumo em queda"
        else:
            trend = "Consumo estável"

        def rank_period(period_totals: dict[str, dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
            ranked = [
                {"name": value["name"], "quantity": round(value["quantity"], 3), "count": value["count"]}
                for key, value in period_totals.items()
                if key.startswith(prefix)
            ]
            return sorted(ranked, key=lambda value: (-value["quantity"], value["name"].casefold()))[:10]

        item_description = (
            item.descricao if item else (history.descricao_item or item_code)
        )
        item_category = item.categoria if item else (history.categoria_item or "Sem categoria")
        if period_span > 90:
            grouped_daily: dict[tuple[str, str], dict[str, Any]] = {}
            for bucket_date, bucket in daily_totals.items():
                period_kind = "atual" if bucket_date >= current_start else "anterior"
                month_key = (bucket_date.strftime("%Y-%m"), period_kind)
                month_bucket = grouped_daily.setdefault(
                    month_key,
                    {
                        "date_label": f"{bucket_date.strftime('%m/%Y')} · {period_kind}",
                        "quantity": 0.0,
                        "count": 0,
                        "period": period_kind,
                    },
                )
                month_bucket["quantity"] += bucket["quantity"]
                month_bucket["count"] += bucket["count"]
            daily_series = [
                {**bucket, "quantity": round(bucket["quantity"], 3)}
                for _, bucket in sorted(grouped_daily.items())
            ]
        else:
            daily_series = [
                {
                    **bucket,
                    "quantity": round(bucket["quantity"], 3),
                    "period": "atual" if bucket_date >= current_start else "anterior",
                }
                for bucket_date, bucket in sorted(daily_totals.items())
            ]

        return {
            "item": {
                "codigo": item_code,
                "descricao": item_description,
                "categoria": item_category or "Sem categoria",
                "unidade": (item.unidade if item else None) or "unidade(s)",
                "saldo_atual": _safe_float(item.get_saldo_fisico_total()) if item else None,
                "historical_only": item is None,
            },
            "period": {
                "key": period,
                "label": period_label,
                "previous_label": previous_label,
                "current_start": current_start.strftime("%d/%m/%Y"),
                "current_end": today.strftime("%d/%m/%Y"),
                "previous_start": previous_start.strftime("%d/%m/%Y"),
                "previous_end": previous_end.strftime("%d/%m/%Y"),
            },
            "summary": {
                "current_quantity": round(current_quantity, 3),
                "previous_quantity": round(previous_quantity, 3),
                "difference": round(current_quantity - previous_quantity, 3),
                "percent_change": percent_change,
                "trend": trend,
                "current_withdrawals": current_count,
                "previous_withdrawals": previous_count,
            },
            "top_employees": rank_period(current_totals, "user:"),
            "top_locations": rank_period(current_totals, "local:"),
            "daily_totals": daily_series,
            "movements": movements,
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