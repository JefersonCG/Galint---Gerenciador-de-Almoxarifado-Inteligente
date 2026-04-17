from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import current_app, has_request_context, url_for

from ..models import InventarioEvento, Item, Saida, Usuario
from .material_return_metadata import extract_material_return_metadata, format_material_return_actor_label
from .network_settings import load_network_settings


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

        return {
            "kind": kind,
            "kind_label": OperationVisualPayloadService._kind_label(kind),
            "status": "completed",
            "item": {
                "codigo": saida.codigo_item,
                "descricao": item.descricao if item else (saida.codigo_item or "Item"),
                "categoria": item.categoria if item else None,
                "unidade": balance_unit or (item.unidade if item else None),
                "saldo": balance_after,
                "saldo_display": OperationVisualPayloadService._format_balance(balance_after, balance_unit or (item.unidade if item else None)),
                **photo,
            },
            "movement": {
                "id": saida.id_saida,
                "quantidade": saida.quantidade,
                "quantidade_display": OperationVisualPayloadService._format_balance(saida.quantidade, balance_unit or (item.unidade if item else None)),
                "balance_before": balance_before,
                "balance_after": balance_after,
                "balance_unit": balance_unit or (item.unidade if item else None),
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
                    "quantidade_display": OperationVisualPayloadService._format_balance(saida.quantidade, item.unidade),
                    **photo,
                }
            )
            if len(gallery) >= limit:
                break
        return gallery

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