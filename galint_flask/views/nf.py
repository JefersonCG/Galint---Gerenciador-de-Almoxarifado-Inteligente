"""Rotas para lançamento e acompanhamento de notas fiscais."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import Date, and_, cast, func, or_
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import CompraPeriodoFechamento, DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, Entrada, FinanceLedgerEntry, Item, TelegramOutbox
from ..services.category_catalog import DEFAULT_INVENTORY_CATEGORY_NAME, category_catalog_service
from ..services.document_integrity_service import allow_document_quantity_update
from ..services.finance_service import finance_service
from ..services.nf_deletion_audit_sqlite import log_document_item_deletion
from ..services.inventory import BASE_ITEM_UNIT_OPTIONS, ensure_base_item_unit, inventory_service, normalize_base_item_unit
from ..services.price_normalization import (
    infer_document_quantity_unit_for_item,
    normalize_document_line,
    should_autofix_packaged_document_unit,
)

blueprint = Blueprint("nf", __name__, url_prefix="/nf")

DEFAULT_DOCUMENT_UNIT_OPTIONS = list(BASE_ITEM_UNIT_OPTIONS)
NF_NEW_ITEM_PACKAGING_OPTIONS: tuple[str, ...] = (
    "rolo",
    "lata",
    "balde",
    "bombona",
    "caixa",
    "pacote",
    "fardo",
    "saco",
    "litro",
)
NF_NEW_ITEM_DIRECT_DOCUMENT_UNIT_OPTIONS: tuple[str, ...] = (
    "par",
)
NF_NEW_ITEM_DOCUMENT_UNIT_OPTIONS: tuple[str, ...] = (
    *NF_NEW_ITEM_PACKAGING_OPTIONS,
    *NF_NEW_ITEM_DIRECT_DOCUMENT_UNIT_OPTIONS,
)

VALID_OPERATIONAL_TABS = {"registro", "processaveis", "erros", "historico"}
LEGACY_OPERATIONAL_TAB_ALIASES = {
    "pendencias": "processaveis",
}


def _normalize_operational_tab(tab_value: str | None) -> str:
    raw = (tab_value or "").strip().lower()
    return LEGACY_OPERATIONAL_TAB_ALIASES.get(raw, raw)


def _parse_iso_date(raw_value: str | None, *, fallback: date | None = None) -> date | None:
    raw = (raw_value or "").strip()
    if not raw:
        return fallback
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return fallback


def _parse_optional_float(raw_value: str | None, *, fallback: float | None = None) -> float | None:
    raw = (raw_value or "").strip()
    if not raw:
        return fallback
    try:
        return float(raw)
    except ValueError:
        return fallback


def _has_explicit_form_value(raw_value: str | None) -> bool:
    return bool((raw_value or "").strip())


def _normalize_nf_new_item_packaging_type(raw_value: str | None) -> str | None:
    normalized = (raw_value or "").strip().lower()
    if not normalized:
        return None
    if normalized in NF_NEW_ITEM_DOCUMENT_UNIT_OPTIONS:
        return normalized
    raise ValueError("Unidade da compra/NF inválida para o novo item.")


def _build_nf_new_item_packaging_payload(
    *,
    base_unit: str,
    packaging_type: str | None,
    content_per_package: float | None,
) -> dict[str, Any]:
    if not packaging_type:
        return {}

    normalized_base_unit = ensure_base_item_unit(base_unit, fallback="Unidade")
    if packaging_type == "par":
        if normalized_base_unit == "Par":
            return {}
        raise ValueError(
            "Quando a compra/NF vier em Par, use também Par como unidade interna/base do item novo."
        )

    if content_per_package is None or float(content_per_package) <= 0:
        raise ValueError(
            "Informe o conteúdo por embalagem do item novo para que a quantidade da NF não seja interpretada como unidade base."
        )

    content_value = float(content_per_package)
    if packaging_type == "litro" and content_value > 1.0:
        raise ValueError(
            "Para recipientes acima de 1 litro, use Lata, Balde ou Bombona como unidade da compra/NF."
        )

    payload: dict[str, Any] = {
        "tipo_embalagem_novo": packaging_type,
        "unidades_por_embalagem": content_value,
    }
    if normalized_base_unit == "Litro":
        payload["litros_por_embalagem"] = content_value
    elif normalized_base_unit in {"Metro", "Quilo"}:
        payload["grandeza_referencia"] = content_value
    return payload


def _derive_item_total(*, quantidade: float, valor_unitario: float | None) -> float | None:
    if valor_unitario is None:
        return None
    return round(float(quantidade) * float(valor_unitario), 2)


def _derive_item_unit_price(*, quantidade: float, valor_total: float | None) -> float | None:
    if valor_total is None or float(quantidade) <= 0:
        return None
    return round(float(valor_total) / float(quantidade), 6)


def _float_changed(current: float | None, fallback: float | None, *, tolerance: float = 0.01) -> bool:
    if current is None and fallback is None:
        return False
    if current is None or fallback is None:
        return True
    return abs(float(current) - float(fallback)) > tolerance


def _resolve_document_item_values(
    *,
    quantidade: float,
    valor_unitario_raw: str | None,
    valor_total_raw: str | None,
    fallback_valor_unitario: float | None,
    fallback_valor_total: float | None,
) -> tuple[float | None, float | None]:
    has_unit_input = _has_explicit_form_value(valor_unitario_raw)
    has_total_input = _has_explicit_form_value(valor_total_raw)

    if not has_unit_input and not has_total_input:
        return fallback_valor_unitario, fallback_valor_total

    valor_unitario = _parse_optional_float(valor_unitario_raw, fallback=None)
    valor_total = _parse_optional_float(valor_total_raw, fallback=None)

    if has_unit_input and has_total_input:
        if valor_unitario is None and valor_total is None:
            return fallback_valor_unitario, fallback_valor_total
        if valor_unitario is None:
            return _derive_item_unit_price(quantidade=quantidade, valor_total=valor_total), valor_total
        if valor_total is None:
            return valor_unitario, _derive_item_total(quantidade=quantidade, valor_unitario=valor_unitario)

        total_calculado = _derive_item_total(quantidade=quantidade, valor_unitario=valor_unitario)
        if total_calculado is not None and abs(float(total_calculado) - float(valor_total)) <= 0.01:
            return valor_unitario, total_calculado

        unit_changed = _float_changed(valor_unitario, fallback_valor_unitario)
        total_changed = _float_changed(valor_total, fallback_valor_total)
        if total_changed and not unit_changed:
            valor_unitario_derivado = _derive_item_unit_price(quantidade=quantidade, valor_total=valor_total)
            return valor_unitario_derivado if valor_unitario_derivado is not None else valor_unitario, valor_total

        if unit_changed or not total_changed:
            return valor_unitario, total_calculado

        valor_unitario_derivado = _derive_item_unit_price(quantidade=quantidade, valor_total=valor_total)
        return valor_unitario_derivado if valor_unitario_derivado is not None else valor_unitario, valor_total

    if has_unit_input:
        return valor_unitario, _derive_item_total(quantidade=quantidade, valor_unitario=valor_unitario)

    return _derive_item_unit_price(quantidade=quantidade, valor_total=valor_total), valor_total


def _parse_form_checkbox(form_name: str, *, default: bool = False) -> bool:
    values = request.form.getlist(form_name)
    if not values:
        return default
    normalized = [str(value).strip().lower() for value in values]
    truthy = {"1", "true", "on", "yes", "sim"}
    falsy = {"0", "false", "off", "no", "nao", "não"}
    if any(value in truthy for value in normalized):
        return True
    if any(value in falsy for value in normalized):
        return False
    return default


def _validate_document_registration_fields(
    *,
    numero_documento: str,
    tipo_documento: str,
    supplier_id: int | None,
    supplier_name: str | None,
    supplier_cnpj: str | None,
    data_emissao: date | None,
    data_recebimento: date | None,
    comprovacao_status: str | None = None,
    observacao: str | None = None,
) -> None:
    missing_fields: list[str] = []
    tipo_documento_normalizado = (tipo_documento or "").strip().lower()
    if not (numero_documento or "").strip():
        missing_fields.append("número do documento")
    if tipo_documento_normalizado != "manual" and not (supplier_id or (supplier_name or "").strip() or (supplier_cnpj or "").strip()):
        missing_fields.append("fornecedor ou CNPJ da loja")
    if data_recebimento is None:
        missing_fields.append("data de recebimento")
    if tipo_documento_normalizado == "nf" and data_emissao is None:
        missing_fields.append("data de emissão")

    comprovacao = (comprovacao_status or "").strip().lower()
    if comprovacao in {"sem_comprovacao", "parcial"} and not (observacao or "").strip():
        missing_fields.append("observação financeira")

    if missing_fields:
        raise ValueError(
            "Complete o cadastro do documento antes de salvar: " + ", ".join(missing_fields) + "."
        )


def _normalize_requested_document_type(raw_value: str | None, *, fallback: str = "nf") -> str:
    normalized = (raw_value or "").strip().lower()
    if normalized in {"nf", "cupom", "recibo", "manual"}:
        return normalized
    return fallback


def _resolve_registration_document_type(
    *,
    ui_mode: str | None,
    raw_document_type: str | None,
    origem_valor: str | None,
    comprovacao_status: str | None,
    supplier_id: int | None,
    supplier_name: str | None,
    supplier_cnpj: str | None,
    chave_acesso: str | None,
    data_emissao_raw: str | None,
) -> str:
    ui_mode_normalized = _normalize_requested_document_type(ui_mode, fallback="")
    if ui_mode_normalized:
        return ui_mode_normalized

    tipo_documento = _normalize_requested_document_type(raw_document_type, fallback="nf")
    if tipo_documento != "nf":
        return tipo_documento

    origem_normalizada = (origem_valor or "").strip().lower()
    comprovacao_normalizada = (comprovacao_status or "").strip().lower()
    has_supplier = bool(supplier_id or (supplier_name or "").strip() or (supplier_cnpj or "").strip())
    has_emission_date = bool((data_emissao_raw or "").strip())
    has_access_key = bool((chave_acesso or "").strip())

    if (
        origem_normalizada == "valor_estimado"
        and comprovacao_normalizada == "sem_comprovacao"
        and not has_supplier
        and not has_emission_date
        and not has_access_key
    ):
        return "manual"

    return tipo_documento


def _resolve_documento_movimenta_estoque(*, data_emissao: date | None, data_recebimento: date | None) -> bool:
    return finance_service.resolve_document_movimenta_estoque(
        data_emissao=data_emissao,
        data_recebimento=data_recebimento,
    )


def _document_is_ready_for_nf_confirmation(documento: DocumentoEntradaEstoque) -> bool:
    tipo_documento = (documento.tipo_documento or "nf").strip().lower() or "nf"
    if not documento.data_emissao or not documento.data_recebimento:
        return False
    if tipo_documento == "nf" and not (documento.chave_acesso or "").strip():
        return False
    if not documento.itens:
        return False
    return all(
        row.valor_unitario not in (None, "") or row.valor_total not in (None, "")
        for row in documento.itens
    )


def _infer_document_origin(documento: DocumentoEntradaEstoque) -> str | None:
    tipo_documento = (documento.tipo_documento or "nf").strip().lower() or "nf"
    if tipo_documento == "nf":
        return "compra_nf"
    if tipo_documento == "cupom":
        return "compra_cupom"
    return None


def _infer_legacy_item_unit_price(entrada: Entrada) -> float | None:
    item = entrada.item
    if item is not None:
        try:
            item_document = (item.preco_compra_documento or "").strip()
        except AttributeError:
            item_document = ""
        if item_document == (entrada.nota_fiscal or "").strip() and item.preco_compra_unitario not in (None, ""):
            return float(item.preco_compra_unitario)

    ledger_entry = (
        FinanceLedgerEntry.query
        .filter(
            or_(
                FinanceLedgerEntry.entrada_id == entrada.id_entrada,
                FinanceLedgerEntry.numero_documento == entrada.nota_fiscal,
            )
        )
        .filter(FinanceLedgerEntry.codigo_item == entrada.codigo_item)
        .order_by(FinanceLedgerEntry.data_lancamento.desc(), FinanceLedgerEntry.id.desc())
        .first()
    )
    if ledger_entry and ledger_entry.valor_unitario not in (None, ""):
        return float(ledger_entry.valor_unitario)
    return None


def _get_or_create_document_from_legacy_number(numero_documento: str) -> tuple[DocumentoEntradaEstoque, bool, int]:
    numero = (numero_documento or "").strip()
    if not numero:
        raise ValueError("Informe o número do documento legado.")

    entradas = (
        Entrada.query
        .filter(Entrada.nota_fiscal == numero)
        .order_by(Entrada.data_entrada.asc(), Entrada.id_entrada.asc())
        .all()
    )
    if not entradas:
        raise ValueError("Documento legado não encontrado no histórico de entradas.")

    document = (
        DocumentoEntradaEstoque.query
        .filter(DocumentoEntradaEstoque.numero_documento == numero)
        .order_by(DocumentoEntradaEstoque.id_documento.desc())
        .first()
    )
    created = False
    imported_items = 0
    if document is None:
        latest_entry = entradas[-1]
        created = True
        document = DocumentoEntradaEstoque(
            tipo_documento="manual",
            numero_documento=numero,
            data_recebimento=latest_entry.data_entrada.date() if latest_entry.data_entrada else None,
            observacao="Convertido automaticamente do histórico legado de entradas.",
            status_integracao="manual",
            mensagem_integracao=None,
            criado_por=current_user.id,
        )
        db.session.add(document)
        db.session.flush()

    existing_entry_ids = {
        row.entrada_id
        for row in document.itens
        if row.entrada_id is not None
    }
    for entrada in entradas:
        if entrada.id_entrada in existing_entry_ids:
            continue
        unit_price = _infer_legacy_item_unit_price(entrada)
        quantity = float(entrada.quantidade or 0.0)
        total_price = round(quantity * unit_price, 2) if unit_price is not None else None
        db.session.add(
            DocumentoEntradaEstoqueItem(
                documento_id=document.id_documento,
                entrada_id=entrada.id_entrada,
                codigo_item=entrada.codigo_item,
                quantidade=quantity,
                valor_unitario=unit_price,
                valor_total=total_price,
                observacao=None,
            )
        )
        imported_items += 1

    if imported_items and not document.data_recebimento:
        latest_entry = entradas[-1]
        document.data_recebimento = latest_entry.data_entrada.date() if latest_entry.data_entrada else document.data_recebimento

    return document, created, imported_items


def _apply_document_item_normalization(
    item_row: DocumentoEntradaEstoqueItem,
    *,
    quantidade: float,
    valor_unitario: float | None,
    valor_total: float | None,
) -> tuple[float | None, float | None]:
    quantity_value = float(quantidade or 0.0)
    unit_price_value = float(valor_unitario) if valor_unitario not in (None, "") else None
    total_value = float(valor_total) if valor_total not in (None, "") else None
    if unit_price_value is not None:
        total_value = round(unit_price_value * quantity_value, 2)
    elif total_value is not None and quantity_value > 0:
        unit_price_value = round(total_value / quantity_value, 2)

    item_model = item_row.item or db.session.get(Item, item_row.codigo_item)
    stored_quantity_unit = (item_row.unidade_quantidade or "").strip().lower()
    quantity_unit = stored_quantity_unit
    status_processamento = (item_row.status_processamento or "pendente").strip().lower() or "pendente"
    should_refresh_document_unit = False
    if item_model is not None:
        should_refresh_document_unit = not quantity_unit
        if (
            not should_refresh_document_unit
            and status_processamento != "processado"
            and item_row.stock_movement_id is None
            and item_row.entrada_id is None
            and should_autofix_packaged_document_unit(
                item_model,
                current_unit=quantity_unit,
                quantity=quantity_value,
                quantity_base=item_row.quantidade_base,
            )
        ):
            should_refresh_document_unit = True
        if should_refresh_document_unit:
            quantity_unit = infer_document_quantity_unit_for_item(item_model)
    if not quantity_unit and item_model is not None:
        quantity_unit = (item_model.unidade or "").strip().lower()
    quantity_unit = quantity_unit or "un"

    stored_price_unit = (item_row.unidade_preco or "").strip().lower()
    if should_refresh_document_unit and (not stored_price_unit or stored_price_unit == stored_quantity_unit):
        price_unit = quantity_unit
    else:
        price_unit = stored_price_unit or quantity_unit

    item_row.quantidade = quantity_value
    item_row.valor_unitario = unit_price_value
    item_row.valor_total = total_value

    if item_model is not None:
        try:
            normalized = normalize_document_line(
                item_model,
                quantity=quantity_value,
                quantity_unit=quantity_unit,
                unit_price=unit_price_value,
                total_price=total_value,
                price_unit=price_unit,
            )
            item_row.unidade_quantidade = normalized.quantity_unit
            item_row.quantidade_base = float(normalized.quantity_base or 0.0)
            item_row.valor_unitario_base = normalized.unit_price_base
            item_row.unidade_preco = normalized.price_unit
            item_row.fator_preco_base = float(normalized.factor_to_base or 1.0)
            item_row.valor_total = normalized.total_value
            if item_row.valor_unitario is None:
                item_row.valor_unitario = normalized.unit_price_input
            return item_row.valor_unitario, item_row.valor_total
        except Exception:
            pass

    item_row.unidade_quantidade = quantity_unit
    item_row.quantidade_base = quantity_value
    item_row.valor_unitario_base = round(total_value / quantity_value, 8) if total_value is not None and quantity_value > 0 else unit_price_value
    item_row.unidade_preco = price_unit
    item_row.fator_preco_base = 1.0 if unit_price_value is not None else None
    return item_row.valor_unitario, item_row.valor_total


def _sync_document_financial_entries(documento: DocumentoEntradaEstoque) -> dict[str, int | bool]:
    updated = 0
    skipped = 0
    auto_confirmed = _document_is_ready_for_nf_confirmation(documento)
    auto_origin = _infer_document_origin(documento)

    for item_row in documento.itens:
        quantidade = float(item_row.quantidade or 0.0)
        valor_unitario = float(item_row.valor_unitario) if item_row.valor_unitario not in (None, "") else None
        valor_total = float(item_row.valor_total) if item_row.valor_total not in (None, "") else None
        valor_unitario, valor_total = _apply_document_item_normalization(
            item_row,
            quantidade=quantidade,
            valor_unitario=valor_unitario,
            valor_total=valor_total,
        )
        quantidade = float(item_row.quantidade or 0.0)

        query = FinanceLedgerEntry.query.filter(FinanceLedgerEntry.codigo_item == item_row.codigo_item)
        if item_row.entrada_id is not None:
            query = query.filter(FinanceLedgerEntry.entrada_id == item_row.entrada_id)
        else:
            query = query.filter(
                or_(
                    FinanceLedgerEntry.numero_documento == documento.numero_documento,
                    and_(
                        or_(
                            FinanceLedgerEntry.numero_documento.is_(None),
                            FinanceLedgerEntry.numero_documento == "",
                        ),
                        FinanceLedgerEntry.comprovacao_status.in_(["sem_comprovacao", "parcial"]),
                    ),
                )
            )

        ledger_entry = (
            query
            .order_by(FinanceLedgerEntry.data_lancamento.desc(), FinanceLedgerEntry.id.desc())
            .first()
        )
        if ledger_entry is None:
            ledger_entry = finance_service.register_financial_entry(
                codigo_item=item_row.codigo_item,
                categoria_nome=item_row.item.categoria if item_row.item and item_row.item.categoria else "Sem categoria",
                quantidade=quantidade,
                valor_unitario=valor_unitario,
                valor_total=valor_total,
                data_lancamento=documento.data_recebimento or documento.data_emissao or datetime.utcnow(),
                fornecedor_id=documento.fornecedor_id,
                entrada_id=item_row.entrada_id,
                usuario_matricula=current_user.id,
                origem_valor=auto_origin or "compra_documento",
                tipo_documento=documento.tipo_documento,
                numero_documento=documento.numero_documento,
                chave_acesso=documento.chave_acesso,
                data_emissao_documento=documento.data_emissao,
                data_recebimento_documento=documento.data_recebimento,
                comprovacao_status="comprovado" if auto_confirmed and auto_origin else "sem_comprovacao",
                observacao=item_row.observacao or documento.observacao,
                unidade_quantidade=item_row.unidade_quantidade,
                quantidade_base=item_row.quantidade_base,
                valor_unitario_base=item_row.valor_unitario_base,
                unidade_preco=item_row.unidade_preco,
                fator_preco_base=item_row.fator_preco_base,
            )
            if ledger_entry is None:
                skipped += 1
                continue

        ledger_entry.fornecedor_id = documento.fornecedor_id
        ledger_entry.usuario_matricula = current_user.id
        ledger_entry.categoria_nome = ledger_entry.categoria_nome or (
            item_row.item.categoria if item_row.item and item_row.item.categoria else "Sem categoria"
        )
        ledger_entry.data_lancamento = ledger_entry.data_lancamento or datetime.utcnow()
        ledger_entry.quantidade = quantidade
        ledger_entry.unidade_quantidade = item_row.unidade_quantidade
        ledger_entry.quantidade_base = item_row.quantidade_base
        if valor_unitario is not None:
            ledger_entry.valor_unitario = valor_unitario
        ledger_entry.valor_unitario_base = item_row.valor_unitario_base
        ledger_entry.unidade_preco = item_row.unidade_preco
        ledger_entry.fator_preco_base = item_row.fator_preco_base
        if valor_total is not None:
            ledger_entry.valor_total = valor_total
        elif valor_unitario is not None:
            ledger_entry.valor_total = round(quantidade * valor_unitario, 2)

        ledger_entry.tipo_documento = documento.tipo_documento
        ledger_entry.numero_documento = documento.numero_documento
        ledger_entry.chave_acesso = documento.chave_acesso
        ledger_entry.data_emissao_documento = documento.data_emissao
        ledger_entry.data_recebimento_documento = documento.data_recebimento
        if item_row.observacao:
            ledger_entry.observacao = item_row.observacao
        elif documento.observacao:
            ledger_entry.observacao = documento.observacao

        if auto_confirmed and auto_origin:
            ledger_entry.origem_valor = auto_origin
            ledger_entry.comprovacao_status = "comprovado"

        if item_row.item is not None:
            item_row.item.nota_fiscal = documento.numero_documento
            item_row.item.preco_compra_documento = documento.numero_documento
            item_row.item.preco_compra_chave_acesso = documento.chave_acesso
            item_row.item.preco_compra_data_emissao = documento.data_emissao
            item_row.item.preco_compra_data_recebimento = documento.data_recebimento
            item_row.item.preco_compra_fonte = auto_origin or item_row.item.preco_compra_fonte or "compra_nf"
            item_row.item.preco_compra_atualizado_em = datetime.utcnow()
            item_row.item.preco_compra_atualizado_por = current_user.id
            if valor_unitario is not None:
                item_row.item.preco_compra_unitario = valor_unitario
                item_row.item.preco_compra_unitario_base = item_row.valor_unitario_base
                item_row.item.preco_compra_unidade_preco = item_row.unidade_preco
                item_row.item.preco_compra_fator_base = item_row.fator_preco_base

        updated += 1

    return {
        "updated": updated,
        "skipped": skipped,
        "auto_confirmed": auto_confirmed,
    }


def _purge_linked_entry(entrada_id: int | None) -> None:
    if entrada_id is None:
        return
    FinanceLedgerEntry.query.filter_by(entrada_id=entrada_id).delete(synchronize_session=False)
    TelegramOutbox.query.filter_by(entrada_id=entrada_id).delete(synchronize_session=False)
    linked_entry = db.session.get(Entrada, entrada_id)
    if linked_entry is not None:
        db.session.delete(linked_entry)


def _purge_document_item_financial_entry(
    documento: DocumentoEntradaEstoque,
    item_row: DocumentoEntradaEstoqueItem,
) -> int:
    if documento is None or item_row is None:
        return 0

    deleted = 0
    if item_row.entrada_id is not None:
        deleted += FinanceLedgerEntry.query.filter_by(entrada_id=item_row.entrada_id).delete(synchronize_session=False)
        return deleted

    base_query = FinanceLedgerEntry.query.filter(
        FinanceLedgerEntry.codigo_item == item_row.codigo_item,
        FinanceLedgerEntry.numero_documento == documento.numero_documento,
    )
    if documento.tipo_documento:
        exact_query = base_query.filter(FinanceLedgerEntry.tipo_documento == documento.tipo_documento)
        deleted = exact_query.delete(synchronize_session=False)
        if deleted:
            return deleted

    if documento.fornecedor_id is not None:
        exact_query = base_query.filter(FinanceLedgerEntry.fornecedor_id == documento.fornecedor_id)
        deleted = exact_query.delete(synchronize_session=False)
        if deleted:
            return deleted

    deleted = base_query.delete(synchronize_session=False)
    return deleted


def _clear_finance_reports_cache() -> None:
    try:
        finance_service.clear_runtime_cache("get_stock_value_report:")
        finance_service.clear_runtime_cache("get_supplier_lab_report:")
    except Exception:
        pass


def _clear_nf_runtime_cache(numero_documento: str | None = None) -> None:
    try:
        inventory_service.clear_runtime_cache("list_items")
        inventory_service.clear_runtime_cache("list_notas_fiscais:")
        inventory_service.clear_runtime_cache("dashboard_snapshot")
        finance_service.clear_runtime_cache("list_stock_documents:")
        if numero_documento:
            inventory_service.clear_runtime_cache(f"get_nota_fiscal:{str(numero_documento).strip()}")
            finance_service.clear_runtime_cache(f"get_stock_document_by_number:{str(numero_documento).strip()}")
        else:
            inventory_service.clear_runtime_cache("get_nota_fiscal:")
            finance_service.clear_runtime_cache("get_stock_document_by_number:")
    except Exception:
        pass


def _process_document_stock_entries(
    documento: DocumentoEntradaEstoque | None,
    *,
    item_ids: list[int] | set[int] | tuple[int, ...] | None = None,
) -> dict[str, Any] | None:
    if documento is None or not bool(getattr(documento, "movimenta_estoque", True)):
        return None

    normalized_item_ids = sorted({int(item_id) for item_id in (item_ids or []) if item_id})
    result = finance_service.process_stock_document_entries(
        documento.id_documento,
        usuario_matricula=getattr(current_user, "id", None),
        only_pending=True,
        item_ids=normalized_item_ids or None,
    )
    if result.get("processed"):
        _clear_nf_runtime_cache(documento.numero_documento)
    return result


def _flash_document_stock_processing_errors(process_result: dict[str, Any] | None) -> None:
    if not process_result:
        return

    errors = int(process_result.get("errors") or 0)
    if errors <= 0:
        return

    messages = [str(message).strip() for message in (process_result.get("messages") or []) if str(message).strip()]
    if messages:
        suffix = f" (+{errors - 1} erro(s))" if errors > 1 else ""
        flash(f"{messages[0]}{suffix}", "danger")
        return

    flash(f"{errors} item(ns) do documento falharam ao entrar no estoque.", "danger")


def _item_matches_seeded_nf_pre_registration(
    item_model: Item | None,
    *,
    document_number: str | None = None,
) -> bool:
    if item_model is None:
        return False

    numero = (document_number or "").strip()
    if not numero:
        return False

    candidate_numbers = {
        str(getattr(item_model, "nota_fiscal", "") or "").strip(),
        str(getattr(item_model, "preco_compra_documento", "") or "").strip(),
    }
    if numero:
        candidate_numbers.add(numero)
    candidate_numbers.discard("")
    if numero not in candidate_numbers:
        return False

    if abs(float(item_model.get_saldo_fisico_total() or 0.0)) > 1e-6:
        return False

    legacy_entries = int(
        db.session.query(func.count(Entrada.id_entrada))
        .filter(Entrada.codigo_item == item_model.codigo_item)
        .scalar()
        or 0
    )
    if legacy_entries > 0:
        return False

    processed_document_rows = int(
        db.session.query(func.count(DocumentoEntradaEstoqueItem.id_documento_item))
        .filter(
            DocumentoEntradaEstoqueItem.codigo_item == item_model.codigo_item,
            DocumentoEntradaEstoqueItem.status_processamento == "processado",
        )
        .scalar()
        or 0
    )
    if processed_document_rows > 0:
        return False

    return True


def _mark_item_for_nf_pre_registration(
    item_model: Item | None,
    *,
    document_item_id: int | None = None,
    document_number: str | None = None,
    force: bool = False,
) -> bool:
    if item_model is None:
        return False

    already_pending = bool(getattr(item_model, "pre_cadastro_pendente", False))
    origin_nf = (getattr(item_model, "pre_cadastro_origem", "") or "").strip().lower() == "nf"
    seeded_by_document = _item_matches_seeded_nf_pre_registration(
        item_model,
        document_number=document_number,
    )
    if not force and not already_pending and not origin_nf and not seeded_by_document:
        return False

    changed = False
    if not already_pending:
        item_model.pre_cadastro_pendente = True
        changed = True

    if not origin_nf:
        item_model.pre_cadastro_origem = "nf"
        changed = True

    if document_item_id is not None and item_model.pre_cadastro_documento_item_id != document_item_id:
        item_model.pre_cadastro_documento_item_id = document_item_id
        changed = True

    if item_model.pre_cadastro_criado_em is None:
        item_model.pre_cadastro_criado_em = datetime.utcnow()
        changed = True

    if item_model.pre_cadastro_finalizado_em is not None:
        item_model.pre_cadastro_finalizado_em = None
        changed = True

    return bool(getattr(item_model, "pre_cadastro_pendente", False))


def _mark_document_items_for_nf_pre_registration(
    document_items: list[DocumentoEntradaEstoqueItem],
    *,
    force: bool = False,
) -> int:
    tracked = 0
    for document_item in document_items:
        if document_item is None:
            continue
        item_model = document_item.item or db.session.get(Item, document_item.codigo_item)
        if _mark_item_for_nf_pre_registration(
            item_model,
            document_item_id=document_item.id_documento_item,
            document_number=document_item.documento.numero_documento if document_item.documento else None,
            force=force,
        ):
            tracked += 1
    return tracked


def _mark_manual_nf_document_items_for_pre_registration(
    document_items: list[DocumentoEntradaEstoqueItem],
    *,
    forced_item_ids: set[int] | None = None,
) -> int:
    pending_items = [document_item for document_item in document_items if document_item is not None]
    if not pending_items:
        return 0

    normalized_forced_ids = {
        int(item_id)
        for item_id in (forced_item_ids or set())
        if item_id is not None
    }
    if not normalized_forced_ids:
        return _mark_document_items_for_nf_pre_registration(pending_items, force=True)

    forced_items: list[DocumentoEntradaEstoqueItem] = []
    regular_items: list[DocumentoEntradaEstoqueItem] = []
    for document_item in pending_items:
        if document_item.id_documento_item in normalized_forced_ids:
            forced_items.append(document_item)
        else:
            regular_items.append(document_item)

    tracked = 0
    if forced_items:
        tracked += _mark_document_items_for_nf_pre_registration(forced_items, force=True)
    if regular_items:
        tracked += _mark_document_items_for_nf_pre_registration(regular_items)
    return tracked


def _audit_document_item_deletion(
    *,
    item_snapshot: dict[str, Any],
    reason: str,
    action_type: str,
    action_result: str = "success",
    extra_details: dict[str, Any] | None = None,
) -> None:
    details: dict[str, Any] = {
        "document_id": item_snapshot.get("document_id"),
        "document_item_id": item_snapshot.get("document_item_id"),
        "numero_documento": item_snapshot.get("numero_documento"),
        "codigo_item": item_snapshot.get("codigo_item"),
        "status_processamento": item_snapshot.get("status_processamento"),
        "reason": reason,
        "user_id": getattr(current_user, "id", None),
        "route": request.path,
        "ip_address": request.remote_addr,
        "user_agent": request.user_agent.string if request.user_agent else None,
        "stock_movement_id": item_snapshot.get("stock_movement_id"),
        "balance_before": item_snapshot.get("balance_before"),
        "balance_after": item_snapshot.get("balance_after"),
    }
    if extra_details:
        details.update(extra_details)
    log_document_item_deletion(action_type=action_type, action_result=action_result, details=details)


@blueprint.before_request
def _abort_if_feature_disabled() -> None:
    if not current_app.config.get("FEATURE_NOTAS_ENABLED", True):
        abort(404)


def _require_admin() -> None:
    if not bool(getattr(current_user, "is_admin", False)):
        abort(403)


def _document_reference_date(documento: DocumentoEntradaEstoque) -> date:
    if documento.data_recebimento:
        return documento.data_recebimento
    if documento.data_emissao:
        return documento.data_emissao
    if documento.criado_em:
        return documento.criado_em.date()
    return date.today()


def _document_total_quantidade(documento: DocumentoEntradaEstoque) -> float:
    return round(sum(float(item.quantidade or 0.0) for item in documento.itens), 2)


def _document_total_valor(documento: DocumentoEntradaEstoque) -> float:
    total = 0.0
    for item in documento.itens:
        if item.valor_total not in (None, ""):
            total += float(item.valor_total)
            continue
        if item.valor_unitario not in (None, ""):
            total += float(item.valor_unitario) * float(item.quantidade or 0.0)
    return round(total, 2)


def _query_period_documents(
    *,
    data_inicio: date,
    data_fim: date,
    fornecedor_id: int | None = None,
    tipo_documento: str | None = None,
) -> list[DocumentoEntradaEstoque]:
    reference_date = func.coalesce(
        DocumentoEntradaEstoque.data_recebimento,
        DocumentoEntradaEstoque.data_emissao,
        cast(DocumentoEntradaEstoque.criado_em, Date),
    )

    query = (
        DocumentoEntradaEstoque.query
        .options(
            joinedload(DocumentoEntradaEstoque.fornecedor),
            joinedload(DocumentoEntradaEstoque.itens).joinedload(DocumentoEntradaEstoqueItem.item),
        )
        .filter(reference_date >= data_inicio)
        .filter(reference_date <= data_fim)
        .order_by(DocumentoEntradaEstoque.criado_em.desc(), DocumentoEntradaEstoque.id_documento.desc())
    )

    if fornecedor_id:
        query = query.filter(DocumentoEntradaEstoque.fornecedor_id == fornecedor_id)
    if tipo_documento and tipo_documento != "todos":
        query = query.filter(DocumentoEntradaEstoque.tipo_documento == tipo_documento)

    return query.all()


def _build_document_category_options() -> list[str]:
    try:
        return category_catalog_service.list_form_choices()
    except Exception:
        return [DEFAULT_INVENTORY_CATEGORY_NAME]


def _build_document_unit_options() -> list[str]:
    seen: set[str] = set()
    options: list[str] = []
    for value in DEFAULT_DOCUMENT_UNIT_OPTIONS:
        normalized = (value or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            options.append(normalized)
    return options

def _document_lookup_number(documento: dict[str, Any]) -> str:
    return str(documento.get("numero_documento") or documento.get("nota_fiscal") or "").strip()

def _document_supplier_name(documento: dict[str, Any]) -> str:
    return str(documento.get("fornecedor_nome") or "").strip()

def _document_type_value(documento: dict[str, Any]) -> str:
    return (str(documento.get("tipo_documento") or "manual").strip().lower() or "manual")

def _item_has_valid_quantity(item: dict[str, Any]) -> bool:
    try:
        return float(item.get("quantidade") or 0) > 0
    except (TypeError, ValueError):
        return False

def _normalize_operational_items(documento: dict[str, Any]) -> list[dict[str, Any]]:
    items = list(documento.get("itens") or [])
    is_legacy_document = documento.get("id_documento") in (None, "") and bool(documento.get("nota_fiscal"))
    document_date = documento.get("data")
    normalized: list[dict[str, Any]] = []

    for item in items:
        status_processamento = (str(item.get("status_processamento") or "").strip().lower() or None)
        erro_processamento = (str(item.get("erro_processamento") or "").strip() or None)
        processado_em = item.get("processado_em")
        has_stock_link = item.get("stock_movement_id") not in (None, "") or item.get("entrada_id") not in (None, "")
        has_legacy_entry = is_legacy_document and item.get("id") not in (None, "")
        is_processed = bool(processado_em) or status_processamento == "processado" or has_legacy_entry or has_stock_link
        effective_error = None if is_processed else erro_processamento

        normalized.append(
            {
                **item,
                "status_processamento": status_processamento or ("processado" if is_processed else "pendente"),
                "erro_processamento": effective_error,
                "processado_em": processado_em or (document_date.isoformat() if has_legacy_entry and hasattr(document_date, "isoformat") else None),
                "quantidade_valida": _item_has_valid_quantity(item),
                "is_processed": is_processed,
                "has_error": bool(effective_error),
            }
        )

    return normalized

def _document_is_complete_for_operations(documento: dict[str, Any]) -> bool:
    numero_documento = _document_lookup_number(documento)
    fornecedor_nome = _document_supplier_name(documento)
    tipo_documento = _document_type_value(documento)
    items = documento.get("operational_items") or []

    return bool(
        numero_documento
        and fornecedor_nome
        and tipo_documento
        and items
        and all(item.get("quantidade_valida") for item in items)
        and not any(item.get("has_error") for item in items)
        and bool(documento.get("movimenta_estoque", True))
    )

def _document_missing_reasons(documento: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not _document_lookup_number(documento):
        reasons.append("sem número de documento")
    if not _document_supplier_name(documento):
        reasons.append("sem fornecedor identificado")
    if not _document_type_value(documento):
        reasons.append("sem tipo documental")

    items = documento.get("operational_items") or []
    if not items:
        reasons.append("sem item vinculado")
    elif not all(item.get("quantidade_valida") for item in items):
        reasons.append("há item com quantidade inválida")

    if any(item.get("has_error") for item in items):
        reasons.append("há item com erro operacional")
    if not bool(documento.get("movimenta_estoque", True)):
        reasons.append("lançamento financeiro sem movimentar estoque")

    if not reasons and any(not item.get("is_processed") for item in items):
        reasons.append("aguardando conferência operacional")
    return reasons

def _resolve_document_status(documento: dict[str, Any]) -> str:
    items = documento.get("operational_items") or []
    if any(item.get("has_error") for item in items):
        return "erros"
    if items and all(item.get("processado_em") for item in items):
        return "historico"
    blocking_reasons = [
        reason for reason in _document_missing_reasons(documento)
        if reason != "aguardando conferência operacional"
    ]
    if blocking_reasons:
        return "erros"
    return "processaveis"

def _document_status_meta(status_key: str) -> dict[str, str]:
    mapping = {
        "processaveis": {
            "label": "Processável",
            "badge_class": "success",
            "action_label": "Abrir / Processar",
            "empty_title": "Nenhum documento pronto para operação.",
        },
        "erros": {
            "label": "Erro",
            "badge_class": "danger",
            "action_label": "Corrigir",
            "empty_title": "Nenhum documento com erro operacional ou cadastro incompleto.",
        },
        "historico": {
            "label": "Histórico",
            "badge_class": "muted",
            "action_label": "Revisar",
            "empty_title": "Nenhum documento processado disponível.",
        },
    }
    return mapping[status_key]

def _build_operational_document(documento: dict[str, Any], *, is_search_match: bool = False) -> dict[str, Any]:
    normalized_items = _normalize_operational_items(documento)
    numero_documento = _document_lookup_number(documento)
    status_key = _resolve_document_status({**documento, "operational_items": normalized_items})
    status_meta = _document_status_meta(status_key)
    error_messages = [str(item.get("erro_processamento") or "").strip() for item in normalized_items if item.get("erro_processamento")]
    pending_count = sum(1 for item in normalized_items if not item.get("is_processed"))
    processed_count = sum(1 for item in normalized_items if item.get("is_processed"))
    data_referencia = documento.get("data_recebimento") or documento.get("data_emissao") or documento.get("data")

    return {
        **documento,
        "lookup_numero": numero_documento,
        "tipo_documento": _document_type_value(documento),
        "fornecedor_nome": _document_supplier_name(documento),
        "operational_items": normalized_items,
        "status_key": status_key,
        "status_label": status_meta["label"],
        "status_badge_class": status_meta["badge_class"],
        "action_label": status_meta["action_label"],
        "empty_title": status_meta["empty_title"],
        "pending_count": pending_count,
        "processed_count": processed_count,
        "is_complete": _document_is_complete_for_operations({**documento, "operational_items": normalized_items}),
        "missing_reasons": _document_missing_reasons({**documento, "operational_items": normalized_items}),
        "error_messages": [message for message in error_messages if message],
        "data_referencia": data_referencia,
        "is_search_match": is_search_match,
    }

def _build_operational_dashboard(*, notas: list[dict[str, Any]], nota_detalhes: dict[str, Any] | None, nota_busca: str) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    by_number: dict[str, dict[str, Any]] = {}

    for nota in notas:
        document = _build_operational_document(nota)
        numero_documento = document["lookup_numero"]
        if numero_documento:
            by_number[numero_documento] = document
        documents.append(document)

    selected_document: dict[str, Any] | None = None
    numero_busca = (nota_busca or "").strip()
    if numero_busca and nota_detalhes:
        lookup_numero = _document_lookup_number(nota_detalhes)
        selected_document = by_number.get(lookup_numero)
        if selected_document is None:
            selected_document = _build_operational_document(nota_detalhes, is_search_match=True)
            if lookup_numero:
                by_number[lookup_numero] = selected_document
            documents.insert(0, selected_document)
        else:
            selected_document["is_search_match"] = True

    documents.sort(
        key=lambda document: (
            0 if document.get("is_search_match") else 1,
            -(document.get("data_referencia").timestamp() if hasattr(document.get("data_referencia"), "timestamp") else 0),
            str(document.get("lookup_numero") or ""),
        )
    )

    grouped: dict[str, list[dict[str, Any]]] = {
        "processaveis": [],
        "erros": [],
        "historico": [],
    }
    for document in documents:
        grouped[document["status_key"]].append(document)

    active_tab = _normalize_operational_tab(request.args.get("aba"))
    if active_tab not in VALID_OPERATIONAL_TABS:
        active_tab = selected_document["status_key"] if selected_document else "registro"

    counts = {
        "total": len(documents),
        "processaveis": len(grouped["processaveis"]),
        "pendencias": 0,
        "erros": len(grouped["erros"]),
        "historico": len(grouped["historico"]),
    }

    return {
        "documents": documents,
        "grouped": grouped,
        "counts": counts,
        "selected_document": selected_document,
        "active_tab": active_tab,
    }


def _requested_operational_tab() -> str | None:
    tab_value = _normalize_operational_tab(request.form.get("active_tab") or request.args.get("aba"))
    return tab_value if tab_value in VALID_OPERATIONAL_TABS else None


def _resolve_document_tab(numero_documento: str | None, fallback: str = "registro") -> str:
    numero = (numero_documento or "").strip()
    if not numero:
        return fallback

    nota_detalhes = inventory_service.get_nota_fiscal(numero)
    if not nota_detalhes:
        return fallback

    operational_document = _build_operational_document(nota_detalhes, is_search_match=True)
    return operational_document.get("status_key") or fallback


def _redirect_to_nf_context(
    *,
    numero_documento: str | None = None,
    anchor: str | None = None,
    fallback_tab: str = "registro",
    clear_selection: bool = False,
) -> str:
    requested_tab = _requested_operational_tab()
    active_tab = requested_tab or _resolve_document_tab(numero_documento, fallback=fallback_tab)
    nota_value = None if clear_selection else (numero_documento or None)
    base_url = url_for("nf.nf_index", nota=nota_value, aba=active_tab)
    return f"{base_url}#{anchor}" if anchor else base_url


def _serialize_period_closure(fechar: CompraPeriodoFechamento) -> dict[str, object]:
    return {
        "id": fechar.id,
        "data_inicio": fechar.data_inicio,
        "data_fim": fechar.data_fim,
        "fornecedor_id": fechar.fornecedor_id,
        "fornecedor_nome": fechar.fornecedor.nome_exibicao() if fechar.fornecedor else None,
        "cnpj_emitente": fechar.cnpj_emitente,
        "tipo_documento": fechar.tipo_documento,
        "status": fechar.status,
        "total_documentos": fechar.total_documentos,
        "total_itens": fechar.total_itens,
        "total_quantidade": fechar.total_quantidade,
        "total_valor": fechar.total_valor,
        "observacao": fechar.observacao,
        "fechado_por": fechar.fechado_por,
        "fechado_em": fechar.fechado_em,
        "reaberto_por": fechar.reaberto_por,
        "reaberto_em": fechar.reaberto_em,
    }


def _build_period_dashboard() -> dict[str, object]:
    today = date.today()
    data_inicio = _parse_iso_date(request.args.get("periodo_inicio"), fallback=today.replace(day=1)) or today.replace(day=1)
    data_fim = _parse_iso_date(request.args.get("periodo_fim"), fallback=today) or today

    if data_inicio > data_fim:
        data_inicio, data_fim = data_fim, data_inicio

    fornecedor_raw = (request.args.get("periodo_fornecedor") or "").strip()
    fornecedor_id = int(fornecedor_raw) if fornecedor_raw.isdigit() else None
    tipo_documento = (request.args.get("periodo_tipo") or "todos").strip().lower() or "todos"

    documentos = _query_period_documents(
        data_inicio=data_inicio,
        data_fim=data_fim,
        fornecedor_id=fornecedor_id,
        tipo_documento=tipo_documento,
    )

    total_documentos = len(documentos)
    total_quantidade = round(sum(_document_total_quantidade(doc) for doc in documentos), 2)
    total_valor = round(sum(_document_total_valor(doc) for doc in documentos), 2)
    cupom_count = sum(1 for doc in documentos if (doc.tipo_documento or "").strip().lower() == "cupom")
    nf_count = sum(1 for doc in documentos if (doc.tipo_documento or "").strip().lower() == "nf")
    manual_count = sum(1 for doc in documentos if (doc.tipo_documento or "").strip().lower() in {"manual", "recibo"})

    suppliers: dict[str, dict[str, object]] = {}
    for doc in documentos:
        supplier_name = doc.fornecedor.nome_exibicao() if doc.fornecedor else (doc.nome_emitente() or "Sem fornecedor identificado")
        supplier_key = str(doc.fornecedor_id or doc.cnpj_emitente or supplier_name)
        summary = suppliers.setdefault(
            supplier_key,
            {
                "fornecedor_id": doc.fornecedor_id,
                "fornecedor_nome": supplier_name,
                "cnpj_emitente": doc.cnpj_emitente,
                "documentos": 0,
                "itens": 0,
                "quantidade": 0.0,
                "valor": 0.0,
                "primeira_data": _document_reference_date(doc),
                "ultima_data": _document_reference_date(doc),
                "tipos": set(),
            },
        )
        summary["documentos"] = int(summary["documentos"] or 0) + 1
        summary["itens"] = int(summary["itens"] or 0) + len(doc.itens)
        summary["quantidade"] = round(float(summary["quantidade"] or 0.0) + _document_total_quantidade(doc), 2)
        summary["valor"] = round(float(summary["valor"] or 0.0) + _document_total_valor(doc), 2)
        summary["primeira_data"] = min(summary["primeira_data"], _document_reference_date(doc))
        summary["ultima_data"] = max(summary["ultima_data"], _document_reference_date(doc))
        summary["tipos"].add((doc.tipo_documento or "manual").strip().lower())

    supplier_rows = []
    for row in suppliers.values():
        row["tipos"] = ", ".join(sorted(str(tipo).upper() for tipo in row["tipos"]))
        supplier_rows.append(row)

    supplier_rows.sort(key=lambda row: (-float(row["valor"] or 0.0), str(row["fornecedor_nome"])))

    closures_query = (
        CompraPeriodoFechamento.query
        .options(joinedload(CompraPeriodoFechamento.fornecedor))
        .order_by(CompraPeriodoFechamento.fechado_em.desc(), CompraPeriodoFechamento.id.desc())
    )
    closures = [_serialize_period_closure(row) for row in closures_query.limit(12).all()]

    active_closure = next(
        (
            closure
            for closure in closures
            if closure["status"] == "fechado"
            and closure["data_inicio"] == data_inicio
            and closure["data_fim"] == data_fim
            and int(closure["fornecedor_id"] or 0) == int(fornecedor_id or 0)
            and (closure["tipo_documento"] or "todos") == (None if tipo_documento == "todos" else tipo_documento)
        ),
        None,
    )

    return {
        "filters": {
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "fornecedor_id": fornecedor_id,
            "tipo_documento": tipo_documento,
        },
        "kpis": {
            "documentos": total_documentos,
            "quantidade": total_quantidade,
            "valor": total_valor,
            "cupom": cupom_count,
            "nf": nf_count,
            "manual": manual_count,
        },
        "supplier_rows": supplier_rows,
        "closures": closures,
        "active_closure": active_closure,
        "documentos": documentos,
    }


@blueprint.get("/api/documentos/autocomplete")
@login_required
def autocomplete_documentos():
    _require_admin()
    term = (request.args.get("q") or "").strip()
    if len(term) < 2:
        return jsonify({"success": True, "results": []})
    return jsonify({"success": True, "results": finance_service.search_stock_documents(term, limit=8)})


@blueprint.get("/api/documentos/<numero>/detalhes")
@login_required
def documento_detalhes(numero: str):
    _require_admin()
    documento = inventory_service.get_nota_fiscal(numero)
    if not documento:
        return jsonify({"success": False, "message": "Documento não encontrado."}), 404

    payload = {
        "numero_documento": documento.get("numero_documento") or documento.get("nota_fiscal") or numero,
        "tipo_documento": documento.get("tipo_documento"),
        "fornecedor_id": documento.get("fornecedor_id"),
        "fornecedor_nome": documento.get("fornecedor_nome"),
        "cnpj_emitente": documento.get("cnpj_emitente"),
        "data_emissao": documento.get("data_emissao").isoformat() if getattr(documento.get("data_emissao"), "isoformat", None) else None,
        "data_recebimento": documento.get("data_recebimento").isoformat() if getattr(documento.get("data_recebimento"), "isoformat", None) else None,
        "chave_acesso": documento.get("chave_acesso"),
        "movimenta_estoque": bool(documento.get("movimenta_estoque", True)),
        "status_integracao": documento.get("status_integracao"),
        "mensagem_integracao": documento.get("mensagem_integracao"),
    }
    return jsonify({"success": True, "document": payload})


@blueprint.get("/")
@login_required
def nf_index():
    nota_busca = (request.args.get("nota") or "").strip()
    codigo_prefill = (request.args.get("codigo") or "").strip()
    period_dashboard = _build_period_dashboard()
    nota_detalhes = inventory_service.get_nota_fiscal(nota_busca) if nota_busca else None
    selected_item = inventory_service.get_item(codigo_prefill) if codigo_prefill else None
    notas = inventory_service.list_notas_fiscais()
    can_manage = bool(getattr(current_user, "is_admin", False))
    return render_template(
        "nf/index.html",
        selected_item=selected_item,
        notas=notas,
        nota_busca=nota_busca,
        codigo_prefill=codigo_prefill,
        nota_detalhes=nota_detalhes,
        can_manage=can_manage,
        preferred_suppliers=finance_service.list_suppliers(limit=100),
        period_dashboard=period_dashboard,
        document_category_options=_build_document_category_options(),
        document_unit_options=_build_document_unit_options(),
        operational_dashboard=_build_operational_dashboard(
            notas=notas,
            nota_detalhes=nota_detalhes,
            nota_busca=nota_busca,
        ),
    )


@blueprint.post("/")
@login_required
def registrar_nf():
    _require_admin()
    codigo = request.form.get("codigo", "").strip()
    novo_codigo = request.form.get("novo_codigo", "").strip()
    nova_descricao = request.form.get("nova_descricao", "").strip()
    nova_marca = (request.form.get("nova_marca") or "").strip() or None
    nova_categoria = category_catalog_service.resolve_name(
        request.form.get("nova_categoria", "").strip(),
        fallback=DEFAULT_INVENTORY_CATEGORY_NAME,
        actor=getattr(current_user, "nome", None) or getattr(current_user, "id", None),
    )
    nova_unidade = normalize_base_item_unit(request.form.get("nova_unidade", "").strip(), fallback="Unidade")
    nova_unidade_documental = _normalize_nf_new_item_packaging_type(request.form.get("nova_unidade_documental"))
    novo_conteudo_embalagem = _parse_optional_float(request.form.get("novo_conteudo_embalagem"), fallback=None)
    nota = request.form.get("nota_fiscal", "").strip()
    supplier_raw = (request.form.get("finance_supplier_id") or "").strip()
    supplier_id = int(supplier_raw) if supplier_raw.isdigit() else None
    supplier_name = (request.form.get("supplier_name") or request.form.get("finance_supplier_search") or "").strip() or None
    supplier_cnpj = (request.form.get("supplier_cnpj") or "").strip() or None
    origem_valor = (request.form.get("finance_origem_valor") or "compra_nf").strip() or "compra_nf"
    comprovacao_status = (request.form.get("finance_comprovacao_status") or "comprovado").strip() or "comprovado"
    preco_unitario_raw = (request.form.get("preco_unitario") or "").strip()
    observacao = (request.form.get("finance_observacao") or "").strip() or None
    chave_acesso = (request.form.get("chave_acesso") or "").strip() or None
    data_emissao_raw = (request.form.get("data_emissao") or "").strip()
    tipo_documento = _resolve_registration_document_type(
        ui_mode=request.form.get("doc_mode"),
        raw_document_type=request.form.get("finance_tipo_documento"),
        origem_valor=origem_valor,
        comprovacao_status=comprovacao_status,
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        supplier_cnpj=supplier_cnpj,
        chave_acesso=chave_acesso,
        data_emissao_raw=data_emissao_raw,
    )
    if tipo_documento != "nf":
        chave_acesso = None
    if tipo_documento == "manual":
        supplier_id = None
        supplier_name = None
        supplier_cnpj = None
    data_recebimento_raw = (request.form.get("data_recebimento") or "").strip()
    quantidade_raw = request.form.get("quantidade", "0")
    try:
        quantidade = float(quantidade_raw or 0)
    except ValueError:
        quantidade = 0.0

    try:
        data_emissao = date.fromisoformat(data_emissao_raw) if data_emissao_raw else None
    except ValueError:
        data_emissao = None
    try:
        data_recebimento = date.fromisoformat(data_recebimento_raw) if data_recebimento_raw else date.today()
    except ValueError:
        data_recebimento = date.today()

    movimenta_estoque = _resolve_documento_movimenta_estoque(
        data_emissao=data_emissao,
        data_recebimento=data_recebimento,
    )

    documento = None
    document_item = None
    item_criado_na_nf = False

    try:
        stock_process_result = None
        nova_unidade = ensure_base_item_unit(nova_unidade, fallback="Unidade")
        if not codigo and novo_codigo:
            codigo = novo_codigo

        if quantidade <= 0:
            raise ValueError("Informe uma quantidade válida")
        if not nota:
            raise ValueError("Informe o número do documento")

        _validate_document_registration_fields(
            numero_documento=nota,
            tipo_documento=tipo_documento,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            supplier_cnpj=supplier_cnpj,
            data_emissao=data_emissao,
            data_recebimento=data_recebimento,
            comprovacao_status=comprovacao_status,
            observacao=observacao,
        )

        item_existente = inventory_service.get_item(codigo) if codigo else None
        if not item_existente:
            if not codigo:
                raise ValueError("Selecione um item existente ou informe o código do novo item")
            if not nova_descricao:
                raise ValueError("Informe a descrição para cadastrar o novo item da nota")
            create_payload = {
                "codigo": codigo,
                "descricao": nova_descricao,
                "categoria": nova_categoria,
                "unidade": nova_unidade,
                "nota_fiscal": nota or None,
                "marca": nova_marca,
                "localizacao": None,
                "quantidade": 0,
                "pre_cadastro_pendente": True,
                "pre_cadastro_origem": "nf",
                "pre_cadastro_criado_em": datetime.utcnow(),
                "pre_cadastro_finalizado_em": None,
            }
            create_payload.update(
                _build_nf_new_item_packaging_payload(
                    base_unit=nova_unidade,
                    packaging_type=nova_unidade_documental,
                    content_per_package=novo_conteudo_embalagem,
                )
            )
            inventory_service.create_item(create_payload)
            item_criado_na_nf = True

        preco_unitario = float(preco_unitario_raw) if preco_unitario_raw else None
        item = inventory_service.get_item(codigo) or {}

        document_result = finance_service.register_stock_document_entry(
            codigo_item=codigo,
            quantidade=float(quantidade),
            tipo_documento=tipo_documento,
            numero_documento=nota,
            data_emissao=data_emissao,
            data_recebimento=data_recebimento,
            chave_acesso=chave_acesso,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            supplier_cnpj=supplier_cnpj,
            entrada_id=None,
            valor_unitario=preco_unitario,
            lote=(item.get("lote") or "") if item else None,
            data_validade=None,
            observacao=observacao,
            usuario_matricula=current_user.id,
            origem_valor=origem_valor,
            document_only=True,
            movimenta_estoque=movimenta_estoque,
        )
        document_item = document_result.get("document_item")
        documento = document_result.get("document")
        pre_registration_count = 0
        if documento and documento.movimenta_estoque and document_item is not None:
            pre_registration_count = _mark_manual_nf_document_items_for_pre_registration(
                [document_item],
            )
        sync_result = _sync_document_financial_entries(documento)
        db.session.commit()
        stock_process_result = _process_document_stock_entries(
            documento,
            item_ids=[document_item.id_documento_item] if document_item is not None else None,
        )
        _clear_nf_runtime_cache(documento.numero_documento)
        if not documento.movimenta_estoque:
            flash("Documento fiscal registrado apenas no financeiro. O estoque não foi movimentado por opção do lançamento.", "info")
        else:
            if pre_registration_count:
                flash("Documento fiscal registrado. Como a linha foi lançada manualmente nesta NF, o item vai para PRÉ CADASTRADOS antes de entrar no estoque.", "success")
            if stock_process_result and stock_process_result.get("processed"):
                flash("Documento fiscal registrado e item incorporado ao estoque.", "success")
            elif not pre_registration_count and not (stock_process_result and stock_process_result.get("errors")):
                flash("Documento fiscal registrado e pronto para conferência operacional.", "success")
        if sync_result["updated"]:
            flash(f"{sync_result['updated']} lançamento(s) financeiro(s) sincronizado(s) com o documento.", "info")
        if item_criado_na_nf and pre_registration_count:
            flash("O item ficou disponível em PRÉ CADASTRADOS para conclusão do cadastro na tela de Itens.", "info")
        _flash_document_stock_processing_errors(stock_process_result)
    except ValueError as exc:
        if item_criado_na_nf and document_item is None and codigo:
            try:
                inventory_service.delete_item(codigo)
            except Exception:
                current_app.logger.exception(
                    "Falha ao limpar item órfão criado via NF após erro de validação.",
                    extra={"codigo_item": codigo, "numero_documento": nota or None},
                )
        flash(str(exc), "danger")
    except Exception:
        if item_criado_na_nf and document_item is None and codigo:
            try:
                db.session.rollback()
                inventory_service.delete_item(codigo)
            except Exception:
                current_app.logger.exception(
                    "Falha ao limpar item órfão criado via NF após erro inesperado.",
                    extra={"codigo_item": codigo, "numero_documento": nota or None},
                )
        raise
    numero_redirect = None
    try:
        numero_redirect = documento.numero_documento if documento else None
    except UnboundLocalError:
        numero_redirect = nota or None
    return redirect(_redirect_to_nf_context(numero_documento=numero_redirect, fallback_tab="registro"))


@blueprint.post("/fechamentos")
@login_required
def fechar_periodo_compras():
    _require_admin()
    data_inicio = _parse_iso_date(request.form.get("periodo_inicio"))
    data_fim = _parse_iso_date(request.form.get("periodo_fim"))
    if not data_inicio or not data_fim:
        flash("Informe um período válido para fechamento.", "danger")
        return redirect(url_for("nf.nf_index"))

    if data_inicio > data_fim:
        data_inicio, data_fim = data_fim, data_inicio

    fornecedor_raw = (request.form.get("periodo_fornecedor") or "").strip()
    fornecedor_id = int(fornecedor_raw) if fornecedor_raw.isdigit() else None
    tipo_documento = (request.form.get("periodo_tipo") or "todos").strip().lower() or "todos"
    observacao = (request.form.get("observacao_fechamento") or "").strip() or None

    documentos = _query_period_documents(
        data_inicio=data_inicio,
        data_fim=data_fim,
        fornecedor_id=fornecedor_id,
        tipo_documento=tipo_documento,
    )
    if not documentos:
        flash("Nenhum documento encontrado no período informado para fechar.", "warning")
        return redirect(
            url_for(
                "nf.nf_index",
                aba="historico",
                periodo_inicio=data_inicio.isoformat(),
                periodo_fim=data_fim.isoformat(),
                periodo_fornecedor=fornecedor_id or "",
                periodo_tipo=tipo_documento,
            )
        )

    total_documentos = len(documentos)
    total_itens = sum(len(doc.itens) for doc in documentos)
    total_quantidade = round(sum(_document_total_quantidade(doc) for doc in documentos), 2)
    total_valor = round(sum(_document_total_valor(doc) for doc in documentos), 2)
    supplier = finance_service.get_supplier(fornecedor_id) if fornecedor_id else None

    fechamento = CompraPeriodoFechamento(
        data_inicio=data_inicio,
        data_fim=data_fim,
        fornecedor_id=fornecedor_id,
        cnpj_emitente=supplier.cnpj if supplier and supplier.cnpj else None,
        tipo_documento=None if tipo_documento == "todos" else tipo_documento,
        status="fechado",
        total_documentos=total_documentos,
        total_itens=total_itens,
        total_quantidade=total_quantidade,
        total_valor=total_valor,
        observacao=observacao,
        fechado_por=current_user.id,
        fechado_em=datetime.utcnow(),
    )
    db.session.add(fechamento)
    db.session.commit()
    flash(
        f"Período fechado com sucesso: {total_documentos} documento(s), {total_itens} item(ns) e total de R$ {total_valor:,.2f}.".replace(",", "X").replace(".", ",").replace("X", "."),
        "success",
    )
    return redirect(
        f"{url_for('nf.nf_index', aba='historico', periodo_inicio=data_inicio.isoformat(), periodo_fim=data_fim.isoformat(), periodo_fornecedor=fornecedor_id or '', periodo_tipo=tipo_documento)}#controle-periodo"
    )


@blueprint.post("/fechamentos/<int:fechamento_id>/reabrir")
@login_required
def reabrir_periodo_compras(fechamento_id: int):
    _require_admin()
    fechamento = db.session.get(CompraPeriodoFechamento, fechamento_id)
    if fechamento is None:
        flash("Fechamento de período não encontrado.", "danger")
        return redirect(url_for("nf.nf_index"))

    fechamento.status = "reaberto"
    fechamento.reaberto_por = current_user.id
    fechamento.reaberto_em = datetime.utcnow()
    db.session.commit()
    flash("Período reaberto para revisão.", "success")
    return redirect(
        f"{url_for('nf.nf_index', aba='historico', periodo_inicio=fechamento.data_inicio.isoformat(), periodo_fim=fechamento.data_fim.isoformat(), periodo_fornecedor=fechamento.fornecedor_id or '', periodo_tipo=fechamento.tipo_documento or 'todos')}#controle-periodo"
    )


@blueprint.post("/converter-legado")
@login_required
def converter_documento_legado():
    _require_admin()
    numero_documento = (request.form.get("nota_fiscal") or request.form.get("numero_documento") or "").strip()
    try:
        document, created, imported_items = _get_or_create_document_from_legacy_number(numero_documento)
        db.session.commit()
        _clear_nf_runtime_cache(document.numero_documento)
        if created:
            flash(
                f"Documento legado {document.numero_documento} convertido para documento fiscal editável com {imported_items} item(ns).",
                "success",
            )
        elif imported_items:
            flash(
                f"Documento fiscal {document.numero_documento} atualizado com {imported_items} item(ns) importado(s) do histórico legado.",
                "success",
            )
        else:
            flash(f"Documento fiscal {document.numero_documento} já estava convertido e pronto para edição.", "info")
        return redirect(
            _redirect_to_nf_context(
                numero_documento=document.numero_documento,
                anchor=f"documento-editar-{document.id_documento}",
                fallback_tab="processaveis",
            )
        )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(_redirect_to_nf_context(numero_documento=numero_documento, fallback_tab="historico"))


@blueprint.post("/<int:documento_id>/editar")
@login_required
def editar_documento(documento_id: int):
    _require_admin()
    documento = db.session.get(DocumentoEntradaEstoque, documento_id)
    if documento is None:
        flash("Documento fiscal não encontrado.", "danger")
        return redirect(url_for("nf.nf_index"))

    previous_movimenta_estoque = bool(getattr(documento, "movimenta_estoque", True))
    try:
        stock_process_result = None
        numero_documento = (request.form.get("numero_documento") or "").strip()
        tipo_documento = (request.form.get("tipo_documento") or "nf").strip() or "nf"
        supplier_raw = (request.form.get("finance_supplier_id") or "").strip()
        supplier_id = int(supplier_raw) if supplier_raw.isdigit() else None
        supplier_name = (
            request.form.get("supplier_name")
            or request.form.get("finance_supplier_search")
            or documento.fornecedor_nome
            or ""
        ).strip() or None
        supplier_cnpj = (request.form.get("supplier_cnpj") or documento.cnpj_emitente or "").strip() or None
        data_emissao = _parse_iso_date(request.form.get("data_emissao"), fallback=documento.data_emissao)
        data_recebimento = _parse_iso_date(request.form.get("data_recebimento"), fallback=documento.data_recebimento)
        chave_acesso = (request.form.get("chave_acesso") or "").strip() or None
        if tipo_documento != "nf":
            chave_acesso = None
        if tipo_documento == "manual":
            supplier_id = None
            supplier_name = None
            supplier_cnpj = None
        observacao = (request.form.get("finance_observacao") or "").strip() or None

        movimenta_estoque = _resolve_documento_movimenta_estoque(
            data_emissao=data_emissao,
            data_recebimento=data_recebimento,
        )

        _validate_document_registration_fields(
            numero_documento=numero_documento,
            tipo_documento=tipo_documento,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            supplier_cnpj=supplier_cnpj,
            data_emissao=data_emissao,
            data_recebimento=data_recebimento,
            observacao=observacao,
        )

        supplier = finance_service._resolve_supplier_for_document(
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            supplier_cnpj=supplier_cnpj,
        )
        cnpj_emitente = supplier.cnpj if supplier and supplier.cnpj else (finance_service.normalize_cnpj(supplier_cnpj) or None)
        fornecedor_nome = supplier.nome_exibicao() if supplier else supplier_name

        documento.numero_documento = numero_documento
        documento.tipo_documento = tipo_documento
        documento.fornecedor_id = supplier.id if supplier else None
        documento.fornecedor_nome = fornecedor_nome
        documento.cnpj_emitente = cnpj_emitente
        documento.data_emissao = data_emissao
        documento.data_recebimento = data_recebimento
        documento.chave_acesso = chave_acesso
        documento.observacao = observacao
        documento.movimenta_estoque = movimenta_estoque
        if chave_acesso and tipo_documento == "nf":
            documento.status_integracao = "aguardando_certificado"
            documento.mensagem_integracao = "Consulta automática bloqueada até a configuração do certificado digital."
        else:
            documento.status_integracao = "manual"
            documento.mensagem_integracao = None

        with allow_document_quantity_update("nf.editar_documento"):
            affected_pending_item_ids: set[int] = set()
            for item_row in documento.itens:
                previous_quantidade = float(item_row.quantidade or 0.0)
                previous_status = (item_row.status_processamento or "pendente").strip().lower() or "pendente"
                previous_valor_unitario = item_row.valor_unitario
                previous_valor_total = item_row.valor_total
                previous_observacao = item_row.observacao
                quantidade = _parse_optional_float(
                    request.form.get(f"item_quantidade_{item_row.id_documento_item}"),
                    fallback=float(item_row.quantidade or 0.0),
                )
                valor_unitario_raw = request.form.get(f"item_valor_unitario_{item_row.id_documento_item}")
                valor_total_raw = request.form.get(f"item_valor_total_{item_row.id_documento_item}")
                valor_unitario, valor_total = _resolve_document_item_values(
                    quantidade=float(quantidade or 0.0),
                    valor_unitario_raw=valor_unitario_raw,
                    valor_total_raw=valor_total_raw,
                    fallback_valor_unitario=item_row.valor_unitario,
                    fallback_valor_total=item_row.valor_total,
                )
                observacao_item = (
                    request.form.get(f"item_observacao_{item_row.id_documento_item}")
                    or item_row.observacao
                    or ""
                ).strip() or None

                if quantidade is None or quantidade <= 0:
                    raise ValueError(f"Informe uma quantidade válida para o item {item_row.codigo_item}.")

                if (
                    previous_status == "processado"
                    and abs(float(quantidade) - float(item_row.quantidade or 0.0)) > 1e-6
                ):
                    raise ValueError(
                        f"O item {item_row.codigo_item} já foi incorporado ao estoque e não pode ter a quantidade alterada neste documento."
                    )

                item_row.quantidade = quantidade
                item_row.valor_unitario = valor_unitario
                item_row.valor_total = valor_total
                item_row.observacao = observacao_item

                if previous_status != "processado" and (
                    abs(float(quantidade) - previous_quantidade) > 1e-6
                    or _float_changed(valor_unitario, previous_valor_unitario)
                    or _float_changed(valor_total, previous_valor_total)
                    or observacao_item != previous_observacao
                ):
                    affected_pending_item_ids.add(item_row.id_documento_item)

            pending_document_items = [
                row for row in documento.itens
                if (row.status_processamento or "pendente").strip().lower() != "processado"
            ]
            process_item_ids: list[int] | None = None
            pre_registration_count = 0
            if bool(documento.movimenta_estoque):
                forced_pre_registration_ids: set[int] | None = None
                if not previous_movimenta_estoque:
                    forced_pre_registration_ids = {row.id_documento_item for row in pending_document_items}
                elif affected_pending_item_ids:
                    forced_pre_registration_ids = set(affected_pending_item_ids)

                pre_registration_count = _mark_manual_nf_document_items_for_pre_registration(
                    pending_document_items,
                    forced_item_ids=forced_pre_registration_ids,
                )
                if not previous_movimenta_estoque:
                    process_item_ids = [row.id_documento_item for row in pending_document_items]
                elif affected_pending_item_ids:
                    process_item_ids = sorted(affected_pending_item_ids)

            sync_result = _sync_document_financial_entries(documento)
            db.session.commit()
        stock_process_result = _process_document_stock_entries(
            documento,
            item_ids=process_item_ids,
        )
        _clear_nf_runtime_cache(documento.numero_documento)

        if sync_result["auto_confirmed"]:
            flash(
                f"Documento fiscal atualizado. {sync_result['updated']} lançamento(s) financeiro(s) sincronizado(s) e marcado(s) como compra com NF.",
                "success",
            )
        else:
            flash(
                "Documento fiscal atualizado. O vínculo financeiro foi sincronizado, mas a troca automática para compra com NF só ocorre após informar datas, chave de acesso e valores dos itens.",
                "warning",
            )
        if not documento.movimenta_estoque:
            flash("Documento fiscal atualizado apenas no financeiro. O estoque permaneceu inalterado.", "info")
        else:
            if pre_registration_count:
                flash(
                    f"{pre_registration_count} item(ns) lançados ou ajustados manualmente nesta NF aguardam finalização do pré-cadastro antes de entrar no estoque.",
                    "info",
                )
            if stock_process_result and stock_process_result.get("processed"):
                flash(
                    f"{stock_process_result['processed']} item(ns) foram incorporados ao estoque a partir do documento fiscal.",
                    "success",
                )
            elif pending_document_items and not pre_registration_count and not (stock_process_result and stock_process_result.get("errors")):
                flash(
                    f"{len(pending_document_items)} item(ns) ficaram prontos para conferência operacional.",
                    "info",
                )
        if sync_result["skipped"]:
            flash(
                f"{sync_result['skipped']} item(ns) não tinham lançamento financeiro compatível para atualização automática.",
                "info",
            )
        _flash_document_stock_processing_errors(stock_process_result)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")

    return redirect(
        _redirect_to_nf_context(
            numero_documento=documento.numero_documento,
            fallback_tab="processaveis",
            clear_selection=True,
        )
    )


@blueprint.post("/<int:documento_id>/itens/adicionar")
@login_required
def adicionar_item_documento(documento_id: int):
    _require_admin()
    documento = db.session.get(DocumentoEntradaEstoque, documento_id)
    if documento is None:
        flash("Documento fiscal não encontrado.", "danger")
        return redirect(url_for("nf.nf_index"))

    try:
        stock_process_result = None
        codigo_item = (request.form.get("codigo_item") or "").strip()
        quantidade = _parse_optional_float(request.form.get("quantidade"), fallback=None)
        valor_unitario = _parse_optional_float(request.form.get("valor_unitario"), fallback=None)
        valor_total = _parse_optional_float(request.form.get("valor_total"), fallback=None)
        observacao = (request.form.get("observacao") or "").strip() or None

        if not codigo_item:
            raise ValueError("Informe o código do item para adicionar ao documento.")
        item = inventory_service.get_item(codigo_item)
        if not item:
            raise ValueError("O item informado não existe no estoque. Cadastre o item antes de vinculá-lo ao documento.")
        if quantidade is None or quantidade <= 0:
            raise ValueError("Informe uma quantidade válida para o novo item do documento.")

        if valor_unitario is not None:
            valor_total = round(float(valor_unitario) * float(quantidade), 2)
        elif valor_total is not None and quantidade > 0:
            valor_unitario = round(float(valor_total) / float(quantidade), 2)

        with allow_document_quantity_update("nf.adicionar_item_documento"):
            affected_item_ids: set[int] = set()
            pending_document_items: list[DocumentoEntradaEstoqueItem] = []
            existing_row = next(
                (
                    row for row in documento.itens
                    if row.codigo_item == codigo_item and (row.status_processamento or "pendente").strip().lower() != "processado"
                ),
                None,
            )
            if existing_row is not None:
                existing_row.quantidade = round(float(existing_row.quantidade or 0.0) + float(quantidade), 2)
                if valor_unitario is not None:
                    existing_row.valor_unitario = valor_unitario
                    existing_row.valor_total = round(float(existing_row.quantidade or 0.0) * float(valor_unitario), 2)
                elif valor_total is not None:
                    existing_row.valor_total = round(float(existing_row.valor_total or 0.0) + float(valor_total), 2)
                if observacao:
                    existing_row.observacao = observacao if not existing_row.observacao else f"{existing_row.observacao} | {observacao}"
                affected_item_ids.add(existing_row.id_documento_item)
                pending_document_items.append(existing_row)
                flash(f"Item {codigo_item} já existia na NF e teve a quantidade somada.", "success")
            else:
                new_item_row = DocumentoEntradaEstoqueItem(
                    documento_id=documento.id_documento,
                    entrada_id=None,
                    codigo_item=codigo_item,
                    quantidade=float(quantidade),
                    valor_unitario=valor_unitario,
                    valor_total=valor_total,
                    lote=(item.get("lote") or "") if item else None,
                    data_validade=None,
                    observacao=observacao,
                )
                db.session.add(new_item_row)
                db.session.flush()
                affected_item_ids.add(new_item_row.id_documento_item)
                pending_document_items.append(new_item_row)
                flash(f"Item {codigo_item} adicionado ao documento fiscal {documento.numero_documento}.", "success")

            pre_registration_count = 0
            if bool(documento.movimenta_estoque):
                pre_registration_count = _mark_manual_nf_document_items_for_pre_registration(pending_document_items)

            sync_result = _sync_document_financial_entries(documento)
            db.session.commit()
        stock_process_result = _process_document_stock_entries(
            documento,
            item_ids=affected_item_ids,
        )
        _clear_nf_runtime_cache(documento.numero_documento)
        if sync_result["skipped"]:
            flash(
                f"{sync_result['skipped']} item(ns) seguem sem lançamento financeiro compatível para sincronização automática.",
                "info",
            )
        if not documento.movimenta_estoque:
            flash("Item adicionado apenas no financeiro. O documento está configurado para não movimentar estoque.", "info")
        else:
            if pre_registration_count:
                flash("O item lançado manualmente nesta NF aguarda finalização do pré-cadastro antes de ser incorporado ao estoque.", "info")
            if stock_process_result and stock_process_result.get("processed"):
                flash("O item foi incorporado ao estoque a partir do documento fiscal.", "success")
            elif affected_item_ids and not pre_registration_count and not (stock_process_result and stock_process_result.get("errors")):
                flash("O item ficou pronto para conferência operacional no documento fiscal.", "info")
        _flash_document_stock_processing_errors(stock_process_result)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")

    return redirect(
        _redirect_to_nf_context(
            numero_documento=documento.numero_documento,
            anchor=f"documento-editar-{documento.id_documento}",
            fallback_tab="processaveis",
        )
    )


@blueprint.post("/<int:documento_id>/itens/<int:documento_item_id>/excluir")
@login_required
def excluir_item_documento(documento_id: int, documento_item_id: int):
    _require_admin()
    documento = db.session.get(DocumentoEntradaEstoque, documento_id)
    item_row = db.session.get(DocumentoEntradaEstoqueItem, documento_item_id)

    if documento is None or item_row is None or item_row.documento_id != documento.id_documento:
        flash("Item do documento fiscal não encontrado.", "danger")
        return redirect(url_for("nf.nf_index"))

    numero_documento = documento.numero_documento
    codigo_item = item_row.codigo_item
    motivo_exclusao = (request.form.get("motivo_exclusao") or "").strip()

    if not motivo_exclusao:
        flash("Informe o motivo da exclusão.", "danger")
        return redirect(_redirect_to_nf_context(numero_documento=numero_documento, fallback_tab="historico"))

    item_snapshot = {
        "document_id": documento.id_documento,
        "document_item_id": item_row.id_documento_item,
        "numero_documento": documento.numero_documento,
        "codigo_item": item_row.codigo_item,
        "status_processamento": item_row.status_processamento,
        "stock_movement_id": item_row.stock_movement_id,
        "balance_before": None,
        "balance_after": None,
    }

    if (item_row.status_processamento or "").strip().lower() == "processado":
        flash(
            "Use a exclusão por erro de digitação para itens já incorporados ao estoque.",
            "info",
        )
        return redirect(_redirect_to_nf_context(numero_documento=numero_documento, fallback_tab="historico"))

    try:
        _purge_linked_entry(item_row.entrada_id)
        _purge_document_item_financial_entry(documento, item_row)
        db.session.delete(item_row)
        db.session.flush()

        has_items = (
            DocumentoEntradaEstoqueItem.query
            .filter_by(documento_id=documento.id_documento)
            .first()
            is not None
        )
        if not has_items:
            db.session.delete(documento)

        db.session.commit()
        _clear_nf_runtime_cache(numero_documento)
        _clear_finance_reports_cache()
        _audit_document_item_deletion(
            item_snapshot=item_snapshot,
            reason=motivo_exclusao,
            action_type="nf.document_item.delete",
        )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(_redirect_to_nf_context(numero_documento=numero_documento, fallback_tab="historico"))

    flash(f"Item {codigo_item} removido do documento fiscal {numero_documento}.", "success")
    return redirect(_redirect_to_nf_context(numero_documento=numero_documento, fallback_tab="processaveis"))


@blueprint.post("/<int:documento_id>/itens/<int:documento_item_id>/excluir-por-erro-digitacao")
@login_required
def excluir_item_documento_por_erro_digitacao(documento_id: int, documento_item_id: int):
    _require_admin()
    documento = db.session.get(DocumentoEntradaEstoque, documento_id)
    item_row = db.session.get(DocumentoEntradaEstoqueItem, documento_item_id)

    if documento is None or item_row is None or item_row.documento_id != documento.id_documento:
        flash("Item do documento fiscal não encontrado.", "danger")
        return redirect(url_for("nf.nf_index"))

    numero_documento = documento.numero_documento
    codigo_item = item_row.codigo_item
    motivo_exclusao = (request.form.get("motivo_exclusao") or "").strip()

    if not motivo_exclusao:
        flash("Informe o motivo da exclusão por erro de digitação.", "danger")
        return redirect(_redirect_to_nf_context(numero_documento=numero_documento, fallback_tab="historico"))

    item_snapshot = {
        "document_id": documento.id_documento,
        "document_item_id": item_row.id_documento_item,
        "numero_documento": documento.numero_documento,
        "codigo_item": item_row.codigo_item,
        "status_processamento": item_row.status_processamento,
        "stock_movement_id": item_row.stock_movement_id,
        "balance_before": None,
        "balance_after": None,
    }

    try:
        reversal_result = finance_service.delete_document_item_for_typo(
            item_row,
            usuario_matricula=current_user.id,
        )

        _purge_linked_entry(item_row.entrada_id)
        _purge_document_item_financial_entry(documento, item_row)
        db.session.delete(item_row)
        db.session.flush()

        has_items = (
            DocumentoEntradaEstoqueItem.query
            .filter_by(documento_id=documento.id_documento)
            .first()
            is not None
        )
        if not has_items:
            db.session.delete(documento)

        db.session.commit()
        _clear_nf_runtime_cache(numero_documento)
        _clear_finance_reports_cache()
        item_snapshot.update({
            "stock_movement_id": reversal_result.get("stock_movement_id"),
            "balance_before": reversal_result.get("balance_before"),
            "balance_after": reversal_result.get("balance_after"),
        })
        _audit_document_item_deletion(
            item_snapshot=item_snapshot,
            reason=motivo_exclusao,
            action_type="nf.document_item.delete.typo",
        )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(_redirect_to_nf_context(numero_documento=numero_documento, fallback_tab="historico"))

    flash(
        f"Item {codigo_item} removido do documento fiscal {numero_documento} por erro de digitação, com estorno do estoque.",
        "success",
    )
    return redirect(_redirect_to_nf_context(numero_documento=numero_documento, fallback_tab="processaveis"))
