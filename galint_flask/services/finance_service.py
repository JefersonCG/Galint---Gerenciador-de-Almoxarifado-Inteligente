from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from io import BytesIO
from typing import Any
import calendar

import requests
from flask import current_app
from sqlalchemy import func, or_

from ..extensions import db
from ..models import (
    FinanceConfig,
    FinanceLedgerEntry,
    FinanceSupplier,
    FinanceSupplierPreference,
    Item,
    Saida,
)


class FinanceService:
    """Serviço de fornecedores, exercício financeiro e prestação de contas."""

    @staticmethod
    def normalize_cnpj(value: str | None) -> str:
        digits = "".join(ch for ch in (value or "") if ch.isdigit())
        if len(digits) != 14:
            return digits
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"

    @staticmethod
    def _cnpj_digits(value: str | None) -> str:
        return "".join(ch for ch in (value or "") if ch.isdigit())

    @staticmethod
    def get_config() -> FinanceConfig:
        config = FinanceConfig.query.first()
        if not config:
            config = FinanceConfig(
                dia_fechamento=10,
                mes_fechamento=2,
                destacar_sem_comprovacao=True,
                permitir_fechamento_manual=True,
                titulo_relatorio_anual="Prestação de Contas do Almoxarifado",
            )
            db.session.add(config)
            db.session.commit()
        return config

    @staticmethod
    def update_config(data: dict[str, Any]) -> FinanceConfig:
        config = FinanceService.get_config()
        allowed = {
            "dia_fechamento",
            "mes_fechamento",
            "destacar_sem_comprovacao",
            "permitir_fechamento_manual",
            "titulo_relatorio_anual",
        }
        for key in allowed:
            if key in data:
                setattr(config, key, data[key])
        db.session.commit()
        return config

    @staticmethod
    def _clamped_closing_date(year: int, month: int, day: int) -> date:
        max_day = calendar.monthrange(year, month)[1]
        safe_day = max(1, min(day, max_day))
        return date(year, month, safe_day)

    @staticmethod
    def get_exercise_for_date(reference: date | datetime | None = None) -> dict[str, Any]:
        config = FinanceService.get_config()
        if reference is None:
            ref_date = date.today()
        elif isinstance(reference, datetime):
            ref_date = reference.date()
        else:
            ref_date = reference

        current_year_closing = FinanceService._clamped_closing_date(
            ref_date.year,
            int(config.mes_fechamento or 2),
            int(config.dia_fechamento or 10),
        )
        if ref_date <= current_year_closing:
            end_date = current_year_closing
        else:
            end_date = FinanceService._clamped_closing_date(
                ref_date.year + 1,
                int(config.mes_fechamento or 2),
                int(config.dia_fechamento or 10),
            )
        previous_closing = FinanceService._clamped_closing_date(
            end_date.year - 1,
            int(config.mes_fechamento or 2),
            int(config.dia_fechamento or 10),
        )
        start_date = previous_closing + timedelta(days=1)
        return {
            "label": f"{start_date.year}/{end_date.year}",
            "start_date": start_date,
            "end_date": end_date,
            "start_dt": datetime.combine(start_date, time.min),
            "end_dt": datetime.combine(end_date, time.max),
            "closing_day": int(config.dia_fechamento or 10),
            "closing_month": int(config.mes_fechamento or 2),
        }

    @staticmethod
    def get_available_exercises() -> list[dict[str, Any]]:
        min_dt, max_dt = db.session.query(
            func.min(FinanceLedgerEntry.data_lancamento),
            func.max(FinanceLedgerEntry.data_lancamento),
        ).one()
        today = date.today()
        start_ref = (min_dt.date() if min_dt else today)
        end_ref = max(today, max_dt.date() if max_dt else today)

        labels: dict[str, dict[str, Any]] = {}
        cursor_year = start_ref.year - 1
        last_year = end_ref.year + 1
        while cursor_year <= last_year:
            ref = date(cursor_year, 7, 1)
            exercise = FinanceService.get_exercise_for_date(ref)
            labels[exercise["label"]] = exercise
            cursor_year += 1

        current = FinanceService.get_exercise_for_date(today)
        labels[current["label"]] = current
        return sorted(labels.values(), key=lambda item: item["end_date"], reverse=True)

    @staticmethod
    def resolve_exercise(label: str | None = None) -> dict[str, Any]:
        if not label:
            return FinanceService.get_exercise_for_date()
        for exercise in FinanceService.get_available_exercises():
            if exercise["label"] == label:
                return exercise
        return FinanceService.get_exercise_for_date()

    @staticmethod
    def search_suppliers(query: str, limit: int = 10) -> list[dict[str, Any]]:
        term = (query or "").strip()
        if not term:
            return []
        like = f"%{term}%"
        rows = (
            FinanceSupplier.query
            .filter(
                or_(
                    FinanceSupplier.razao_social.ilike(like),
                    FinanceSupplier.nome_fantasia.ilike(like),
                    FinanceSupplier.cnpj.ilike(like),
                )
            )
            .filter(FinanceSupplier.ativo.is_(True))
            .order_by(FinanceSupplier.nome_fantasia.asc(), FinanceSupplier.razao_social.asc())
            .limit(limit)
            .all()
        )
        return [row.to_dict() for row in rows]

    @staticmethod
    def list_suppliers(limit: int = 200) -> list[dict[str, Any]]:
        rows = (
            FinanceSupplier.query
            .order_by(FinanceSupplier.ativo.desc(), FinanceSupplier.nome_fantasia.asc(), FinanceSupplier.razao_social.asc())
            .limit(limit)
            .all()
        )
        return [row.to_dict() for row in rows]

    @staticmethod
    def get_supplier(supplier_id: int | None) -> FinanceSupplier | None:
        if not supplier_id:
            return None
        return FinanceSupplier.query.get(int(supplier_id))

    @staticmethod
    def save_supplier(data: dict[str, Any]) -> FinanceSupplier:
        supplier_id = data.get("id")
        supplier = FinanceSupplier.query.get(int(supplier_id)) if supplier_id else None
        cnpj = FinanceService.normalize_cnpj(data.get("cnpj")) or None
        if cnpj:
            existing = FinanceSupplier.query.filter(FinanceSupplier.cnpj == cnpj).first()
            if existing and (not supplier or existing.id != supplier.id):
                supplier = existing

        if not supplier:
            supplier = FinanceSupplier()
            db.session.add(supplier)

        razao_social = (data.get("razao_social") or "").strip()
        nome_fantasia = (data.get("nome_fantasia") or "").strip()
        if not razao_social:
            razao_social = nome_fantasia
        if not razao_social:
            raise ValueError("Informe a razão social ou nome fantasia do fornecedor")

        supplier.razao_social = razao_social
        supplier.nome_fantasia = nome_fantasia or None
        supplier.cnpj = cnpj
        supplier.inscricao_estadual = (data.get("inscricao_estadual") or "").strip() or None
        supplier.endereco_rua = (data.get("endereco_rua") or "").strip() or None
        supplier.endereco_numero = (data.get("endereco_numero") or "").strip() or None
        supplier.endereco_complemento = (data.get("endereco_complemento") or "").strip() or None
        supplier.endereco_bairro = (data.get("endereco_bairro") or "").strip() or None
        supplier.endereco_cidade = (data.get("endereco_cidade") or "").strip() or None
        supplier.endereco_estado = ((data.get("endereco_estado") or "").strip() or None)
        supplier.endereco_cep = (data.get("endereco_cep") or "").strip() or None
        supplier.telefone = (data.get("telefone") or "").strip() or None
        supplier.email = (data.get("email") or "").strip() or None
        supplier.site = (data.get("site") or "").strip() or None
        supplier.situacao_cadastral = (data.get("situacao_cadastral") or "").strip() or None
        supplier.api_origem = (data.get("api_origem") or "").strip() or None
        supplier.observacoes = (data.get("observacoes") or "").strip() or None
        supplier.ativo = bool(data.get("ativo", True))
        if data.get("data_consulta_cnpj"):
            supplier.data_consulta_cnpj = data["data_consulta_cnpj"]

        db.session.commit()
        return supplier

    @staticmethod
    def fetch_supplier_by_cnpj(cnpj: str) -> dict[str, Any]:
        digits = FinanceService._cnpj_digits(cnpj)
        if len(digits) != 14:
            raise ValueError("CNPJ inválido")

        endpoints = [
            (
                f"https://brasilapi.com.br/api/cnpj/v1/{digits}",
                FinanceService._map_brasilapi_supplier,
                "BrasilAPI",
            ),
        ]

        errors: list[str] = []
        headers = {"Accept": "application/json", "User-Agent": "GALINT/1.0"}
        for url, mapper, source in endpoints:
            try:
                response = requests.get(url, headers=headers, timeout=8)
                if response.status_code >= 400:
                    errors.append(f"{source}: HTTP {response.status_code}")
                    continue
                payload = response.json()
                mapped = mapper(payload)
                mapped["api_origem"] = source
                mapped["data_consulta_cnpj"] = datetime.utcnow()
                return mapped
            except Exception as exc:
                errors.append(f"{source}: {exc}")
                continue
        raise RuntimeError("Falha ao consultar CNPJ. " + " | ".join(errors))

    @staticmethod
    def _map_brasilapi_supplier(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "razao_social": (payload.get("razao_social") or payload.get("nome") or "").strip(),
            "nome_fantasia": (payload.get("nome_fantasia") or "").strip() or None,
            "cnpj": FinanceService.normalize_cnpj(payload.get("cnpj")),
            "inscricao_estadual": None,
            "endereco_rua": (payload.get("logradouro") or "").strip() or None,
            "endereco_numero": (payload.get("numero") or "").strip() or None,
            "endereco_complemento": (payload.get("complemento") or "").strip() or None,
            "endereco_bairro": (payload.get("bairro") or "").strip() or None,
            "endereco_cidade": (payload.get("municipio") or "").strip() or None,
            "endereco_estado": (payload.get("uf") or "").strip() or None,
            "endereco_cep": (payload.get("cep") or "").strip() or None,
            "telefone": (payload.get("ddd_telefone_1") or payload.get("ddd_telefone_2") or "").strip() or None,
            "email": (payload.get("email") or "").strip() or None,
            "situacao_cadastral": (payload.get("descricao_situacao_cadastral") or payload.get("situacao_cadastral") or "").strip() or None,
            "site": None,
            "observacoes": None,
            "ativo": True,
        }

    @staticmethod
    def set_item_supplier_preference(codigo_item: str, supplier_id: int | None, *, origem: str | None = None, atualizado_por: str | None = None) -> None:
        codigo = (codigo_item or "").strip()
        if not codigo:
            return
        existing = FinanceSupplierPreference.query.filter_by(codigo_item=codigo).first()
        if not supplier_id:
            if existing:
                db.session.delete(existing)
                db.session.commit()
            return
        if not existing:
            existing = FinanceSupplierPreference(codigo_item=codigo, fornecedor_id=int(supplier_id))
            db.session.add(existing)
        existing.fornecedor_id = int(supplier_id)
        existing.ultima_origem = (origem or "").strip() or None
        existing.atualizado_por = atualizado_por
        db.session.commit()

    @staticmethod
    def get_item_supplier_preference(codigo_item: str | None) -> dict[str, Any] | None:
        codigo = (codigo_item or "").strip()
        if not codigo:
            return None
        pref = FinanceSupplierPreference.query.filter_by(codigo_item=codigo).first()
        if pref and pref.fornecedor:
            return pref.fornecedor.to_dict()

        latest = (
            FinanceLedgerEntry.query
            .filter(FinanceLedgerEntry.codigo_item == codigo)
            .filter(FinanceLedgerEntry.fornecedor_id.isnot(None))
            .order_by(FinanceLedgerEntry.data_lancamento.desc())
            .first()
        )
        if latest and latest.fornecedor:
            return latest.fornecedor.to_dict()
        return None

    @staticmethod
    def register_financial_entry(
        *,
        codigo_item: str,
        categoria_nome: str,
        quantidade: float,
        valor_unitario: float | None,
        valor_total: float | None = None,
        data_lancamento: datetime | date | None = None,
        fornecedor_id: int | None = None,
        entrada_id: int | None = None,
        usuario_matricula: str | None = None,
        origem_valor: str | None = None,
        tipo_documento: str | None = None,
        numero_documento: str | None = None,
        comprovacao_status: str | None = None,
        observacao: str | None = None,
    ) -> FinanceLedgerEntry | None:
        codigo = (codigo_item or "").strip()
        if not codigo:
            return None
        qty = float(quantidade or 0)
        unit = float(valor_unitario) if valor_unitario not in (None, "") else None
        total = float(valor_total) if valor_total not in (None, "") else None
        if total is None and unit is not None:
            total = round(unit * qty, 2)
        if total is None:
            return None

        when: datetime
        if data_lancamento is None:
            when = datetime.utcnow()
        elif isinstance(data_lancamento, date) and not isinstance(data_lancamento, datetime):
            when = datetime.combine(data_lancamento, time.min)
        else:
            when = data_lancamento

        entry = FinanceLedgerEntry(
            codigo_item=codigo,
            entrada_id=entrada_id,
            fornecedor_id=fornecedor_id,
            usuario_matricula=usuario_matricula,
            categoria_nome=(categoria_nome or "Sem categoria").strip() or "Sem categoria",
            data_lancamento=when,
            quantidade=qty,
            valor_unitario=unit,
            valor_total=round(total, 2),
            origem_valor=(origem_valor or "inventario_inicial").strip() or "inventario_inicial",
            tipo_documento=(tipo_documento or "").strip() or None,
            numero_documento=(numero_documento or "").strip() or None,
            comprovacao_status=(comprovacao_status or "sem_comprovacao").strip() or "sem_comprovacao",
            observacao=(observacao or "").strip() or None,
        )
        db.session.add(entry)
        db.session.commit()

        if fornecedor_id:
            FinanceService.set_item_supplier_preference(
                codigo,
                fornecedor_id,
                origem=origem_valor,
                atualizado_por=usuario_matricula,
            )
        return entry

    @staticmethod
    def get_stock_value_report(exercise_label: str | None = None) -> dict[str, Any]:
        from .inventory import inventory_service

        exercise = FinanceService.resolve_exercise(exercise_label)
        items = [dict(item) for item in inventory_service.list_items()]
        item_map = {str(item.get("codigo")): item for item in items}

        total_compra_atual = 0.0
        total_reposicao_atual = 0.0
        missing_compra = 0
        missing_reposicao = 0
        for item in items:
            vc = item.get("valor_estoque_compra_total")
            vr = item.get("valor_estoque_reposicao_total")
            if vc is None:
                missing_compra += 1
            else:
                total_compra_atual += float(vc or 0)
            if vr is None:
                missing_reposicao += 1
            else:
                total_reposicao_atual += float(vr or 0)

        ledger_entries = (
            FinanceLedgerEntry.query
            .filter(FinanceLedgerEntry.data_lancamento >= exercise["start_dt"])
            .filter(FinanceLedgerEntry.data_lancamento <= exercise["end_dt"])
            .order_by(FinanceLedgerEntry.data_lancamento.desc())
            .all()
        )
        purchases_by_item: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "investido": 0.0,
            "quantidade": 0.0,
            "sem_comprovacao": 0.0,
            "fornecedor_nome": None,
            "avg_unit": None,
        })
        purchases_by_category: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "investido": 0.0,
            "sem_comprovacao": 0.0,
            "fornecedores": defaultdict(float),
        })
        total_investido = 0.0
        total_sem_comprovacao = 0.0
        for entry in ledger_entries:
            code = entry.codigo_item
            item = item_map.get(code)
            category = (entry.categoria_nome or (item.get("categoria") if item else None) or "Sem categoria").strip()
            item_totals = purchases_by_item[code]
            item_totals["investido"] += float(entry.valor_total or 0)
            item_totals["quantidade"] += float(entry.quantidade or 0)
            if entry.fornecedor:
                item_totals["fornecedor_nome"] = entry.fornecedor.nome_exibicao()
            if item_totals["quantidade"] > 0:
                item_totals["avg_unit"] = item_totals["investido"] / item_totals["quantidade"]
            if entry.comprovacao_status != "comprovado":
                item_totals["sem_comprovacao"] += float(entry.valor_total or 0)

            cat_totals = purchases_by_category[category]
            cat_totals["investido"] += float(entry.valor_total or 0)
            if entry.comprovacao_status != "comprovado":
                cat_totals["sem_comprovacao"] += float(entry.valor_total or 0)
            if entry.fornecedor:
                cat_totals["fornecedores"][entry.fornecedor.nome_exibicao()] += float(entry.valor_total or 0)

            total_investido += float(entry.valor_total or 0)
            if entry.comprovacao_status != "comprovado":
                total_sem_comprovacao += float(entry.valor_total or 0)

        saidas = (
            Saida.query
            .filter(Saida.data_saida >= exercise["start_dt"])
            .filter(Saida.data_saida <= exercise["end_dt"])
            .all()
        )
        consumed_by_item: dict[str, float] = defaultdict(float)
        for saida in saidas:
            if saida.codigo_item:
                consumed_by_item[saida.codigo_item] += float(saida.quantidade or 0)

        categories: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "categoria": "Sem categoria",
            "items": [],
            "total_investido": 0.0,
            "total_consumido": 0.0,
            "total_atual_compra": 0.0,
            "total_atual_reposicao": 0.0,
            "total_sem_comprovacao": 0.0,
            "top_item_nome": None,
            "top_item_quantidade": 0.0,
            "top_fornecedor_nome": None,
            "top_fornecedor_total": 0.0,
        })

        total_consumido = 0.0
        for item in items:
            code = str(item.get("codigo") or "")
            category = (item.get("categoria") or "Sem categoria").strip() or "Sem categoria"
            purchase = purchases_by_item.get(code, {})
            consumed_qty = float(consumed_by_item.get(code, 0.0) or 0.0)
            avg_unit = purchase.get("avg_unit")
            if avg_unit is None:
                raw_price = item.get("preco_compra_unitario")
                avg_unit = float(raw_price) if raw_price not in (None, "") else 0.0
            consumed_value = round(consumed_qty * float(avg_unit or 0.0), 2)
            total_consumido += consumed_value

            item["investido_exercicio"] = round(float(purchase.get("investido") or 0.0), 2)
            item["consumo_quantidade_exercicio"] = consumed_qty
            item["consumo_valor_exercicio"] = consumed_value
            item["fornecedor_preferido_nome"] = purchase.get("fornecedor_nome")
            item["sem_comprovacao_valor_exercicio"] = round(float(purchase.get("sem_comprovacao") or 0.0), 2)

            card = categories[category]
            card["categoria"] = category
            card["items"].append(item)
            card["total_investido"] += item["investido_exercicio"]
            card["total_consumido"] += consumed_value
            card["total_atual_compra"] += float(item.get("valor_estoque_compra_total") or 0.0)
            card["total_atual_reposicao"] += float(item.get("valor_estoque_reposicao_total") or 0.0)
            card["total_sem_comprovacao"] += item["sem_comprovacao_valor_exercicio"]
            if consumed_qty > float(card.get("top_item_quantidade") or 0.0):
                card["top_item_quantidade"] = consumed_qty
                card["top_item_nome"] = item.get("descricao")

        for category, info in purchases_by_category.items():
            card = categories[category]
            card["categoria"] = category
            if info["fornecedores"]:
                top_name, top_total = max(info["fornecedores"].items(), key=lambda row: row[1])
                card["top_fornecedor_nome"] = top_name
                card["top_fornecedor_total"] = round(float(top_total or 0.0), 2)

        category_cards = sorted(categories.values(), key=lambda card: card["categoria"].lower())
        for card in category_cards:
            card["items"].sort(key=lambda item: (str(item.get("descricao") or "").lower(), str(item.get("codigo") or "")))

        return {
            "exercise": exercise,
            "exercise_options": FinanceService.get_available_exercises(),
            "items": items,
            "category_cards": category_cards,
            "total_compra": round(total_compra_atual, 2),
            "total_reposicao": round(total_reposicao_atual, 2),
            "missing_compra": missing_compra,
            "missing_reposicao": missing_reposicao,
            "total_investido_exercicio": round(total_investido, 2),
            "total_consumido_exercicio": round(total_consumido, 2),
            "total_sem_comprovacao_exercicio": round(total_sem_comprovacao, 2),
        }

    @staticmethod
    def build_stock_value_pdf(exercise_label: str | None = None) -> BytesIO:
        summary = FinanceService.get_stock_value_report(exercise_label)
        config = FinanceService.get_config()
        company_title = (config.titulo_relatorio_anual or "Prestação de Contas do Almoxarifado").strip()

        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except Exception as exc:
            raise RuntimeError("ReportLab não disponível para gerar PDF") from exc

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.2 * cm, bottomMargin=1.2 * cm)
        styles = getSampleStyleSheet()
        story: list[Any] = []
        exercise = summary["exercise"]
        story.append(Paragraph(company_title, styles["Title"]))
        story.append(Paragraph(
            f"Exercício {exercise['label']} • Período {exercise['start_date'].strftime('%d/%m/%Y')} a {exercise['end_date'].strftime('%d/%m/%Y')}",
            styles["Normal"],
        ))
        story.append(Spacer(1, 0.4 * cm))

        kpi_rows = [
            [
                "Total investido",
                f"R$ {summary['total_investido_exercicio']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                "Total consumido",
                f"R$ {summary['total_consumido_exercicio']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                "Sem comprovação",
                f"R$ {summary['total_sem_comprovacao_exercicio']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            ]
        ]
        kpi_table = Table(kpi_rows, colWidths=[3.2 * cm, 3.5 * cm, 3.2 * cm, 3.5 * cm, 3.2 * cm, 3.5 * cm])
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#0f172a")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#1e293b")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 0.5 * cm))

        header = ["Categoria", "Investido", "Consumido", "Atual compra", "Atual reposição", "Item mais usado", "Fornecedor destaque"]
        rows = [header]
        for card in summary["category_cards"]:
            rows.append([
                card["categoria"],
                f"R$ {card['total_investido']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                f"R$ {card['total_consumido']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                f"R$ {card['total_atual_compra']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                f"R$ {card['total_atual_reposicao']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                card.get("top_item_nome") or "—",
                card.get("top_fornecedor_nome") or "—",
            ])
        table = Table(rows, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(table)
        doc.build(story)
        buffer.seek(0)
        return buffer


finance_service = FinanceService()
