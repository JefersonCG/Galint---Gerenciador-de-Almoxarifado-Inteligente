from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from flask import current_app, has_request_context, url_for

from ..models import InventarioEvento, Item, Saida, StockMovement, Usuario
from .balance_provider import balance_provider
from .legacy_stock_normalizer import (
    ignore_packaging_metadata_for_stock,
    is_packaging_unit_code,
    resolve_canonical_unit,
    resolve_packaging_factor,
)
from .material_return_metadata import extract_material_return_metadata, format_material_return_actor_label
from .network_settings import load_network_settings


_QTD_ORIGINAL_RE = re.compile(r"QTD_ORIGINAL\s*=\s*([0-9]+(?:[.,][0-9]+)?)", re.IGNORECASE)
_UNIDADE_RE = re.compile(r"UNIDADE\s*=\s*([A-ZÇÃÕÁÉÍÓÚ_ ]+)", re.IGNORECASE)
_FRACIONADA_RE = re.compile(
    r"RETIRADA\s+FRACIONADA:\s*([0-9]+(?:[.,][0-9]+)?)\s*([A-ZÇÃÕÁÉÍÓÚ]+)",
    re.IGNORECASE,
)


class OperationVisualPayloadService:
    @staticmethod
    def build_for_saida(
        saida: Saida,
        *,
        balance_before: float | None = None,
        balance_after: float | None = None,
        balance_unit: str | None = None,
    ) -> dict[str, Any]:
        item = saida.item
        actor = saida.usuario or OperationVisualPayloadService._get_user(saida.matricula)
        kind = OperationVisualPayloadService._kind_for_saida(saida, item)
        photo = OperationVisualPayloadService._photo_payload(item)
        display = OperationVisualPayloadService.resolve_withdrawal_display_context(
            saida,
            balance_before=balance_before,
            balance_after=balance_after,
            balance_unit=balance_unit,
        )

        return {
            "kind": kind,
            "kind_label": OperationVisualPayloadService._kind_label(kind),
            "status": "completed",
            "item": {
                "codigo": saida.codigo_item,
                "descricao": item.descricao if item else (saida.codigo_item or "Item"),
                "categoria": item.categoria if item else None,
                "unidade": display["balance_unit_display"],
                "saldo": display["balance_after"],
                "saldo_display": display["balance_after_display"],
                **photo,
            },
            "movement": {
                "id": saida.id_saida,
                "quantidade": saida.quantidade,
                "quantidade_display": display["quantity_display"],
                "balance_before": display["balance_before"],
                "balance_after": display["balance_after"],
                "balance_unit": display["balance_unit_display"],
                "balance_before_display": display["balance_before_display"],
                "balance_after_display": display["balance_after_display"],
                "tipo_custodia": saida.tipo_custodia,
                "fracionada": bool(getattr(saida, "usou_fracao", False)),
            },
            "actor": OperationVisualPayloadService._actor_payload(actor, saida.matricula),
            "context": {
                "local_servico": (saida.local_servico or "").strip() or None,
                "observacao": (saida.observacao or "").strip() or None,
            },
            "batch_label": OperationVisualPayloadService._batch_label(saida, item),
            "source_label": "notificacao operacional",
            "generated_at": saida.data_saida.isoformat() if saida.data_saida else None,
        }

    @staticmethod
    def build_for_inventory_event(event: InventarioEvento) -> dict[str, Any]:
        item = OperationVisualPayloadService._get_item(event.codigo_item)
        kind = OperationVisualPayloadService._kind_for_inventory(event, item)
        unit = item.unidade if item else None
        photo = OperationVisualPayloadService._photo_payload(item)
        event_type = (event.tipo or "").strip().lower()
        return_metadata = extract_material_return_metadata(event.descricao) if event_type == "devolucao_material" else None

        actor_matricula = event.matricula
        withdrawer_label = None
        returner_label = None
        if return_metadata:
            withdrawer_matricula = return_metadata["withdrawer"].get("matricula") or event.matricula
            returner_matricula = return_metadata["returner"].get("matricula") or None
            withdrawer_user = OperationVisualPayloadService._get_user(withdrawer_matricula)
            actor_matricula = returner_matricula or event.matricula
            actor = OperationVisualPayloadService._get_user(actor_matricula)
            withdrawer_label = return_metadata["withdrawer"].get("raw") or format_material_return_actor_label(
                nome=getattr(withdrawer_user, "nome", None),
                matricula=withdrawer_matricula,
            )
            returner_label = return_metadata["returner"].get("raw") or format_material_return_actor_label(
                nome=getattr(actor, "nome", None),
                matricula=actor_matricula,
            )
            clean_description = return_metadata.get("clean_description") or (event.descricao or "").strip() or None
        else:
            actor = OperationVisualPayloadService._get_user(event.matricula)
            clean_description = (event.descricao or "").strip() or None

        return {
            "kind": kind,
            "kind_label": OperationVisualPayloadService._kind_label(kind),
            "status": "completed",
            "item": {
                "codigo": event.codigo_item,
                "descricao": item.descricao if item else (event.codigo_item or "Item"),
                "categoria": item.categoria if item else None,
                "unidade": unit,
                **photo,
            },
            "movement": {
                "id": event.id_evento,
                "quantidade": event.quantidade,
                "quantidade_display": OperationVisualPayloadService._format_balance(event.quantidade, unit),
                "tipo": event.tipo,
            },
            "actor": OperationVisualPayloadService._actor_payload(actor, actor_matricula),
            "context": {
                "local_servico": None,
                "observacao": clean_description,
                "retirado_por": withdrawer_label,
                "devolvido_por": returner_label,
            },
            "batch_label": OperationVisualPayloadService._event_badge(event),
            "source_label": "evento de inventario",
            "generated_at": event.data_evento.isoformat() if event.data_evento else None,
        }

    @staticmethod
    def build_for_item(
        item: Item | None,
        *,
        kind: str = "item",
        kind_label: str | None = None,
        item_code: str | None = None,
        item_description: str | None = None,
        item_category: str | None = None,
        unit: str | None = None,
        quantity: float | None = None,
        quantity_display: str | None = None,
        actor_name: str | None = None,
        actor_matricula: str | None = None,
        context: dict[str, Any] | None = None,
        source_label: str | None = None,
        generated_at: Any = None,
    ) -> dict[str, Any]:
        resolved_unit = unit or (item.unidade if item else None)
        photo = OperationVisualPayloadService._photo_payload(item)
        generated_value = generated_at.isoformat() if hasattr(generated_at, "isoformat") else generated_at
        context = context or {}

        return {
            "kind": kind,
            "kind_label": kind_label or OperationVisualPayloadService._kind_label(kind),
            "status": "completed",
            "item": {
                "codigo": item_code or (item.codigo_item if item else None),
                "descricao": item_description or (item.descricao if item else (item_code or "Item")),
                "categoria": item_category or (item.categoria if item else None),
                "unidade": resolved_unit,
                **photo,
            },
            "movement": {
                "id": None,
                "quantidade": quantity,
                "quantidade_display": quantity_display or OperationVisualPayloadService._format_balance(quantity, resolved_unit),
            },
            "actor": {
                "matricula": actor_matricula,
                "nome": actor_name,
            },
            "context": {
                "local_servico": (str(context.get("local_servico", "") or "").strip() or None),
                "observacao": (str(context.get("observacao", "") or "").strip() or None),
            },
            "batch_label": ((getattr(item, "lote", None) or "").strip() if item else None) or None,
            "source_label": source_label or "notificacao operacional",
            "generated_at": generated_value,
        }

    @staticmethod
    def build_media_payload(visual_payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(visual_payload, dict):
            return None
        item = visual_payload.get("item") or {}
        photo_path = (item.get("foto_path") or "").strip() if isinstance(item, dict) else ""
        photo_url = (item.get("foto_url") or "").strip() if isinstance(item, dict) else ""
        gallery = visual_payload.get("gallery") if isinstance(visual_payload.get("gallery"), list) else []
        if not photo_path and not photo_url:
            for entry in gallery:
                if not isinstance(entry, dict):
                    continue
                photo_path = (entry.get("foto_path") or "").strip()
                photo_url = (entry.get("foto_url") or "").strip()
                if photo_path or photo_url:
                    break
        resolved_path = OperationVisualPayloadService._resolve_photo_file(photo_path)
        if not resolved_path and not photo_url:
            return None
        return {
            "type": "photo",
            "path": str(resolved_path) if resolved_path else None,
            "url": photo_url or None,
            "caption": None,
        }

    @staticmethod
    def build_gallery_for_saidas(saidas: list[Saida] | None, *, limit: int = 4) -> list[dict[str, Any]]:
        gallery: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        for saida in saidas or []:
            item = saida.item or OperationVisualPayloadService._get_item(saida.codigo_item)
            if not item:
                continue
            code = (item.codigo_item or saida.codigo_item or "").strip()
            if code and code in seen_codes:
                continue
            photo = OperationVisualPayloadService._photo_payload(item)
            if not photo.get("foto_path") and not photo.get("foto_url"):
                continue
            if code:
                seen_codes.add(code)
            gallery.append(
                {
                    "codigo": code or None,
                    "descricao": item.descricao,
                    "quantidade": saida.quantidade,
                    "quantidade_display": OperationVisualPayloadService.format_saida_quantity_display(saida, item, short=True),
                    **photo,
                }
            )
            if len(gallery) >= limit:
                break
        return gallery

    @staticmethod
    def resolve_withdrawal_display_context(
        saida: Saida,
        *,
        balance_before: float | None = None,
        balance_after: float | None = None,
        balance_unit: str | None = None,
    ) -> dict[str, Any]:
        item = saida.item
        movement = OperationVisualPayloadService._get_saida_stock_movement(saida)
        resolved_unit = OperationVisualPayloadService._resolve_withdrawal_balance_unit(
            item,
            balance_unit=balance_unit,
            movement_unit=(movement.unit_base if movement else None),
        )
        quantity_base = OperationVisualPayloadService._resolve_quantity_base(saida, movement)

        resolved_after = balance_after
        if resolved_after is None and item is not None:
            resolved_after = OperationVisualPayloadService._get_current_balance(item, resolved_unit)

        resolved_before = balance_before
        if resolved_before is None and resolved_after is not None and quantity_base is not None:
            resolved_before = float(resolved_after) + float(quantity_base)

        return {
            "balance_unit": resolved_unit,
            "balance_unit_display": OperationVisualPayloadService._display_unit(resolved_unit, short=True),
            "balance_before": resolved_before,
            "balance_after": resolved_after,
            "balance_before_display": OperationVisualPayloadService.format_balance_display(
                resolved_before,
                item,
                unit_hint=resolved_unit,
                short=True,
            ),
            "balance_after_display": OperationVisualPayloadService.format_balance_display(
                resolved_after,
                item,
                unit_hint=resolved_unit,
                short=True,
            ),
            "quantity_display": OperationVisualPayloadService.format_saida_quantity_display(saida, item, movement=movement, short=True),
        }

    @staticmethod
    def format_saida_quantity_display(
        saida: Saida,
        item: Item | None,
        *,
        movement: StockMovement | None = None,
        short: bool = False,
    ) -> str | None:
        movement = movement or OperationVisualPayloadService._get_saida_stock_movement(saida)
        original_quantity, original_unit = OperationVisualPayloadService._extract_saida_original_quantity(saida, movement)
        if original_quantity is not None and original_unit:
            return OperationVisualPayloadService._format_value_with_unit(
                original_quantity,
                original_unit,
                item=item,
                short=short,
            )

        quantity_base = OperationVisualPayloadService._resolve_quantity_base(saida, movement)
        if quantity_base is None:
            try:
                quantity_base = abs(float(saida.quantidade or 0.0))
            except Exception:
                quantity_base = None

        if quantity_base is None:
            return None

        unit_hint = OperationVisualPayloadService._resolve_withdrawal_balance_unit(
            item,
            movement_unit=(movement.unit_base if movement else None),
        )
        return OperationVisualPayloadService._format_value_with_unit(quantity_base, unit_hint, item=item, short=short)

    @staticmethod
    def format_balance_display(
        value: float | None,
        item: Item | None,
        *,
        unit_hint: str | None = None,
        short: bool = False,
    ) -> str | None:
        if value is None:
            return None

        display_unit = OperationVisualPayloadService._resolve_withdrawal_balance_unit(item, balance_unit=unit_hint)
        base_display = OperationVisualPayloadService._format_value_with_unit(value, display_unit, item=item, short=short)
        if not base_display or item is None or ignore_packaging_metadata_for_stock(item):
            return base_display

        packaging_hint = OperationVisualPayloadService._format_packaging_equivalent(
            value,
            item,
            unit_hint=display_unit,
            short=short,
        )
        if packaging_hint:
            return f"{base_display} ({packaging_hint})"
        return base_display

    @staticmethod
    def _kind_for_saida(saida: Saida, item: Item | None) -> str:
        if bool(getattr(saida, "usou_fracao", False)):
            return "fracionada"
        categoria = ((item.categoria if item else "") or "").strip().lower()
        if "ferrament" in categoria:
            return "ferramenta"
        return "saida"

    @staticmethod
    def _kind_for_inventory(event: InventarioEvento, item: Item | None) -> str:
        tipo = (event.tipo or "").strip().lower()
        if "ferramenta" in tipo:
            return "ferramenta"
        categoria = ((item.categoria if item else "") or "").strip().lower()
        if "ferrament" in categoria:
            return "ferramenta"
        return "entrada"

    @staticmethod
    def _kind_label(kind: str) -> str:
        labels = {
            "saida": "Saida",
            "entrada": "Devolucao",
            "ferramenta": "Ferramenta",
            "fracionada": "Saida fracionada",
        }
        return labels.get(kind, "Operacao")

    @staticmethod
    def _photo_payload(item: Item | None) -> dict[str, Any]:
        foto_path = ((item.foto_path if item else "") or "").strip() or None
        return {
            "foto_path": foto_path,
            "foto_url": OperationVisualPayloadService._build_photo_url(foto_path),
        }

    @staticmethod
    def _build_photo_url(foto_path: str | None) -> str | None:
        if not foto_path:
            return None
        try:
            if has_request_context():
                return url_for("static", filename=foto_path)
            settings = load_network_settings(current_app)
            return f"{settings.base_url()}/static/{foto_path.lstrip('/')}"
        except Exception:
            return None

    @staticmethod
    def _resolve_photo_file(foto_path: str | None) -> Path | None:
        if not foto_path:
            return None
        try:
            candidate = Path(current_app.root_path) / "static" / foto_path
        except Exception:
            return None
        if candidate.exists() and candidate.is_file():
            return candidate
        return None

    @staticmethod
    def _get_item(codigo_item: str | None) -> Item | None:
        if not codigo_item:
            return None
        return Item.query.get(codigo_item)

    @staticmethod
    def _get_user(matricula: str | None) -> Usuario | None:
        if not matricula:
            return None
        return Usuario.query.get(matricula)

    @staticmethod
    def _get_saida_stock_movement(saida: Saida) -> StockMovement | None:
        try:
            movement = (
                StockMovement.query
                .filter(
                    StockMovement.product_id == saida.codigo_item,
                    StockMovement.reference_type == "legacy_movimento",
                    StockMovement.reference_id == str(saida.id_saida),
                    StockMovement.movement_type == "saida",
                )
                .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
                .first()
            )
            if movement is not None:
                return movement

            if saida.data_saida is None:
                return None

            window_start = saida.data_saida.replace(microsecond=0)
            window_end = saida.data_saida.replace(microsecond=999999)
            candidates = (
                StockMovement.query
                .filter(
                    StockMovement.product_id == saida.codigo_item,
                    StockMovement.reference_type == "legacy_movimento",
                    StockMovement.movement_type == "saida",
                    StockMovement.created_at >= window_start,
                    StockMovement.created_at <= window_end,
                )
                .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
                .all()
            )
            if not candidates:
                return None

            def _candidate_rank(row: StockMovement) -> tuple[float, int, int, int]:
                metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
                legacy_payload = metadata.get("legacy_payload") if isinstance(metadata.get("legacy_payload"), dict) else {}
                input_quantity = OperationVisualPayloadService._parse_float(metadata.get("input_quantity"))
                row_quantity = abs(float(row.quantity_base or 0.0))
                delta = abs((row.created_at - saida.data_saida).total_seconds()) if row.created_at and saida.data_saida else 999999.0
                local_penalty = 0 if str(legacy_payload.get("local_servico") or "").strip().casefold() == str(saida.local_servico or "").strip().casefold() else 1
                qty_match = input_quantity if input_quantity is not None else row_quantity
                qty_penalty = 0 if abs(float(qty_match or 0.0) - abs(float(saida.quantidade or 0.0))) <= 1e-6 else 1
                return (delta, local_penalty, qty_penalty, -int(row.id or 0))

            return sorted(candidates, key=_candidate_rank)[0]
        except Exception:
            return None

    @staticmethod
    def _normalize_unit(unit: str | None) -> str:
        raw = (unit or "").strip().lower()
        aliases = {
            "lt": "l",
            "lts": "l",
            "litro": "l",
            "litros": "l",
            "quilo": "kg",
            "quilos": "kg",
            "kilo": "kg",
            "kilos": "kg",
            "metro": "m",
            "metros": "m",
            "unidade": "un",
            "unidades": "un",
            "par": "par",
            "pares": "par",
        }
        return aliases.get(raw, raw)

    @staticmethod
    def _parse_float(value: object) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _format_number(value: float, *, decimals: int = 3) -> str:
        try:
            value_f = float(value)
        except Exception:
            return "0"
        if abs(value_f - round(value_f)) < 1e-9:
            return str(int(round(value_f)))
        return f"{value_f:.{decimals}f}".rstrip("0").rstrip(".").replace(".", ",")

    @staticmethod
    def _display_unit(unit: str | None, *, value: float | None = None, short: bool = False, item: Item | None = None) -> str | None:
        normalized = OperationVisualPayloadService._normalize_unit(unit)
        singular = abs(float(value or 0.0) - 1.0) < 1e-9

        if normalized == "l":
            return "L" if short else ("litro" if singular else "litros")
        if normalized == "kg":
            return "kg"
        if normalized == "m":
            return "m" if short else ("metro" if singular else "metros")
        if normalized == "un":
            return "un" if short else ("unidade" if singular else "unidades")
        if normalized == "par":
            return "par" if singular else "pares"

        if normalized and is_packaging_unit_code(normalized):
            if item is not None and hasattr(item, "get_nome_embalagem"):
                try:
                    return item.get_nome_embalagem() if singular else item.get_nome_embalagem_plural()
                except Exception:
                    pass
            if singular or normalized.endswith("s"):
                return normalized
            return f"{normalized}s"

        cleaned = (unit or "").strip()
        return cleaned or None

    @staticmethod
    def _format_value_with_unit(
        value: float | None,
        unit: str | None,
        *,
        item: Item | None = None,
        short: bool = False,
    ) -> str | None:
        if value is None:
            return None
        unit_label = OperationVisualPayloadService._display_unit(unit, value=value, short=short, item=item)
        number = OperationVisualPayloadService._format_number(value)
        return f"{number} {unit_label}".strip() if unit_label else number

    @staticmethod
    def _resolve_withdrawal_balance_unit(
        item: Item | None,
        *,
        balance_unit: str | None = None,
        movement_unit: str | None = None,
    ) -> str | None:
        candidates = [balance_unit, movement_unit]
        if item is not None:
            try:
                candidates.append(resolve_canonical_unit(item))
            except Exception:
                pass
            candidates.append(item.unidade)

        for candidate in candidates:
            normalized = OperationVisualPayloadService._normalize_unit(candidate)
            if normalized and not is_packaging_unit_code(normalized):
                return normalized

        for candidate in candidates:
            normalized = OperationVisualPayloadService._normalize_unit(candidate)
            if normalized:
                return normalized
        return None

    @staticmethod
    def _get_current_balance(item: Item, unit_hint: str | None) -> float | None:
        try:
            normalized = OperationVisualPayloadService._normalize_unit(unit_hint)
            if normalized and not is_packaging_unit_code(normalized):
                return float(balance_provider.get_balance(item.codigo_item, item=item).quantity_base or 0.0)
        except Exception:
            pass
        try:
            return float(item.get_saldo_atual() or 0.0)
        except Exception:
            return None

    @staticmethod
    def _resolve_quantity_base(saida: Saida, movement: StockMovement | None) -> float | None:
        if movement is not None:
            try:
                return abs(float(movement.quantity_base or 0.0))
            except Exception:
                return None
        return None

    @staticmethod
    def _extract_saida_original_quantity(
        saida: Saida,
        movement: StockMovement | None,
    ) -> tuple[float | None, str | None]:
        metadata = movement.metadata_json if movement is not None and isinstance(movement.metadata_json, dict) else {}
        input_quantity = OperationVisualPayloadService._parse_float(metadata.get("input_quantity"))
        input_unit = OperationVisualPayloadService._normalize_unit(str(metadata.get("input_unit") or ""))
        if input_quantity is not None and input_unit:
            return abs(float(input_quantity)), input_unit

        retirada_litros = OperationVisualPayloadService._parse_float(getattr(saida, "quantidade_retirada_em_litros", None))
        if retirada_litros is not None and retirada_litros > 0:
            return retirada_litros, "l"

        retirada_quilos = OperationVisualPayloadService._parse_float(getattr(saida, "quantidade_retirada_em_quilos", None))
        if retirada_quilos is not None and retirada_quilos > 0:
            return retirada_quilos, "kg"

        observacao = str(getattr(saida, "observacao", "") or "")
        unidade_match = _UNIDADE_RE.search(observacao)
        qtd_match = _QTD_ORIGINAL_RE.search(observacao)
        if unidade_match and qtd_match:
            parsed_quantity = OperationVisualPayloadService._parse_float(qtd_match.group(1))
            parsed_unit = OperationVisualPayloadService._normalize_unit(unidade_match.group(1))
            if parsed_quantity is not None and parsed_unit:
                return parsed_quantity, parsed_unit

        fracionada_match = _FRACIONADA_RE.search(observacao.upper())
        if fracionada_match:
            parsed_quantity = OperationVisualPayloadService._parse_float(fracionada_match.group(1))
            parsed_unit = OperationVisualPayloadService._normalize_unit(fracionada_match.group(2))
            if parsed_quantity is not None and parsed_unit:
                return parsed_quantity, parsed_unit

        return None, None

    @staticmethod
    def _format_packaging_equivalent(
        value: float | None,
        item: Item,
        *,
        unit_hint: str | None,
        short: bool = False,
    ) -> str | None:
        if value is None:
            return None

        try:
            factor = float(resolve_packaging_factor(item) or 0.0)
        except Exception:
            factor = 0.0
        if factor <= 0:
            return None

        display_unit = OperationVisualPayloadService._normalize_unit(unit_hint)
        if not display_unit or is_packaging_unit_code(display_unit):
            return None

        total_value = abs(float(value))
        embalagens = int((total_value + 1e-9) // factor)
        if embalagens <= 0:
            return None

        resto = total_value - (embalagens * factor)
        if abs(resto) <= 1e-6:
            resto = 0.0

        nome_emb = OperationVisualPayloadService._display_unit(
            item.tipo_embalagem_novo or item.unidade,
            value=float(embalagens),
            item=item,
        )
        if not nome_emb:
            return None

        if resto > 0:
            resto_display = OperationVisualPayloadService._format_value_with_unit(
                resto,
                display_unit,
                item=item,
                short=short,
            )
            if resto_display:
                return f"{embalagens} {nome_emb} + {resto_display}"
        return f"{embalagens} {nome_emb}"

    @staticmethod
    def _actor_payload(user: Usuario | None, matricula: str | None) -> dict[str, Any]:
        return {
            "matricula": matricula,
            "nome": user.nome if user else None,
        }

    @staticmethod
    def _batch_label(saida: Saida, item: Item | None) -> str | None:
        lote = ((getattr(item, "lote", None) or "").strip() if item else "")
        if lote:
            return lote
        if bool(getattr(saida, "usou_fracao", False)):
            return "Fracionado"
        return None

    @staticmethod
    def _event_badge(event: InventarioEvento) -> str | None:
        tipo = (event.tipo or "").strip().lower()
        if tipo == "devolucao_ferramenta":
            return "Devolucao de ferramenta"
        if tipo == "devolucao_material":
            return "Devolucao de material"
        return (event.tipo or "").strip() or None

    @staticmethod
    def _format_balance(value: float | None, unit: str | None) -> str | None:
        if value is None:
            return None
        try:
            value_f = float(value)
        except Exception:
            return None
        if abs(value_f - round(value_f)) < 1e-9:
            formatted = str(int(round(value_f)))
        else:
            formatted = f"{value_f:.3f}".rstrip("0").rstrip(".")
        suffix = ((unit or "") or "").strip()
        return f"{formatted} {suffix}".strip()


operation_visual_payload_service = OperationVisualPayloadService()