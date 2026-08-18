from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from io import BytesIO
from typing import Any
import re
from time import monotonic

import requests
from flask import current_app
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
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
from .category_catalog import category_catalog_service
from .legacy_stock_normalizer import infer_packaging_measure, ignore_packaging_metadata_for_stock, resolve_canonical_unit, resolve_packaging_factor
from .price_normalization import (
    infer_document_quantity_unit_for_item,
    normalize_document_line,
    should_autofix_packaged_document_unit,
)

_DOCUMENT_UNIT_LABELS = {
    "m": ("metro", "metros"),
    "kg": ("kg", "kg"),
    "l": ("litro", "litros"),
    "un": ("unidade", "unidades"),
    "unidade": ("unidade", "unidades"),
    "unidades": ("unidade", "unidades"),
    "par": ("par", "pares"),
    "pares": ("par", "pares"),
}
_PACKAGING_UNIT_LABELS = {
    "lata": ("lata", "latas"),
    "rolo": ("rolo", "rolos"),
    "pacote": ("pacote", "pacotes"),
    "caixa": ("caixa", "caixas"),
    "fardo": ("fardo", "fardos"),
    "litro": ("litro", "litros"),
    "balde": ("balde", "baldes"),
    "bombona": ("bombona", "bombonas"),
    "saco": ("saco", "sacos"),
}
_LEGACY_CONVERSION_DOCUMENT_OBSERVATION = "Convertido automaticamente do histórico legado de entradas."
MANUAL_INTERNAL_DOCUMENT_NUMBER = "NOTA INTERNA"
MANUAL_INTERNAL_DOCUMENT_LEGACY_ALIASES = frozenset({
    MANUAL_INTERNAL_DOCUMENT_NUMBER,
    "SEM NF/CUPOM",
})
MANUAL_INTERNAL_DOCUMENT_UPPER_ALIASES = frozenset(alias.upper() for alias in MANUAL_INTERNAL_DOCUMENT_LEGACY_ALIASES)
_SUPPLIER_FIELD_LENGTH_LIMITS = {
    "razao_social": 200,
    "nome_fantasia": 200,
    "cnpj": 18,
    "inscricao_estadual": 30,
    "endereco_rua": 255,
    "endereco_numero": 20,
    "endereco_complemento": 100,
    "endereco_bairro": 100,
    "endereco_cidade": 100,
    "endereco_estado": 2,
    "endereco_cep": 10,
    "telefone": 30,
    "email": 120,
    "site": 120,
    "situacao_cadastral": 40,
    "api_origem": 40,
}
_SUPPLIER_FIELD_LABELS = {
    "razao_social": "Razao social",
    "nome_fantasia": "Nome fantasia",
    "cnpj": "CNPJ",
    "inscricao_estadual": "Inscricao estadual",
    "endereco_rua": "Logradouro",
    "endereco_numero": "Numero",
    "endereco_complemento": "Complemento",
    "endereco_bairro": "Bairro",
    "endereco_cidade": "Cidade",
    "endereco_estado": "UF",
    "endereco_cep": "CEP",
    "telefone": "Telefone",
    "email": "E-mail",
    "site": "Site",
    "situacao_cadastral": "Situacao cadastral",
    "api_origem": "Origem da API",
}
_WITHDRAWAL_REFERENCE_TYPES = frozenset({
    "saida",
    "legacy_movimento",
    "movements_saida_multipla",
    "api_mobile_retirar",
    "api_mobile_retirar_multipla",
})


def _format_compact_number(value: object) -> str | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if abs(number - round(number)) <= 1e-6:
        return str(int(round(number)))
    return f"{number:.6f}".rstrip("0").rstrip(".").replace(".", ",")


def _resolve_display_unit_label(item: Item | None, unit_code: str | None, quantity: float | None) -> str | None:
    normalized = (unit_code or "").strip().lower()
    if not normalized:
        return None

    amount = float(quantity or 0.0)
    singular_plural = _PACKAGING_UNIT_LABELS.get(normalized)
    if singular_plural is None:
        singular_plural = _DOCUMENT_UNIT_LABELS.get(normalized, (normalized, normalized))

    singular, plural = singular_plural
    return singular if abs(amount - 1.0) <= 1e-6 else plural


def _format_quantity_text(value: object, unit_label: str | None) -> str | None:
    number = _format_compact_number(value)
    if not number:
        return None
    if unit_label:
        return f"{number} {unit_label}"
    return number


def _normalize_document_unit_code(value: object) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "unidade": "un",
        "unidades": "un",
        "un": "un",
        "par": "par",
        "pares": "par",
        "quilo": "kg",
        "kg": "kg",
        "litro": "l",
        "litros": "l",
        "l": "l",
        "metro": "m",
        "metros": "m",
        "m": "m",
    }
    return aliases.get(raw, raw)


def _resolve_internal_content_document_unit(
    item: Item | None,
    *,
    row: DocumentoEntradaEstoqueItem | None = None,
) -> str | None:
    if item is None:
        return None

    packaging_factor = float(resolve_packaging_factor(item) or 0.0)
    if packaging_factor <= 0 or packaging_factor > 1.0 or ignore_packaging_metadata_for_stock(item):
        return None

    packaging_measure = infer_packaging_measure(item)
    if packaging_measure is None or packaging_measure[1] not in {"kg", "l", "m"}:
        return None

    if row is not None:
        row_unit = _normalize_document_unit_code(row.unidade_quantidade)
        if row_unit in {"un", "par"}:
            return row_unit

    canonical_unit = _normalize_document_unit_code(resolve_canonical_unit(item))
    if canonical_unit in {"un", "par"}:
        return canonical_unit
    return None


def _build_document_item_display_metadata(row: DocumentoEntradaEstoqueItem) -> dict[str, Any]:
    item_model = row.item
    quantity_value = float(row.quantidade or 0.0)
    stored_quantity_unit = (row.unidade_quantidade or "").strip().lower() or None
    stored_price_unit = (row.unidade_preco or stored_quantity_unit or "").strip().lower() or None

    try:
        quantity_base_value = float(row.quantidade_base) if row.quantidade_base not in (None, "") else None
    except (TypeError, ValueError):
        quantity_base_value = None

    effective_quantity_unit = stored_quantity_unit
    effective_price_unit = stored_price_unit
    base_unit = None
    packaging_unit = None
    packaging_factor = 0.0
    auto_fixed_preview = False
    uses_packaging_documental = False

    if item_model is not None:
        packaging_unit = (item_model.tipo_embalagem_novo or "").strip().lower() or None
        packaging_factor = float(resolve_packaging_factor(item_model) or 0.0)
        has_packaging = bool(packaging_unit and packaging_factor > 0 and not ignore_packaging_metadata_for_stock(item_model))
        can_autofix = (
            has_packaging
            and (row.status_processamento or "pendente").strip().lower() != "processado"
            and row.stock_movement_id is None
            and row.entrada_id is None
        )
        if not effective_quantity_unit:
            effective_quantity_unit = infer_document_quantity_unit_for_item(item_model)
            auto_fixed_preview = bool(has_packaging)
        elif can_autofix and should_autofix_packaged_document_unit(
            item_model,
            current_unit=effective_quantity_unit,
            quantity=quantity_value,
            quantity_base=quantity_base_value,
        ):
            effective_quantity_unit = infer_document_quantity_unit_for_item(item_model)
            auto_fixed_preview = True

        if auto_fixed_preview and (not stored_price_unit or stored_price_unit == stored_quantity_unit):
            effective_price_unit = effective_quantity_unit
        effective_price_unit = effective_price_unit or effective_quantity_unit
        try:
            normalized = normalize_document_line(
                item_model,
                quantity=quantity_value,
                quantity_unit=effective_quantity_unit,
                unit_price=float(row.valor_unitario) if row.valor_unitario not in (None, "") else None,
                total_price=float(row.valor_total) if row.valor_total not in (None, "") else None,
                price_unit=effective_price_unit,
            )
            effective_quantity_unit = normalized.quantity_unit or effective_quantity_unit
            effective_price_unit = normalized.price_unit or effective_price_unit
            quantity_base_value = float(normalized.quantity_base or 0.0)
            base_unit = (normalized.unit_base or resolve_canonical_unit(item_model) or "").strip().lower() or None
        except Exception:
            base_unit = (resolve_canonical_unit(item_model) or "").strip().lower() or None
    else:
        base_unit = stored_quantity_unit

    document_unit_label = _resolve_display_unit_label(item_model, effective_quantity_unit, quantity_value)
    base_unit_label = _resolve_display_unit_label(item_model, base_unit, quantity_base_value)
    content_unit_label = _resolve_display_unit_label(item_model, base_unit, packaging_factor)

    quantity_display = _format_quantity_text(quantity_value, document_unit_label)
    quantity_base_display = _format_quantity_text(quantity_base_value, base_unit_label)
    content_display = _format_quantity_text(packaging_factor, content_unit_label)

    if item_model is not None and packaging_unit and packaging_factor > 0 and not ignore_packaging_metadata_for_stock(item_model):
        uses_packaging_documental = effective_quantity_unit == packaging_unit

    conversion_display = None
    if uses_packaging_documental and quantity_display and content_display and quantity_base_display:
        conversion_display = f"{quantity_display} de {content_display} = {quantity_base_display}"

    return {
        "unidade_quantidade": row.unidade_quantidade,
        "unidade_quantidade_efetiva": effective_quantity_unit,
        "unidade_preco": row.unidade_preco,
        "unidade_preco_efetiva": effective_price_unit,
        "quantidade_base": row.quantidade_base,
        "quantidade_base_efetiva": round(float(quantity_base_value or 0.0), 6) if quantity_base_value is not None else None,
        "unidade_base_efetiva": base_unit,
        "tipo_embalagem_documental": packaging_unit,
        "conteudo_por_embalagem": round(float(packaging_factor or 0.0), 6) if packaging_factor > 0 else None,
        "usa_embalagem_documental": uses_packaging_documental,
        "autocorrecao_documental_preview": auto_fixed_preview,
        "quantidade_documento_display": quantity_display,
        "quantidade_base_display": quantity_base_display,
        "conteudo_por_embalagem_display": content_display,
        "conversao_display": conversion_display,
    }


def _normalize_financial_line(
    item: Item | None,
    *,
    quantity: float,
    valor_unitario: float | None,
    valor_total: float | None,
    quantity_unit: str | None = None,
    price_unit: str | None = None,
) -> dict[str, Any]:
    qty = float(quantity or 0.0)
    raw_unit = float(valor_unitario) if valor_unitario not in (None, "") else None
    raw_total = float(valor_total) if valor_total not in (None, "") else None

    resolved_quantity_unit = (quantity_unit or "").strip().lower()
    if not resolved_quantity_unit and item is not None:
        resolved_quantity_unit = infer_document_quantity_unit_for_item(item)
    if not resolved_quantity_unit:
        resolved_quantity_unit = "un"

    resolved_price_unit = (price_unit or "").strip().lower() or resolved_quantity_unit
    if raw_total is None and raw_unit is not None:
        raw_total = round(raw_unit * qty, 2)

    if item is not None:
        try:
            normalized = normalize_document_line(
                item,
                quantity=qty,
                quantity_unit=resolved_quantity_unit,
                unit_price=raw_unit,
                total_price=raw_total,
                price_unit=resolved_price_unit,
            )
            return {
                "quantity": qty,
                "quantity_unit": normalized.quantity_unit,
                "quantity_base": float(normalized.quantity_base or 0.0),
                "unit_price_input": normalized.unit_price_input,
                "unit_price_base": normalized.unit_price_base,
                "total_value": normalized.total_value,
                "price_unit": normalized.price_unit,
                "factor_to_base": float(normalized.factor_to_base or 1.0),
            }
        except Exception:
            pass

    unit_price_base = None
    if raw_total is not None and qty > 0:
        unit_price_base = round(raw_total / qty, 8)
    elif raw_unit is not None:
        unit_price_base = raw_unit

    return {
        "quantity": qty,
        "quantity_unit": resolved_quantity_unit,
        "quantity_base": qty,
        "unit_price_input": raw_unit,
        "unit_price_base": unit_price_base,
        "total_value": raw_total,
        "price_unit": resolved_price_unit,
        "factor_to_base": 1.0 if raw_unit is not None else None,
    }


def _coerce_float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_financial_entry_metrics(entry: FinanceLedgerEntry) -> dict[str, float]:
    raw_quantity = _coerce_float_or_none(getattr(entry, "quantidade", None)) or 0.0
    stored_quantity_base = _coerce_float_or_none(getattr(entry, "quantidade_base", None))
    raw_unit_price = _coerce_float_or_none(getattr(entry, "valor_unitario", None))
    stored_unit_price_base = _coerce_float_or_none(getattr(entry, "valor_unitario_base", None))
    raw_total = _coerce_float_or_none(getattr(entry, "valor_total", None))

    normalized_line = _normalize_financial_line(
        getattr(entry, "item", None),
        quantity=raw_quantity,
        valor_unitario=raw_unit_price,
        valor_total=raw_total,
        quantity_unit=getattr(entry, "unidade_quantidade", None),
        price_unit=getattr(entry, "unidade_preco", None),
    )
    normalized_quantity_base = _coerce_float_or_none(normalized_line.get("quantity_base"))
    normalized_unit_price_base = _coerce_float_or_none(normalized_line.get("unit_price_base"))

    quantity_base = stored_quantity_base if stored_quantity_base not in (None, 0.0) else normalized_quantity_base
    if (
        normalized_quantity_base not in (None, 0.0)
        and stored_quantity_base not in (None, 0.0)
        and raw_quantity > 0
        and abs(float(stored_quantity_base) - raw_quantity) <= 1e-6
        and abs(float(normalized_quantity_base) - raw_quantity) > 1e-6
    ):
        quantity_base = normalized_quantity_base
    if quantity_base in (None, 0.0):
        quantity_base = raw_quantity

    unit_price_base = stored_unit_price_base if stored_unit_price_base not in (None, 0.0) else normalized_unit_price_base
    if (
        normalized_unit_price_base not in (None, 0.0)
        and stored_unit_price_base not in (None, 0.0)
        and raw_unit_price not in (None, 0.0)
        and abs(float(stored_unit_price_base) - float(raw_unit_price)) <= 1e-6
        and abs(float(normalized_unit_price_base) - float(raw_unit_price)) > 1e-6
    ):
        unit_price_base = normalized_unit_price_base
    if unit_price_base in (None, 0.0):
        unit_price_base = normalized_unit_price_base if normalized_unit_price_base not in (None, 0.0) else (raw_unit_price or 0.0)

    return {
        "quantity_base": float(quantity_base or 0.0),
        "unit_price_base": float(unit_price_base or 0.0),
    }


class FinanceService:
    """Serviço de fornecedores, exercício financeiro e prestação de contas."""

    _runtime_cache: dict[str, tuple[float, Any]] = {}

    @staticmethod
    def normalize_manual_internal_document_number(numero_documento: str | None) -> str:
        numero = (numero_documento or "").strip()
        if not numero:
            return ""
        if numero.upper() in MANUAL_INTERNAL_DOCUMENT_UPPER_ALIASES:
            return MANUAL_INTERNAL_DOCUMENT_NUMBER
        return numero

    @staticmethod
    def is_manual_internal_document_number(numero_documento: str | None) -> bool:
        numero = (numero_documento or "").strip()
        if not numero:
            return False
        return numero.upper() in MANUAL_INTERNAL_DOCUMENT_UPPER_ALIASES

    @staticmethod
    def manual_internal_document_aliases() -> tuple[str, ...]:
        return tuple(sorted(MANUAL_INTERNAL_DOCUMENT_LEGACY_ALIASES))

    @staticmethod
    def is_manual_internal_bucket_document(document: DocumentoEntradaEstoque | None) -> bool:
        if document is None:
            return False
        tipo = (document.tipo_documento or "").strip().lower()
        if tipo != "manual":
            return False
        if FinanceService.is_manual_internal_document_number(document.numero_documento):
            return True
        has_supplier = document.fornecedor_id is not None or bool((document.fornecedor_nome or "").strip())
        has_cnpj = bool((document.cnpj_emitente or "").strip())
        has_access_key = bool((document.chave_acesso or "").strip())
        return not has_supplier and not has_cnpj and not has_access_key

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
    def normalize_stock_document_type(value: str | None, *, fallback: str = "nf") -> str:
        normalized = (value or "").strip().lower()
        return normalized or fallback

    @staticmethod
    def document_allows_supplier_cnpj(tipo_documento: str | None) -> bool:
        return FinanceService.normalize_stock_document_type(tipo_documento) in {"nf", "cupom"}

    @staticmethod
    def sanitize_document_supplier_inputs(
        *,
        tipo_documento: str | None,
        supplier_id: int | None = None,
        supplier_name: str | None = None,
        supplier_cnpj: str | None = None,
    ) -> dict[str, Any]:
        tipo = FinanceService.normalize_stock_document_type(tipo_documento)
        normalized_supplier_id = int(supplier_id) if supplier_id else None
        normalized_supplier_name = (supplier_name or "").strip() or None
        normalized_supplier_cnpj = FinanceService.normalize_cnpj(supplier_cnpj) or None

        if tipo == "manual":
            return {
                "supplier_id": None,
                "supplier_name": None,
                "supplier_cnpj": None,
            }

        if not FinanceService.document_allows_supplier_cnpj(tipo):
            normalized_supplier_cnpj = None

        return {
            "supplier_id": normalized_supplier_id,
            "supplier_name": normalized_supplier_name,
            "supplier_cnpj": normalized_supplier_cnpj,
        }

    @staticmethod
    def _cnpj_digits(value: str | None) -> str:
        return "".join(ch for ch in (value or "") if ch.isdigit())

    @staticmethod
    def _payload_value(payload: Any, *path: str) -> Any:
        current = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
            if current is None:
                return None
        return current

    @staticmethod
    def _as_text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _first_nested_text(value: Any, *, preferred_keys: tuple[str, ...] = ()) -> str:
        if value in (None, ""):
            return ""
        if isinstance(value, dict):
            for key in preferred_keys:
                text = FinanceService._first_nested_text(value.get(key), preferred_keys=preferred_keys)
                if text:
                    return text
            for nested in value.values():
                text = FinanceService._first_nested_text(nested, preferred_keys=preferred_keys)
                if text:
                    return text
            return ""
        if isinstance(value, (list, tuple, set)):
            for item in value:
                text = FinanceService._first_nested_text(item, preferred_keys=preferred_keys)
                if text:
                    return text
            return ""
        return FinanceService._as_text(value)

    @staticmethod
    def _extract_supplier_registration(value: Any) -> str | None:
        text = FinanceService._first_nested_text(
            value,
            preferred_keys=(
                "inscricao_estadual",
                "inscricao",
                "numero",
                "registration",
                "value",
            ),
        )
        return text or None

    @staticmethod
    def _normalize_supplier_phone(*values: Any) -> str | None:
        parts: list[str] = []

        def _collect(raw_value: Any) -> None:
            if raw_value in (None, ""):
                return
            if isinstance(raw_value, dict):
                ddd = FinanceService._first_nested_text(
                    raw_value.get("ddd") or raw_value.get("ddd1") or raw_value.get("ddd2") or raw_value.get("codigo_area")
                )
                number = FinanceService._first_nested_text(
                    raw_value.get("telefone") or raw_value.get("telefone1") or raw_value.get("telefone2") or raw_value.get("numero")
                )
                joined = " ".join(part for part in (ddd, number) if part).strip()
                if joined:
                    parts.append(joined)
                    return
                for nested in raw_value.values():
                    _collect(nested)
                return
            if isinstance(raw_value, (list, tuple, set)):
                for item in raw_value:
                    _collect(item)
                return
            text = FinanceService._as_text(raw_value)
            if text:
                parts.append(re.sub(r"\s+", " ", text))

        for candidate in values:
            _collect(candidate)

        normalized_parts: list[str] = []
        seen: set[str] = set()
        for part in parts:
            cleaned = part.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized_parts.append(cleaned)
        return " / ".join(normalized_parts) or None

    @staticmethod
    def _validate_supplier_string_lengths(data: dict[str, Any]) -> None:
        for field_name, max_length in _SUPPLIER_FIELD_LENGTH_LIMITS.items():
            value = data.get(field_name)
            if value in (None, ""):
                continue
            text = FinanceService._as_text(value)
            if len(text) > max_length:
                label = _SUPPLIER_FIELD_LABELS.get(field_name, field_name.replace("_", " ").capitalize())
                raise ValueError(f"{label} excede o limite de {max_length} caracteres.")

    @staticmethod
    def _is_legacy_conversion_placeholder(document: DocumentoEntradaEstoque | None) -> bool:
        if document is None:
            return False
        if (document.tipo_documento or "").strip().lower() != "manual":
            return False
        if (document.status_integracao or "").strip().lower() != "manual":
            return False
        if (document.observacao or "").strip() != _LEGACY_CONVERSION_DOCUMENT_OBSERVATION:
            return False
        if document.fornecedor_id is not None:
            return False
        if (document.fornecedor_nome or "").strip():
            return False
        if (document.cnpj_emitente or "").strip():
            return False
        if (document.chave_acesso or "").strip():
            return False
        return True

    @staticmethod
    def _stock_document_priority(document: DocumentoEntradaEstoque) -> tuple[int, datetime, int]:
        score = 0
        tipo = (document.tipo_documento or "").strip().lower()
        if tipo == "nf":
            score += 100
        if not FinanceService._is_legacy_conversion_placeholder(document):
            score += 50
        if document.fornecedor_id is not None or (document.fornecedor_nome or "").strip():
            score += 10
        if (document.cnpj_emitente or "").strip():
            score += 5
        if (document.chave_acesso or "").strip():
            score += 5
        return (score, document.criado_em or datetime.min, int(document.id_documento or 0))

    @staticmethod
    def _stock_document_supplier_identity(document: DocumentoEntradaEstoque | None) -> str:
        if document is None:
            return ""
        cnpj = (document.cnpj_emitente or "").strip()
        if cnpj:
            return f"cnpj:{cnpj}"
        if document.fornecedor_id is not None:
            return f"fornecedor:{int(document.fornecedor_id)}"
        if FinanceService._is_legacy_conversion_placeholder(document):
            return ""
        supplier_name = (document.fornecedor_nome or "").strip().lower()
        if supplier_name:
            return f"nome:{supplier_name}"
        return ""

    @staticmethod
    def _select_reusable_existing_document(
        documents: list[DocumentoEntradaEstoque],
        *,
        require_unambiguous_identity: bool = False,
    ) -> DocumentoEntradaEstoque | None:
        if not documents:
            return None

        ordered = sorted(
            documents,
            key=FinanceService._stock_document_priority,
            reverse=True,
        )
        if not require_unambiguous_identity:
            return ordered[0]

        identities: dict[str, DocumentoEntradaEstoque] = {}
        for document in ordered:
            identity = FinanceService._stock_document_supplier_identity(document)
            if not identity:
                continue
            identities.setdefault(identity, document)

        if len(identities) > 1:
            raise ValueError(
                "Já existem documentos com esse mesmo número vinculados a fornecedores diferentes. "
                "Informe o fornecedor ou o CNPJ para evitar mistura documental."
            )

        if identities:
            return next(iter(identities.values()))

        return ordered[0]

    @staticmethod
    def _select_canonical_documents(documents: list[DocumentoEntradaEstoque]) -> list[DocumentoEntradaEstoque]:
        documents_by_number: dict[str, DocumentoEntradaEstoque] = {}
        documents_without_number: list[DocumentoEntradaEstoque] = []
        for document in documents:
            numero = FinanceService.normalize_manual_internal_document_number(document.numero_documento)
            if not numero:
                documents_without_number.append(document)
                continue
            current = documents_by_number.get(numero)
            if current is None or FinanceService._stock_document_priority(document) > FinanceService._stock_document_priority(current):
                documents_by_number[numero] = document

        ordered = list(documents_by_number.values()) + documents_without_number
        ordered.sort(
            key=lambda row: (row.criado_em or datetime.min, int(row.id_documento or 0)),
            reverse=True,
        )
        return ordered

    @staticmethod
    def _find_legacy_placeholder_document(numero_documento: str) -> DocumentoEntradaEstoque | None:
        numero = FinanceService.normalize_manual_internal_document_number(numero_documento)
        if not numero:
            return None
        aliases = FinanceService.manual_internal_document_aliases() if FinanceService.is_manual_internal_document_number(numero) else (numero,)
        rows = (
            DocumentoEntradaEstoque.query
            .filter(DocumentoEntradaEstoque.numero_documento.in_(aliases))
            .order_by(DocumentoEntradaEstoque.criado_em.desc(), DocumentoEntradaEstoque.id_documento.desc())
            .all()
        )
        for row in rows:
            if FinanceService._is_legacy_conversion_placeholder(row):
                return row
        return None

    @staticmethod
    def normalize_nf_identity_number(numero_documento: str | None) -> str:
        raw = (numero_documento or "").strip()
        if not raw:
            return ""
        digits = re.sub(r"\D+", "", raw)
        if digits:
            return digits.lstrip("0") or "0"
        return re.sub(r"\s+", "", raw).upper()

    @staticmethod
    def _find_nf_documents_by_identity(numero_documento: str) -> list[DocumentoEntradaEstoque]:
        identity = FinanceService.normalize_nf_identity_number(numero_documento)
        if not identity:
            return []
        rows = (
            DocumentoEntradaEstoque.query
            .filter(DocumentoEntradaEstoque.tipo_documento == "nf")
            .order_by(DocumentoEntradaEstoque.id_documento.desc())
            .all()
        )
        return [
            row
            for row in rows
            if FinanceService.normalize_nf_identity_number(row.numero_documento) == identity
        ]

    @staticmethod
    def _select_preferred_nf_document(
        documents: list[DocumentoEntradaEstoque],
        *,
        numero_documento: str,
    ) -> DocumentoEntradaEstoque | None:
        if not documents:
            return None
        requested = (numero_documento or "").strip()

        def sort_key(document: DocumentoEntradaEstoque) -> tuple[bool, bool, int, tuple[int, datetime, int]]:
            existing_number = (document.numero_documento or "").strip()
            return (
                existing_number == requested,
                existing_number.startswith("0"),
                len(existing_number),
                FinanceService._stock_document_priority(document),
            )

        return sorted(documents, key=sort_key, reverse=True)[0]

    @staticmethod
    def _validate_nf_existing_document_identity(
        document: DocumentoEntradaEstoque,
        *,
        numero_documento: str,
        chave_acesso: str | None = None,
        cnpj_emitente: str | None = None,
        supplier_id: int | None = None,
        supplier_name: str | None = None,
    ) -> None:
        normalized_key = (chave_acesso or "").strip() or None
        existing_key = (getattr(document, "chave_acesso", None) or "").strip() or None
        if normalized_key and existing_key and existing_key != normalized_key:
            raise ValueError(
                f"A NF {numero_documento} já está cadastrada com outra chave de acesso. "
                "Edite o documento existente ou exclua-o antes de recadastrar."
            )

        normalized_cnpj = FinanceService.normalize_cnpj(cnpj_emitente) or None
        existing_cnpj = FinanceService.normalize_cnpj(getattr(document, "cnpj_emitente", None)) or None
        if normalized_cnpj and existing_cnpj and existing_cnpj != normalized_cnpj:
            raise ValueError(
                f"A NF {numero_documento} já está cadastrada para outro emitente. "
                "Edite o documento existente ou exclua-o antes de recadastrar."
            )

        existing_supplier_id = getattr(document, "fornecedor_id", None)
        if supplier_id is not None and existing_supplier_id is not None and int(existing_supplier_id) != int(supplier_id):
            raise ValueError(
                f"A NF {numero_documento} já está vinculada a outro fornecedor. "
                "Edite o documento existente ou exclua-o antes de recadastrar."
            )

        requested_name = (supplier_name or "").strip().lower()
        existing_name = (getattr(document, "fornecedor_nome", None) or "").strip().lower()
        if requested_name and existing_name and requested_name != existing_name and not any(
            [supplier_id, existing_supplier_id, normalized_cnpj, existing_cnpj]
        ):
            raise ValueError(
                f"A NF {numero_documento} já está cadastrada com outro emitente informado. "
                "Edite o documento existente ou exclua-o antes de recadastrar."
            )

    @staticmethod
    def _resolve_unique_nf_existing_document(
        documents: list[DocumentoEntradaEstoque],
        *,
        numero_documento: str,
        chave_acesso: str | None = None,
        cnpj_emitente: str | None = None,
        supplier_id: int | None = None,
        supplier_name: str | None = None,
    ) -> DocumentoEntradaEstoque | None:
        if not documents:
            return None

        ordered = sorted(
            documents,
            key=FinanceService._stock_document_priority,
            reverse=True,
        )
        requested_identity = FinanceService.normalize_nf_identity_number(numero_documento)
        existing_identities = {
            FinanceService.normalize_nf_identity_number(document.numero_documento)
            for document in ordered
        }
        if len(existing_identities) > 1 or requested_identity not in existing_identities:
            raise ValueError(
                f"A NF {numero_documento} conflita com documentos fiscais de outra numeração. "
                "Revise o cadastro antes de continuar."
            )

        requested_has_identity = any([supplier_id, cnpj_emitente, supplier_name])
        if not requested_has_identity:
            supplier_identities = {
                FinanceService._stock_document_supplier_identity(document)
                for document in ordered
                if FinanceService._stock_document_supplier_identity(document)
            }
            if len(supplier_identities) > 1:
                raise ValueError(
                    f"A NF {numero_documento} já está cadastrada para fornecedores diferentes. "
                    "Informe o fornecedor ou CNPJ correto para evitar mistura documental."
                )

        for document in ordered:
            FinanceService._validate_nf_existing_document_identity(
                document,
                numero_documento=numero_documento,
                chave_acesso=chave_acesso,
                cnpj_emitente=cnpj_emitente,
                supplier_id=supplier_id,
                supplier_name=supplier_name,
            )

        document = FinanceService._select_preferred_nf_document(ordered, numero_documento=numero_documento)
        if document is None:
            raise ValueError(
                f"Não foi possível localizar o cadastro existente da NF {numero_documento}."
            )

        return document

    @staticmethod
    def _numbers_match(left: object, right: object, *, tolerance: float = 1e-6) -> bool:
        if left in (None, "") and right in (None, ""):
            return True
        if left in (None, "") or right in (None, ""):
            return False
        try:
            return abs(float(left) - float(right)) <= tolerance
        except (TypeError, ValueError):
            return str(left).strip() == str(right).strip()

    @staticmethod
    def _find_equivalent_nf_document_item(
        document: DocumentoEntradaEstoque | None,
        *,
        codigo_item: str,
        quantidade: float,
        unidade_quantidade: str | None,
        quantidade_base: float | None,
        valor_unitario: float | None,
        valor_total: float | None,
        unidade_preco: str | None,
        valor_unitario_base: float | None,
    ) -> DocumentoEntradaEstoqueItem | None:
        if document is None:
            return None

        quantity_unit = (unidade_quantidade or "").strip().lower()
        price_unit = (unidade_preco or "").strip().lower()
        candidates: list[DocumentoEntradaEstoqueItem] = []
        for row in document.itens:
            if row.codigo_item != codigo_item:
                continue
            if (row.unidade_quantidade or "").strip().lower() != quantity_unit:
                continue
            if (row.unidade_preco or "").strip().lower() != price_unit:
                continue
            if not FinanceService._numbers_match(row.quantidade, quantidade):
                continue
            if not FinanceService._numbers_match(row.quantidade_base, quantidade_base):
                continue
            if not FinanceService._numbers_match(row.valor_unitario, valor_unitario):
                continue
            if not FinanceService._numbers_match(row.valor_unitario_base, valor_unitario_base):
                continue
            if not FinanceService._numbers_match(row.valor_total, valor_total):
                continue
            candidates.append(row)

        if not candidates:
            return None

        candidates.sort(
            key=lambda row: (
                1 if (row.status_processamento or "").strip().lower() == "processado" else 0,
                int(row.stock_movement_id or 0),
                int(row.id_documento_item or 0),
            ),
            reverse=True,
        )
        return candidates[0]

    @staticmethod
    def _find_reusable_legacy_document_item(
        document: DocumentoEntradaEstoque | None,
        *,
        codigo_item: str,
        quantidade: float,
        unidade_quantidade: str | None,
        valor_unitario: float | None,
        valor_total: float | None,
    ) -> DocumentoEntradaEstoqueItem | None:
        if document is None:
            return None

        def _same_number(left: object, right: object) -> bool:
            if left in (None, "") or right in (None, ""):
                return False
            try:
                return abs(float(left) - float(right)) <= 1e-6
            except (TypeError, ValueError):
                return False

        unidade_norm = (unidade_quantidade or "").strip().lower() or None
        for row in document.itens:
            if row.codigo_item != codigo_item:
                continue
            if row.entrada_id is None:
                continue
            if row.stock_movement_id is not None or row.operation_log_id is not None:
                continue
            if not _same_number(row.quantidade, quantidade):
                continue

            row_unit = (row.unidade_quantidade or "").strip().lower() or None
            if row_unit and unidade_norm and row_unit != unidade_norm:
                continue
            if valor_unitario is not None and row.valor_unitario not in (None, "") and not _same_number(row.valor_unitario, valor_unitario):
                continue
            if valor_total is not None and row.valor_total not in (None, "") and not _same_number(row.valor_total, valor_total):
                continue
            return row

        return None

    @staticmethod
    def _build_category_conic_gradient(segments: list[dict[str, Any]]) -> str:
        if not segments:
            return "conic-gradient(from -90deg, rgba(51, 65, 85, 0.76) 0% 100%)"

        parts: list[str] = []
        start = 0.0
        for segment in segments:
            share_pct = max(0.0, float(segment.get("share_pct") or 0.0))
            if share_pct <= 0:
                continue
            end = min(100.0, start + share_pct)
            parts.append(f"{segment.get('color') or '#94a3b8'} {start:.2f}% {end:.2f}%")
            start = end

        if start < 100.0:
            parts.append(f"rgba(51, 65, 85, 0.76) {start:.2f}% 100%")

        return "conic-gradient(from -90deg, " + ", ".join(parts) + ")"

    @staticmethod
    def _compact_finance_kpi_segments(
        segments: list[dict[str, Any]],
        *,
        visible_limit: int = 4,
    ) -> tuple[list[dict[str, Any]], int]:
        if len(segments) <= visible_limit:
            return [dict(segment) for segment in segments], 0

        visible_segments = [dict(segment) for segment in segments[:visible_limit]]
        hidden_segments = segments[visible_limit:]
        hidden_value = round(sum(float(segment.get("value") or 0.0) for segment in hidden_segments), 2)
        hidden_share = sum(float(segment.get("share_pct") or 0.0) for segment in hidden_segments)

        if hidden_value > 0 or hidden_share > 0:
            visible_segments.append(
                {
                    "categoria": "Outras categorias",
                    "value": hidden_value,
                    "share_pct": hidden_share,
                    "color": "#64748b",
                    "soft": "rgba(100, 116, 139, 0.18)",
                    "soft_strong": "rgba(100, 116, 139, 0.28)",
                    "icon": "+",
                    "is_aggregate": True,
                    "hidden_categories_count": len(hidden_segments),
                }
            )

        return visible_segments, len(hidden_segments)

    @staticmethod
    def _build_finance_category_kpis(category_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        definitions = (
            {
                "key": "estoque-compra",
                "title": "Estoque por compra",
                "value_key": "total_atual_compra",
                "note": "Saldo atual no custo de compra repartido pelas categorias do estoque.",
            },
            {
                "key": "estoque-reposicao",
                "title": "Estoque por reposição",
                "value_key": "total_atual_reposicao",
                "note": "Saldo atual no custo de reposição usando a mesma paleta das categorias.",
            },
            {
                "key": "investido-exercicio",
                "title": "Investido no exercício",
                "value_key": "total_investido",
                "note": "Entradas financeiras do exercício distribuídas por categoria.",
            },
            {
                "key": "consumido-exercicio",
                "title": "Consumido no exercício",
                "value_key": "total_consumido",
                "note": "Consumo estimado do exercício quebrado pelas categorias de itens.",
            },
            {
                "key": "sem-comprovacao",
                "title": "Sem comprovação",
                "value_key": "total_sem_comprovacao",
                "note": "Pendência fiscal distribuída pelas mesmas cores padrão das categorias.",
            },
        )

        kpis: list[dict[str, Any]] = []
        for definition in definitions:
            segments: list[dict[str, Any]] = []
            total_value = 0.0
            for index, card in enumerate(category_cards):
                value = round(float(card.get(definition["value_key"]) or 0.0), 2)
                if value <= 0:
                    continue
                visual = card.get("visual") or category_catalog_service.get_visual(card.get("categoria"), fallback_index=index)
                total_value += value
                segments.append(
                    {
                        "categoria": card.get("categoria") or "Sem categoria",
                        "value": value,
                        "color": visual.get("color"),
                        "soft": visual.get("soft"),
                        "soft_strong": visual.get("soft_strong"),
                        "icon": visual.get("icon"),
                    }
                )

            segments.sort(key=lambda row: (-float(row.get("value") or 0.0), str(row.get("categoria") or "").casefold()))
            if total_value > 0:
                for segment in segments:
                    segment["share_pct"] = (float(segment.get("value") or 0.0) / total_value) * 100.0
            else:
                for segment in segments:
                    segment["share_pct"] = 0.0

            top_segment = segments[0] if segments else None
            visible_segments, hidden_segments_count = FinanceService._compact_finance_kpi_segments(segments)
            kpis.append(
                {
                    "key": definition["key"],
                    "title": definition["title"],
                    "value": round(total_value, 2),
                    "note": definition["note"],
                    "segments": visible_segments,
                    "segments_count": len(segments),
                    "visible_segments_count": len(visible_segments),
                    "hidden_segments_count": hidden_segments_count,
                    "legend_note": (
                        f"Top 4 categorias visíveis e {hidden_segments_count} agrupada(s) em Outras categorias."
                        if hidden_segments_count
                        else ""
                    ),
                    "top_category": top_segment.get("categoria") if top_segment else None,
                    "top_share_pct": round(float(top_segment.get("share_pct") or 0.0), 1) if top_segment else 0.0,
                    "accent_color": top_segment.get("color") if top_segment else "#94a3b8",
                    "accent_soft": top_segment.get("soft") if top_segment else "rgba(148, 163, 184, 0.18)",
                    "ring_gradient": FinanceService._build_category_conic_gradient(visible_segments),
                }
            )

        return kpis

    @staticmethod
    def resolve_document_movimenta_estoque(*, data_emissao: date | None, data_recebimento: date | None) -> bool:
        return True

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
    @staticmethod
    def get_exercise_for_date(reference: date | datetime | None = None) -> dict[str, Any]:
        if reference is None:
            ref_date = date.today()
        elif isinstance(reference, datetime):
            ref_date = reference.date()
        else:
            ref_date = reference

        start_date = date(ref_date.year, 1, 1)
        end_date = date(ref_date.year, 12, 31)
        return {
            "label": f"{ref_date.year}",
            "start_date": start_date,
            "end_date": end_date,
            "start_dt": datetime.combine(start_date, time.min),
            "end_dt": datetime.combine(end_date, time.max),
            "closing_day": 31,
            "closing_month": 12,
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
        cursor_year = start_ref.year
        last_year = end_ref.year
        while cursor_year <= last_year:
            exercise = FinanceService.get_exercise_for_date(date(cursor_year, 7, 1))
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
        year_match = re.match(r"^(\d{4})$", clean)
        if year_match:
            year = int(year_match.group(1))
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)
            return {
                "label": f"{year}",
                "start_date": start_date,
                "end_date": end_date,
                "start_dt": datetime.combine(start_date, time.min),
                "end_dt": datetime.combine(end_date, time.max),
                "closing_day": 31,
                "closing_month": 12,
            }

        match = re.match(r"^(\d{4})\/(\d{4})$", clean)
        if match:
            year = int(match.group(2))
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)
            return {
                "label": f"{year}",
                "start_date": start_date,
                "end_date": end_date,
                "start_dt": datetime.combine(start_date, time.min),
                "end_dt": datetime.combine(end_date, time.max),
                "closing_day": 31,
                "closing_month": 12,
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

        normalized_data = {
            "razao_social": razao_social,
            "nome_fantasia": nome_fantasia or None,
            "cnpj": cnpj,
            "inscricao_estadual": FinanceService._extract_supplier_registration(data.get("inscricao_estadual")),
            "endereco_rua": (data.get("endereco_rua") or "").strip() or None,
            "endereco_numero": (data.get("endereco_numero") or "").strip() or None,
            "endereco_complemento": (data.get("endereco_complemento") or "").strip() or None,
            "endereco_bairro": (data.get("endereco_bairro") or "").strip() or None,
            "endereco_cidade": (data.get("endereco_cidade") or "").strip() or None,
            "endereco_estado": ((data.get("endereco_estado") or "").strip().upper() or None),
            "endereco_cep": (data.get("endereco_cep") or "").strip() or None,
            "telefone": FinanceService._normalize_supplier_phone(data.get("telefone")),
            "email": (data.get("email") or "").strip() or None,
            "site": (data.get("site") or "").strip() or None,
            "situacao_cadastral": (data.get("situacao_cadastral") or "").strip() or None,
            "api_origem": (data.get("api_origem") or "").strip() or None,
            "observacoes": (data.get("observacoes") or "").strip() or None,
        }
        FinanceService._validate_supplier_string_lengths(normalized_data)

        supplier.razao_social = normalized_data["razao_social"]
        supplier.nome_fantasia = normalized_data["nome_fantasia"]
        supplier.cnpj = normalized_data["cnpj"]
        supplier.inscricao_estadual = normalized_data["inscricao_estadual"]
        supplier.endereco_rua = normalized_data["endereco_rua"]
        supplier.endereco_numero = normalized_data["endereco_numero"]
        supplier.endereco_complemento = normalized_data["endereco_complemento"]
        supplier.endereco_bairro = normalized_data["endereco_bairro"]
        supplier.endereco_cidade = normalized_data["endereco_cidade"]
        supplier.endereco_estado = normalized_data["endereco_estado"]
        supplier.endereco_cep = normalized_data["endereco_cep"]
        supplier.telefone = normalized_data["telefone"]
        supplier.email = normalized_data["email"]
        supplier.site = normalized_data["site"]
        supplier.situacao_cadastral = normalized_data["situacao_cadastral"]
        supplier.api_origem = normalized_data["api_origem"]
        supplier.observacoes = normalized_data["observacoes"]
        supplier.ativo = bool(data.get("ativo", True))
        if data.get("data_consulta_cnpj"):
            supplier.data_consulta_cnpj = data["data_consulta_cnpj"]

        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
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
            (
                f"https://publica.cnpj.ws/cnpj/{digits}",
                FinanceService._map_cnpjws_supplier,
                "CNPJ.ws",
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
                try:
                    payload = response.json()
                except ValueError as exc:
                    errors.append(f"{source}: resposta JSON inválida ({exc})")
                    continue
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
            "razao_social": FinanceService._as_text(payload.get("razao_social") or payload.get("nome")),
            "nome_fantasia": FinanceService._as_text(payload.get("nome_fantasia")) or None,
            "cnpj": FinanceService.normalize_cnpj(payload.get("cnpj")),
            "inscricao_estadual": None,
            "endereco_rua": FinanceService._as_text(payload.get("logradouro")) or None,
            "endereco_numero": FinanceService._as_text(payload.get("numero")) or None,
            "endereco_complemento": FinanceService._as_text(payload.get("complemento")) or None,
            "endereco_bairro": FinanceService._as_text(payload.get("bairro")) or None,
            "endereco_cidade": FinanceService._as_text(payload.get("municipio")) or None,
            "endereco_estado": FinanceService._as_text(payload.get("uf")) or None,
            "endereco_cep": FinanceService._as_text(payload.get("cep")) or None,
            "telefone": FinanceService._as_text(payload.get("ddd_telefone_1") or payload.get("ddd_telefone_2")) or None,
            "email": FinanceService._as_text(payload.get("email")) or None,
            "situacao_cadastral": FinanceService._as_text(payload.get("descricao_situacao_cadastral") or payload.get("situacao_cadastral")) or None,
            "site": None,
            "observacoes": None,
            "ativo": True,
        }

    @staticmethod
    def _map_cnpjws_supplier(payload: dict[str, Any]) -> dict[str, Any]:
        estabelecimento = payload.get("estabelecimento") or {}
        atividade_principal = payload.get("atividade_principal") or {}
        razao_social = FinanceService._as_text(payload.get("razao_social") or payload.get("empresa", {}).get("razao_social") if isinstance(payload.get("empresa"), dict) else None)
        if not razao_social:
            razao_social = FinanceService._as_text(payload.get("nome"))
        nome_fantasia = FinanceService._as_text(estabelecimento.get("nome_fantasia") or payload.get("nome_fantasia")) or None
        endereco_numero = FinanceService._as_text(estabelecimento.get("numero")) or None
        return {
            "razao_social": razao_social,
            "nome_fantasia": nome_fantasia,
            "cnpj": FinanceService.normalize_cnpj(payload.get("cnpj") or estabelecimento.get("cnpj")),
            "inscricao_estadual": FinanceService._extract_supplier_registration(
                estabelecimento.get("inscricoes_estaduais") or estabelecimento.get("inscricao_estadual")
            ),
            "endereco_rua": FinanceService._as_text(estabelecimento.get("logradouro")) or None,
            "endereco_numero": endereco_numero,
            "endereco_complemento": FinanceService._as_text(estabelecimento.get("complemento")) or None,
            "endereco_bairro": FinanceService._as_text(estabelecimento.get("bairro")) or None,
            "endereco_cidade": FinanceService._as_text(estabelecimento.get("cidade", {}).get("nome") if isinstance(estabelecimento.get("cidade"), dict) else estabelecimento.get("municipio")) or None,
            "endereco_estado": FinanceService._as_text(estabelecimento.get("estado", {}).get("sigla") if isinstance(estabelecimento.get("estado"), dict) else estabelecimento.get("uf")) or None,
            "endereco_cep": FinanceService._as_text(estabelecimento.get("cep")) or None,
            "telefone": FinanceService._normalize_supplier_phone(
                {
                    "ddd": estabelecimento.get("ddd1"),
                    "telefone": estabelecimento.get("telefone1") or estabelecimento.get("telefone"),
                },
                {
                    "ddd": estabelecimento.get("ddd2"),
                    "telefone": estabelecimento.get("telefone2"),
                },
                payload.get("telefone"),
            ),
            "email": FinanceService._as_text(estabelecimento.get("email")) or None,
            "situacao_cadastral": FinanceService._as_text(payload.get("situacao_cadastral") or estabelecimento.get("situacao_cadastral")) or None,
            "site": FinanceService._as_text(payload.get("site")) or None,
            "observacoes": atividade_principal.get("descricao") or None,
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
                    **_build_document_item_display_metadata(row),
                }
            )

        supplier_name = document.fornecedor.nome_exibicao() if document.fornecedor else document.nome_emitente()
        status_integracao = (document.status_integracao or "manual").strip() or "manual"
        mensagem_integracao = (document.mensagem_integracao or "").strip() or None
        numero_documento = FinanceService.normalize_manual_internal_document_number(document.numero_documento)
        return {
            "id_documento": document.id_documento,
            "nota_fiscal": numero_documento,
            "numero_documento": numero_documento,
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
        rows = FinanceService._select_canonical_documents(rows)
        payload = [FinanceService._serialize_stock_document(row) for row in rows]
        return FinanceService._set_cached(cache_key, [dict(row) for row in payload], ttl_seconds=8.0)

    @staticmethod
    def get_stock_document_by_number(numero_documento: str) -> dict[str, Any] | None:
        numero = FinanceService.normalize_manual_internal_document_number(numero_documento)
        if not numero:
            return None
        cache_key = f"get_stock_document_by_number:{numero}"
        cached = FinanceService._get_cached(cache_key)
        if cached is not None:
            return dict(cached)

        aliases = FinanceService.manual_internal_document_aliases() if FinanceService.is_manual_internal_document_number(numero) else (numero,)

        rows = (
            DocumentoEntradaEstoque.query
            .options(
                joinedload(DocumentoEntradaEstoque.fornecedor),
                joinedload(DocumentoEntradaEstoque.itens).joinedload(DocumentoEntradaEstoqueItem.item),
            )
            .filter(DocumentoEntradaEstoque.numero_documento.in_(aliases))
            .order_by(DocumentoEntradaEstoque.criado_em.desc(), DocumentoEntradaEstoque.id_documento.desc())
            .all()
        )
        row = FinanceService._select_canonical_documents(rows)[:1]
        row = row[0] if row else None
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
        search_filters = [DocumentoEntradaEstoque.numero_documento.ilike(like)]
        if MANUAL_INTERNAL_DOCUMENT_NUMBER.lower().startswith(term.lower()) or "sem nf/cupom".startswith(term.lower()) or term.lower() in MANUAL_INTERNAL_DOCUMENT_NUMBER.lower():
            search_filters.append(DocumentoEntradaEstoque.numero_documento.in_(FinanceService.manual_internal_document_aliases()))
        rows = (
            DocumentoEntradaEstoque.query
            .options(joinedload(DocumentoEntradaEstoque.fornecedor))
            .filter(or_(*search_filters))
            .order_by(DocumentoEntradaEstoque.criado_em.desc(), DocumentoEntradaEstoque.id_documento.desc())
            .limit(limit)
            .all()
        )
        rows = FinanceService._select_canonical_documents(rows)[:limit]
        return [
            {
                "id_documento": row.id_documento,
                "numero_documento": FinanceService.normalize_manual_internal_document_number(row.numero_documento),
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
        numero = FinanceService.normalize_manual_internal_document_number(numero_documento)
        if not numero:
            return None

        aliases = FinanceService.manual_internal_document_aliases() if FinanceService.is_manual_internal_document_number(numero) else (numero,)

        query = (
            DocumentoEntradaEstoque.query
            .options(joinedload(DocumentoEntradaEstoque.itens))
            .filter(DocumentoEntradaEstoque.numero_documento.in_(aliases))
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
        numero = FinanceService.normalize_manual_internal_document_number(numero_documento)
        tipo = FinanceService.normalize_stock_document_type(tipo_documento)
        if not codigo:
            raise ValueError("Informe o item da entrada")
        if not numero:
            raise ValueError("Informe o número do documento")
        if tipo == "manual":
            numero = MANUAL_INTERNAL_DOCUMENT_NUMBER

        supplier_inputs = FinanceService.sanitize_document_supplier_inputs(
            tipo_documento=tipo,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            supplier_cnpj=supplier_cnpj,
        )
        supplier_id = supplier_inputs["supplier_id"]
        supplier_name = supplier_inputs["supplier_name"]
        supplier_cnpj = supplier_inputs["supplier_cnpj"]

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
        movimenta_estoque_documento = (
            bool(movimenta_estoque)
            if movimenta_estoque is not None
            else FinanceService.resolve_document_movimenta_estoque(
                data_emissao=data_emissao,
                data_recebimento=data_recebimento,
            )
        )

        existing_nf_document = None
        existing_nf_documents: list[DocumentoEntradaEstoque] = []
        duplicate_notices: list[str] = []
        if tipo == "nf":
            existing_nf_documents = FinanceService._find_nf_documents_by_identity(numero)
            existing_nf_document = FinanceService._resolve_unique_nf_existing_document(
                existing_nf_documents,
                numero_documento=numero,
                chave_acesso=chave,
                cnpj_emitente=cnpj,
                supplier_id=supplier.id if supplier else supplier_id,
                supplier_name=supplier_display,
            )
            if existing_nf_document is not None:
                previous_number = (existing_nf_document.numero_documento or "").strip()
                exact_duplicate_exists = any(
                    document.id_documento != existing_nf_document.id_documento
                    and (document.numero_documento or "").strip() == numero
                    for document in existing_nf_documents
                )
                if previous_number and previous_number != numero and not exact_duplicate_exists:
                    existing_nf_document.numero_documento = numero
                    duplicate_notices.append(
                        f"A NF {numero} já existia como {previous_number}; o sistema reaproveitou o documento e normalizou a numeração."
                    )
                elif len(existing_nf_documents) > 1:
                    duplicate_notices.append(
                        f"A NF {numero} já possuía cadastro equivalente; o sistema bloqueou novo lançamento duplicado."
                    )

        aliases = FinanceService.manual_internal_document_aliases() if tipo == "manual" and FinanceService.is_manual_internal_document_number(numero) else (numero,)

        document_query = DocumentoEntradaEstoque.query.filter(
            DocumentoEntradaEstoque.tipo_documento == tipo,
            DocumentoEntradaEstoque.numero_documento.in_(aliases),
        )
        if cnpj:
            document_query = document_query.filter(DocumentoEntradaEstoque.cnpj_emitente == cnpj)
        elif supplier:
            document_query = document_query.filter(DocumentoEntradaEstoque.fornecedor_id == supplier.id)

        document = FinanceService._select_reusable_existing_document(
            document_query.order_by(DocumentoEntradaEstoque.id_documento.desc()).all(),
            require_unambiguous_identity=not bool(cnpj or supplier),
        )
        if document is None and existing_nf_document is not None:
            document = existing_nf_document
        reused_legacy_placeholder = False
        if document is None and tipo == "nf":
            legacy_placeholder = FinanceService._find_legacy_placeholder_document(numero)
            if legacy_placeholder is not None:
                document = legacy_placeholder
                reused_legacy_placeholder = True

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
            manual_shared_bucket = tipo == "manual" and FinanceService.is_manual_internal_document_number(numero)
            if reused_legacy_placeholder:
                document.tipo_documento = tipo
                document.status_integracao = status_integracao
                document.mensagem_integracao = mensagem_integracao
            if manual_shared_bucket:
                document.numero_documento = MANUAL_INTERNAL_DOCUMENT_NUMBER
            document.movimenta_estoque = movimenta_estoque_documento
            if supplier and not document.fornecedor_id:
                document.fornecedor_id = supplier.id
            if cnpj and not document.cnpj_emitente:
                document.cnpj_emitente = cnpj
            if supplier_display and not document.fornecedor_nome:
                document.fornecedor_nome = supplier_display
            if manual_shared_bucket:
                document.data_emissao = data_emissao
                document.data_recebimento = data_recebimento
            elif data_emissao and not document.data_emissao:
                document.data_emissao = data_emissao
            if not manual_shared_bucket and data_recebimento and not document.data_recebimento:
                document.data_recebimento = data_recebimento
            if chave and not document.chave_acesso:
                document.chave_acesso = chave
            if observacao and not document.observacao:
                document.observacao = observacao.strip() or None
            if chave and tipo == "nf" and (document.status_integracao or "manual") == "manual":
                document.status_integracao = "aguardando_certificado"
                document.mensagem_integracao = mensagem_integracao

        item_model = db.session.get(Item, codigo)
        default_document_unit = infer_document_quantity_unit_for_item(item_model) if item_model is not None else None
        normalized_line = _normalize_financial_line(
            item_model,
            quantity=float(quantidade or 0),
            valor_unitario=float(valor_unitario) if valor_unitario not in (None, "") else None,
            valor_total=None,
            quantity_unit=default_document_unit,
            price_unit=default_document_unit,
        )
        qty = float(normalized_line["quantity"] or 0.0)
        unit = normalized_line["unit_price_input"]
        total = normalized_line["total_value"]
        linked_entry_id = None if document_only else entrada_id
        item_row = None
        reused_equivalent_document_item = False
        if reused_legacy_placeholder:
            item_row = FinanceService._find_reusable_legacy_document_item(
                document,
                codigo_item=codigo,
                quantidade=qty,
                unidade_quantidade=normalized_line["quantity_unit"],
                valor_unitario=unit,
                valor_total=total,
            )

        if item_row is None and tipo == "nf":
            equivalent_item = FinanceService._find_equivalent_nf_document_item(
                document,
                codigo_item=codigo,
                quantidade=qty,
                unidade_quantidade=normalized_line["quantity_unit"],
                quantidade_base=normalized_line["quantity_base"],
                valor_unitario=unit,
                valor_total=total,
                unidade_preco=normalized_line["price_unit"],
                valor_unitario_base=normalized_line["unit_price_base"],
            )
            if equivalent_item is not None:
                item_row = equivalent_item
                reused_equivalent_document_item = True
                duplicate_notices.append(
                    f"A NF {numero} já tinha esta mesma linha de item; o recadastro foi descartado e o item existente foi mantido."
                )

        if item_row is None:
            item_row = DocumentoEntradaEstoqueItem(
                documento_id=document.id_documento,
                entrada_id=linked_entry_id,
                codigo_item=codigo,
                quantidade=qty,
                unidade_quantidade=normalized_line["quantity_unit"],
                quantidade_base=normalized_line["quantity_base"],
                valor_unitario=unit,
                valor_unitario_base=normalized_line["unit_price_base"],
                unidade_preco=normalized_line["price_unit"],
                fator_preco_base=normalized_line["factor_to_base"],
                valor_total=total,
                lote=(lote or "").strip() or None,
                data_validade=data_validade,
                observacao=(observacao or "").strip() or None,
                status_processamento="processado" if linked_entry_id is not None else "pendente",
                processado_em=datetime.utcnow() if linked_entry_id is not None else None,
            )
            db.session.add(item_row)
            db.session.flush()
        else:
            item_row.codigo_item = codigo
            item_row.quantidade = qty
            item_row.unidade_quantidade = normalized_line["quantity_unit"]
            item_row.quantidade_base = normalized_line["quantity_base"]
            item_row.valor_unitario = unit
            item_row.valor_unitario_base = normalized_line["unit_price_base"]
            item_row.unidade_preco = normalized_line["price_unit"]
            item_row.fator_preco_base = normalized_line["factor_to_base"]
            item_row.valor_total = total
            item_row.lote = (lote or "").strip() or None
            item_row.data_validade = data_validade
            item_row.observacao = (observacao or "").strip() or None
            if reused_equivalent_document_item and item_row.stock_movement_id is not None:
                item_row.status_processamento = "processado"
                item_row.processado_em = item_row.processado_em or datetime.utcnow()
            elif linked_entry_id is not None and item_row.entrada_id is None:
                item_row.entrada_id = linked_entry_id
            if not reused_equivalent_document_item and item_row.entrada_id is not None:
                item_row.status_processamento = "processado"
                item_row.processado_em = item_row.processado_em or datetime.utcnow()
            elif not reused_equivalent_document_item:
                item_row.status_processamento = "pendente"
                item_row.processado_em = None

        if item_model is not None:
            origem_pre_cadastro = (getattr(item_model, "pre_cadastro_origem", "") or "").strip().lower()
            if (
                bool(getattr(item_model, "pre_cadastro_pendente", False))
                and origem_pre_cadastro == "nf"
                and item_model.pre_cadastro_documento_item_id != item_row.id_documento_item
            ):
                item_model.pre_cadastro_documento_item_id = item_row.id_documento_item

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
            "duplicate_notices": duplicate_notices,
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

        state_repaired = FinanceService._repair_nf_origin_item_state(item_row)

        recovered = FinanceService._recover_document_item_movement(item_row)
        if recovered is not None:
            return recovered

        if item_row.stock_movement_id is not None or item_row.entrada_id is not None:
            repaired_packaging_read_model = False
            if item_row.item is not None:
                try:
                    repaired_packaging_read_model = inventory_engine.sync_packaging_read_model(
                        product_id=item_row.codigo_item,
                        commit=False,
                    )
                except Exception:
                    repaired_packaging_read_model = False
            if (item_row.status_processamento or "").strip().lower() != "processado":
                item_row.status_processamento = "processado"
                item_row.processado_em = item_row.processado_em or datetime.utcnow()
                item_row.erro_processamento = None
                db.session.commit()
            elif repaired_packaging_read_model or state_repaired:
                db.session.commit()
            return {
                "success": True,
                "processed": False,
                "skipped": True,
                "reason": "already_processed",
                "documento_item_id": item_row.id_documento_item,
                "stock_movement_id": item_row.stock_movement_id,
                "operation_log_id": item_row.operation_log_id,
                "packaging_read_model_repaired": repaired_packaging_read_model,
            }

        if item_row.item is None:
            raise ValueError("O item vinculado ao documento não existe mais no estoque.")

        if FinanceService._document_item_requires_pre_registration(item_row):
            return {
                "success": True,
                "processed": False,
                "skipped": True,
                "reason": "pre_cadastro_pendente",
                "documento_item_id": item_row.id_documento_item,
                "stock_movement_id": item_row.stock_movement_id,
                "operation_log_id": item_row.operation_log_id,
            }

        quantidade = float(item_row.quantidade or 0.0)
        if quantidade <= 0:
            raise ValueError("Quantidade documental inválida para processamento de estoque.")

        documento = item_row.documento
        stored_quantity_unit = (item_row.unidade_quantidade or "").strip().lower()
        should_refresh_document_unit = False
        if not stored_quantity_unit:
            should_refresh_document_unit = True
        elif should_autofix_packaged_document_unit(
            item_row.item,
            current_unit=stored_quantity_unit,
            quantity=quantidade,
            quantity_base=item_row.quantidade_base,
        ):
            should_refresh_document_unit = True

        if should_refresh_document_unit:
            inferred_quantity_unit = infer_document_quantity_unit_for_item(item_row.item)
            inferred_price_unit = (item_row.unidade_preco or "").strip().lower()
            if not inferred_price_unit or inferred_price_unit == stored_quantity_unit:
                inferred_price_unit = inferred_quantity_unit
            normalized_line = _normalize_financial_line(
                item_row.item,
                quantity=quantidade,
                valor_unitario=float(item_row.valor_unitario) if item_row.valor_unitario not in (None, "") else None,
                valor_total=float(item_row.valor_total) if item_row.valor_total not in (None, "") else None,
                quantity_unit=inferred_quantity_unit,
                price_unit=inferred_price_unit,
            )
            item_row.unidade_quantidade = normalized_line["quantity_unit"]
            item_row.quantidade_base = normalized_line["quantity_base"]
            item_row.valor_unitario_base = normalized_line["unit_price_base"]
            item_row.unidade_preco = normalized_line["price_unit"]
            item_row.fator_preco_base = normalized_line["factor_to_base"]
            item_row.valor_total = normalized_line["total_value"]
            if item_row.valor_unitario is None:
                item_row.valor_unitario = normalized_line["unit_price_input"]

        from_unit = (item_row.unidade_quantidade or item_row.item.unidade or "Unidade").strip() or "Unidade"
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

            try:
                inventory_engine.sync_packaging_read_model(
                    product_id=item_row.codigo_item,
                    commit=False,
                )
            except Exception:
                pass

            FinanceService._repair_nf_origin_item_state(item_row)

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
        from .inventory_engine import inventory_engine

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

        FinanceService._repair_nf_origin_item_state(item_row)

        try:
            inventory_engine.sync_packaging_read_model(
                product_id=item_row.codigo_item,
                commit=False,
            )
        except Exception:
            pass

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
    def _repair_nf_origin_item_state(item_row: DocumentoEntradaEstoqueItem) -> bool:
        item_model = item_row.item or db.session.get(Item, item_row.codigo_item)
        if item_model is None:
            return False

        changed = False
        internal_content_unit = _resolve_internal_content_document_unit(item_model, row=item_row)
        balance = db.session.get(StockBalance, item_row.codigo_item)
        if (
            item_row.entrada_id is None
            and balance is not None
            and hasattr(balance, "read_model_ready")
            and not bool(getattr(balance, "read_model_ready", False))
        ):
            balance.read_model_ready = True
            changed = True

        origem = (getattr(item_model, "pre_cadastro_origem", "") or "").strip().lower()
        if origem != "nf":
            return changed

        if item_model.pre_cadastro_documento_item_id != item_row.id_documento_item:
            item_model.pre_cadastro_documento_item_id = item_row.id_documento_item
            changed = True

        if internal_content_unit is not None:
            desired_unit = "Par" if internal_content_unit == "par" else "Unidade"
            if item_model.unidade != desired_unit:
                item_model.unidade = desired_unit
                changed = True
            if abs(float(item_model.estoque_embalagens or 0.0)) > 1e-6:
                item_model.estoque_embalagens = 0.0
                changed = True
            if abs(float(item_model.estoque_unidades_soltas or 0.0)) > 1e-6:
                item_model.estoque_unidades_soltas = 0.0
                changed = True

        if balance is not None and hasattr(balance, "read_model_ready") and not bool(getattr(balance, "read_model_ready", False)):
            balance.read_model_ready = True
            changed = True

        return changed

    @staticmethod
    def _document_item_requires_pre_registration(item_row: DocumentoEntradaEstoqueItem) -> bool:
        item_model = item_row.item or db.session.get(Item, item_row.codigo_item)
        if item_model is None:
            return False
        return bool(getattr(item_model, "pre_cadastro_pendente", False))

    @staticmethod
    def process_pending_document_items_for_item(
        codigo_item: str,
        *,
        usuario_matricula: str | None = None,
    ) -> dict[str, Any]:
        codigo = (codigo_item or "").strip()
        if not codigo:
            raise ValueError("Informe o código do item para processar documentos pendentes.")

        rows = (
            DocumentoEntradaEstoqueItem.query
            .options(
                joinedload(DocumentoEntradaEstoqueItem.item),
                joinedload(DocumentoEntradaEstoqueItem.documento),
            )
            .join(DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem.documento_id == DocumentoEntradaEstoque.id_documento)
            .filter(DocumentoEntradaEstoqueItem.codigo_item == codigo)
            .filter(DocumentoEntradaEstoque.movimenta_estoque.is_(True))
            .filter(DocumentoEntradaEstoqueItem.stock_movement_id.is_(None))
            .filter(DocumentoEntradaEstoqueItem.entrada_id.is_(None))
            .filter(DocumentoEntradaEstoqueItem.status_processamento != "processado")
            .order_by(DocumentoEntradaEstoque.data_recebimento.asc(), DocumentoEntradaEstoque.id_documento.asc(), DocumentoEntradaEstoqueItem.id_documento_item.asc())
            .all()
        )

        processed = 0
        skipped = 0
        errors = 0
        messages: list[str] = []
        document_numbers: list[str] = []

        for row in rows:
            numero_documento = (row.documento.numero_documento if row.documento is not None else "") or ""
            if numero_documento and numero_documento not in document_numbers:
                document_numbers.append(numero_documento)
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
            "document_numbers": document_numbers,
        }

    @staticmethod
    def process_stock_document_entries(
        documento_id: int,
        *,
        usuario_matricula: str | None = None,
        only_pending: bool = True,
        item_ids: list[int] | None = None,
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
        item_filter = {int(item_id) for item_id in item_ids} if item_ids else None

        for row in sorted(documento.itens, key=lambda item: item.id_documento_item):
            if item_filter is not None and row.id_documento_item not in item_filter:
                skipped += 1
                continue
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
        unidade_quantidade: str | None = None,
        quantidade_base: float | None = None,
        valor_unitario_base: float | None = None,
        unidade_preco: str | None = None,
        fator_preco_base: float | None = None,
    ) -> FinanceLedgerEntry | None:
        codigo = (codigo_item or "").strip()
        if not codigo:
            return None
        item_model = db.session.get(Item, codigo)
        normalized_line = _normalize_financial_line(
            item_model,
            quantity=float(quantidade or 0),
            valor_unitario=float(valor_unitario) if valor_unitario not in (None, "") else None,
            valor_total=float(valor_total) if valor_total not in (None, "") else None,
            quantity_unit=unidade_quantidade,
            price_unit=unidade_preco,
        )
        qty = float(normalized_line["quantity"] or 0.0)
        unit = normalized_line["unit_price_input"]
        total = normalized_line["total_value"]
        if total is None:
            return None

        normalized_qty_base = float(normalized_line["quantity_base"] or 0.0)
        qty_base = normalized_qty_base
        if qty_base <= 0 and quantidade_base not in (None, ""):
            qty_base = float(quantidade_base)

        normalized_unit_base = normalized_line["unit_price_base"]
        if normalized_unit_base not in (None, ""):
            unit_base = float(normalized_unit_base)
        elif valor_unitario_base not in (None, ""):
            unit_base = float(valor_unitario_base)
        else:
            unit_base = None

        quantity_unit_value = (normalized_line["quantity_unit"] or unidade_quantidade or "").strip().lower() or None
        price_unit_value = (normalized_line["price_unit"] or unidade_preco or "").strip().lower() or None

        normalized_factor = normalized_line["factor_to_base"]
        if normalized_factor not in (None, ""):
            factor_value = float(normalized_factor)
        elif fator_preco_base not in (None, ""):
            factor_value = float(fator_preco_base)
        else:
            factor_value = None

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
            unidade_quantidade=quantity_unit_value,
            quantidade_base=qty_base,
            valor_unitario=unit,
            valor_unitario_base=unit_base,
            unidade_preco=price_unit_value,
            fator_preco_base=factor_value,
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
    def _normalize_consumption_local(value: str | None) -> str:
        normalized = " ".join(str(value or "").strip().split()).upper()
        return normalized or "SEM LOCAL"

    @staticmethod
    def _resolve_consumption_unit_price(
        item_data: dict[str, Any] | None,
        purchase_data: dict[str, Any] | None,
    ) -> float:
        if purchase_data:
            avg_unit = purchase_data.get("avg_unit")
            try:
                if avg_unit not in (None, ""):
                    unit_price = float(avg_unit)
                    if unit_price > 0:
                        return unit_price
            except (TypeError, ValueError):
                pass

        if item_data:
            for price_key in ("preco_compra_unitario_base", "preco_reposicao_unitario_base"):
                raw_unit_price = item_data.get(price_key)
                try:
                    if raw_unit_price not in (None, ""):
                        unit_price = float(raw_unit_price)
                        if unit_price > 0:
                            return unit_price
                except (TypeError, ValueError):
                    pass

        return 0.0

    @staticmethod
    def _format_consumption_quantity_display(entry: dict[str, Any]) -> str:
        litros = float(entry.get("quantidade_litros") or 0.0)
        if litros > 0:
            return f"{litros:g} L"

        quilos = float(entry.get("quantidade_quilos") or 0.0)
        if quilos > 0:
            return f"{quilos:g} Kg"

        quantidade_base = float(entry.get("quantidade_base") or 0.0)
        unit_base = (entry.get("unit_base") or entry.get("unidade_item") or "un").strip() or "un"
        return f"{quantidade_base:g} {unit_base.upper()}"

    @staticmethod
    def _resolve_employee_administrative_opinion(summary: dict[str, Any]) -> dict[str, Any]:
        total_saidas = int(summary.get("saidas") or 0)
        total_locais = int(summary.get("locais") or 0)
        total_categorias = int(summary.get("categorias") or 0)
        local_fill_rate = float(summary.get("local_fill_rate") or 0.0)
        cargo_present = bool((summary.get("cargo") or "").strip())

        if total_saidas <= 0:
            return {
                "score": 0,
                "label": "Sem base",
                "tone": "secondary",
                "text": "Ainda não há retiradas suficientes para formar um parecer administrativo confiável.",
            }

        score = int(local_fill_rate * 60)
        if cargo_present:
            score += 10
        score += min(total_locais, 4) * 5
        score += min(total_categorias, 4) * 5
        score += min(total_saidas, 10)
        score = max(0, min(score, 100))

        if score >= 85:
            label = "Excelente"
            tone = "success"
        elif score >= 70:
            label = "Bom"
            tone = "primary"
        elif score >= 50:
            label = "Atenção"
            tone = "warning"
        else:
            label = "Crítico"
            tone = "danger"

        fill_percent = round(local_fill_rate * 100)
        if fill_percent >= 95:
            quality_text = "registros muito bem rastreados"
        elif fill_percent >= 80:
            quality_text = "boa rastreabilidade operacional"
        elif fill_percent >= 60:
            quality_text = "rastreabilidade mediana"
        else:
            quality_text = "rastreamento insuficiente"

        text = (
            f"Parecer administrativo operacional: {quality_text}, com {fill_percent}% dos lançamentos "
            f"informando o local de uso, atuação em {max(total_locais, 1)} local(is) e "
            f"{max(total_categorias, 1)} categoria(s)."
        )
        return {
            "score": score,
            "label": label,
            "tone": tone,
            "text": text,
        }

    @staticmethod
    def _is_tool_consumption_category(category: Any) -> bool:
        return "ferrament" in str(category or "").strip().lower()

    @classmethod
    def _aggregate_consumption_entries(cls, entries: list[dict[str, Any]]) -> dict[str, Any]:
        filtered_entries = [
            row for row in entries
            if not cls._is_tool_consumption_category(row.get("categoria"))
        ]
        sorted_entries = sorted(
            filtered_entries,
            key=lambda row: (
                row.get("data_saida") or datetime.min,
                int(row.get("saida_id") or 0),
            ),
            reverse=True,
        )

        overview = {
            "total_valor": 0.0,
            "total_litros": 0.0,
            "total_quilos": 0.0,
            "saidas": 0,
            "locais": 0,
            "categorias": 0,
            "colaboradores": 0,
            "itens": 0,
        }

        grouped_locals: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "local": "SEM LOCAL",
            "total_valor": 0.0,
            "total_litros": 0.0,
            "total_quilos": 0.0,
            "total_quantidade_base": 0.0,
            "saidas": 0,
            "_items": set(),
            "_employees": set(),
            "_categories": set(),
            "_material_values": defaultdict(float),
            "_employee_values": defaultdict(float),
            "_employee_names": {},
            "_employee_cargos": {},
            "_latest_entry": None,
        })
        grouped_categories: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "categoria": "Sem categoria",
            "total_valor": 0.0,
            "total_litros": 0.0,
            "total_quilos": 0.0,
            "total_quantidade_base": 0.0,
            "saidas": 0,
            "_items": set(),
            "_employees": set(),
            "_locations": set(),
            "_material_values": defaultdict(float),
            "_location_values": defaultdict(float),
            "_latest_entry": None,
        })
        grouped_employees: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "matricula": None,
            "nome": "Não informado",
            "cargo": "Sem cargo",
            "total_valor": 0.0,
            "total_litros": 0.0,
            "total_quilos": 0.0,
            "total_quantidade_base": 0.0,
            "saidas": 0,
            "_items": set(),
            "_locations": set(),
            "_categories": set(),
            "_material_values": defaultdict(float),
            "_location_values": defaultdict(float),
            "_filled_locations": 0,
            "_latest_entry": None,
        })

        for entry in sorted_entries:
            local_key = cls._normalize_consumption_local(entry.get("local"))
            category_name = (entry.get("categoria") or "Sem categoria").strip() or "Sem categoria"
            employee_key = str(entry.get("matricula") or entry.get("colaborador_nome") or "SEM_USUARIO")
            item_code = str(entry.get("codigo_item") or "")
            item_name = (entry.get("descricao_item") or item_code or "Item sem descrição").strip()
            value = float(entry.get("valor_total") or 0.0)
            litros = float(entry.get("quantidade_litros") or 0.0)
            quilos = float(entry.get("quantidade_quilos") or 0.0)
            quantity_base = float(entry.get("quantidade_base") or 0.0)
            entry_dt = entry.get("data_saida") or datetime.min

            overview["total_valor"] += value
            overview["total_litros"] += litros
            overview["total_quilos"] += quilos
            overview["saidas"] += 1

            local_bucket = grouped_locals[local_key]
            local_bucket["local"] = local_key
            local_bucket["total_valor"] += value
            local_bucket["total_litros"] += litros
            local_bucket["total_quilos"] += quilos
            local_bucket["total_quantidade_base"] += quantity_base
            local_bucket["saidas"] += 1
            if item_code:
                local_bucket["_items"].add(item_code)
            local_bucket["_categories"].add(category_name)
            local_bucket["_material_values"][item_name] += value
            local_bucket["_employees"].add(employee_key)
            local_bucket["_employee_values"][employee_key] += value
            local_bucket["_employee_names"][employee_key] = entry.get("colaborador_nome") or "Não informado"
            local_bucket["_employee_cargos"][employee_key] = entry.get("cargo") or "Sem cargo"
            latest_local_entry = local_bucket.get("_latest_entry")
            if latest_local_entry is None or entry_dt > (latest_local_entry.get("data_saida") or datetime.min):
                local_bucket["_latest_entry"] = entry

            category_bucket = grouped_categories[category_name]
            category_bucket["categoria"] = category_name
            category_bucket["total_valor"] += value
            category_bucket["total_litros"] += litros
            category_bucket["total_quilos"] += quilos
            category_bucket["total_quantidade_base"] += quantity_base
            category_bucket["saidas"] += 1
            if item_code:
                category_bucket["_items"].add(item_code)
            category_bucket["_employees"].add(employee_key)
            category_bucket["_locations"].add(local_key)
            category_bucket["_material_values"][item_name] += value
            category_bucket["_location_values"][local_key] += value
            latest_category_entry = category_bucket.get("_latest_entry")
            if latest_category_entry is None or entry_dt > (latest_category_entry.get("data_saida") or datetime.min):
                category_bucket["_latest_entry"] = entry

            employee_bucket = grouped_employees[employee_key]
            employee_bucket["matricula"] = entry.get("matricula")
            employee_bucket["nome"] = entry.get("colaborador_nome") or "Não informado"
            employee_bucket["cargo"] = entry.get("cargo") or "Sem cargo"
            employee_bucket["total_valor"] += value
            employee_bucket["total_litros"] += litros
            employee_bucket["total_quilos"] += quilos
            employee_bucket["total_quantidade_base"] += quantity_base
            employee_bucket["saidas"] += 1
            if item_code:
                employee_bucket["_items"].add(item_code)
            employee_bucket["_locations"].add(local_key)
            employee_bucket["_categories"].add(category_name)
            employee_bucket["_material_values"][item_name] += value
            employee_bucket["_location_values"][local_key] += value
            if local_key != "SEM LOCAL":
                employee_bucket["_filled_locations"] += 1
            latest_employee_entry = employee_bucket.get("_latest_entry")
            if latest_employee_entry is None or entry_dt > (latest_employee_entry.get("data_saida") or datetime.min):
                employee_bucket["_latest_entry"] = entry

        locations: list[dict[str, Any]] = []
        for bucket in grouped_locals.values():
            top_material_name, top_material_value = max(
                bucket["_material_values"].items(),
                key=lambda row: row[1],
                default=(None, 0.0),
            )
            top_employee_key, top_employee_value = max(
                bucket["_employee_values"].items(),
                key=lambda row: row[1],
                default=(None, 0.0),
            )
            latest_entry = bucket.get("_latest_entry") or {}
            locations.append({
                "local": bucket["local"],
                "total_valor": round(float(bucket["total_valor"] or 0.0), 2),
                "total_litros": round(float(bucket["total_litros"] or 0.0), 3),
                "total_quilos": round(float(bucket["total_quilos"] or 0.0), 3),
                "total_quantidade_base": round(float(bucket["total_quantidade_base"] or 0.0), 3),
                "saidas": int(bucket["saidas"] or 0),
                "itens": len(bucket["_items"]),
                "colaboradores": len(bucket["_employees"]),
                "categorias": len(bucket["_categories"]),
                "material_destaque": top_material_name,
                "material_destaque_valor": round(float(top_material_value or 0.0), 2),
                "colaborador_destaque": bucket["_employee_names"].get(top_employee_key) if top_employee_key else None,
                "cargo_destaque": bucket["_employee_cargos"].get(top_employee_key) if top_employee_key else None,
                "colaborador_destaque_valor": round(float(top_employee_value or 0.0), 2),
                "ultimo_colaborador_nome": latest_entry.get("colaborador_nome"),
                "ultimo_colaborador_cargo": latest_entry.get("cargo"),
                "ultimo_material_nome": latest_entry.get("descricao_item"),
                "ultimo_lancamento": latest_entry.get("data_saida_label"),
                "ultimo_contexto": latest_entry.get("contexto_uso") or latest_entry.get("local"),
            })

        categories: list[dict[str, Any]] = []
        for bucket in grouped_categories.values():
            top_material_name, top_material_value = max(
                bucket["_material_values"].items(),
                key=lambda row: row[1],
                default=(None, 0.0),
            )
            top_location_name, top_location_value = max(
                bucket["_location_values"].items(),
                key=lambda row: row[1],
                default=(None, 0.0),
            )
            latest_entry = bucket.get("_latest_entry") or {}
            categories.append({
                "categoria": bucket["categoria"],
                "total_valor": round(float(bucket["total_valor"] or 0.0), 2),
                "total_litros": round(float(bucket["total_litros"] or 0.0), 3),
                "total_quilos": round(float(bucket["total_quilos"] or 0.0), 3),
                "total_quantidade_base": round(float(bucket["total_quantidade_base"] or 0.0), 3),
                "saidas": int(bucket["saidas"] or 0),
                "itens": len(bucket["_items"]),
                "colaboradores": len(bucket["_employees"]),
                "locais": len(bucket["_locations"]),
                "material_destaque": top_material_name,
                "material_destaque_valor": round(float(top_material_value or 0.0), 2),
                "local_destaque": top_location_name,
                "local_destaque_valor": round(float(top_location_value or 0.0), 2),
                "ultimo_colaborador_nome": latest_entry.get("colaborador_nome"),
                "ultimo_material_nome": latest_entry.get("descricao_item"),
                "ultimo_local": latest_entry.get("local"),
                "ultimo_lancamento": latest_entry.get("data_saida_label"),
            })

        employees: list[dict[str, Any]] = []
        for bucket in grouped_employees.values():
            top_material_name, top_material_value = max(
                bucket["_material_values"].items(),
                key=lambda row: row[1],
                default=(None, 0.0),
            )
            top_location_name, top_location_value = max(
                bucket["_location_values"].items(),
                key=lambda row: row[1],
                default=(None, 0.0),
            )
            latest_entry = bucket.get("_latest_entry") or {}
            local_fill_rate = (
                float(bucket["_filled_locations"] or 0.0) / float(bucket["saidas"] or 1.0)
                if bucket["saidas"]
                else 0.0
            )
            employee_summary = {
                "matricula": bucket["matricula"],
                "nome": bucket["nome"],
                "cargo": bucket["cargo"],
                "total_valor": round(float(bucket["total_valor"] or 0.0), 2),
                "total_litros": round(float(bucket["total_litros"] or 0.0), 3),
                "total_quilos": round(float(bucket["total_quilos"] or 0.0), 3),
                "total_quantidade_base": round(float(bucket["total_quantidade_base"] or 0.0), 3),
                "saidas": int(bucket["saidas"] or 0),
                "itens": len(bucket["_items"]),
                "locais": len(bucket["_locations"]),
                "categorias": len(bucket["_categories"]),
                "material_destaque": top_material_name,
                "material_destaque_valor": round(float(top_material_value or 0.0), 2),
                "local_destaque": top_location_name,
                "local_destaque_valor": round(float(top_location_value or 0.0), 2),
                "ultimo_material_nome": latest_entry.get("descricao_item"),
                "ultimo_local": latest_entry.get("local"),
                "ultimo_lancamento": latest_entry.get("data_saida_label"),
                "local_fill_rate": round(local_fill_rate, 4),
            }
            employee_summary["parecer_administrativo"] = cls._resolve_employee_administrative_opinion(employee_summary)
            employees.append(employee_summary)

        locations.sort(key=lambda row: (-float(row.get("total_valor") or 0.0), str(row.get("local") or "")))
        categories.sort(key=lambda row: (-float(row.get("total_valor") or 0.0), str(row.get("categoria") or "")))
        employees.sort(key=lambda row: (-float(row.get("total_valor") or 0.0), str(row.get("nome") or "")))

        overview["total_valor"] = round(float(overview["total_valor"] or 0.0), 2)
        overview["total_litros"] = round(float(overview["total_litros"] or 0.0), 3)
        overview["total_quilos"] = round(float(overview["total_quilos"] or 0.0), 3)
        overview["locais"] = len(grouped_locals)
        overview["categorias"] = len(grouped_categories)
        overview["colaboradores"] = len(grouped_employees)
        overview["itens"] = len({str(row.get("codigo_item") or "") for row in sorted_entries if row.get("codigo_item")})

        return {
            "overview": overview,
            "locations": locations,
            "categories": categories,
            "employees": employees,
            "recent_entries": sorted_entries[:12],
            "entries": sorted_entries,
        }

    @classmethod
    def _build_consumption_distribution_chart(
        cls,
        rows: list[dict[str, Any]],
        *,
        title: str,
        subtitle: str,
        label_key: str,
        fallback_label: str,
        max_segments: int = 4,
    ) -> dict[str, Any] | None:
        palette = (
            "#38bdf8",
            "#34d399",
            "#f59e0b",
            "#fb7185",
            "#a78bfa",
            "#f97316",
        )

        ordered_rows: list[dict[str, Any]] = []
        total_valor = 0.0
        for row in rows or []:
            valor = float(row.get("total_valor") or 0.0)
            if valor <= 0:
                continue
            ordered_rows.append(
                {
                    "label": (str(row.get(label_key) or fallback_label).strip() or fallback_label),
                    "value": round(valor, 2),
                }
            )
            total_valor += valor

        if total_valor <= 0 or not ordered_rows:
            return None

        visible_rows = ordered_rows[:max_segments]
        visible_total = sum(float(row["value"] or 0.0) for row in visible_rows)
        remainder = round(total_valor - visible_total, 2)
        if len(ordered_rows) > max_segments and remainder > 0:
            visible_rows.append({"label": "Outros", "value": remainder})

        gradient_parts: list[str] = []
        legend: list[dict[str, Any]] = []
        cursor = 0.0
        for index, row in enumerate(visible_rows):
            percent = (float(row["value"] or 0.0) / total_valor) * 100 if total_valor else 0.0
            next_cursor = cursor + percent
            color = palette[index % len(palette)]
            gradient_parts.append(f"{color} {cursor:.4f}% {next_cursor:.4f}%")
            legend.append(
                {
                    "label": row["label"],
                    "value": round(float(row["value"] or 0.0), 2),
                    "percent": round(percent, 1),
                    "color": color,
                }
            )
            cursor = next_cursor

        if cursor < 100.0:
            gradient_parts.append(f"rgba(148, 163, 184, 0.12) {cursor:.4f}% 100.0000%")

        primary = ordered_rows[0]
        secondary = ordered_rows[-1] if len(ordered_rows) > 1 else None
        primary_percent = round((float(primary["value"] or 0.0) / total_valor) * 100, 1) if total_valor else 0.0
        secondary_percent = (
            round((float(secondary["value"] or 0.0) / total_valor) * 100, 1)
            if total_valor and secondary is not None
            else None
        )

        return {
            "title": title,
            "subtitle": subtitle,
            "total_valor": round(total_valor, 2),
            "gradient": f"conic-gradient({', '.join(gradient_parts)})",
            "legend": legend,
            "primary_label": primary["label"],
            "primary_value": round(float(primary["value"] or 0.0), 2),
            "primary_percent": primary_percent,
            "secondary_label": secondary["label"] if secondary is not None else None,
            "secondary_value": round(float(secondary["value"] or 0.0), 2) if secondary is not None else None,
            "secondary_percent": secondary_percent,
        }

    @classmethod
    def _build_consumption_distribution_charts(
        cls,
        analytics: dict[str, Any],
        *,
        scope_type: str,
    ) -> list[dict[str, Any]]:
        configs: list[dict[str, Any]]
        if scope_type == "local":
            configs = [
                {
                    "title": "Categorias por valor",
                    "subtitle": "Como o valor deste local se distribui entre as categorias.",
                    "rows": analytics.get("categories") or [],
                    "label_key": "categoria",
                    "fallback_label": "Sem categoria",
                },
                {
                    "title": "Colaboradores por valor",
                    "subtitle": "Participação dos responsáveis no consumo deste local.",
                    "rows": analytics.get("employees") or [],
                    "label_key": "nome",
                    "fallback_label": "Não informado",
                },
            ]
        elif scope_type == "categoria":
            configs = [
                {
                    "title": "Locais por valor",
                    "subtitle": "Como esta categoria se distribui entre os locais atendidos.",
                    "rows": analytics.get("locations") or [],
                    "label_key": "local",
                    "fallback_label": "Sem local",
                },
                {
                    "title": "Colaboradores por valor",
                    "subtitle": "Participação dos responsáveis dentro desta categoria.",
                    "rows": analytics.get("employees") or [],
                    "label_key": "nome",
                    "fallback_label": "Não informado",
                },
            ]
        elif scope_type == "funcionario":
            configs = [
                {
                    "title": "Categorias por valor",
                    "subtitle": "Onde este colaborador concentrou mais valor consumido.",
                    "rows": analytics.get("categories") or [],
                    "label_key": "categoria",
                    "fallback_label": "Sem categoria",
                },
                {
                    "title": "Locais por valor",
                    "subtitle": "Distribuição do consumo deste colaborador entre os locais.",
                    "rows": analytics.get("locations") or [],
                    "label_key": "local",
                    "fallback_label": "Sem local",
                },
            ]
        else:
            configs = [
                {
                    "title": "Categorias por valor",
                    "subtitle": "Onde o valor consumido mais se concentra no exercício.",
                    "rows": analytics.get("categories") or [],
                    "label_key": "categoria",
                    "fallback_label": "Sem categoria",
                },
                {
                    "title": "Locais por valor",
                    "subtitle": "Distribuição do valor consumido entre os locais monitorados.",
                    "rows": analytics.get("locations") or [],
                    "label_key": "local",
                    "fallback_label": "Sem local",
                },
                {
                    "title": "Colaboradores por valor",
                    "subtitle": "Participação dos responsáveis no valor total consumido.",
                    "rows": analytics.get("employees") or [],
                    "label_key": "nome",
                    "fallback_label": "Não informado",
                },
            ]

        charts: list[dict[str, Any]] = []
        for config in configs:
            chart = cls._build_consumption_distribution_chart(
                config["rows"],
                title=str(config["title"]),
                subtitle=str(config["subtitle"]),
                label_key=str(config["label_key"]),
                fallback_label=str(config["fallback_label"]),
            )
            if chart is not None:
                charts.append(chart)
        return charts

    @staticmethod
    def get_stock_value_report(exercise_label: str | None = None, *, use_cache: bool = False) -> dict[str, Any]:
        from .inventory import inventory_service

        exercise = FinanceService.resolve_exercise(exercise_label)
        cache_key = f"get_stock_value_report:{exercise['label']}"
        cached = FinanceService._get_cached(cache_key) if use_cache else None
        if cached is not None:
            return dict(cached)

        items = [dict(item) for item in inventory_service.list_items(use_cache=use_cache)]
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
            metrics = _resolve_financial_entry_metrics(entry)
            item_totals["investido"] += float(entry.valor_total or 0)
            item_totals["quantidade"] += float(metrics["quantity_base"] or 0.0)
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
            .options(joinedload(Saida.usuario), joinedload(Saida.item))
            .filter(Saida.data_saida >= exercise["start_dt"])
            .filter(Saida.data_saida <= exercise["end_dt"])
            .all()
        )
        consumed_by_item: dict[str, float] = defaultdict(float)
        movement_rows = (
            db.session.query(
                StockMovement.product_id,
                func.coalesce(func.sum(func.abs(StockMovement.quantity_base)), 0.0),
            )
            .filter(StockMovement.movement_type == "saida")
            .filter(StockMovement.created_at >= exercise["start_dt"])
            .filter(StockMovement.created_at <= exercise["end_dt"])
            .group_by(StockMovement.product_id)
            .all()
        )
        for product_id, total_quantity in movement_rows:
            if product_id:
                consumed_by_item[str(product_id)] += float(total_quantity or 0.0)

        movement_by_saida: dict[str, dict[str, Any]] = {}
        saida_ids = [str(saida.id_saida) for saida in saidas if getattr(saida, "id_saida", None) is not None]
        if saida_ids:
            saida_movements = (
                StockMovement.query
                .filter(StockMovement.movement_type == "saida")
                .filter(StockMovement.reference_type.in_(tuple(_WITHDRAWAL_REFERENCE_TYPES)))
                .filter(StockMovement.reference_id.in_(saida_ids))
                .order_by(StockMovement.created_at.asc(), StockMovement.id.asc())
                .all()
            )
            for movement in saida_movements:
                ref_key = str(movement.reference_id or "").strip()
                if not ref_key:
                    continue
                bucket = movement_by_saida.setdefault(ref_key, {
                    "quantity_base": 0.0,
                    "unit_base": movement.unit_base,
                    "latest_id": 0,
                })
                bucket["quantity_base"] += abs(float(movement.quantity_base or 0.0))
                if int(movement.id or 0) >= int(bucket.get("latest_id") or 0):
                    bucket["unit_base"] = movement.unit_base
                    bucket["latest_id"] = int(movement.id or 0)
            for bucket in movement_by_saida.values():
                bucket.pop("latest_id", None)

        # Consumo fracionado por local (rastreabilidade): usa litros/kg registrados na saída.
        # Regra de custo: preço da embalagem (média do exercício quando disponível) / capacidade interna (L ou Kg).
        fracionado_por_local: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "local": "SEM LOCAL",
            "total_valor": 0.0,
            "total_litros": 0.0,
            "total_quilos": 0.0,
            "saidas": 0,
            "itens": set(),
            "latest_at": None,
            "ultimo_colaborador_nome": None,
            "ultimo_colaborador_cargo": None,
            "ultimo_material_nome": None,
            "ultimo_contexto": None,
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
            preco_emb = FinanceService._resolve_consumption_unit_price(item, purchase)
            preco_emb = float(preco_emb or 0.0)
            if preco_emb <= 0:
                fracionado_linhas_ignoradas += 1
                continue

            unidade = None
            qtd_interna = 0.0
            if retirada_l not in (None, ""):
                unidade = "L"
                try:
                    qtd_interna = float(retirada_l or 0.0)
                except Exception:
                    qtd_interna = 0.0
            elif retirada_kg not in (None, ""):
                unidade = "Kg"
                try:
                    qtd_interna = float(retirada_kg or 0.0)
                except Exception:
                    qtd_interna = 0.0

            if not unidade or qtd_interna <= 0:
                fracionado_linhas_ignoradas += 1
                continue

            valor = round(qtd_interna * preco_emb, 2)
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

            latest_at = row.get("latest_at")
            if latest_at is None or (saida.data_saida or datetime.min) > latest_at:
                usuario = getattr(saida, "usuario", None)
                observacao = (getattr(saida, "observacao", None) or "").strip()
                row["latest_at"] = saida.data_saida or datetime.min
                row["ultimo_colaborador_nome"] = (getattr(usuario, "nome", None) or "").strip() or "Não informado"
                row["ultimo_colaborador_cargo"] = (getattr(usuario, "cargo", None) or "").strip() or "Sem cargo"
                row["ultimo_material_nome"] = (
                    (item.get("descricao") if isinstance(item, dict) else None)
                    or getattr(getattr(saida, "item", None), "descricao", None)
                    or code
                )
                row["ultimo_contexto"] = f"{local_key} | {observacao}" if observacao else local_key

        consumo_fracionado_por_local: list[dict[str, Any]] = []
        for info in fracionado_por_local.values():
            consumo_fracionado_por_local.append({
                "local": info["local"],
                "total_valor": round(float(info["total_valor"] or 0.0), 2),
                "total_litros": round(float(info["total_litros"] or 0.0), 3),
                "total_quilos": round(float(info["total_quilos"] or 0.0), 3),
                "saidas": int(info["saidas"] or 0),
                "itens": len(info["itens"] or set()),
                "ultimo_colaborador_nome": info.get("ultimo_colaborador_nome"),
                "ultimo_colaborador_cargo": info.get("ultimo_colaborador_cargo"),
                "ultimo_material_nome": info.get("ultimo_material_nome"),
                "ultimo_contexto": info.get("ultimo_contexto"),
            })
        consumo_fracionado_por_local.sort(key=lambda r: (-float(r.get("total_valor") or 0.0), str(r.get("local") or "")))

        consumo_analitico_linhas: list[dict[str, Any]] = []
        for saida in saidas:
            code = str(saida.codigo_item or "").strip()
            if not code:
                continue

            item = item_map.get(code) or {}
            categoria_nome = (
                str(item.get("categoria") or "").strip()
                or str(getattr(getattr(saida, "item", None), "categoria", "") or "").strip()
                or "Sem categoria"
            )
            if FinanceService._is_tool_consumption_category(categoria_nome):
                continue
            purchase = purchases_by_item.get(code, {})
            movement_info = movement_by_saida.get(str(getattr(saida, "id_saida", "") or "").strip(), {})

            retirada_l_raw = getattr(saida, "quantidade_retirada_em_litros", None)
            retirada_kg_raw = getattr(saida, "quantidade_retirada_em_quilos", None)
            try:
                retirada_l = float(retirada_l_raw or 0.0)
            except (TypeError, ValueError):
                retirada_l = 0.0
            try:
                retirada_kg = float(retirada_kg_raw or 0.0)
            except (TypeError, ValueError):
                retirada_kg = 0.0

            quantidade_base = float(movement_info.get("quantity_base") or 0.0)
            if quantidade_base <= 0:
                if retirada_l > 0:
                    quantidade_base = retirada_l
                elif retirada_kg > 0:
                    quantidade_base = retirada_kg
                else:
                    try:
                        quantidade_base = abs(float(saida.quantidade or 0.0))
                    except (TypeError, ValueError):
                        quantidade_base = 0.0
            if quantidade_base <= 0:
                continue

            usuario = getattr(saida, "usuario", None)
            colaborador_nome = (getattr(usuario, "nome", None) or "").strip() or "Não informado"
            cargo = (getattr(usuario, "cargo", None) or "").strip() or "Sem cargo"
            local_key = FinanceService._normalize_consumption_local(getattr(saida, "local_servico", None))
            observacao = (getattr(saida, "observacao", None) or "").strip()
            unit_base = (
                (movement_info.get("unit_base") or "").strip()
                or str(item.get("unidade") or getattr(getattr(saida, "item", None), "unidade", None) or "un").strip()
                or "un"
            )
            unit_price_base = FinanceService._resolve_consumption_unit_price(item, purchase)
            valor_total = round(quantidade_base * unit_price_base, 2) if unit_price_base > 0 else 0.0
            descricao_item = (
                str(item.get("descricao") or "").strip()
                or str(getattr(getattr(saida, "item", None), "descricao", "") or "").strip()
                or code
            )
            unidade_item = (
                str(item.get("unidade") or "").strip()
                or str(getattr(getattr(saida, "item", None), "unidade", "") or "").strip()
                or "un"
            )

            entry = {
                "saida_id": getattr(saida, "id_saida", None),
                "codigo_item": code,
                "descricao_item": descricao_item,
                "categoria": categoria_nome,
                "unidade_item": unidade_item,
                "matricula": getattr(saida, "matricula", None),
                "colaborador_nome": colaborador_nome,
                "cargo": cargo,
                "local": local_key,
                "onde_usou": local_key,
                "observacao": observacao,
                "contexto_uso": f"{local_key} | {observacao}" if observacao else local_key,
                "data_saida": getattr(saida, "data_saida", None),
                "data_saida_label": saida.data_saida.strftime("%d/%m/%Y %H:%M") if getattr(saida, "data_saida", None) else "-",
                "quantidade_base": round(float(quantidade_base or 0.0), 3),
                "unit_base": unit_base,
                "quantidade_litros": round(float(retirada_l or 0.0), 3),
                "quantidade_quilos": round(float(retirada_kg or 0.0), 3),
                "valor_total": valor_total,
                "valor_unitario_base": round(float(unit_price_base or 0.0), 6),
                "tipo_consumo": "fracionado" if (retirada_l > 0 or retirada_kg > 0) else "padrao",
            }
            entry["quantidade_display"] = FinanceService._format_consumption_quantity_display(entry)
            consumo_analitico_linhas.append(entry)

        consumo_analitico = FinanceService._aggregate_consumption_entries(consumo_analitico_linhas)
        for index, row in enumerate(consumo_analitico.get("categories") or []):
            visual = category_catalog_service.get_visual(row.get("categoria"), fallback_index=index)
            row["visual"] = visual
            row["category_key"] = visual["key"]
            row["color"] = visual["color"]
            row["soft"] = visual["soft"]
            row["soft_strong"] = visual["soft_strong"]
            row["icon"] = visual["icon"]

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
            avg_unit = FinanceService._resolve_consumption_unit_price(item, purchase)
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

        visual_catalog = category_catalog_service.list_visual_catalog(include_inactive=True)
        visual_order = {
            str(row.get("key") or ""): index
            for index, row in enumerate(visual_catalog)
        }

        category_cards = list(categories.values())
        for index, card in enumerate(category_cards):
            visual = category_catalog_service.get_visual(card.get("categoria"), fallback_index=index)
            card["visual"] = visual
            card["category_key"] = visual["key"]
            card["color"] = visual["color"]
            card["soft"] = visual["soft"]
            card["soft_strong"] = visual["soft_strong"]
            card["icon"] = visual["icon"]

        category_cards.sort(
            key=lambda card: (
                visual_order.get(str(card.get("category_key") or ""), 999),
                str(card.get("categoria") or "").casefold(),
            )
        )
        for card in category_cards:
            card["items"].sort(key=lambda item: (str(item.get("descricao") or "").lower(), str(item.get("codigo") or "")))

        category_kpis = FinanceService._build_finance_category_kpis(category_cards)

        report = {
            "exercise": exercise,
            "exercise_options": FinanceService.get_available_exercises(),
            "items": items,
            "category_cards": category_cards,
            "category_kpis": category_kpis,
            "category_visual_catalog": visual_catalog,
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
            "consumo_analitico": consumo_analitico,
        }
        if use_cache:
            return FinanceService._set_cached(cache_key, dict(report), ttl_seconds=10.0)
        return report

    @classmethod
    def get_consumption_panel_report(
        cls,
        exercise_label: str | None = None,
        *,
        local_name: str | None = None,
        category_name: str | None = None,
        employee_id: str | None = None,
    ) -> dict[str, Any]:
        base_report = cls.get_stock_value_report(exercise_label)
        analytics = dict(base_report.get("consumo_analitico") or {})
        all_entries = list(analytics.get("entries") or [])

        normalized_local = cls._normalize_consumption_local(local_name) if local_name else None
        normalized_category = (category_name or "").strip() or None
        normalized_employee_id = (employee_id or "").strip() or None

        filtered_entries = all_entries
        scope_type = "geral"
        scope_title = "Painel de Consumo por Local"
        scope_subtitle = "Visão consolidada de valor, quantidade, local de uso e responsável pelas retiradas do exercício."

        if normalized_local:
            filtered_entries = [row for row in filtered_entries if cls._normalize_consumption_local(row.get("local")) == normalized_local]
            scope_type = "local"
            scope_title = f"Consumo no local {normalized_local}"
            scope_subtitle = "Rastreamento detalhado dos materiais consumidos neste local, com valor, colaborador e contexto operacional."

        if normalized_category:
            filtered_entries = [row for row in filtered_entries if (row.get("categoria") or "").strip() == normalized_category]
            scope_type = "categoria"
            scope_title = f"Consumo da categoria {normalized_category}"
            scope_subtitle = "Subpágina analítica da categoria, com materiais, locais de uso, responsáveis e valor movimentado."

        if normalized_employee_id:
            filtered_entries = [row for row in filtered_entries if str(row.get("matricula") or "").strip() == normalized_employee_id]
            scope_type = "funcionario"
            scope_title = f"Consumo do colaborador {normalized_employee_id}"
            scope_subtitle = "Histórico individual de materiais consumidos, locais atendidos, valor movimentado e parecer administrativo operacional."

        scoped_analytics = analytics if not (normalized_local or normalized_category or normalized_employee_id) else cls._aggregate_consumption_entries(filtered_entries)
        current_local = None
        current_category = None
        current_employee = None

        if normalized_local:
            current_local = next(
                (row for row in analytics.get("locations") or [] if row.get("local") == normalized_local),
                None,
            )
            if current_local is not None:
                scope_title = f"Consumo no local {current_local['local']}"

        if normalized_category:
            current_category = next(
                (row for row in analytics.get("categories") or [] if (row.get("categoria") or "") == normalized_category),
                None,
            )
            if current_category is not None:
                scope_title = f"Consumo da categoria {current_category['categoria']}"

        if normalized_employee_id:
            current_employee = next(
                (row for row in analytics.get("employees") or [] if str(row.get("matricula") or "").strip() == normalized_employee_id),
                None,
            )
            if current_employee is None and (scoped_analytics.get("employees") or []):
                current_employee = scoped_analytics["employees"][0]
            if current_employee is not None:
                scope_title = f"Consumo de {current_employee.get('nome') or normalized_employee_id}"

        return {
            "exercise": base_report["exercise"],
            "exercise_options": base_report.get("exercise_options") or [],
            "overview": scoped_analytics.get("overview") or {},
            "locations": scoped_analytics.get("locations") or [],
            "categories": scoped_analytics.get("categories") or [],
            "employees": scoped_analytics.get("employees") or [],
            "distribution_charts": cls._build_consumption_distribution_charts(scoped_analytics, scope_type=scope_type),
            "recent_entries": scoped_analytics.get("recent_entries") or [],
            "entries": scoped_analytics.get("entries") or [],
            "scope_type": scope_type,
            "scope_title": scope_title,
            "scope_subtitle": scope_subtitle,
            "filters": {
                "local": current_local.get("local") if current_local else normalized_local,
                "categoria": current_category.get("categoria") if current_category else normalized_category,
                "matricula": current_employee.get("matricula") if current_employee else normalized_employee_id,
            },
            "current_local": current_local,
            "current_category": current_category,
            "current_employee": current_employee,
            "global_locations": analytics.get("locations") or [],
            "global_categories": analytics.get("categories") or [],
            "global_employees": analytics.get("employees") or [],
        }

    @classmethod
    def build_consumption_panel_pdf(
        cls,
        exercise_label: str | None = None,
        *,
        local_name: str | None = None,
        category_name: str | None = None,
        employee_id: str | None = None,
    ) -> BytesIO:
        panel = cls.get_consumption_panel_report(
            exercise_label,
            local_name=local_name,
            category_name=category_name,
            employee_id=employee_id,
        )

        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except Exception as exc:
            raise RuntimeError("ReportLab não disponível para gerar PDF") from exc

        from ..utils.report_branding import get_company_header_html

        def _brl(value: float | int | None) -> str:
            return f"R$ {float(value or 0.0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=0.7 * cm,
            rightMargin=0.7 * cm,
            topMargin=0.8 * cm,
            bottomMargin=0.8 * cm,
            title="Relatório Analítico de Consumo",
            author="GALINT",
        )
        styles = getSampleStyleSheet()
        body_style = ParagraphStyle(
            "ConsumptionBody",
            parent=styles["BodyText"],
            fontSize=7.4,
            leading=8.4,
            spaceAfter=0,
        )
        note_style = ParagraphStyle(
            "ConsumptionNote",
            parent=styles["BodyText"],
            fontSize=8.3,
            leading=10,
            textColor=colors.HexColor("#334155"),
        )

        story: list[Any] = []
        exercise = panel["exercise"]
        overview = panel.get("overview") or {}
        story.append(Paragraph("RELATÓRIO ANALÍTICO DE CONSUMO", styles["Title"]))
        story.append(Paragraph(get_company_header_html(), styles["Normal"]))
        story.append(
            Paragraph(
                f"{panel['scope_title']} • Exercício {exercise['label']} • Período {exercise['start_date'].strftime('%d/%m/%Y')} a {exercise['end_date'].strftime('%d/%m/%Y')}",
                styles["Heading3"],
            )
        )
        story.append(Paragraph(panel["scope_subtitle"], note_style))
        story.append(Spacer(1, 0.3 * cm))

        kpi_rows = [[
            "Valor total", _brl(overview.get("total_valor")),
            "Saídas", str(int(overview.get("saidas") or 0)),
            "Locais", str(int(overview.get("locais") or 0)),
            "Colaboradores", str(int(overview.get("colaboradores") or 0)),
        ], [
            "Itens", str(int(overview.get("itens") or 0)),
            "Categorias", str(int(overview.get("categorias") or 0)),
            "Litros", f"{float(overview.get('total_litros') or 0.0):g}",
            "Kg", f"{float(overview.get('total_quilos') or 0.0):g}",
        ]]
        kpi_table = Table(kpi_rows, colWidths=[2.3 * cm, 3.1 * cm, 2.1 * cm, 1.8 * cm, 2.1 * cm, 1.8 * cm, 2.6 * cm, 1.8 * cm])
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#0f172a")),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#1e293b")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 0.35 * cm))

        if panel.get("locations"):
            story.append(Paragraph("Resumo por local", styles["Heading2"]))
            local_rows: list[list[Any]] = [["Local", "Valor", "Saídas", "Itens", "Colaboradores", "Material destaque"]]
            for row in panel["locations"]:
                local_rows.append([
                    row.get("local") or "SEM LOCAL",
                    _brl(row.get("total_valor")),
                    str(int(row.get("saidas") or 0)),
                    str(int(row.get("itens") or 0)),
                    str(int(row.get("colaboradores") or 0)),
                    row.get("material_destaque") or "—",
                ])
            local_table = Table(local_rows, repeatRows=1, colWidths=[5.2 * cm, 2.4 * cm, 1.7 * cm, 1.5 * cm, 2.2 * cm, 6.0 * cm])
            local_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(local_table)
            story.append(Spacer(1, 0.25 * cm))

        if panel.get("categories"):
            story.append(Paragraph("Resumo por categoria", styles["Heading2"]))
            category_rows: list[list[Any]] = [["Categoria", "Valor", "Saídas", "Locais", "Colaboradores", "Local destaque"]]
            for row in panel["categories"]:
                category_rows.append([
                    row.get("categoria") or "Sem categoria",
                    _brl(row.get("total_valor")),
                    str(int(row.get("saidas") or 0)),
                    str(int(row.get("locais") or 0)),
                    str(int(row.get("colaboradores") or 0)),
                    row.get("local_destaque") or "—",
                ])
            category_table = Table(category_rows, repeatRows=1, colWidths=[5.0 * cm, 2.4 * cm, 1.7 * cm, 1.6 * cm, 2.2 * cm, 6.1 * cm])
            category_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(category_table)
            story.append(Spacer(1, 0.25 * cm))

        if panel.get("employees"):
            story.append(Paragraph("Resumo por colaborador", styles["Heading2"]))
            employee_rows: list[list[Any]] = [["Colaborador", "Cargo", "Valor", "Saídas", "Locais", "Parecer"]]
            for row in panel["employees"]:
                opinion = (row.get("parecer_administrativo") or {}).get("label") or "Sem base"
                employee_rows.append([
                    row.get("nome") or "Não informado",
                    row.get("cargo") or "Sem cargo",
                    _brl(row.get("total_valor")),
                    str(int(row.get("saidas") or 0)),
                    str(int(row.get("locais") or 0)),
                    opinion,
                ])
            employee_table = Table(employee_rows, repeatRows=1, colWidths=[4.6 * cm, 3.3 * cm, 2.3 * cm, 1.7 * cm, 1.6 * cm, 5.1 * cm])
            employee_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(employee_table)
            story.append(Spacer(1, 0.3 * cm))

        story.append(Paragraph("Lançamentos detalhados", styles["Heading2"]))
        detail_rows: list[list[Any]] = [[
            "Data/Hora",
            "Colaborador",
            "Cargo",
            "Material",
            "Categoria",
            "Local",
            "Qtde",
            "Valor",
            "Contexto",
        ]]
        for row in panel.get("entries") or []:
            detail_rows.append([
                row.get("data_saida_label") or "-",
                Paragraph(str(row.get("colaborador_nome") or "Não informado"), body_style),
                Paragraph(str(row.get("cargo") or "Sem cargo"), body_style),
                Paragraph(str(row.get("descricao_item") or "Item sem descrição"), body_style),
                Paragraph(str(row.get("categoria") or "Sem categoria"), body_style),
                Paragraph(str(row.get("local") or "SEM LOCAL"), body_style),
                row.get("quantidade_display") or "0",
                _brl(row.get("valor_total")),
                Paragraph(str(row.get("contexto_uso") or row.get("local") or "SEM CONTEXTO"), body_style),
            ])
        details_table = Table(
            detail_rows,
            repeatRows=1,
            colWidths=[2.4 * cm, 3.0 * cm, 2.5 * cm, 5.0 * cm, 2.6 * cm, 2.9 * cm, 2.1 * cm, 2.4 * cm, 5.2 * cm],
        )
        details_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("FONTSIZE", (0, 0), (-1, -1), 7.3),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(details_table)
        story.append(Spacer(1, 0.3 * cm))

        current_employee = panel.get("current_employee")
        if current_employee:
            opinion = current_employee.get("parecer_administrativo") or {}
            story.append(Paragraph("Parecer administrativo", styles["Heading2"]))
            story.append(
                Paragraph(
                    f"<b>{current_employee.get('nome') or 'Colaborador'}</b> • Score {int(opinion.get('score') or 0)} • {opinion.get('label') or 'Sem base'}<br/>{opinion.get('text') or ''}",
                    note_style,
                )
            )
        elif panel.get("employees"):
            story.append(Paragraph("Parecer administrativo consolidado", styles["Heading2"]))
            story.append(
                Paragraph(
                    "O parecer administrativo deste relatório mede disciplina operacional e rastreabilidade de consumo, especialmente preenchimento de local de uso, cargo e distribuição dos registros. Não representa avaliação de produtividade isolada.",
                    note_style,
                )
            )

        doc.build(story)
        buffer.seek(0)
        return buffer

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

                metrics = _resolve_financial_entry_metrics(e)
                qtd = float(metrics["quantity_base"] or 0.0)
                item_stats["quantidade"] += qtd

                vu = float(metrics["unit_price_base"] or 0.0)
                if vu > 0:
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
