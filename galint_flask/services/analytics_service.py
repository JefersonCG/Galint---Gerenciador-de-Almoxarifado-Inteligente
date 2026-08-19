from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from time import monotonic
from typing import Any

from .analytics_read_service import analytics_read_service


class AnalyticsService:
    _runtime_cache: dict[str, tuple[float, Any]] = {}

    @classmethod
    def clear_runtime_cache(cls, prefix: str | None = None) -> None:
        if prefix is None:
            cls._runtime_cache.clear()
            return
        keys = [key for key in cls._runtime_cache if key.startswith(prefix)]
        for key in keys:
            cls._runtime_cache.pop(key, None)

    @classmethod
    def _get_cached(cls, key: str) -> Any | None:
        cached = cls._runtime_cache.get(key)
        if not cached:
            return None
        expires_at, value = cached
        if expires_at <= monotonic():
            cls._runtime_cache.pop(key, None)
            return None
        return value

    @classmethod
    def _set_cached(cls, key: str, value: Any, *, ttl_seconds: float) -> Any:
        cls._runtime_cache[key] = (monotonic() + max(float(ttl_seconds or 0.0), 0.1), value)
        return value

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        return " ".join(str(value or "").lower().split())

    @classmethod
    def _matches_search(cls, row: dict[str, Any], search: str) -> bool:
        query = cls._normalize_text(search)
        if not query:
            return True
        haystack = cls._normalize_text(
            " ".join(
                [
                    str(row.get("descricao_item") or ""),
                    str(row.get("codigo_item") or ""),
                    str(row.get("categoria") or ""),
                    str(row.get("colaborador_nome") or ""),
                    str(row.get("cargo") or ""),
                    str(row.get("local") or ""),
                    str(row.get("observacao") or ""),
                ]
            )
        )
        return query in haystack

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _format_date_label(value: Any) -> str | None:
        parsed = AnalyticsService._parse_date(value)
        if parsed is None:
            return None
        return parsed.date().strftime("%d/%m/%Y")

    @staticmethod
    def _photo_url(photo_path: Any) -> str | None:
        raw = str(photo_path or "").strip()
        if not raw:
            return None
        normalized = raw.replace("\\", "/")
        if normalized.startswith(("http://", "https://", "data:")):
            return normalized
        if normalized.startswith("/"):
            return normalized
        try:
            from flask import url_for
            return url_for("static", filename=normalized)
        except Exception:
            return f"/static/{normalized.lstrip('/')}"

    @staticmethod
    def _group_label(period_date: date, *, use_month: bool) -> str:
        if use_month:
            return period_date.strftime("%m/%Y")
        return period_date.strftime("%d/%m")

    @classmethod
    def _build_movement_series(
        cls,
        period: dict[str, Any],
        entry_rows: list[dict[str, Any]],
        exits: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        duration_days = max(int((period.get("end_date") - period.get("start_date")).days) + 1, 1)
        use_month = duration_days > 90

        grouped: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "label": "",
                "sort_key": "",
                "entradas": 0,
                "saidas": 0,
                "quantidade_entrada": 0.0,
                "quantidade_saida": 0.0,
            }
        )

        for entry in entry_rows:
            entry_dt = entry.get("data_entrada")
            if entry_dt is None:
                continue
            bucket_key = entry_dt.strftime("%Y-%m" if use_month else "%Y-%m-%d")
            label = cls._group_label(entry_dt.date(), use_month=use_month)
            row = grouped[bucket_key]
            row["label"] = label
            row["sort_key"] = bucket_key
            row["entradas"] += 1
            row["quantidade_entrada"] += cls._safe_float(entry.get("quantidade"))

        for exit_row in exits:
            raw_date = exit_row.get("data_saida")
            if raw_date is None:
                continue
            bucket_key = raw_date.strftime("%Y-%m" if use_month else "%Y-%m-%d")
            label = cls._group_label(raw_date.date(), use_month=use_month)
            row = grouped[bucket_key]
            row["label"] = label
            row["sort_key"] = bucket_key
            row["saidas"] += 1
            row["quantidade_saida"] += cls._safe_float(exit_row.get("quantidade_base"))

        series = list(grouped.values())
        series.sort(key=lambda row: str(row.get("sort_key") or ""))
        result = series[-12:] if use_month else series[-20:]
        for row in result:
            row.pop("sort_key", None)
        return result

    @classmethod
    def _build_top_items(cls, entries: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        total_value = 0.0
        for row in entries:
            code = str(row.get("codigo_item") or "").strip()
            if not code:
                continue
            bucket = buckets.setdefault(
                code,
                {
                    "codigo_item": code,
                    "descricao_item": row.get("descricao_item") or code,
                    "categoria": row.get("categoria") or "Sem categoria",
                    "valor_total": 0.0,
                    "quantidade_base": 0.0,
                    "saidas": 0,
                },
            )
            value = cls._safe_float(row.get("valor_total"))
            bucket["valor_total"] += value
            bucket["quantidade_base"] += cls._safe_float(row.get("quantidade_base"))
            bucket["saidas"] += 1
            total_value += value

        items = sorted(buckets.values(), key=lambda row: (-float(row.get("valor_total") or 0.0), str(row.get("descricao_item") or "")))[:limit]
        for item in items:
            value = cls._safe_float(item.get("valor_total"))
            item["share_percent"] = round((value / total_value) * 100, 1) if total_value > 0 else 0.0
        return items

    @classmethod
    def _build_type_distribution(cls, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {
            "padrao": {"label": "Saída padrão", "key": "padrao", "count": 0, "value": 0.0},
            "fracionado": {"label": "Saída fracionada", "key": "fracionado", "count": 0, "value": 0.0},
        }
        total = 0.0
        for row in entries:
            key = str(row.get("tipo_consumo") or "padrao").strip().lower()
            if key not in grouped:
                key = "padrao"
            value = cls._safe_float(row.get("valor_total"))
            grouped[key]["count"] += 1
            grouped[key]["value"] += value
            total += value

        distribution = list(grouped.values())
        for row in distribution:
            row["percent"] = round((cls._safe_float(row.get("value")) / total) * 100, 1) if total > 0 else 0.0
        return distribution

    @classmethod
    def _build_operational_insights(
        cls,
        dataset: dict[str, Any],
        *,
        top_items: list[dict[str, Any]],
        average_value: float,
        movement_balance: dict[str, Any],
    ) -> list[dict[str, Any]]:
        insights: list[dict[str, Any]] = []
        locations = dataset.get("locations") or []
        employees = dataset.get("employees") or []
        overview = dataset.get("overview") or {}
        maintenance = dataset.get("maintenance") or {}

        if top_items:
            lead_item = top_items[0]
            insights.append(
                {
                    "title": "Item de maior impacto",
                    "value": lead_item.get("descricao_item"),
                    "caption": f"{lead_item.get('share_percent', 0)}% do valor movimentado no recorte atual.",
                }
            )

        if locations:
            lead_local = locations[0]
            insights.append(
                {
                    "title": "Local com maior consumo",
                    "value": lead_local.get("local"),
                    "caption": f"{lead_local.get('saidas', 0)} saídas e {lead_local.get('material_destaque') or 'sem material destaque'} como material líder.",
                }
            )

        if employees:
            lead_employee = employees[0]
            insights.append(
                {
                    "title": "Colaborador em destaque",
                    "value": lead_employee.get("nome"),
                    "caption": f"{lead_employee.get('parecer_administrativo') or 'Sem parecer'} • {lead_employee.get('saidas', 0)} saídas no período.",
                }
            )

        if maintenance.get("groups"):
            lead_activity = maintenance["groups"][0]
            insights.append(
                {
                    "title": "Atividade operacional líder",
                    "value": lead_activity.get("label"),
                    "caption": f"{lead_activity.get('count', 0)} movimentos • {maintenance.get('structured_percent', 0)}% ja estruturado e {maintenance.get('coverage_percent', 0)}% de cobertura total fora da Central de Kits.",
                }
            )

        if cls._safe_float(movement_balance.get("saidas_qty")) > cls._safe_float(movement_balance.get("entradas_qty")):
            insights.append(
                {
                    "title": "Pressão operacional",
                    "value": "Saídas acima das entradas",
                    "caption": f"Diferença de {cls._safe_float(movement_balance.get('saidas_qty')) - cls._safe_float(movement_balance.get('entradas_qty')):.2f} unidades no período geral.",
                }
            )
        else:
            insights.append(
                {
                    "title": "Reposição acompanhando consumo",
                    "value": "Entradas equilibradas",
                    "caption": "O fluxo geral do período não mostra pressão líquida negativa acima das saídas.",
                }
            )

        if not insights:
            insights.append(
                {
                    "title": "Sem insight crítico",
                    "value": "Base estável",
                    "caption": f"{overview.get('saidas', 0)} movimentações analisadas e ticket médio de R$ {average_value:,.2f}.",
                }
            )

        return insights[:4]

    @classmethod
    def _build_entry_exit_balance(cls, entry_rows: list[dict[str, Any]], exit_rows: list[dict[str, Any]]) -> dict[str, Any]:
        entradas_qty = round(sum(cls._safe_float(row.get("quantidade")) for row in entry_rows), 3)
        saidas_qty = round(sum(cls._safe_float(row.get("quantidade_base")) for row in exit_rows), 3)

        return {
            "entradas_count": len(entry_rows),
            "saidas_count": len(exit_rows),
            "entradas_qty": entradas_qty,
            "saidas_qty": saidas_qty,
            "saldo_qty": round(entradas_qty - saidas_qty, 3),
            "entradas_valor": round(sum(cls._safe_float(row.get("valor_total")) for row in entry_rows), 2),
            "saidas_valor": round(sum(cls._safe_float(row.get("valor_total")) for row in exit_rows), 2),
        }

    @staticmethod
    def _serialize_table_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "saida_id": row.get("saida_id"),
            "codigo_item": row.get("codigo_item"),
            "descricao_item": row.get("descricao_item"),
            "categoria": row.get("categoria"),
            "matricula": row.get("matricula"),
            "colaborador_nome": row.get("colaborador_nome"),
            "cargo": row.get("cargo"),
            "local": row.get("local"),
            "observacao": row.get("observacao"),
            "ordem_servico": row.get("ordem_servico"),
            "centro_custo": row.get("centro_custo"),
            "atividade_estruturada_label": row.get("atividade_estruturada_label"),
            "data_saida_label": row.get("data_saida_label"),
            "quantidade_base": row.get("quantidade_base"),
            "unit_base": row.get("unit_base"),
            "quantidade_display": row.get("quantidade_display"),
            "valor_total": row.get("valor_total"),
            "tipo_consumo": row.get("tipo_consumo"),
            "atividade_label": row.get("atividade_label"),
            "atividade_confianca": row.get("atividade_confianca"),
            "atividade_source": row.get("atividade_source"),
        }

    @classmethod
    def _build_shell_payload(
        cls,
        *,
        exercise_label: str | None = None,
        period_preset: str | None = None,
        start_date_value: str | None = None,
        end_date_value: str | None = None,
        local_name: str | None = None,
        category_name: str | None = None,
        employee_id: str | None = None,
        search: str = "",
        sort_by: str | None = None,
        sort_dir: str | None = None,
        per_page: int = 25,
    ) -> dict[str, Any]:
        filter_options = analytics_read_service.get_filter_options()
        period = analytics_read_service.resolve_period(
            exercise_label=exercise_label,
            period_preset=period_preset,
            start_date_value=start_date_value,
            end_date_value=end_date_value,
        )
        normalized_sort_by, normalized_sort_dir = analytics_read_service._resolve_sort(sort_by, sort_dir)
        return {
            "header": {
                "period_label": period.get("label") or "Atual",
                "exercise_label": period.get("exercise_label") or "Atual",
                "period_mode": period.get("mode") or "exercise",
                "start_date_label": period.get("start_date_label") or "-",
                "end_date_label": period.get("end_date_label") or "-",
                "generated_at_label": datetime.utcnow().strftime("%d/%m/%Y %H:%M"),
            },
            "filters": {
                "search": str(search or "").strip(),
                "selected_exercise": str(exercise_label or period.get("exercise_label") or "").strip(),
                "selected_period_preset": str(period.get("selected_period_preset") or "").strip(),
                "selected_period_preset_label": period.get("label") if period.get("mode") == "preset" else "",
                "selected_start_date": period.get("selected_start_date") or "",
                "selected_end_date": period.get("selected_end_date") or "",
                "selected_local": str(local_name or "").strip(),
                "selected_category": str(category_name or "").strip(),
                "selected_employee": str(employee_id or "").strip(),
                "sort_by": normalized_sort_by,
                "sort_dir": normalized_sort_dir,
                "per_page": min(max(int(per_page or 25), 10), 100),
                **filter_options,
            },
            "context": analytics_read_service._build_scope_context(
                period=period,
                local_name=local_name,
                category_name=category_name,
                employee_id=employee_id,
                search=search,
                filter_options=filter_options,
            ),
        }

    @staticmethod
    def _parse_date(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
                try:
                    return datetime.strptime(raw, fmt)
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                return None
        return None

    @classmethod
    def build_projection_cards(cls, exit_rows: list[dict[str, Any]], stock_snapshot: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        stock_by_code: dict[str, float] = {}
        metadata_by_code: dict[str, dict[str, Any]] = {}
        for row in (stock_snapshot or {}).get("resumo") or []:
            code = str(row.get("codigo") or "").strip()
            if code:
                stock_by_code[code] = cls._safe_float(row.get("saldo"))
                metadata_by_code[code] = {
                    "foto_path": row.get("foto_path") or row.get("photo_path") or row.get("foto_url") or row.get("photo_url"),
                    "foto_url": row.get("foto_url") or row.get("photo_url") or row.get("foto_path") or row.get("photo_path"),
                    "data_entrada": row.get("data_entrada") or row.get("entry_date") or row.get("data_cadastro"),
                    "document_number": row.get("document_number") or row.get("numero_documento") or row.get("nota_fiscal") or row.get("preco_compra_documento"),
                }

        if metadata_by_code:
            item_codes = [code for code in metadata_by_code if code]
            try:
                from flask import has_app_context
                if has_app_context():
                    from ..models import Item
                    item_rows = Item.query.filter(Item.codigo_item.in_(item_codes)).all() if item_codes else []
                    for item in item_rows:
                        code = str(item.codigo_item or "").strip()
                        if not code:
                            continue
                        metadata = metadata_by_code.setdefault(code, {})
                        metadata.setdefault("foto_path", item.foto_path)
                        metadata.setdefault("foto_url", item.foto_path)
                        metadata.setdefault("data_entrada", item.data_entrada)
                        metadata.setdefault("document_number", item.preco_compra_documento or item.nota_fiscal)
            except Exception:
                pass

        item_consumption: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        item_damage: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

        for row in exit_rows or []:
            code = str(row.get("codigo_item") or "").strip()
            if not code:
                continue
            item = str(row.get("descricao_item") or code).strip() or code
            dt = cls._parse_date(row.get("data_saida") or row.get("data") or row.get("data_saida_label"))
            if dt is None:
                continue
            quantity = cls._safe_float(row.get("quantidade_base"))
            item_consumption[code].append({"item": item, "date": dt, "quantity": quantity})
            if bool(row.get("is_loss_damage")):
                item_damage[code].append({
                    "item": item,
                    "date": dt,
                    "kind": str(row.get("loss_damage_kind") or "quebrada").strip().lower(),
                    "quantity": quantity,
                })

        def _estimate_zero_date(entries: list[dict[str, Any]], stock_balance: float) -> tuple[str | None, str, int, float]:
            if not entries:
                return None, "estável", 0, 0.0
            ordered_entries = sorted(entries, key=lambda item: item["date"])
            daily_usage: defaultdict[date, float] = defaultdict(float)
            for entry in ordered_entries:
                daily_usage[entry["date"].date()] += cls._safe_float(entry.get("quantity"))
            values = sorted(daily_usage.items(), key=lambda item: item[0])
            if len(values) < 2:
                return None, "estável", 0, 0.0

            x_values = list(range(len(values)))
            y_values = [float(amount) for _, amount in values]
            x_mean = sum(x_values) / len(x_values)
            y_mean = sum(y_values) / len(y_values)
            numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
            denominator = sum((x - x_mean) ** 2 for x in x_values)
            slope = numerator / denominator if denominator else 0.0
            if slope <= 0:
                return None, "estável", 0, 0.0

            last_day = values[-1][0]
            days_to_zero = max(0.0, stock_balance / slope)
            zero_date = last_day + timedelta(days=max(int(days_to_zero), 1))
            status = "em_atenção" if days_to_zero <= 30 else "estável"
            return zero_date.strftime("%d/%m/%Y"), status, int(days_to_zero), slope

        cards: list[dict[str, Any]] = []

        for code, entries in item_consumption.items():
            item_name = entries[0]["item"]
            stock_balance = stock_by_code.get(code, 0.0)
            projected_date, status, days_to_zero, slope = _estimate_zero_date(entries, stock_balance)
            if projected_date is None:
                continue
            metadata = metadata_by_code.get(code, {})
            entry_date = cls._format_date_label(metadata.get("data_entrada"))
            photo_url = cls._photo_url(metadata.get("foto_url") or metadata.get("foto_path"))
            document_number = str(metadata.get("document_number") or "").strip() or "-"
            cards.append({
                "type": "consumo_ferramentas",
                "item": item_name,
                "codigo": code,
                "date": projected_date,
                "negative_date": projected_date,
                "entry_date": entry_date,
                "document_number": document_number,
                "status": status,
                "forecast_days": days_to_zero,
                "trend": round(slope, 2),
                "stock_balance": round(stock_balance, 2),
                "photo_url": photo_url,
                "details": f"Consumo médio de {round(slope, 2)} und/dia; estoque previsto para zerar em {days_to_zero} dias.",
            })

        for code, entries in item_damage.items():
            if not entries:
                continue
            item_name = entries[0]["item"]
            ordered_dates = sorted(item["date"] for item in entries)
            span_days = max((ordered_dates[-1] - ordered_dates[0]).days, 1)
            total_damage = len(entries)
            projected_count = max(0, round((total_damage / span_days) * 30))
            projected_date = (ordered_dates[-1] + timedelta(days=30)).strftime("%d/%m/%Y")
            cards.append({
                "type": "perdas_avarias_futuras",
                "item": item_name,
                "codigo": code,
                "date": projected_date,
                "status": "alto" if projected_count >= 2 else "moderado",
                "projected_count": projected_count,
                "details": f"Risco estimado de {projected_count} ocorrência(s) em 30 dias com base no histórico recente.",
            })

        degradation_candidates: list[dict[str, Any]] = []
        for code, entries in item_consumption.items():
            if not entries:
                continue
            item_name = entries[0]["item"]
            total_quantity = sum(item["quantity"] for item in entries)
            stock_balance = stock_by_code.get(code, 0.0)
            wear_index = round((total_quantity / max(stock_balance, 1.0)) * 100, 1)
            if stock_balance <= 0:
                wear_index = 100.0
            latest_date = max(item["date"] for item in entries)
            degradation_candidates.append({
                "type": "degradacao_ferramentas",
                "item": item_name,
                "codigo": code,
                "date": (latest_date + timedelta(days=30)).strftime("%d/%m/%Y"),
                "status": "crítico" if wear_index >= 80 else "alerta",
                "wear_index": wear_index,
                "details": f"Uso acumulado equivale a {wear_index}% do estoque atual; degradação esperada em 30 dias.",
            })

        if degradation_candidates:
            cards.append(sorted(degradation_candidates, key=lambda item: item["wear_index"], reverse=True)[0])

        if not cards:
            return [{
                "type": "consumo_ferramentas",
                "item": "Sem risco identificado",
                "codigo": "-",
                "date": datetime.now().strftime("%d/%m/%Y"),
                "status": "estável",
                "forecast_days": 0,
                "details": "Sem histórico suficiente para projetar consumo crítico.",
            }]

        cards.sort(key=lambda item: (0 if item["type"] == "consumo_ferramentas" else 1 if item["type"] == "perdas_avarias_futuras" else 2, item.get("date") or ""))
        return cards[:3]

    @classmethod
    def get_dashboard_payload(
        cls,
        *,
        exercise_label: str | None = None,
        period_preset: str | None = None,
        start_date_value: str | None = None,
        end_date_value: str | None = None,
        local_name: str | None = None,
        category_name: str | None = None,
        employee_id: str | None = None,
        search: str = "",
        page: int = 1,
        per_page: int = 25,
        sort_by: str | None = None,
        sort_dir: str | None = None,
    ) -> dict[str, Any]:
        normalized_page = max(int(page or 1), 1)
        normalized_per_page = min(max(int(per_page or 25), 10), 100)
        cache_key = (
            "central_analytics:"
            f"{exercise_label or ''}:"
            f"{period_preset or ''}:"
            f"{start_date_value or ''}:"
            f"{end_date_value or ''}:"
            f"{local_name or ''}:"
            f"{category_name or ''}:"
            f"{employee_id or ''}:"
            f"{search.strip().lower()}:"
            f"{sort_by or ''}:"
            f"{sort_dir or ''}:"
            f"{normalized_page}:"
            f"{normalized_per_page}"
        )
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return dict(cached)

        dataset = analytics_read_service.get_dataset(
            exercise_label=exercise_label,
            period_preset=period_preset,
            start_date_value=start_date_value,
            end_date_value=end_date_value,
            local_name=local_name,
            category_name=category_name,
            employee_id=employee_id,
            search=search,
            page=normalized_page,
            per_page=normalized_per_page,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        period = dict(dataset.get("period") or {})
        exit_rows = list((dataset.get("table") or {}).get("all_rows") or [])
        entry_rows = list(dataset.get("entry_rows") or [])
        overview = dict(dataset.get("overview") or {})

        total_quantity = round(sum(cls._safe_float(row.get("quantidade_base")) for row in exit_rows), 3)
        total_value = round(sum(cls._safe_float(row.get("valor_total")) for row in exit_rows), 2)
        total_movements = len(exit_rows)
        average_value = round(total_value / total_movements, 2) if total_movements else 0.0
        average_quantity = round(total_quantity / total_movements, 3) if total_movements else 0.0

        top_items = cls._build_top_items(exit_rows)
        type_distribution = cls._build_type_distribution(exit_rows)
        movement_balance = cls._build_entry_exit_balance(entry_rows, exit_rows)
        movement_series = cls._build_movement_series(period, entry_rows, exit_rows)

        locations_source = list(dataset.get("locations") or [])
        categories_source = list(dataset.get("categories") or [])
        max_location_value = max((cls._safe_float(row.get("total_valor")) for row in locations_source), default=0.0)
        max_category_value = max((cls._safe_float(row.get("total_valor")) for row in categories_source), default=0.0)

        locations_chart = []
        for row in locations_source[:6]:
            value = cls._safe_float(row.get("total_valor"))
            locations_chart.append({
                **row,
                "percent": round((value / max_location_value) * 100, 1) if max_location_value > 0 else 0.0,
            })

        categories_chart = []
        for row in categories_source[:6]:
            value = cls._safe_float(row.get("total_valor"))
            categories_chart.append({
                **row,
                "percent": round((value / max_category_value) * 100, 1) if max_category_value > 0 else 0.0,
            })

        table = dict(dataset.get("table") or {})
        stock = dict(dataset.get("stock") or {})
        shell = cls._build_shell_payload(
            exercise_label=exercise_label,
            period_preset=period_preset,
            start_date_value=start_date_value,
            end_date_value=end_date_value,
            local_name=local_name,
            category_name=category_name,
            employee_id=employee_id,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
            per_page=normalized_per_page,
        )

        payload = {
            "header": shell.get("header") or {},
            "filters": shell.get("filters") or {},
            "kpis": {
                "movements": total_movements,
                "quantity": total_quantity,
                "value": total_value,
                "average_value": average_value,
                "average_quantity": average_quantity,
                "collaborators": overview.get("colaboradores") or 0,
                "items": overview.get("itens") or 0,
                "stock_total": stock.get("total_quantity") or 0,
                "stock_low": stock.get("low_count") or 0,
                "entry_value": movement_balance.get("entradas_valor") or 0.0,
                "period_label": period.get("label") or "Atual",
            },
            "charts": {
                "movement_series": movement_series,
                "locations": locations_chart,
                "categories": categories_chart,
                "type_distribution": type_distribution,
                "entry_exit_balance": movement_balance,
            },
            "top_items": top_items,
            "projection_cards": cls.build_projection_cards(exit_rows, stock),
            "insights": cls._build_operational_insights(
                dataset,
                top_items=top_items,
                average_value=average_value,
                movement_balance=movement_balance,
            ),
            "table": table,
            "context": shell.get("context") or {},
            "maintenance": dataset.get("maintenance") or {},
        }
        return cls._set_cached(cache_key, dict(payload), ttl_seconds=15.0)

    @classmethod
    def get_shell_payload(
        cls,
        *,
        exercise_label: str | None = None,
        period_preset: str | None = None,
        start_date_value: str | None = None,
        end_date_value: str | None = None,
        local_name: str | None = None,
        category_name: str | None = None,
        employee_id: str | None = None,
        search: str = "",
        page: int = 1,
        sort_by: str | None = None,
        sort_dir: str | None = None,
        per_page: int = 25,
    ) -> dict[str, Any]:
        return cls._build_shell_payload(
            exercise_label=exercise_label,
            period_preset=period_preset,
            start_date_value=start_date_value,
            end_date_value=end_date_value,
            local_name=local_name,
            category_name=category_name,
            employee_id=employee_id,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
            per_page=per_page,
        )

    @classmethod
    def get_overview_widget(cls, **filters: Any) -> dict[str, Any]:
        payload = cls.get_dashboard_payload(**filters)
        return {
            "header": dict(payload.get("header") or {}),
            "context": dict(payload.get("context") or {}),
            "kpis": dict(payload.get("kpis") or {}),
            "projection_cards": list(payload.get("projection_cards") or []),
            "insights": list(payload.get("insights") or []),
            "table_summary": {
                "total_rows": ((payload.get("table") or {}).get("total_rows") or 0),
                "page": ((payload.get("table") or {}).get("page") or 1),
                "total_pages": ((payload.get("table") or {}).get("total_pages") or 1),
            },
        }

    @classmethod
    def get_charts_widget(cls, **filters: Any) -> dict[str, Any]:
        payload = cls.get_dashboard_payload(**filters)
        return {
            "charts": dict(payload.get("charts") or {}),
            "top_items": list(payload.get("top_items") or []),
        }

    @classmethod
    def get_table_widget(cls, **filters: Any) -> dict[str, Any]:
        payload = cls.get_dashboard_payload(**filters)
        table = dict(payload.get("table") or {})
        table.pop("all_rows", None)
        table["rows"] = [cls._serialize_table_row(row) for row in table.get("rows") or []]
        return {
            "table": table,
        }

    @classmethod
    def get_maintenance_widget(cls, **filters: Any) -> dict[str, Any]:
        payload = cls.get_dashboard_payload(**filters)
        maintenance = dict(payload.get("maintenance") or {})
        maintenance["recent_rows"] = [cls._serialize_table_row(row) for row in maintenance.get("recent_rows") or []]
        return {
            "maintenance": maintenance,
        }


analytics_service = AnalyticsService()