from __future__ import annotations

from datetime import datetime
import math
import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func

from ..extensions import db
from ..models import Item, ItemPotentialSupplierQuote, PotentialSupplier
from ..utils.formatters import format_currency_br
from .price_normalization import infer_price_unit_for_item, normalize_item_price


def _clean_text(value: object, *, max_length: int | None = None) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    if max_length and len(text) > max_length:
        return text[:max_length].rstrip()
    return text


def _clean_cnpj(value: object) -> str | None:
    digits = re.sub(r"\D+", "", str(value or ""))
    if len(digits) != 14:
        return None
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _source_host(url: object) -> str | None:
    try:
        host = urlparse(str(url or "")).netloc.lower().replace("www.", "")
    except Exception:
        return None
    return host or None


def _safe_float(value: object) -> float | None:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _format_currency(value: object) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return "-"
    return format_currency_br(parsed)


class PotentialSupplierService:
    DEFAULT_LIMIT = 12

    def build_reference(self, item: Item | None) -> dict[str, object]:
        if item is None:
            return {"unit_price_base": None, "unit_price": None, "price_unit": None, "source_label": "Sem referencia"}

        price_base = _safe_float(getattr(item, "preco_compra_unitario_base", None))
        price_raw = _safe_float(getattr(item, "preco_compra_unitario", None))
        price_unit = _clean_text(getattr(item, "preco_compra_unidade_preco", None)) or infer_price_unit_for_item(item)
        source = _clean_text(getattr(item, "preco_compra_fonte", None))
        document = _clean_text(getattr(item, "preco_compra_documento", None)) or _clean_text(getattr(item, "nota_fiscal", None))
        if price_base is None and price_raw is not None:
            try:
                normalized = normalize_item_price(item, unit_price=price_raw, price_unit=price_unit)
                price_base = normalized.unit_price_base
                price_unit = normalized.price_unit
            except Exception:
                pass

        source_label = "Ultima NF/Cupom" if document else "Preco de compra cadastrado"
        if source and source not in {"manual", "sem_nf"}:
            source_label = source.replace("_", " ").title()
        return {
            "unit_price": price_raw,
            "unit_price_base": price_base,
            "price_unit": price_unit,
            "price_display": _format_currency(price_raw),
            "price_display_base": _format_currency(price_base),
            "source": source,
            "source_label": source_label,
            "document": document,
            "document_type": _clean_text(getattr(item, "finance_tipo_documento", None)),
        }

    def list_item_quotes(
        self,
        codigo_item: str,
        *,
        reference_price_base: object = None,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        safe_limit = max(1, min(int(limit or self.DEFAULT_LIMIT), 50))
        query = (
            ItemPotentialSupplierQuote.query
            .filter(ItemPotentialSupplierQuote.codigo_item == codigo_item)
            .join(PotentialSupplier)
            .order_by(
                ItemPotentialSupplierQuote.unit_price_base.is_(None),
                ItemPotentialSupplierQuote.unit_price_base.asc(),
                ItemPotentialSupplierQuote.captured_at.desc(),
                ItemPotentialSupplierQuote.id.desc(),
            )
            .limit(safe_limit)
        )
        return [
            self.serialize_quote(quote, reference_price_base=reference_price_base)
            for quote in query.all()
        ]

    def list_best_quotes_by_item(
        self,
        item_codes: list[str] | tuple[str, ...] | set[str],
        *,
        limit_per_item: int = 4,
        reference_prices: dict[str, object] | None = None,
    ) -> dict[str, list[dict[str, object]]]:
        codes = [str(code or "").strip() for code in item_codes if str(code or "").strip()]
        if not codes:
            return {}
        rows = (
            ItemPotentialSupplierQuote.query
            .filter(ItemPotentialSupplierQuote.codigo_item.in_(codes))
            .join(PotentialSupplier)
            .order_by(
                ItemPotentialSupplierQuote.codigo_item.asc(),
                ItemPotentialSupplierQuote.unit_price_base.is_(None),
                ItemPotentialSupplierQuote.unit_price_base.asc(),
                ItemPotentialSupplierQuote.captured_at.desc(),
                ItemPotentialSupplierQuote.id.desc(),
            )
            .all()
        )
        grouped: dict[str, list[dict[str, object]]] = {}
        refs = dict(reference_prices or {})
        for quote in rows:
            codigo = str(quote.codigo_item or "")
            bucket = grouped.setdefault(codigo, [])
            if len(bucket) >= max(1, limit_per_item):
                continue
            bucket.append(self.serialize_quote(quote, reference_price_base=refs.get(codigo)))
        return grouped

    def get_quote(self, quote_id: object, *, reference_price_base: object = None) -> dict[str, object] | None:
        try:
            parsed_id = int(quote_id)
        except (TypeError, ValueError):
            return None
        quote = ItemPotentialSupplierQuote.query.get(parsed_id)
        if not quote:
            return None
        return self.serialize_quote(quote, reference_price_base=reference_price_base)

    def capture_suggestions(
        self,
        item: Item,
        suggestions: list[dict[str, Any]],
        *,
        query: str | None = None,
        uf: str | None = None,
        price_unit: str | None = None,
        actor_matricula: str | None = None,
    ) -> list[dict[str, object]]:
        captured: list[ItemPotentialSupplierQuote] = []
        resolved_unit = _clean_text(price_unit) or infer_price_unit_for_item(item)
        for suggestion in suggestions:
            price = _safe_float(suggestion.get("price"))
            if price is None or price <= 0:
                continue
            try:
                normalized = normalize_item_price(item, unit_price=price, price_unit=resolved_unit)
            except Exception:
                normalized = None

            supplier = self._upsert_supplier(suggestion, actor_matricula=actor_matricula)
            product_url = _clean_text(suggestion.get("url"))
            quote = self._find_existing_quote(item.codigo_item, product_url)
            if quote is None:
                quote = ItemPotentialSupplierQuote(
                    codigo_item=item.codigo_item,
                    potential_supplier=supplier,
                    product_url=product_url,
                )
                db.session.add(quote)
            quote.potential_supplier = supplier
            quote.source_name = _clean_text(suggestion.get("source"), max_length=80)
            quote.offer_title = _clean_text(suggestion.get("title"), max_length=255)
            quote.product_url = product_url
            quote.currency = _clean_text(suggestion.get("currency"), max_length=10) or "BRL"
            quote.unit_price = float(price)
            quote.price_unit = normalized.price_unit if normalized is not None else resolved_unit
            quote.unit_price_base = normalized.unit_price_base if normalized is not None else None
            quote.factor_to_base = normalized.factor_to_base if normalized is not None else None
            quote.uf = _clean_text(suggestion.get("uf") or uf, max_length=2)
            quote.quote_status = "capturada"
            quote.capture_query = _clean_text(query)
            quote.metadata_json = {
                "source_payload": {key: value for key, value in suggestion.items() if value not in (None, "")},
                "seller_missing_fields": self._seller_missing_fields(suggestion),
            }
            quote.captured_by_matricula = actor_matricula
            quote.captured_at = datetime.utcnow()
            captured.append(quote)

        db.session.flush()
        reference = self.build_reference(item)
        reference_price = reference.get("unit_price_base")
        return [self.serialize_quote(quote, reference_price_base=reference_price) for quote in captured]

    def _upsert_supplier(self, suggestion: dict[str, Any], *, actor_matricula: str | None = None) -> PotentialSupplier:
        source_name = _clean_text(suggestion.get("source"), max_length=80)
        seller_identifier = _clean_text(suggestion.get("seller_identifier"), max_length=120)
        cnpj = _clean_cnpj(suggestion.get("seller_cnpj"))
        product_url = _clean_text(suggestion.get("url"))
        host = _source_host(product_url)
        display_name = (
            _clean_text(suggestion.get("seller_name"), max_length=160)
            or host
            or source_name
            or "Potencial Fornecedor"
        )

        supplier: PotentialSupplier | None = None
        if seller_identifier and source_name:
            supplier = PotentialSupplier.query.filter(
                func.lower(PotentialSupplier.source_name) == source_name.lower(),
                PotentialSupplier.marketplace_seller_id == seller_identifier,
            ).first()
        if supplier is None and cnpj:
            supplier = PotentialSupplier.query.filter(PotentialSupplier.cnpj == cnpj).first()
        if supplier is None and host:
            supplier = PotentialSupplier.query.filter(
                func.lower(PotentialSupplier.website) == host.lower()
            ).first()
        if supplier is None:
            supplier = PotentialSupplier(display_name=display_name)
            supplier.created_by_matricula = actor_matricula
            db.session.add(supplier)

        supplier.display_name = display_name or supplier.display_name
        supplier.legal_name = _clean_text(suggestion.get("seller_legal_name"), max_length=180) or supplier.legal_name
        supplier.cnpj = cnpj or supplier.cnpj
        supplier.source_name = source_name or supplier.source_name
        supplier.source_url = product_url or supplier.source_url
        supplier.website = host or supplier.website
        supplier.marketplace_seller_id = seller_identifier or supplier.marketplace_seller_id
        supplier.address_line = _clean_text(suggestion.get("seller_address"), max_length=255) or supplier.address_line
        supplier.city = _clean_text(suggestion.get("seller_city"), max_length=120) or supplier.city
        supplier.state = _clean_text(suggestion.get("seller_state"), max_length=40) or supplier.state
        supplier.contact_url = _clean_text(suggestion.get("seller_contact_url")) or product_url or supplier.contact_url
        supplier.status = supplier.status or "capturado"
        supplier.updated_by_matricula = actor_matricula or supplier.updated_by_matricula
        supplier.metadata_json = {
            **dict(supplier.metadata_json or {}),
            "last_capture_source": source_name,
            "last_product_url": product_url,
            "data_completeness": self._data_completeness_score(supplier, suggestion),
        }
        return supplier

    def _find_existing_quote(self, codigo_item: str, product_url: str | None) -> ItemPotentialSupplierQuote | None:
        if not product_url:
            return None
        return ItemPotentialSupplierQuote.query.filter(
            ItemPotentialSupplierQuote.codigo_item == codigo_item,
            ItemPotentialSupplierQuote.product_url == product_url,
        ).first()

    def serialize_quote(
        self,
        quote: ItemPotentialSupplierQuote,
        *,
        reference_price_base: object = None,
        requested_quantity_base: object = None,
    ) -> dict[str, object]:
        supplier = quote.potential_supplier
        price_base = _safe_float(quote.unit_price_base)
        reference_base = _safe_float(reference_price_base)
        quantity_base = _safe_float(requested_quantity_base)
        variation_percent = None
        savings_total = None
        if price_base is not None and reference_base is not None and reference_base > 0:
            variation_percent = ((price_base - reference_base) / reference_base) * 100.0
            if quantity_base is not None and quantity_base > 0:
                savings_total = (reference_base - price_base) * quantity_base
        return {
            "id": quote.id,
            "codigo_item": quote.codigo_item,
            "source_name": quote.source_name,
            "offer_title": quote.offer_title,
            "product_url": quote.product_url,
            "currency": quote.currency,
            "unit_price": quote.unit_price,
            "unit_price_display": _format_currency(quote.unit_price),
            "price_unit": quote.price_unit,
            "unit_price_base": price_base,
            "unit_price_base_display": _format_currency(price_base),
            "variation_percent": variation_percent,
            "variation_display": self._format_variation(variation_percent),
            "estimated_savings_total": savings_total,
            "estimated_savings_display": _format_currency(savings_total) if savings_total is not None else None,
            "captured_at": quote.captured_at.isoformat() if quote.captured_at else None,
            "captured_at_display": quote.captured_at.strftime("%d/%m/%Y %H:%M") if quote.captured_at else "-",
            "status": quote.quote_status,
            "supplier": supplier.to_dict() if supplier else None,
        }

    @staticmethod
    def _format_variation(value: object) -> str:
        parsed = _safe_float(value)
        if parsed is None:
            return "-"
        sign = "+" if parsed > 0 else ""
        return f"{sign}{parsed:.1f}%".replace(".", ",")

    @staticmethod
    def _seller_missing_fields(suggestion: dict[str, Any]) -> list[str]:
        fields = {
            "cnpj": suggestion.get("seller_cnpj"),
            "endereco": suggestion.get("seller_address") or suggestion.get("seller_city"),
            "contato": suggestion.get("seller_contact_url"),
        }
        return [name for name, value in fields.items() if not _clean_text(value)]

    @staticmethod
    def _data_completeness_score(supplier: PotentialSupplier, suggestion: dict[str, Any]) -> float:
        values = [
            supplier.display_name,
            supplier.cnpj or suggestion.get("seller_cnpj"),
            supplier.city or suggestion.get("seller_city"),
            supplier.state or suggestion.get("seller_state"),
            supplier.contact_url or suggestion.get("seller_contact_url"),
        ]
        present = sum(1 for value in values if _clean_text(value))
        return round(present / len(values), 2)


potential_supplier_service = PotentialSupplierService()