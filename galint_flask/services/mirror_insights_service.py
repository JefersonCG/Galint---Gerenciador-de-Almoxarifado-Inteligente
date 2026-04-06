from __future__ import annotations

from datetime import datetime
from time import monotonic
from typing import Any

from sqlalchemy import case, func

from ..extensions import db
from ..models import Entrada, InventarioEvento, Item, RetiradaFerramenta, Saida, Usuario
from .analytics_read_service import analytics_read_service
from .inventory import inventory_service
from .operation_visual_payload import operation_visual_payload_service
from .tool_custody_service import ToolCustodyService


class MirrorInsightsService:
    _runtime_cache: dict[str, tuple[float, Any]] = {}
    ROTATION_SECONDS = 10

    @classmethod
    def _get_cached(cls, key: str) -> Any | None:
        cached = cls._runtime_cache.get(key)
        if cached is None:
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
    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @classmethod
    def _format_integer(cls, value: Any) -> str:
        try:
            number = int(round(float(value or 0)))
        except (TypeError, ValueError):
            number = 0
        return f"{number:,}".replace(",", ".")

    @classmethod
    def _format_quantity(cls, value: Any) -> str:
        try:
            number = float(value or 0)
        except (TypeError, ValueError):
            number = 0.0
        if abs(number - round(number)) < 1e-9:
            return cls._format_integer(number)
        return f"{number:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

    @classmethod
    def _format_currency(cls, value: Any) -> str:
        try:
            number = float(value or 0)
        except (TypeError, ValueError):
            number = 0.0
        formatted = f"{number:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        return f"R$ {formatted}"

    @staticmethod
    def _photo_url(photo_path: str | None) -> str | None:
        normalized = str(photo_path or "").strip() or None
        if not normalized:
            return None
        return operation_visual_payload_service._build_photo_url(normalized)

    @classmethod
    def _build_photo_payload(
        cls,
        *,
        item: Item | None = None,
        photo_path: str | None = None,
        alt: str | None = None,
        badge: str | None = None,
    ) -> dict[str, Any]:
        resolved_path = photo_path or getattr(item, "foto_path", None)
        url = cls._photo_url(resolved_path)
        if url is None:
            return {
                "photo_url": None,
                "photo_alt": None,
                "photo_badge": None,
            }
        return {
            "photo_url": url,
            "photo_alt": alt or getattr(item, "descricao", None) or "Item em destaque",
            "photo_badge": badge or None,
        }

    @classmethod
    def _current_month_rows(cls) -> list[dict[str, Any]]:
        dataset = analytics_read_service.get_dataset(period_preset="current_month", per_page=100)
        return list((((dataset.get("table") or {}).get("all_rows")) or []))

    @classmethod
    def _current_month_snapshot(cls) -> dict[str, Any]:
        dataset = analytics_read_service.get_dataset(period_preset="current_month", per_page=100)
        return {
            "rows": list((((dataset.get("table") or {}).get("all_rows")) or [])),
            "entry_rows": list(dataset.get("entry_rows") or []),
            "overview": dict(dataset.get("overview") or {}),
        }

    @classmethod
    def _build_overdue_tool_insight(cls) -> dict[str, Any] | None:
        active_withdrawals = (
            RetiradaFerramenta.query
            .filter(RetiradaFerramenta.status.in_(["em_uso", "atrasada", "para_reparo"]))
            .order_by(RetiradaFerramenta.data_retirada.asc())
            .all()
        )

        selected: RetiradaFerramenta | None = None
        selected_days = -1
        overdue_count = 0

        for withdrawal in active_withdrawals:
            if withdrawal.status == "devolvida":
                continue
            days_in_use = max((datetime.now() - withdrawal.data_retirada).days, 0) if withdrawal.data_retirada else 0
            if not withdrawal.verificar_atraso() and days_in_use <= 0:
                continue
            overdue_count += 1
            if days_in_use > selected_days:
                selected = withdrawal
                selected_days = days_in_use

        if not selected:
            return None

        item = getattr(selected, "item", None)
        user = getattr(selected, "usuario", None)
        nome = cls._normalize_text(getattr(user, "nome", None)) or (selected.matricula or "Colaborador")
        descricao = cls._normalize_text(getattr(item, "descricao", None)) or selected.codigo_item

        return {
            "id": f"overdue-tool-{selected.id}",
            "domain": "custodia",
            "tone": "warning",
            "icon": "bi-exclamation-diamond",
            "kicker": "Custódia crítica",
            "title": f"{nome} está com {descricao}",
            "text": f"A ferramenta segue sem devolução há {cls._format_integer(selected_days)} dia(s) e exige conferência imediata no controle operacional.",
            "primary_label": "Sem devolução",
            "primary_value": f"{cls._format_integer(selected_days)} dia(s)",
            "secondary_label": "Pendências abertas",
            "secondary_value": cls._format_integer(overdue_count),
            "source_label": "Custódia de ferramentas",
            **cls._build_photo_payload(item=item, alt=descricao, badge="Ferramenta"),
        }

    @classmethod
    def _build_top_withdrawer_insight(cls) -> dict[str, Any] | None:
        row = (
            db.session.query(
                Usuario.matricula.label("matricula"),
                Usuario.nome.label("nome"),
                func.count(Saida.id_saida).label("total_retiradas"),
                func.max(Saida.data_saida).label("ultima_retirada"),
            )
            .join(Saida, Usuario.matricula == Saida.matricula)
            .group_by(Usuario.matricula, Usuario.nome)
            .order_by(func.count(Saida.id_saida).desc(), func.max(Saida.data_saida).desc())
            .first()
        )
        if not row:
            return None

        nome = cls._normalize_text(getattr(row, "nome", None)) or getattr(row, "matricula", None) or "Colaborador"
        photo_path = ToolCustodyService.get_employee_photo_path(getattr(row, "matricula", None) or "")

        return {
            "id": f"top-withdrawer-{getattr(row, 'matricula', 'sem-matricula')}",
            "domain": "colaborador",
            "tone": "info",
            "icon": "bi-person-lines-fill",
            "kicker": "Histórico operacional",
            "title": f"{nome} lidera o volume de retiradas",
            "text": f"O colaborador já acumulou {cls._format_integer(getattr(row, 'total_retiradas', 0))} retiradas registradas no GALINT.",
            "primary_label": "Retiradas",
            "primary_value": cls._format_integer(getattr(row, "total_retiradas", 0)),
            "secondary_label": "Último lançamento",
            "secondary_value": getattr(row, "ultima_retirada", None).strftime("%d/%m/%Y") if getattr(row, "ultima_retirada", None) else "--",
            "source_label": "Histórico consolidado de saídas",
            **cls._build_photo_payload(photo_path=photo_path, alt=nome, badge="Colaborador"),
        }

    @classmethod
    def _build_low_return_employee_insight(cls) -> dict[str, Any] | None:
        material_outputs = {
            str(row.matricula or "").strip(): {
                "count": int(row.total_saidas or 0),
                "quantity": cls._safe_float(row.total_quantidade),
            }
            for row in (
                db.session.query(
                    Saida.matricula.label("matricula"),
                    func.count(Saida.id_saida).label("total_saidas"),
                    func.sum(Saida.quantidade).label("total_quantidade"),
                )
                .filter(Saida.matricula.is_not(None))
                .group_by(Saida.matricula)
                .all()
            )
        }

        material_returns: dict[str, dict[str, float | int]] = {}
        for row in (
            db.session.query(
                InventarioEvento.matricula.label("matricula"),
                func.count(InventarioEvento.id_evento).label("total_eventos"),
                func.sum(InventarioEvento.quantidade).label("total_quantidade"),
            )
            .filter(InventarioEvento.tipo == "devolucao_material")
            .filter(InventarioEvento.matricula.is_not(None))
            .group_by(InventarioEvento.matricula)
            .all()
        ):
            key = str(row.matricula or "").strip()
            material_returns[key] = {
                "count": int(row.total_eventos or 0),
                "quantity": cls._safe_float(row.total_quantidade),
            }

        for row in (
            db.session.query(
                Entrada.matricula.label("matricula"),
                func.count(Entrada.id_entrada).label("total_eventos"),
                func.sum(Entrada.quantidade).label("total_quantidade"),
            )
            .filter(Entrada.nota_fiscal.is_(None))
            .filter(Entrada.matricula.is_not(None))
            .group_by(Entrada.matricula)
            .all()
        ):
            key = str(row.matricula or "").strip()
            bucket = material_returns.setdefault(key, {"count": 0, "quantity": 0.0})
            bucket["count"] = int(bucket.get("count") or 0) + int(row.total_eventos or 0)
            bucket["quantity"] = cls._safe_float(bucket.get("quantity")) + cls._safe_float(row.total_quantidade)

        tool_stats = {
            str(row.matricula or "").strip(): {
                "withdraw_count": int(row.total_retiradas or 0),
                "withdraw_qty": cls._safe_float(row.total_quantidade),
                "return_count": int(row.total_devolvidas or 0),
                "return_qty": cls._safe_float(row.total_quantidade_devolvida),
                "open_count": int(row.total_abertas or 0),
            }
            for row in (
                db.session.query(
                    RetiradaFerramenta.matricula.label("matricula"),
                    func.count(RetiradaFerramenta.id).label("total_retiradas"),
                    func.sum(RetiradaFerramenta.quantidade).label("total_quantidade"),
                    func.sum(case((RetiradaFerramenta.status == "devolvida", 1), else_=0)).label("total_devolvidas"),
                    func.sum(case((RetiradaFerramenta.status == "devolvida", RetiradaFerramenta.quantidade), else_=0)).label("total_quantidade_devolvida"),
                    func.sum(case((RetiradaFerramenta.status.in_(["em_uso", "atrasada", "para_reparo"]), 1), else_=0)).label("total_abertas"),
                )
                .group_by(RetiradaFerramenta.matricula)
                .all()
            )
        }

        candidates = set(material_outputs) | set(material_returns) | set(tool_stats)
        if not candidates:
            return None

        user_map = {
            user.matricula: user
            for user in Usuario.query.filter(Usuario.matricula.in_(list(candidates))).all()
        }

        selected: dict[str, Any] | None = None
        selected_key: tuple[float, float, float] | None = None
        for matricula in candidates:
            output_data = material_outputs.get(matricula, {})
            return_data = material_returns.get(matricula, {})
            tool_data = tool_stats.get(matricula, {})

            expected_events = int(output_data.get("count") or 0) + int(tool_data.get("withdraw_count") or 0)
            if expected_events <= 0:
                continue

            returned_events = min(int(return_data.get("count") or 0), int(output_data.get("count") or 0))
            returned_events += min(int(tool_data.get("return_count") or 0), int(tool_data.get("withdraw_count") or 0))
            pending_events = max(expected_events - returned_events, 0)
            if expected_events < 3 and pending_events <= 0:
                continue

            expected_qty = cls._safe_float(output_data.get("quantity")) + cls._safe_float(tool_data.get("withdraw_qty"))
            returned_qty = min(cls._safe_float(return_data.get("quantity")), cls._safe_float(output_data.get("quantity")))
            returned_qty += min(cls._safe_float(tool_data.get("return_qty")), cls._safe_float(tool_data.get("withdraw_qty")))
            pending_qty = max(expected_qty - returned_qty, 0.0)
            return_rate = (returned_events / expected_events) if expected_events else 1.0
            open_tools = int(tool_data.get("open_count") or 0)
            candidate_key = (return_rate, -float(pending_events), -float(pending_qty + open_tools))

            if selected_key is None or candidate_key < selected_key:
                user = user_map.get(matricula)
                selected = {
                    "matricula": matricula,
                    "nome": cls._normalize_text(getattr(user, "nome", None)) or matricula or "Colaborador",
                    "return_rate": return_rate,
                    "expected_events": expected_events,
                    "returned_events": returned_events,
                    "pending_events": pending_events,
                    "pending_qty": pending_qty,
                    "open_tools": open_tools,
                }
                selected_key = candidate_key

        if not selected:
            return None

        pending_parts = []
        if selected["pending_qty"] > 0:
            pending_parts.append(f"{cls._format_quantity(selected['pending_qty'])} unidade(s) pendentes")
        if selected["open_tools"] > 0:
            pending_parts.append(f"{cls._format_integer(selected['open_tools'])} ferramenta(s) ainda abertas")
        pending_text = " e ".join(pending_parts) if pending_parts else f"{cls._format_integer(selected['pending_events'])} retorno(s) em aberto"
        photo_path = ToolCustodyService.get_employee_photo_path(selected["matricula"] or "")

        return {
            "id": f"low-return-{selected['matricula'] or 'sem-matricula'}",
            "domain": "devolucao",
            "tone": "warning",
            "icon": "bi-arrow-counterclockwise",
            "kicker": "Quem menos devolve",
            "title": f"{selected['nome']} está com o menor índice de devolução",
            "text": f"Só {cls._format_integer(selected['returned_events'])} de {cls._format_integer(selected['expected_events'])} devoluções esperadas foram concluídas. Ainda restam {pending_text}.",
            "primary_label": "Índice de devolução",
            "primary_value": f"{round(float(selected['return_rate']) * 100)}%",
            "secondary_label": "Pendências",
            "secondary_value": cls._format_integer(selected["pending_events"]),
            "source_label": "Saídas, devoluções de material e ferramentas",
            **cls._build_photo_payload(photo_path=photo_path, alt=selected["nome"], badge="Acompanhar"),
        }

    @classmethod
    def _bucket_context_rows(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            value = cls._safe_float(row.get("valor_total"))
            quantity = cls._safe_float(row.get("quantidade_base"))
            context_label = (
                cls._normalize_text(row.get("centro_custo"))
                or cls._normalize_text(row.get("atividade_estruturada_label"))
                or cls._normalize_text(row.get("atividade_label"))
                or cls._normalize_text(row.get("local"))
                or "Operação geral"
            )
            bucket = buckets.setdefault(
                context_label,
                {
                    "label": context_label,
                    "value": 0.0,
                    "count": 0,
                    "quantity": 0.0,
                    "top_item_code": None,
                    "top_item_description": None,
                    "top_item_value": 0.0,
                },
            )
            bucket["value"] += value
            bucket["count"] += 1
            bucket["quantity"] += quantity
            if value >= float(bucket.get("top_item_value") or 0.0):
                bucket["top_item_code"] = row.get("codigo_item")
                bucket["top_item_description"] = row.get("descricao_item")
                bucket["top_item_value"] = value

        return sorted(buckets.values(), key=lambda bucket: (-float(bucket.get("value") or 0.0), -int(bucket.get("count") or 0)))

    @classmethod
    def _inventory_valuation_summary(cls) -> dict[str, Any]:
        cached = cls._get_cached("mirror-insights:inventory-valuation")
        if cached is not None:
            return dict(cached)

        items = inventory_service.list_items()
        tracked_items = []
        total_purchase = 0.0
        total_replacement = 0.0
        missing_replacement = 0
        top_item: dict[str, Any] | None = None
        top_value = -1.0

        for item in items:
            saldo = cls._safe_float(item.get("saldo"))
            if saldo <= 0:
                continue

            tracked_items.append(item)
            purchase_value = cls._safe_float(item.get("valor_estoque_compra_total"))
            replacement_value = cls._safe_float(item.get("valor_estoque_reposicao_total"))
            total_purchase += purchase_value
            total_replacement += replacement_value
            if replacement_value <= 0:
                missing_replacement += 1

            candidate_value = replacement_value or purchase_value
            if candidate_value > top_value:
                top_item = item
                top_value = candidate_value

        payload = {
            "tracked_count": len(tracked_items),
            "total_purchase": round(total_purchase, 2),
            "total_replacement": round(total_replacement, 2),
            "missing_replacement": missing_replacement,
            "top_item": top_item,
        }
        return cls._set_cached("mirror-insights:inventory-valuation", dict(payload), ttl_seconds=15.0)

    @classmethod
    def _build_month_context_insight(cls, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        buckets = cls._bucket_context_rows(rows)
        if not buckets:
            return None
        top_bucket = buckets[0]
        item = Item.query.get(top_bucket.get("top_item_code")) if top_bucket.get("top_item_code") else None
        value = cls._safe_float(top_bucket.get("value"))
        quantity = cls._safe_float(top_bucket.get("quantity"))

        if value > 0:
            text = f"Foram consumidos {cls._format_currency(value)} em materiais neste mês, puxados por {cls._normalize_text(top_bucket.get('top_item_description')) or 'itens operacionais'}."
            primary_label = "Valor do mês"
            primary_value = cls._format_currency(value)
        else:
            text = f"O contexto concentrou {cls._format_quantity(quantity)} unidade(s) movimentadas neste mês, com {cls._format_integer(top_bucket.get('count'))} retiradas registradas."
            primary_label = "Quantidade"
            primary_value = cls._format_quantity(quantity)

        return {
            "id": f"month-context-{cls._normalize_text(top_bucket.get('label')).lower().replace(' ', '-')}",
            "domain": "setor",
            "tone": "success",
            "icon": "bi-graph-up-arrow",
            "kicker": "Setor que mais consome",
            "title": f"{top_bucket.get('label')} lidera o consumo do mês",
            "text": text,
            "primary_label": primary_label,
            "primary_value": primary_value,
            "secondary_label": "Retiradas",
            "secondary_value": cls._format_integer(top_bucket.get("count")),
            "source_label": "Saídas do mês por setor operacional",
            **cls._build_photo_payload(item=item, alt=top_bucket.get("top_item_description"), badge="Item-chave"),
        }

    @classmethod
    def _build_low_context_insight(cls, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        buckets = cls._bucket_context_rows(rows)
        if len(buckets) < 2:
            return None

        low_bucket = sorted(
            buckets,
            key=lambda bucket: (float(bucket.get("value") or 0.0), int(bucket.get("count") or 0), str(bucket.get("label") or "")),
        )[0]
        item = Item.query.get(low_bucket.get("top_item_code")) if low_bucket.get("top_item_code") else None

        return {
            "id": f"low-context-{cls._normalize_text(low_bucket.get('label')).lower().replace(' ', '-')}",
            "domain": "setor",
            "tone": "neutral",
            "icon": "bi-graph-down-arrow",
            "kicker": "Setor que menos consome",
            "title": f"{low_bucket.get('label')} está com giro menor",
            "text": f"No mês atual, o setor soma {cls._format_currency(low_bucket.get('value'))} e {cls._format_integer(low_bucket.get('count'))} retirada(s), com {cls._format_quantity(low_bucket.get('quantity'))} unidade(s) movimentadas.",
            "primary_label": "Gasto do mês",
            "primary_value": cls._format_currency(low_bucket.get("value")),
            "secondary_label": "Retiradas",
            "secondary_value": cls._format_integer(low_bucket.get("count")),
            "source_label": "Saídas do mês por setor operacional",
            **cls._build_photo_payload(item=item, alt=low_bucket.get("top_item_description"), badge="Baixo giro"),
        }

    @classmethod
    def _build_top_item_insight(cls, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            code = cls._normalize_text(row.get("codigo_item"))
            if not code:
                continue
            bucket = buckets.setdefault(
                code,
                {
                    "codigo_item": code,
                    "descricao_item": cls._normalize_text(row.get("descricao_item")) or code,
                    "count": 0,
                    "quantity": 0.0,
                    "value": 0.0,
                },
            )
            bucket["count"] += 1
            bucket["quantity"] += cls._safe_float(row.get("quantidade_base"))
            bucket["value"] += cls._safe_float(row.get("valor_total"))

        if not buckets:
            return None
        top_bucket = sorted(buckets.values(), key=lambda bucket: (-int(bucket.get("count") or 0), -float(bucket.get("value") or 0.0)))[0]
        item = Item.query.get(top_bucket.get("codigo_item")) if top_bucket.get("codigo_item") else None
        descricao = cls._normalize_text(top_bucket.get("descricao_item")) or top_bucket.get("codigo_item") or "Item"

        return {
            "id": f"top-item-{top_bucket.get('codigo_item')}",
            "domain": "consumo",
            "tone": "accent",
            "icon": "bi-box-seam",
            "kicker": "Item em evidência",
            "title": f"{descricao} é o item mais acionado",
            "text": f"Foram {cls._format_integer(top_bucket.get('count'))} retiradas no mês, somando {cls._format_quantity(top_bucket.get('quantity'))} unidade(s) movimentadas.",
            "primary_label": "Retiradas",
            "primary_value": cls._format_integer(top_bucket.get("count")),
            "secondary_label": "Volume",
            "secondary_value": cls._format_quantity(top_bucket.get("quantity")),
            "source_label": "Monitor analítico de consumo",
            **cls._build_photo_payload(item=item, alt=descricao, badge="Mais demandado"),
        }

    @classmethod
    def _build_low_item_insight(cls, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            code = cls._normalize_text(row.get("codigo_item"))
            if not code:
                continue
            bucket = buckets.setdefault(
                code,
                {
                    "codigo_item": code,
                    "descricao_item": cls._normalize_text(row.get("descricao_item")) or code,
                    "count": 0,
                    "quantity": 0.0,
                    "value": 0.0,
                },
            )
            bucket["count"] += 1
            bucket["quantity"] += cls._safe_float(row.get("quantidade_base"))
            bucket["value"] += cls._safe_float(row.get("valor_total"))

        if len(buckets) < 2:
            return None

        low_bucket = sorted(
            buckets.values(),
            key=lambda bucket: (int(bucket.get("count") or 0), float(bucket.get("value") or 0.0), str(bucket.get("descricao_item") or "")),
        )[0]
        item = Item.query.get(low_bucket.get("codigo_item")) if low_bucket.get("codigo_item") else None
        descricao = cls._normalize_text(low_bucket.get("descricao_item")) or low_bucket.get("codigo_item") or "Item"

        return {
            "id": f"low-item-{low_bucket.get('codigo_item')}",
            "domain": "consumo",
            "tone": "neutral",
            "icon": "bi-hourglass-bottom",
            "kicker": "O que menos consome",
            "title": f"{descricao} está com o menor giro do mês",
            "text": f"Até agora o item apareceu em {cls._format_integer(low_bucket.get('count'))} retirada(s), somando {cls._format_quantity(low_bucket.get('quantity'))} unidade(s) movimentadas.",
            "primary_label": "Retiradas",
            "primary_value": cls._format_integer(low_bucket.get("count")),
            "secondary_label": "Volume",
            "secondary_value": cls._format_quantity(low_bucket.get("quantity")),
            "source_label": "Monitor analítico de consumo",
            **cls._build_photo_payload(item=item, alt=descricao, badge="Baixo giro"),
        }

    @classmethod
    def _build_month_employee_insight(cls, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            employee_id = cls._normalize_text(row.get("matricula"))
            employee_name = cls._normalize_text(row.get("colaborador_nome")) or employee_id
            if not employee_id and not employee_name:
                continue
            key = employee_id or employee_name
            bucket = buckets.setdefault(
                key,
                {
                    "matricula": employee_id,
                    "nome": employee_name or "Colaborador",
                    "count": 0,
                    "value": 0.0,
                },
            )
            bucket["count"] += 1
            bucket["value"] += cls._safe_float(row.get("valor_total"))

        if not buckets:
            return None
        top_bucket = sorted(buckets.values(), key=lambda bucket: (-int(bucket.get("count") or 0), -float(bucket.get("value") or 0.0)))[0]
        photo_path = ToolCustodyService.get_employee_photo_path(top_bucket.get("matricula") or "") if top_bucket.get("matricula") else None
        nome = top_bucket.get("nome") or "Colaborador"

        return {
            "id": f"month-employee-{top_bucket.get('matricula') or nome}",
            "domain": "colaborador",
            "tone": "info",
            "icon": "bi-people-fill",
            "kicker": "Ritmo operacional",
            "title": f"{nome} concentrou mais retiradas no mês",
            "text": f"O colaborador respondeu por {cls._format_integer(top_bucket.get('count'))} retiradas no período atual, mantendo ritmo operacional acima da média.",
            "primary_label": "Retiradas no mês",
            "primary_value": cls._format_integer(top_bucket.get("count")),
            "secondary_label": "Valor vinculado",
            "secondary_value": cls._format_currency(top_bucket.get("value")),
            "source_label": "Saídas do mês atual",
            **cls._build_photo_payload(photo_path=photo_path, alt=nome, badge="Equipe"),
        }

    @classmethod
    def _build_stock_value_insight(cls) -> dict[str, Any] | None:
        summary = cls._inventory_valuation_summary()
        if int(summary.get("tracked_count") or 0) <= 0:
            return None

        top_item = summary.get("top_item") if isinstance(summary.get("top_item"), dict) else None

        return {
            "id": "stock-estimated-value",
            "domain": "estoque",
            "tone": "info",
            "icon": "bi-cash-stack",
            "kicker": "Valor estimado de estoque",
            "title": "O estoque atual já tem valuation operacional",
            "text": f"A base disponível representa {cls._format_currency(summary.get('total_replacement'))} em reposição e {cls._format_currency(summary.get('total_purchase'))} em valor de compra estimado.",
            "primary_label": "Reposição estimada",
            "primary_value": cls._format_currency(summary.get("total_replacement")),
            "secondary_label": "Itens com saldo",
            "secondary_value": cls._format_integer(summary.get("tracked_count")),
            "source_label": (
                f"Estoque físico valorizado • {cls._format_integer(summary.get('missing_replacement'))} item(ns) sem preço de reposição"
                if int(summary.get("missing_replacement") or 0) > 0
                else "Estoque físico valorizado"
            ),
            **cls._build_photo_payload(
                photo_path=str((top_item or {}).get("foto_path") or "") or None,
                alt=str((top_item or {}).get("descricao") or "Estoque"),
                badge="Estoque",
            ),
        }

    @classmethod
    def _build_month_replenishment_insight(cls, entry_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not entry_rows:
            summary = cls._inventory_valuation_summary()
            return {
                "id": "month-replenishment-empty",
                "domain": "reposicao",
                "tone": "neutral",
                "icon": "bi-arrow-repeat",
                "kicker": "Reposição do mês",
                "title": "Ainda não houve entrada de reposição neste mês",
                "text": f"Nenhuma entrada de reposição foi consolidada no período atual. O estoque disponível sustenta hoje um valor estimado de {cls._format_currency(summary.get('total_replacement'))} em reposição.",
                "primary_label": "Entradas do mês",
                "primary_value": "0",
                "secondary_label": "Reposição estimada",
                "secondary_value": cls._format_currency(summary.get("total_replacement")),
                "source_label": "Entradas do mês atual",
                "photo_url": None,
                "photo_alt": None,
                "photo_badge": None,
            }

        total_value = round(sum(cls._safe_float(row.get("valor_total")) for row in entry_rows), 2)
        total_quantity = round(sum(cls._safe_float(row.get("quantidade")) for row in entry_rows), 3)
        lead_row = max(entry_rows, key=lambda row: (cls._safe_float(row.get("valor_total")), cls._safe_float(row.get("quantidade"))), default=None)
        if lead_row is None:
            return None

        codigo_item = cls._normalize_text(lead_row.get("codigo_item"))
        item = Item.query.get(codigo_item) if codigo_item else None
        descricao = cls._normalize_text(lead_row.get("descricao_item")) or codigo_item or "Item"

        return {
            "id": "month-replenishment",
            "domain": "reposicao",
            "tone": "success",
            "icon": "bi-arrow-repeat",
            "kicker": "Reposição do mês",
            "title": "Entradas do mês reforçam a operação",
            "text": f"As reposições do período já somam {cls._format_currency(total_value)}, com destaque para {descricao} entre as últimas entradas consolidadas.",
            "primary_label": "Valor em reposição",
            "primary_value": cls._format_currency(total_value),
            "secondary_label": "Quantidade lançada",
            "secondary_value": cls._format_quantity(total_quantity),
            "source_label": "Entradas do mês atual",
            **cls._build_photo_payload(item=item, alt=descricao, badge="Reposição"),
        }

    @classmethod
    def _fallback_insight(cls) -> dict[str, Any]:
        return {
            "id": "fallback-empty",
            "domain": "geral",
            "tone": "neutral",
            "icon": "bi-stars",
            "kicker": "Painel operacional",
            "title": "Aguardando base para destaques automáticos",
            "text": "Assim que o histórico de saídas e custódia ganhar volume suficiente, os informativos rotativos aparecem aqui sem interromper a operação ao vivo.",
            "primary_label": "Status",
            "primary_value": "Em preparação",
            "secondary_label": "Rotação",
            "secondary_value": f"{cls.ROTATION_SECONDS}s",
            "source_label": "Painel espelho local",
            "photo_url": None,
            "photo_alt": None,
            "photo_badge": None,
        }

    @classmethod
    def build_payload(cls, *, mode: str | None = None) -> dict[str, Any]:
        normalized_mode = cls._normalize_text(mode).lower()
        cache_key = f"mirror-insights:{normalized_mode}"
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return dict(cached)

        snapshot = cls._current_month_snapshot()
        rows = list(snapshot.get("rows") or [])
        entry_rows = list(snapshot.get("entry_rows") or [])
        insights = [
            cls._build_overdue_tool_insight(),
            cls._build_low_return_employee_insight(),
            cls._build_top_withdrawer_insight(),
            cls._build_month_context_insight(rows),
            cls._build_low_context_insight(rows),
            cls._build_top_item_insight(rows),
            cls._build_low_item_insight(rows),
            cls._build_month_employee_insight(rows),
            cls._build_stock_value_insight(),
            cls._build_month_replenishment_insight(entry_rows),
        ]
        filtered = [entry for entry in insights if entry]
        if not filtered:
            filtered = [cls._fallback_insight()]

        if normalized_mode == "ferramenta":
            priority = {
                "custodia": 0,
                "devolucao": 1,
                "colaborador": 2,
                "reposicao": 3,
                "estoque": 4,
                "setor": 5,
                "consumo": 6,
                "geral": 7,
            }
            filtered.sort(key=lambda entry: (priority.get(str(entry.get("domain") or "geral"), 9), str(entry.get("title") or "")))

        payload = {
            "rotation_seconds": cls.ROTATION_SECONDS,
            "generated_at": datetime.utcnow().isoformat(),
            "items": filtered,
        }
        return cls._set_cached(cache_key, dict(payload), ttl_seconds=30.0)


mirror_insights_service = MirrorInsightsService()