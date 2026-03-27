from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from io import BytesIO
from typing import Any
import calendar
import re
from time import monotonic

import requests
from flask import current_app
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import (
    DocumentoEntradaEstoque,
    DocumentoEntradaEstoqueItem,
    FinanceConfig,
    FinanceLedgerEntry,
    FinanceSupplier,
    FinanceSupplierPreference,
    Item,
    Saida,
    StockBalance,
    StockMovement,
)


class FinanceService:
    """Serviço de fornecedores, exercício financeiro e prestação de contas."""

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
        cls._runtime_cache[key] = (monotonic() + ttl_seconds, value)
        return value

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
        min_ledger_dt, max_ledger_dt = db.session.query(
            func.min(FinanceLedgerEntry.data_lancamento),
            func.max(FinanceLedgerEntry.data_lancamento),
        ).one()
        min_saida_dt, max_saida_dt = db.session.query(
            func.min(Saida.data_saida),
            func.max(Saida.data_saida),
        ).one()

        min_dt_candidates = [dt for dt in (min_ledger_dt, min_saida_dt) if dt is not None]
        max_dt_candidates = [dt for dt in (max_ledger_dt, max_saida_dt) if dt is not None]
        min_dt = min(min_dt_candidates) if min_dt_candidates else None
        max_dt = max(max_dt_candidates) if max_dt_candidates else None
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

        clean = (label or "").strip()
        match = re.match(r"^(\d{4})\/(\d{4})$", clean)
        if match:
            start_year = int(match.group(1))
            end_year = int(match.group(2))
            config = FinanceService.get_config()
            closing_month = int(config.mes_fechamento or 2)
            closing_day = int(config.dia_fechamento or 10)
            end_date = FinanceService._clamped_closing_date(end_year, closing_month, closing_day)
            previous_closing = FinanceService._clamped_closing_date(start_year, closing_month, closing_day)
            start_date = previous_closing + timedelta(days=1)
            return {
                "label": f"{start_date.year}/{end_date.year}",
                "start_date": start_date,
                "end_date": end_date,
                "start_dt": datetime.combine(start_date, time.min),
                "end_dt": datetime.combine(end_date, time.max),
                "closing_day": closing_day,
                "closing_month": closing_month,
            }

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
        cache_key = f"list_suppliers:{int(limit)}"
        cached = FinanceService._get_cached(cache_key)
        if cached is not None:
            return [dict(row) for row in cached]

        rows = (
            FinanceSupplier.query
            .order_by(FinanceSupplier.ativo.desc(), FinanceSupplier.nome_fantasia.asc(), FinanceSupplier.razao_social.asc())
            .limit(limit)
            .all()
        )
        payload = [row.to_dict() for row in rows]
        return FinanceService._set_cached(cache_key, [dict(row) for row in payload], ttl_seconds=20.0)

    @staticmethod
    def get_supplier(supplier_id: int | None) -> FinanceSupplier | None:
        if not supplier_id:
            return None
        return FinanceSupplier.query.get(int(supplier_id))

    @staticmethod
    def get_supplier_by_cnpj(cnpj: str | None) -> FinanceSupplier | None:
        normalized = FinanceService.normalize_cnpj(cnpj)
        if not normalized:
            return None
        return FinanceSupplier.query.filter(FinanceSupplier.cnpj == normalized).first()

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
    def _resolve_supplier_for_document(
        *,
        supplier_id: int | None = None,
        supplier_name: str | None = None,
        supplier_cnpj: str | None = None,
    ) -> FinanceSupplier | None:
        name = (supplier_name or "").strip() or None
        cnpj = FinanceService.normalize_cnpj(supplier_cnpj) or None

        if supplier_id:
            supplier = FinanceService.get_supplier(supplier_id)
            if not supplier:
                raise ValueError("Fornecedor informado não foi encontrado")
            return supplier

        if cnpj:
            existing = FinanceSupplier.query.filter(FinanceSupplier.cnpj == cnpj).first()
            if existing:
                return existing

            payload: dict[str, Any] = {}
            try:
                payload = FinanceService.fetch_supplier_by_cnpj(cnpj)
            except Exception:
                if not name:
                    raise ValueError("CNPJ não cadastrado e sem nome da loja para criar o fornecedor")

            if name and not payload.get("nome_fantasia"):
                payload["nome_fantasia"] = name
            if name and not payload.get("razao_social"):
                payload["razao_social"] = name
            payload["cnpj"] = cnpj
            return FinanceService.save_supplier(payload)

        if name:
            return FinanceService.save_supplier({"razao_social": name, "nome_fantasia": name})

        return None

    @staticmethod
    def _serialize_stock_document(document: DocumentoEntradaEstoque) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        total_quantidade = 0.0
        total_valor = 0.0
        for row in sorted(document.itens, key=lambda item: item.id_documento_item):
            line_total = float(row.valor_total or 0)
            total_quantidade += float(row.quantidade or 0)
            total_valor += line_total
            items.append(
                {
                    "id": row.id_documento_item,
                    "entrada_id": row.entrada_id,
                    "stock_movement_id": row.stock_movement_id,
                    "operation_log_id": row.operation_log_id,
                    "codigo": row.codigo_item,
                    "descricao": row.item.descricao if row.item else "",
                    "quantidade": row.quantidade,
                    "valor_unitario": row.valor_unitario,
                    "valor_total": row.valor_total,
                    "lote": row.lote,
                    "data_validade": row.data_validade,
                    "observacao": row.observacao,
                    "status_processamento": row.status_processamento,
                    "processado_em": row.processado_em.isoformat() if row.processado_em else None,
                    "erro_processamento": row.erro_processamento,
                }
            )

        supplier_name = document.fornecedor.nome_exibicao() if document.fornecedor else document.nome_emitente()
        status_integracao = (document.status_integracao or "manual").strip() or "manual"
        mensagem_integracao = (document.mensagem_integracao or "").strip() or None
        return {
            "id_documento": document.id_documento,
            "nota_fiscal": document.numero_documento,
            "numero_documento": document.numero_documento,
            "tipo_documento": document.tipo_documento,
            "data": document.criado_em,
            "data_emissao": document.data_emissao,
            "data_recebimento": document.data_recebimento,
            "movimenta_estoque": bool(document.movimenta_estoque) if document.movimenta_estoque is not None else True,
            "chave_acesso": document.chave_acesso,
            "fornecedor_id": document.fornecedor_id,
            "fornecedor_nome": supplier_name,
            "cnpj_emitente": document.cnpj_emitente,
            "observacao": document.observacao,
            "status_integracao": status_integracao,
            "mensagem_integracao": mensagem_integracao,
            "usuarios": [document.criado_por] if document.criado_por else [],
            "itens": items,
            "total_itens": len(items),
            "total_quantidade": round(total_quantidade, 2),
            "total_valor": round(total_valor, 2),
        }

    @staticmethod
    def list_stock_documents(limit: int = 100) -> list[dict[str, Any]]:
        cache_key = f"list_stock_documents:{int(limit)}"
        cached = FinanceService._get_cached(cache_key)
        if cached is not None:
            return [dict(row) for row in cached]

        rows = (
            DocumentoEntradaEstoque.query
            .options(
                joinedload(DocumentoEntradaEstoque.fornecedor),
                joinedload(DocumentoEntradaEstoque.itens).joinedload(DocumentoEntradaEstoqueItem.item),
            )
            .order_by(DocumentoEntradaEstoque.criado_em.desc(), DocumentoEntradaEstoque.id_documento.desc())
            .limit(limit)
            .all()
        )
        payload = [FinanceService._serialize_stock_document(row) for row in rows]
        return FinanceService._set_cached(cache_key, [dict(row) for row in payload], ttl_seconds=8.0)

    @staticmethod
    def get_stock_document_by_number(numero_documento: str) -> dict[str, Any] | None:
        numero = (numero_documento or "").strip()
        if not numero:
            return None
        cache_key = f"get_stock_document_by_number:{numero}"
        cached = FinanceService._get_cached(cache_key)
        if cached is not None:
            return dict(cached)

        row = (
            DocumentoEntradaEstoque.query
            .options(
                joinedload(DocumentoEntradaEstoque.fornecedor),
                joinedload(DocumentoEntradaEstoque.itens).joinedload(DocumentoEntradaEstoqueItem.item),
            )
            .filter(DocumentoEntradaEstoque.numero_documento == numero)
            .order_by(DocumentoEntradaEstoque.criado_em.desc(), DocumentoEntradaEstoque.id_documento.desc())
            .first()
        )
        if not row:
            return None
        payload = FinanceService._serialize_stock_document(row)
        return FinanceService._set_cached(cache_key, dict(payload), ttl_seconds=8.0)

    @staticmethod
    def search_stock_documents(query: str, limit: int = 8) -> list[dict[str, Any]]:
        term = (query or "").strip()
        if not term:
            return []
        like = f"%{term}%"
        rows = (
            DocumentoEntradaEstoque.query
            .options(joinedload(DocumentoEntradaEstoque.fornecedor))
            .filter(DocumentoEntradaEstoque.numero_documento.ilike(like))
            .order_by(DocumentoEntradaEstoque.criado_em.desc(), DocumentoEntradaEstoque.id_documento.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id_documento": row.id_documento,
                "numero_documento": row.numero_documento,
                "tipo_documento": row.tipo_documento,
                "fornecedor_id": row.fornecedor_id,
                "fornecedor_nome": row.fornecedor.nome_exibicao() if row.fornecedor else row.nome_emitente(),
                "cnpj_emitente": row.cnpj_emitente,
                "data_emissao": row.data_emissao.isoformat() if row.data_emissao else None,
                "data_recebimento": row.data_recebimento.isoformat() if row.data_recebimento else None,
            }
            for row in rows
        ]

    @staticmethod
    def _document_reconciliation_query(
        *,
        numero_documento: str,
        tipo_documento: str | None = None,
        data_emissao: date | None = None,
    ):
        numero = (numero_documento or "").strip()
        if not numero:
            return None

        query = (
            DocumentoEntradaEstoque.query
            .options(joinedload(DocumentoEntradaEstoque.itens))
            .filter(DocumentoEntradaEstoque.numero_documento == numero)
        )
        tipo = (tipo_documento or "").strip() or None
        if tipo:
            query = query.filter(DocumentoEntradaEstoque.tipo_documento == tipo)
        if data_emissao is not None:
            query = query.filter(DocumentoEntradaEstoque.data_emissao == data_emissao)
        return query.order_by(DocumentoEntradaEstoque.id_documento.desc())

    @staticmethod
    def get_document_item_reconciliation(
        *,
        codigo_item: str,
        numero_documento: str,
        tipo_documento: str | None = None,
        data_emissao: date | None = None,
    ) -> dict[str, Any] | None:
        codigo = (codigo_item or "").strip()
        query = FinanceService._document_reconciliation_query(
            numero_documento=numero_documento,
            tipo_documento=tipo_documento,
            data_emissao=data_emissao,
        )
        if not codigo or query is None:
            return None

        documents = query.all()
        if not documents:
            return None

        documented_quantity = 0.0
        linked_quantity = 0.0
        matching_rows = 0
        for document in documents:
            for row in document.itens:
                if str(row.codigo_item or "").strip() != codigo:
                    continue
                matching_rows += 1
                quantity = float(row.quantidade or 0.0)
                documented_quantity += quantity
                if row.entrada_id is not None or row.stock_movement_id is not None or (row.status_processamento or "").strip().lower() == "processado":
                    linked_quantity += quantity

        return {
            "document": documents[0],
            "document_count": len(documents),
            "matching_rows": matching_rows,
            "documented_quantity": round(documented_quantity, 6),
            "linked_quantity": round(linked_quantity, 6),
            "pending_quantity": round(documented_quantity - linked_quantity, 6),
        }

    @staticmethod
    def validate_document_backed_stock_entry(
        *,
        codigo_item: str,
        quantidade: float,
        numero_documento: str,
        tipo_documento: str | None = None,
        data_emissao: date | None = None,
        allow_new_document_item: bool = False,
    ) -> dict[str, Any]:
        qty = float(quantidade or 0.0)
        if qty <= 0:
            raise ValueError("Informe uma quantidade válida para conferência documental")

        reconciliation = FinanceService.get_document_item_reconciliation(
            codigo_item=codigo_item,
            numero_documento=numero_documento,
            tipo_documento=tipo_documento,
            data_emissao=data_emissao,
        )
        if reconciliation is None:
            if allow_new_document_item:
                return {
                    "document": None,
                    "document_count": 0,
                    "matching_rows": 0,
                    "documented_quantity": 0.0,
                    "linked_quantity": 0.0,
                    "pending_quantity": 0.0,
                }
            raise ValueError("Documento fiscal não encontrado para conciliar a entrada. Registre o documento primeiro.")

        if int(reconciliation.get("matching_rows") or 0) <= 0:
            if allow_new_document_item:
                return reconciliation
            raise ValueError("O item não existe no documento informado. Cadastre o item correto no documento fiscal antes de entrar no estoque.")

        documented_quantity = float(reconciliation.get("documented_quantity") or 0.0)
        pending_quantity = float(reconciliation.get("pending_quantity") or 0.0)
        tolerance = 1e-6

        if documented_quantity <= tolerance:
            raise ValueError("O documento informado não possui quantidade documental disponível para este item.")

        if pending_quantity <= tolerance:
            raise ValueError("A quantidade deste item já foi totalmente conciliada com o documento informado.")

        if qty - pending_quantity > tolerance:
            raise ValueError(
                f"Quantidade maior que o saldo documental pendente. Pendente no documento: {pending_quantity:g}."
            )

        return reconciliation

    @staticmethod
    def register_stock_document_entry(
        *,
        codigo_item: str,
        quantidade: float,
        tipo_documento: str,
        numero_documento: str,
        data_emissao: date | None = None,
        data_recebimento: date | None = None,
        chave_acesso: str | None = None,
        supplier_id: int | None = None,
        supplier_name: str | None = None,
        supplier_cnpj: str | None = None,
        entrada_id: int | None = None,
        valor_unitario: float | None = None,
        lote: str | None = None,
        data_validade: date | None = None,
        observacao: str | None = None,
        usuario_matricula: str | None = None,
        origem_valor: str | None = None,
        document_only: bool = False,
        movimenta_estoque: bool | None = None,
    ) -> dict[str, Any]:
        codigo = (codigo_item or "").strip()
        numero = (numero_documento or "").strip()
        tipo = (tipo_documento or "nf").strip() or "nf"
        if not codigo:
            raise ValueError("Informe o item da entrada")
        if not numero:
            raise ValueError("Informe o número do documento")

        supplier = FinanceService._resolve_supplier_for_document(
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            supplier_cnpj=supplier_cnpj,
        )
        chave = (chave_acesso or "").strip() or None
        cnpj = supplier.cnpj if supplier and supplier.cnpj else (FinanceService.normalize_cnpj(supplier_cnpj) or None)
        supplier_display = supplier.nome_exibicao() if supplier else ((supplier_name or "").strip() or None)
        status_integracao = "aguardando_certificado" if chave and tipo == "nf" else "manual"
        mensagem_integracao = (
            "Consulta automática bloqueada até a configuração do certificado digital."
            if chave and tipo == "nf"
            else None
        )
        movimenta_estoque_documento = True if movimenta_estoque is None else bool(movimenta_estoque)

        document_query = DocumentoEntradaEstoque.query.filter(
            DocumentoEntradaEstoque.tipo_documento == tipo,
            DocumentoEntradaEstoque.numero_documento == numero,
        )
        if cnpj:
            document_query = document_query.filter(DocumentoEntradaEstoque.cnpj_emitente == cnpj)
        elif supplier:
            document_query = document_query.filter(DocumentoEntradaEstoque.fornecedor_id == supplier.id)

        document = document_query.order_by(DocumentoEntradaEstoque.id_documento.desc()).first()
        if not document:
            document = DocumentoEntradaEstoque(
                fornecedor_id=supplier.id if supplier else None,
                tipo_documento=tipo,
                numero_documento=numero,
                data_emissao=data_emissao,
                data_recebimento=data_recebimento,
                movimenta_estoque=movimenta_estoque_documento,
                chave_acesso=chave,
                cnpj_emitente=cnpj,
                fornecedor_nome=supplier_display,
                observacao=(observacao or "").strip() or None,
                status_integracao=status_integracao,
                mensagem_integracao=mensagem_integracao,
                criado_por=usuario_matricula,
            )
            db.session.add(document)
            db.session.flush()
        else:
            if movimenta_estoque is not None:
                document.movimenta_estoque = movimenta_estoque_documento
            if supplier and not document.fornecedor_id:
                document.fornecedor_id = supplier.id
            if cnpj and not document.cnpj_emitente:
                document.cnpj_emitente = cnpj
            if supplier_display and not document.fornecedor_nome:
                document.fornecedor_nome = supplier_display
            if data_emissao and not document.data_emissao:
                document.data_emissao = data_emissao
            if data_recebimento and not document.data_recebimento:
                document.data_recebimento = data_recebimento
            if chave and not document.chave_acesso:
                document.chave_acesso = chave
            if observacao and not document.observacao:
                document.observacao = observacao.strip() or None
            if chave and tipo == "nf" and (document.status_integracao or "manual") == "manual":
                document.status_integracao = "aguardando_certificado"
                document.mensagem_integracao = mensagem_integracao

        qty = float(quantidade or 0)
        unit = float(valor_unitario) if valor_unitario not in (None, "") else None
        total = round(unit * qty, 2) if unit is not None else None
        linked_entry_id = None if document_only else entrada_id
        item_row = DocumentoEntradaEstoqueItem(
            documento_id=document.id_documento,
            entrada_id=linked_entry_id,
            codigo_item=codigo,
            quantidade=qty,
            valor_unitario=unit,
            valor_total=total,
            lote=(lote or "").strip() or None,
            data_validade=data_validade,
            observacao=(observacao or "").strip() or None,
            status_processamento="processado" if linked_entry_id is not None else "pendente",
            processado_em=datetime.utcnow() if linked_entry_id is not None else None,
        )
        db.session.add(item_row)
        db.session.commit()

        if supplier:
            FinanceService.set_item_supplier_preference(
                codigo,
                supplier.id,
                origem=origem_valor,
                atualizado_por=usuario_matricula,
            )

        return {
            "document": document,
            "document_item": item_row,
            "supplier": supplier,
        }

    @staticmethod
    def process_stock_document_item(
        documento_item_id: int,
        *,
        usuario_matricula: str | None = None,
    ) -> dict[str, Any]:
        from .inventory_engine import inventory_engine
        from .operation_log_service import operation_log_service

        item_row = (
            DocumentoEntradaEstoqueItem.query
            .options(
                joinedload(DocumentoEntradaEstoqueItem.item),
                joinedload(DocumentoEntradaEstoqueItem.documento),
            )
            .filter(DocumentoEntradaEstoqueItem.id_documento_item == documento_item_id)
            .first()
        )
        if item_row is None:
            raise ValueError("Item do documento fiscal não encontrado.")

        documento = item_row.documento
        if documento is not None and not bool(getattr(documento, "movimenta_estoque", True)):
            return {
                "success": True,
                "processed": False,
                "skipped": True,
                "reason": "movimenta_estoque_desativado",
                "documento_item_id": item_row.id_documento_item,
                "stock_movement_id": item_row.stock_movement_id,
                "operation_log_id": item_row.operation_log_id,
            }

        recovered = FinanceService._recover_document_item_movement(item_row)
        if recovered is not None:
            return recovered

        if item_row.stock_movement_id is not None or item_row.entrada_id is not None:
            if (item_row.status_processamento or "").strip().lower() != "processado":
                item_row.status_processamento = "processado"
                item_row.processado_em = item_row.processado_em or datetime.utcnow()
                item_row.erro_processamento = None
                db.session.commit()
            return {
                "success": True,
                "processed": False,
                "skipped": True,
                "reason": "already_processed",
                "documento_item_id": item_row.id_documento_item,
                "stock_movement_id": item_row.stock_movement_id,
                "operation_log_id": item_row.operation_log_id,
            }

        if item_row.item is None:
            raise ValueError("O item vinculado ao documento não existe mais no estoque.")

        quantidade = float(item_row.quantidade or 0.0)
        if quantidade <= 0:
            raise ValueError("Quantidade documental inválida para processamento de estoque.")

        documento = item_row.documento
        from_unit = (item_row.item.unidade or "Unidade").strip() or "Unidade"
        metadata = {
            "source": "documento_fiscal",
            "channel": "documento_fiscal",
            "reference_type": "entrada_documento_item",
            "reference_id": str(item_row.id_documento_item),
            "documento_id": item_row.documento_id,
            "documento_item_id": item_row.id_documento_item,
            "numero_documento": documento.numero_documento if documento else None,
            "tipo_documento": documento.tipo_documento if documento else None,
            "user_id": usuario_matricula,
            "matricula": usuario_matricula,
            "observacao": item_row.observacao or (documento.observacao if documento else None),
        }

        try:
            item_row.status_processamento = "processando"
            item_row.erro_processamento = None
            db.session.flush()

            result = inventory_engine.register_entry(
                product_id=item_row.codigo_item,
                quantity=quantidade,
                from_unit=from_unit,
                metadata=metadata,
                commit=False,
                write_audit=True,
            )

            item_row.stock_movement_id = result.movement_id
            item_row.operation_log_id = result.operation_log_id
            item_row.status_processamento = "processado"
            item_row.processado_em = datetime.utcnow()
            item_row.erro_processamento = None
            db.session.commit()

            telegram_result = operation_log_service.notify_telegram(result.operation_log_id)
            return {
                "success": True,
                "processed": True,
                "skipped": False,
                "documento_item_id": item_row.id_documento_item,
                "stock_movement_id": result.movement_id,
                "operation_log_id": result.operation_log_id,
                "telegram": telegram_result,
            }
        except Exception as exc:
            db.session.rollback()
            failed_row = db.session.get(DocumentoEntradaEstoqueItem, documento_item_id)
            if failed_row is not None:
                failed_row.status_processamento = "erro"
                failed_row.erro_processamento = str(exc)[:4000]
                failed_row.processado_em = None
                db.session.commit()
            raise

    @staticmethod
    def reverse_and_delete_document_item(
        item_row: DocumentoEntradaEstoqueItem,
        *,
        usuario_matricula: str | None = None,
    ) -> dict[str, Any]:
        from .inventory_engine import inventory_engine

        if item_row is None:
            raise ValueError("Item do documento fiscal não encontrado.")

        if (item_row.status_processamento or "").strip().lower() != "processado":
            raise ValueError("A exclusão com estorno só se aplica a itens já processados.")

        stock_movement = item_row.stock_movement or (
            db.session.get(StockMovement, item_row.stock_movement_id)
            if item_row.stock_movement_id is not None
            else None
        )
        if stock_movement is None:
            raise ValueError("Não foi possível localizar o movimento de estoque para estorno.")

        quantity_base = abs(float(stock_movement.quantity_base or 0.0))
        if quantity_base <= 0:
            raise ValueError("Quantidade inválida para estornar a exclusão do item.")

        unit_base = (stock_movement.unit_base or "").strip() or (
            (item_row.item.unidade or "").strip() if item_row.item is not None else ""
        ) or "Unidade"

        documento = item_row.documento
        metadata = {
            "source": "documento_fiscal",
            "channel": "documento_fiscal",
            "reference_type": "entrada_documento_item_exclusao",
            "reference_id": str(item_row.id_documento_item),
            "documento_id": item_row.documento_id,
            "documento_item_id": item_row.id_documento_item,
            "numero_documento": documento.numero_documento if documento else None,
            "tipo_documento": documento.tipo_documento if documento else None,
            "user_id": usuario_matricula,
            "matricula": usuario_matricula,
            "observacao": item_row.observacao or (documento.observacao if documento else None),
            "origin_movement_id": stock_movement.id,
            "origin_movement_type": stock_movement.movement_type,
        }

        result = inventory_engine.register_exit(
            product_id=item_row.codigo_item,
            quantity=quantity_base,
            from_unit=unit_base,
            metadata=metadata,
            commit=False,
            write_audit=True,
        )

        return {
            "success": True,
            "reversed": True,
            "documento_item_id": item_row.id_documento_item,
            "stock_movement_id": result.movement_id,
            "operation_log_id": result.operation_log_id,
            "balance_before": result.balance_before,
            "balance_after": result.balance_after,
            "quantity_base": result.quantity_base,
            "unit_base": result.unit_base,
        }

    @staticmethod
    def delete_document_item_for_typo(
        item_row: DocumentoEntradaEstoqueItem,
        *,
        usuario_matricula: str | None = None,
    ) -> dict[str, Any]:
        if item_row is None:
            raise ValueError("Item do documento fiscal não encontrado.")

        if (item_row.status_processamento or "").strip().lower() != "processado":
            raise ValueError("A exclusão por erro de digitação é destinada a itens já processados.")

        result = FinanceService.reverse_and_delete_document_item(
            item_row,
            usuario_matricula=usuario_matricula,
        )
        result["reason"] = "erro_digitacao"
        return result

    @staticmethod
    def _recover_document_item_movement(item_row: DocumentoEntradaEstoqueItem) -> dict[str, Any] | None:
        existing_movements = (
            StockMovement.query
            .filter(
                StockMovement.reference_type == "entrada_documento_item",
                StockMovement.reference_id == str(item_row.id_documento_item),
                StockMovement.product_id == item_row.codigo_item,
            )
            .order_by(StockMovement.id.asc())
            .all()
        )
        if not existing_movements:
            return None

        canonical = existing_movements[0]
        duplicate_signature = {
            (
                movement.product_id,
                movement.movement_type,
                float(movement.quantity_base or 0.0),
                (movement.unit_base or "").strip().lower(),
                movement.reference_type,
                movement.reference_id,
            )
            for movement in existing_movements
        }
        if len(duplicate_signature) > 1:
            raise ValueError(
                f"Item documental {item_row.id_documento_item} possui múltiplos movimentos divergentes no ledger."
            )

        for duplicate in existing_movements[1:]:
            db.session.delete(duplicate)

        total_quantity = (
            db.session.query(func.coalesce(func.sum(StockMovement.quantity_base), 0.0))
            .filter(StockMovement.product_id == item_row.codigo_item)
            .scalar()
        )
        balance = db.session.get(StockBalance, item_row.codigo_item)
        if balance is None:
            balance = StockBalance(product_id=item_row.codigo_item)
            db.session.add(balance)
        balance.quantity_base = float(total_quantity or 0.0)

        item_row.stock_movement_id = canonical.id
        item_row.status_processamento = "processado"
        item_row.processado_em = item_row.processado_em or datetime.utcnow()
        item_row.erro_processamento = None
        db.session.commit()
        return {
            "success": True,
            "processed": False,
            "skipped": True,
            "reason": "recovered_existing_movement",
            "documento_item_id": item_row.id_documento_item,
            "stock_movement_id": canonical.id,
            "operation_log_id": item_row.operation_log_id,
        }

    @staticmethod
    def process_stock_document_entries(
        documento_id: int,
        *,
        usuario_matricula: str | None = None,
        only_pending: bool = True,
    ) -> dict[str, Any]:
        documento = (
            DocumentoEntradaEstoque.query
            .options(joinedload(DocumentoEntradaEstoque.itens).joinedload(DocumentoEntradaEstoqueItem.item))
            .filter(DocumentoEntradaEstoque.id_documento == documento_id)
            .first()
        )
        if documento is None:
            raise ValueError("Documento fiscal não encontrado.")

        if not bool(getattr(documento, "movimenta_estoque", True)):
            return {
                "processed": 0,
                "skipped": len(documento.itens),
                "errors": 0,
                "messages": ["Documento configurado para lançamento financeiro sem movimentar estoque."],
            }

        processed = 0
        skipped = 0
        errors = 0
        messages: list[str] = []

        for row in sorted(documento.itens, key=lambda item: item.id_documento_item):
            status = (row.status_processamento or "pendente").strip().lower() or "pendente"
            if only_pending and status == "processado":
                skipped += 1
                continue
            try:
                result = FinanceService.process_stock_document_item(
                    row.id_documento_item,
                    usuario_matricula=usuario_matricula,
                )
                if result.get("processed"):
                    processed += 1
                else:
                    skipped += 1
            except Exception as exc:
                errors += 1
                messages.append(f"{row.codigo_item}: {str(exc)}")

        return {
            "processed": processed,
            "skipped": skipped,
            "errors": errors,
            "messages": messages,
        }

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
        chave_acesso: str | None = None,
        data_emissao_documento: date | None = None,
        data_recebimento_documento: date | None = None,
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
            chave_acesso=(chave_acesso or "").strip() or None,
            data_emissao_documento=data_emissao_documento,
            data_recebimento_documento=data_recebimento_documento,
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
        cache_key = f"get_stock_value_report:{exercise['label']}"
        cached = FinanceService._get_cached(cache_key)
        if cached is not None:
            return dict(cached)

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

        # Consumo fracionado por local (rastreabilidade): usa litros/kg registrados na saída.
        # Regra de custo: preço da embalagem (média do exercício quando disponível) / capacidade interna (L ou Kg).
        fracionado_por_local: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "local": "SEM LOCAL",
            "total_valor": 0.0,
            "total_litros": 0.0,
            "total_quilos": 0.0,
            "saidas": 0,
            "itens": set(),
        })
        total_fracionado_valor = 0.0
        total_fracionado_litros = 0.0
        total_fracionado_quilos = 0.0
        fracionado_linhas_ignoradas = 0

        def _norm_local(value: str | None) -> str:
            norm = (value or "").strip().upper()
            return norm or "SEM LOCAL"

        for saida in saidas:
            code = str(saida.codigo_item or "").strip()
            if not code:
                continue

            retirada_l = getattr(saida, "quantidade_retirada_em_litros", None)
            retirada_kg = getattr(saida, "quantidade_retirada_em_quilos", None)
            if retirada_l in (None, "") and retirada_kg in (None, ""):
                continue

            item = item_map.get(code)
            if not item:
                fracionado_linhas_ignoradas += 1
                continue

            purchase = purchases_by_item.get(code, {})
            preco_emb = purchase.get("avg_unit")
            if preco_emb is None:
                raw_price = item.get("preco_compra_unitario")
                preco_emb = float(raw_price) if raw_price not in (None, "") else 0.0
            preco_emb = float(preco_emb or 0.0)
            if preco_emb <= 0:
                fracionado_linhas_ignoradas += 1
                continue

            capacidade_emb = getattr(saida, "quantidade_total_embalagem", None)
            try:
                capacidade_emb_f = float(capacidade_emb) if capacidade_emb not in (None, "") else 0.0
            except Exception:
                capacidade_emb_f = 0.0

            unidade = None
            qtd_interna = 0.0
            if retirada_l not in (None, ""):
                unidade = "L"
                try:
                    qtd_interna = float(retirada_l or 0.0)
                except Exception:
                    qtd_interna = 0.0
                if capacidade_emb_f <= 0:
                    try:
                        capacidade_emb_f = float(item.get("litros_por_embalagem") or 0.0)
                    except Exception:
                        capacidade_emb_f = 0.0
            elif retirada_kg not in (None, ""):
                unidade = "Kg"
                try:
                    qtd_interna = float(retirada_kg or 0.0)
                except Exception:
                    qtd_interna = 0.0
                if capacidade_emb_f <= 0:
                    try:
                        capacidade_emb_f = float(item.get("grandeza_referencia") or 0.0)
                    except Exception:
                        capacidade_emb_f = 0.0

            if not unidade or qtd_interna <= 0 or capacidade_emb_f <= 0:
                fracionado_linhas_ignoradas += 1
                continue

            custo_interno = preco_emb / capacidade_emb_f
            valor = round(qtd_interna * custo_interno, 2)
            local_key = _norm_local(getattr(saida, "local_servico", None))

            row = fracionado_por_local[local_key]
            row["local"] = local_key
            row["total_valor"] += valor
            row["saidas"] += 1
            row["itens"].add(code)
            if unidade == "L":
                row["total_litros"] += qtd_interna
                total_fracionado_litros += qtd_interna
            else:
                row["total_quilos"] += qtd_interna
                total_fracionado_quilos += qtd_interna
            total_fracionado_valor += valor

        consumo_fracionado_por_local: list[dict[str, Any]] = []
        for info in fracionado_por_local.values():
            consumo_fracionado_por_local.append({
                "local": info["local"],
                "total_valor": round(float(info["total_valor"] or 0.0), 2),
                "total_litros": round(float(info["total_litros"] or 0.0), 3),
                "total_quilos": round(float(info["total_quilos"] or 0.0), 3),
                "saidas": int(info["saidas"] or 0),
                "itens": len(info["itens"] or set()),
            })
        consumo_fracionado_por_local.sort(key=lambda r: (-float(r.get("total_valor") or 0.0), str(r.get("local") or "")))

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

        report = {
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
            "consumo_fracionado_por_local": consumo_fracionado_por_local,
            "total_fracionado_valor": round(total_fracionado_valor, 2),
            "total_fracionado_litros": round(total_fracionado_litros, 3),
            "total_fracionado_quilos": round(total_fracionado_quilos, 3),
            "fracionado_linhas_ignoradas": int(fracionado_linhas_ignoradas),
        }
        return FinanceService._set_cached(cache_key, dict(report), ttl_seconds=10.0)

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

        # Consumo fracionado por local (quando existir)
        fr_rows = summary.get("consumo_fracionado_por_local") or []
        if fr_rows:
            story.append(Paragraph("Consumo fracionado por local (L/Kg)", styles["Heading2"]))
            story.append(Spacer(1, 0.2 * cm))
            local_table_data: list[list[Any]] = [["Local", "Litros", "Kg", "Saídas", "Itens", "Total (R$)"]]
            for row in fr_rows:
                local_table_data.append([
                    row.get("local") or "SEM LOCAL",
                    f"{float(row.get('total_litros') or 0.0):g}",
                    f"{float(row.get('total_quilos') or 0.0):g}",
                    str(int(row.get("saidas") or 0)),
                    str(int(row.get("itens") or 0)),
                    f"R$ {float(row.get('total_valor') or 0.0):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                ])

            local_table = Table(local_table_data, repeatRows=1, colWidths=[7.5 * cm, 2.3 * cm, 2.3 * cm, 1.8 * cm, 1.6 * cm, 3.2 * cm])
            local_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ]))
            story.append(local_table)
            story.append(Spacer(1, 0.35 * cm))

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

    @staticmethod
    def get_supplier_lab_report(exercise_label: str | None = None) -> dict[str, Any]:
        """Relatório de 'Laboratório de Lojas': cruzamentos por fornecedor.

        Base de dados:
        - Fornecedores: FinanceSupplier
        - Compras/documentos: FinanceLedgerEntry (tipo_documento/número_documento)

        Observação:
        - Lançamentos sem fornecedor permanecem no Financeiro (não aparecem por loja).
        """
        exercise = FinanceService.resolve_exercise(exercise_label)

        supplier_rows = (
            FinanceSupplier.query
            .order_by(FinanceSupplier.ativo.desc(), FinanceSupplier.nome_fantasia.asc().nullslast(), FinanceSupplier.razao_social.asc())
            .all()
        )
        suppliers: list[dict[str, Any]] = []
        supplier_map: dict[int, dict[str, Any]] = {}
        for s in supplier_rows:
            payload = s.to_dict()
            payload.update({
                "investido_total": 0.0,
                "sem_comprovacao_total": 0.0,
                "itens_distintos": 0,
                "documentos_distintos": 0,
                "nf_total": 0,
                "cupom_total": 0,
                "ult_compra_em": None,
                "categoria_breakdown": [],
                "monthly_series": [],
                "documentos": [],
                "produtos": [],
                "variacoes_preco": [],
            })
            suppliers.append(payload)
            supplier_map[int(s.id)] = payload

        entries = (
            FinanceLedgerEntry.query
            .options(joinedload(FinanceLedgerEntry.fornecedor), joinedload(FinanceLedgerEntry.item))
            .filter(FinanceLedgerEntry.data_lancamento >= exercise["start_dt"])
            .filter(FinanceLedgerEntry.data_lancamento <= exercise["end_dt"])
            .filter(FinanceLedgerEntry.fornecedor_id.isnot(None))
            .order_by(FinanceLedgerEntry.data_lancamento.desc())
            .all()
        )

        # Totais do exercício sem loja (ficam no Financeiro)
        sem_loja_total = (
            db.session.query(func.sum(FinanceLedgerEntry.valor_total))
            .filter(FinanceLedgerEntry.data_lancamento >= exercise["start_dt"])
            .filter(FinanceLedgerEntry.data_lancamento <= exercise["end_dt"])
            .filter(FinanceLedgerEntry.fornecedor_id.is_(None))
            .scalar()
        )
        sem_loja_total = float(sem_loja_total or 0.0)

        # Estruturas auxiliares
        by_supplier_items: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
        by_supplier_docs: dict[int, dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)
        by_supplier_cat: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        by_supplier_month: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        by_supplier_sets: dict[int, dict[str, Any]] = defaultdict(lambda: {
            "itens": set(),
            "docs": set(),
        })

        # Cruzamento global para comparação entre lojas (mesmo item)
        global_item_by_supplier: dict[str, dict[int, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: {"investido": 0.0, "quantidade": 0.0}))
        global_item_desc: dict[str, str] = {}

        for e in entries:
            if not e.fornecedor_id:
                continue
            supplier_id = int(e.fornecedor_id)
            supplier = supplier_map.get(supplier_id)
            if not supplier:
                continue

            valor_total = float(e.valor_total or 0.0)
            supplier["investido_total"] += valor_total
            if (e.comprovacao_status or "").strip() != "comprovado":
                supplier["sem_comprovacao_total"] += valor_total

            if e.data_lancamento and (supplier.get("ult_compra_em") is None or e.data_lancamento > supplier["ult_compra_em"]):
                supplier["ult_compra_em"] = e.data_lancamento

            codigo_item = (e.codigo_item or "").strip()
            if codigo_item:
                by_supplier_sets[supplier_id]["itens"].add(codigo_item)

            categoria = (e.categoria_nome or (e.item.categoria if e.item else None) or "Sem categoria").strip() or "Sem categoria"
            by_supplier_cat[supplier_id][categoria] += valor_total

            month_key = "—"
            if e.data_lancamento:
                month_key = f"{e.data_lancamento.year:04d}-{e.data_lancamento.month:02d}"
            by_supplier_month[supplier_id][month_key] += valor_total

            tipo_doc = (e.tipo_documento or "").strip().lower() or "—"
            numero_doc = (e.numero_documento or "").strip()
            if numero_doc:
                doc_key = (tipo_doc, numero_doc)
                by_supplier_sets[supplier_id]["docs"].add(doc_key)
                doc = by_supplier_docs[supplier_id].get(doc_key)
                if not doc:
                    doc = {
                        "tipo": tipo_doc,
                        "numero": numero_doc,
                        "total": 0.0,
                        "itens": set(),
                        "entradas": 0,
                        "data": e.data_lancamento,
                    }
                    by_supplier_docs[supplier_id][doc_key] = doc
                doc["total"] += valor_total
                doc["entradas"] += 1
                if codigo_item:
                    doc["itens"].add(codigo_item)
                if e.data_lancamento and (doc.get("data") is None or e.data_lancamento > doc["data"]):
                    doc["data"] = e.data_lancamento

            # Produtos e variação de preço (por loja)
            if codigo_item:
                item_stats = by_supplier_items[supplier_id].get(codigo_item)
                if not item_stats:
                    desc = (e.item.descricao if e.item else None) or codigo_item
                    item_stats = {
                        "codigo": codigo_item,
                        "descricao": desc,
                        "total": 0.0,
                        "quantidade": 0.0,
                        "min_unit": None,
                        "max_unit": None,
                        "last_date": None,
                        "compras": 0,
                    }
                    by_supplier_items[supplier_id][codigo_item] = item_stats
                item_stats["total"] += valor_total
                item_stats["compras"] += 1
                if e.data_lancamento and (item_stats["last_date"] is None or e.data_lancamento > item_stats["last_date"]):
                    item_stats["last_date"] = e.data_lancamento

                try:
                    qtd = float(e.quantidade or 0.0)
                except Exception:
                    qtd = 0.0
                item_stats["quantidade"] += qtd

                if e.valor_unitario is not None:
                    try:
                        vu = float(e.valor_unitario)
                    except Exception:
                        vu = None
                    if vu is not None and vu > 0:
                        if item_stats["min_unit"] is None or vu < float(item_stats["min_unit"]):
                            item_stats["min_unit"] = vu
                        if item_stats["max_unit"] is None or vu > float(item_stats["max_unit"]):
                            item_stats["max_unit"] = vu

                        # Global (comparação entre lojas)
                        global_item_desc.setdefault(codigo_item, item_stats["descricao"])
                        global_item_by_supplier[codigo_item][supplier_id]["investido"] += valor_total
                        global_item_by_supplier[codigo_item][supplier_id]["quantidade"] += max(qtd, 0.0)

        # Finalização por fornecedor
        total_investido_com_loja = 0.0
        total_sem_comprovacao_com_loja = 0.0
        total_docs = 0
        total_itens_distintos = set()

        for sid, supplier in supplier_map.items():
            supplier["investido_total"] = round(float(supplier["investido_total"] or 0.0), 2)
            supplier["sem_comprovacao_total"] = round(float(supplier["sem_comprovacao_total"] or 0.0), 2)
            supplier["itens_distintos"] = len(by_supplier_sets[sid]["itens"]) if sid in by_supplier_sets else 0
            supplier["documentos_distintos"] = len(by_supplier_sets[sid]["docs"]) if sid in by_supplier_sets else 0
            total_investido_com_loja += float(supplier["investido_total"] or 0.0)
            total_sem_comprovacao_com_loja += float(supplier["sem_comprovacao_total"] or 0.0)
            total_docs += int(supplier["documentos_distintos"] or 0)
            total_itens_distintos.update(by_supplier_sets[sid]["itens"]) if sid in by_supplier_sets else None

            # categoria pie
            cats = by_supplier_cat.get(sid, {})
            cat_rows = [
                {"categoria": name, "total": round(float(total or 0.0), 2)}
                for name, total in cats.items()
                if float(total or 0.0) > 0
            ]
            cat_rows.sort(key=lambda r: -float(r.get("total") or 0.0))
            supplier["categoria_breakdown"] = cat_rows[:12]

            # monthly series
            months = by_supplier_month.get(sid, {})
            month_rows = [
                {"month": m, "total": round(float(total or 0.0), 2)}
                for m, total in months.items()
                if m and m != "—"
            ]
            month_rows.sort(key=lambda r: str(r.get("month") or ""))
            supplier["monthly_series"] = month_rows

            # documentos
            docs_map = by_supplier_docs.get(sid, {})
            docs_rows: list[dict[str, Any]] = []
            for (tipo, numero), doc in docs_map.items():
                docs_rows.append({
                    "tipo": tipo,
                    "numero": numero,
                    "total": round(float(doc.get("total") or 0.0), 2),
                    "itens": len(doc.get("itens") or set()),
                    "entradas": int(doc.get("entradas") or 0),
                    "data": doc.get("data"),
                })
            docs_rows.sort(key=lambda r: (r.get("data") or datetime.min), reverse=True)
            supplier["documentos"] = docs_rows[:60]
            supplier["nf_total"] = sum(1 for row in docs_rows if str(row.get("tipo") or "").lower() == "nf")
            supplier["cupom_total"] = sum(1 for row in docs_rows if str(row.get("tipo") or "").lower() == "cupom")

            # produtos
            item_rows: list[dict[str, Any]] = []
            variacoes: list[dict[str, Any]] = []
            for code, st in (by_supplier_items.get(sid) or {}).items():
                qty = float(st.get("quantidade") or 0.0)
                total = float(st.get("total") or 0.0)
                avg = (total / qty) if qty > 0 else None
                min_u = st.get("min_unit")
                max_u = st.get("max_unit")
                var_pct = None
                if min_u is not None and max_u is not None and float(min_u) > 0 and float(max_u) > float(min_u):
                    var_pct = ((float(max_u) / float(min_u)) - 1.0) * 100.0
                    variacoes.append({
                        "codigo": st.get("codigo"),
                        "descricao": st.get("descricao"),
                        "min_unit": round(float(min_u), 2),
                        "max_unit": round(float(max_u), 2),
                        "var_pct": round(float(var_pct), 1),
                        "compras": int(st.get("compras") or 0),
                    })

                item_rows.append({
                    "codigo": st.get("codigo"),
                    "descricao": st.get("descricao"),
                    "total": round(total, 2),
                    "quantidade": round(qty, 3),
                    "avg_unit": round(float(avg), 2) if avg is not None else None,
                    "min_unit": round(float(min_u), 2) if min_u is not None else None,
                    "max_unit": round(float(max_u), 2) if max_u is not None else None,
                    "last_date": st.get("last_date"),
                    "compras": int(st.get("compras") or 0),
                })

            item_rows.sort(key=lambda r: -float(r.get("total") or 0.0))
            supplier["produtos"] = item_rows[:80]
            variacoes.sort(key=lambda r: (-float(r.get("var_pct") or 0.0), -int(r.get("compras") or 0)))
            supplier["variacoes_preco"] = variacoes[:30]

        # Comparação entre lojas (mesmo item) — top itens por valor, quando houver +1 loja
        cross_items: list[dict[str, Any]] = []
        for code, by_sup in global_item_by_supplier.items():
            if len(by_sup) < 2:
                continue
            total_item = sum(float(v.get("investido") or 0.0) for v in by_sup.values())
            cross_items.append({"codigo": code, "descricao": global_item_desc.get(code) or code, "total": total_item, "by_supplier": by_sup})
        cross_items.sort(key=lambda r: -float(r.get("total") or 0.0))

        cross_rows: list[dict[str, Any]] = []
        for row in cross_items[:15]:
            code = str(row.get("codigo") or "")
            by_sup = row.get("by_supplier") or {}
            supplier_prices: list[dict[str, Any]] = []
            for sid, st in by_sup.items():
                inv = float(st.get("investido") or 0.0)
                qty = float(st.get("quantidade") or 0.0)
                avg_unit = (inv / qty) if qty > 0 else None
                supplier_name = (supplier_map.get(int(sid), {}) or {}).get("nome_exibicao")
                supplier_prices.append({
                    "supplier_id": int(sid),
                    "supplier": supplier_name or f"Fornecedor {sid}",
                    "avg_unit": round(float(avg_unit), 2) if avg_unit is not None else None,
                    "total": round(inv, 2),
                })
            supplier_prices.sort(key=lambda r: (r.get("avg_unit") is None, float(r.get("avg_unit") or 0.0)))
            cross_rows.append({
                "codigo": code,
                "descricao": row.get("descricao") or code,
                "total": round(float(row.get("total") or 0.0), 2),
                "suppliers": supplier_prices,
            })

        suppliers = [
            supplier
            for supplier in suppliers
            if float(supplier.get("investido_total") or 0.0) > 0.0
            or int(supplier.get("documentos_distintos") or 0) > 0
            or supplier.get("ult_compra_em") is not None
        ]
        suppliers.sort(key=lambda s: (-float(s.get("investido_total") or 0.0), str(s.get("nome_exibicao") or "").lower()))

        return {
            "exercise": exercise,
            "exercise_options": FinanceService.get_available_exercises(),
            "summary": {
                "total_investido_com_loja": round(float(total_investido_com_loja or 0.0), 2),
                "total_sem_comprovacao_com_loja": round(float(total_sem_comprovacao_com_loja or 0.0), 2),
                "total_sem_loja": round(float(sem_loja_total or 0.0), 2),
                "total_lojas": len(suppliers),
                "total_docs": int(total_docs),
                "total_itens_distintos": int(len(total_itens_distintos)),
            },
            "suppliers": suppliers,
            "comparacao_itens": cross_rows,
        }


finance_service = FinanceService()
