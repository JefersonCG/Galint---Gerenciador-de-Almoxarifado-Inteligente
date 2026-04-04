from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import unicodedata

from sqlalchemy import and_, or_

from ..extensions import db
from ..models import Entrada, InventarioEvento, Item, Saida, Usuario
from ..utils.time_service import TimeService
from .inventory import MovimentoPayload, inventory_service
from .tool_custody_service import ToolCustodyService


class CentralKitsService:
    _CLOSE_EVENT_TYPES = (
        "devolucao_ferramenta",
        "devolucao_material",
        "quebra_ferramenta",
        "reparo_ferramenta",
    )
    _BAG_KEYWORDS = (
        "bolsa wonder",
        "bolsa",
        "maleta",
        "mochila",
        "case",
    )
    _EPI_KEYWORDS = (
        "epi",
        "oculos",
        "bota",
        "capacete",
        "protetor auricular",
        "protetor",
        "respirador",
        "masca",
        "calca",
        "avental",
        "cinto",
    )
    _EPI_GLOVE_HINTS = (
        "luva de",
        "luva anti",
        "luva emborrach",
        "luva latex",
        "luva eletricista",
        "luva prote",
        "luva pvc",
        "luva algod",
        "luva nitril",
        "luva vaqueta",
        "luva raspa",
    )
    _NON_EPI_GLOVE_CONTEXTS = (
        "material hidraul",
        "material eletr",
        "soldavel",
        "solda",
        "correr",
        "rosca",
    )
    _GROUP_HINTS = (
        ("Eletricistas", ("eletric", "eletro")),
        ("Manutenção Geral", ("manut", "hidraul", "bombeiro", "oficial")),
    )
    _ALLOWED_EMPLOYEE_HINTS = (
        "1/2 oficial",
        "meio oficial",
        "oficial de manut",
        "oficial de eletr",
        "eletricista",
        "bombeiro",
    )
    _FAMILY_ORDER = {
        "bolsa": 0,
        "ferramenta": 1,
        "epi": 2,
        "extra": 3,
    }
    _FAMILY_LABELS = {
        "bolsa": "Bolsa-chave",
        "ferramenta": "Ferramenta",
        "epi": "EPI",
        "extra": "Item complementar",
    }

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        return " ".join(ascii_text.lower().split())

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _format_quantity(cls, value: Any) -> str:
        parsed = cls._to_float(value)
        if abs(parsed - int(parsed)) < 1e-9:
            return str(int(parsed))
        return f"{parsed:.2f}".rstrip("0").rstrip(".").replace(".", ",")

    @classmethod
    def _item_text(cls, item: Item | None) -> str:
        if item is None:
            return ""
        return cls._normalize_text(
            " ".join(
                [
                    item.categoria or "",
                    item.descricao or "",
                    item.marca or "",
                ]
            )
        )

    @classmethod
    def _is_bag_item(cls, item: Item | None) -> bool:
        text = cls._item_text(item)
        return any(keyword in text for keyword in cls._BAG_KEYWORDS)

    @classmethod
    def _is_tool_item(cls, item: Item | None) -> bool:
        text = cls._item_text(item)
        return "ferrament" in text

    @classmethod
    def _is_epi_item(cls, item: Item | None) -> bool:
        text = cls._item_text(item)
        if not text:
            return False
        if "epi" in text or ("material" in text and " ep" in f" {text}"):
            return True
        if any(keyword in text for keyword in cls._EPI_KEYWORDS):
            return True
        if "luva" not in text:
            return False
        if any(keyword in text for keyword in cls._NON_EPI_GLOVE_CONTEXTS):
            return False
        return any(keyword in text for keyword in cls._EPI_GLOVE_HINTS)

    @classmethod
    def _is_eligible_item(cls, item: Item | None) -> bool:
        return cls._is_bag_item(item) or cls._is_tool_item(item) or cls._is_epi_item(item)

    @classmethod
    def _resolve_family(cls, item: Item | None) -> str:
        if cls._is_bag_item(item):
            return "bolsa"
        if cls._is_tool_item(item):
            return "ferramenta"
        if cls._is_epi_item(item):
            return "epi"
        return "extra"

    @classmethod
    def _resolve_unit_value(cls, item: Item | None) -> float:
        if item is None:
            return 0.0

        for candidate in (
            item.preco_reposicao_unitario_base,
            item.preco_reposicao_unitario,
            item.preco_compra_unitario_base,
            item.preco_compra_unitario,
        ):
            parsed = cls._to_float(candidate)
            if parsed > 0:
                return round(parsed, 2)
        return 0.0

    @classmethod
    def _resolve_group(cls, usuario: Usuario, items: list[dict[str, Any]]) -> str:
        persona = cls._normalize_text(" ".join([usuario.cargo or "", usuario.setor or ""]))
        for label, hints in cls._GROUP_HINTS:
            if any(hint in persona for hint in hints):
                return label

        item_text = " ".join(cls._normalize_text(item.get("descricao")) for item in items)
        if "eletric" in item_text:
            return "Eletricistas"
        if any(hint in item_text for hint in ("hidraul", "bomba", "manut")):
            return "Manutenção Geral"
        return "Operacional"

    @classmethod
    def _is_allowed_employee_for_kits(cls, usuario: Usuario | None) -> bool:
        if usuario is None:
            return False

        persona = cls._normalize_text(" ".join([usuario.cargo or "", usuario.setor or ""]))
        if not persona:
            return False

        return any(hint in persona for hint in cls._ALLOWED_EMPLOYEE_HINTS)

    @classmethod
    def _find_close_event(cls, matricula: str | None, codigo_item: str | None, data_base: datetime | None) -> dict[str, Any] | None:
        if not matricula or not codigo_item or data_base is None:
            return None

        evento = (
            db.session.query(InventarioEvento)
            .filter(
                InventarioEvento.matricula == matricula,
                InventarioEvento.codigo_item == codigo_item,
                InventarioEvento.tipo.in_(cls._CLOSE_EVENT_TYPES),
                InventarioEvento.data_evento >= data_base,
            )
            .order_by(InventarioEvento.data_evento.desc())
            .first()
        )
        if evento is not None:
            return {
                "tipo": evento.tipo,
                "data": evento.data_evento,
                "descricao": evento.descricao or "",
            }

        entrada = (
            db.session.query(Entrada)
            .filter(
                Entrada.codigo_item == codigo_item,
                Entrada.matricula == matricula,
                Entrada.nota_fiscal.is_(None),
                Entrada.data_entrada >= data_base,
            )
            .order_by(Entrada.data_entrada.desc())
            .first()
        )
        if entrada is not None:
            return {
                "tipo": "devolucao_material",
                "data": entrada.data_entrada,
                "descricao": "Devolução conciliada por entrada interna.",
            }

        return None

    @classmethod
    def _build_item_payload(cls, saida: Saida, item: Item) -> dict[str, Any]:
        family = cls._resolve_family(item)
        quantity = cls._to_float(saida.quantidade)
        unit_value = cls._resolve_unit_value(item)
        total_value = round(quantity * unit_value, 2)
        days_in_use = max(0, (datetime.utcnow() - saida.data_saida).days) if saida.data_saida else 0
        tipo_custodia = (
            "permanente"
            if ToolCustodyService.is_permanent_custody(
                tipo_custodia_raw=saida.tipo_custodia,
                local_servico=saida.local_servico,
                observacao=saida.observacao,
                days_in_use=days_in_use,
            )
            else "temporaria"
        )
        is_alert = tipo_custodia == "temporaria" and days_in_use > 30

        return {
            "saida_id": saida.id_saida,
            "codigo_item": item.codigo_item,
            "descricao": item.descricao,
            "categoria": item.categoria or "Sem categoria",
            "marca": item.marca or "N/D",
            "quantidade": quantity,
            "quantidade_display": cls._format_quantity(quantity),
            "family": family,
            "family_label": cls._FAMILY_LABELS[family],
            "valor_unitario": unit_value,
            "valor_total": total_value,
            "tipo_custodia": tipo_custodia,
            "tipo_custodia_label": "Permanente" if tipo_custodia == "permanente" else "Diária",
            "data_saida": saida.data_saida,
            "data_saida_formatada": TimeService.format_local(saida.data_saida, "%d/%m/%Y %H:%M") if saida.data_saida else "",
            "local_servico": saida.local_servico or "Não informado",
            "observacao": saida.observacao or "",
            "days_in_use": days_in_use,
            "is_alert": is_alert,
            "status_label": "Atenção" if is_alert else "Em posse",
            "foto_path": item.foto_path,
        }

    @classmethod
    def _build_available_tool_payload(cls, item: Item) -> dict[str, Any]:
        try:
            saldo_disponivel = cls._to_float(item.get_saldo_atual())
        except Exception:
            saldo_disponivel = 0.0

        unidade = (item.unidade or "un").strip() or "un"
        family = cls._resolve_family(item)
        return {
            "codigo": item.codigo_item,
            "descricao": item.descricao or item.codigo_item,
            "categoria": item.categoria or "Ferramentas",
            "marca": item.marca or "N/D",
            "family": family,
            "family_label": cls._FAMILY_LABELS.get(family, "Item"),
            "saldo_disponivel": saldo_disponivel,
            "saldo_disponivel_display": f"{cls._format_quantity(saldo_disponivel)} {unidade}",
            "unidade": unidade,
            "foto_path": item.foto_path,
        }

    @classmethod
    def _is_assignment_stock_item(cls, item: Item | None) -> bool:
        return cls._is_tool_item(item) or cls._is_epi_item(item)

    @classmethod
    def _get_assignment_responsibility_tools(cls, matricula: str, kit: dict[str, Any]) -> list[dict[str, Any]]:
        merged_rows: dict[str, dict[str, Any]] = {}

        custody_payload = ToolCustodyService.get_employee_details(matricula) or {}
        source_rows = [
            *(kit.get("tools", []) or []),
            *(kit.get("epis", []) or []),
            *(kit.get("extras", []) or []),
            *(custody_payload.get("active_tools", []) or []),
        ]

        for row in source_rows:
            saida_id = row.get("saida_id")
            codigo = row.get("codigo_item") or row.get("codigo") or ""
            fallback_ref = row.get("data_saida_formatada") or row.get("local_servico") or row.get("descricao") or codigo
            entry_key = f"saida:{saida_id}" if saida_id is not None else f"tool:{codigo}:{fallback_ref}"

            merged = merged_rows.setdefault(entry_key, {})
            for field, value in row.items():
                if value is None:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                if isinstance(value, (list, dict)) and not value:
                    continue
                merged[field] = value

        responsibility_tools = list(merged_rows.values())
        responsibility_tools.sort(
            key=lambda row: (
                row.get("data_saida") or datetime.min,
                str(row.get("descricao") or ""),
                str(row.get("codigo_item") or row.get("codigo") or ""),
            ),
            reverse=True,
        )
        return responsibility_tools

    @classmethod
    def _load_active_items_for_employee(cls, matricula: str) -> list[dict[str, Any]]:
        saidas = (
            db.session.query(Saida, Item)
            .join(Item, Saida.codigo_item == Item.codigo_item)
            .filter(Saida.matricula == matricula)
            .order_by(Saida.data_saida.desc(), Saida.id_saida.desc())
            .all()
        )

        active_items: list[dict[str, Any]] = []
        for saida, item in saidas:
            if not cls._is_eligible_item(item):
                continue
            if cls._find_close_event(saida.matricula, saida.codigo_item, saida.data_saida):
                continue
            active_items.append(cls._build_item_payload(saida, item))

        return sorted(
            active_items,
            key=lambda row: (
                cls._FAMILY_ORDER.get(str(row.get("family") or "extra"), 99),
                -(cls._to_float(row.get("valor_total"))),
                str(row.get("descricao") or ""),
            ),
        )

    @classmethod
    def _load_recent_occurrences(cls, matricula: str, *, days: int = 60) -> list[dict[str, Any]]:
        cutoff = datetime.utcnow() - timedelta(days=days)
        rows = (
            db.session.query(InventarioEvento, Item)
            .join(Item, InventarioEvento.codigo_item == Item.codigo_item)
            .filter(
                InventarioEvento.matricula == matricula,
                InventarioEvento.tipo.in_(cls._CLOSE_EVENT_TYPES),
                InventarioEvento.data_evento >= cutoff,
            )
            .order_by(InventarioEvento.data_evento.desc())
            .all()
        )

        type_map = {
            "devolucao_ferramenta": ("Devolução", "success"),
            "devolucao_material": ("Devolução", "success"),
            "quebra_ferramenta": ("Quebra / perda", "warning"),
            "reparo_ferramenta": ("Reparo", "info"),
        }

        occurrences: list[dict[str, Any]] = []
        for evento, item in rows:
            if not cls._is_eligible_item(item):
                continue
            title, tone = type_map.get(evento.tipo, ("Movimento", "secondary"))
            family = cls._resolve_family(item)
            occurrences.append(
                {
                    "title": title,
                    "tone": tone,
                    "descricao": item.descricao,
                    "categoria": item.categoria or "Sem categoria",
                    "family": family,
                    "family_label": cls._FAMILY_LABELS.get(family, "Item"),
                    "data": evento.data_evento,
                    "data_formatada": TimeService.format_local(evento.data_evento, "%d/%m/%Y %H:%M") if evento.data_evento else "",
                    "observacao": evento.descricao or "",
                }
            )
        return occurrences

    @classmethod
    def _build_kit_payload(
        cls,
        usuario: Usuario,
        active_items: list[dict[str, Any]],
        occurrences: list[dict[str, Any]],
    ) -> dict[str, Any]:
        bolsa_chave = next((item for item in active_items if item.get("family") == "bolsa"), None)
        total_quantity = sum(cls._to_float(item.get("quantidade")) for item in active_items)
        total_value = round(sum(cls._to_float(item.get("valor_total")) for item in active_items), 2)
        permanent_count = sum(1 for item in active_items if item.get("tipo_custodia") == "permanente")
        temporary_count = sum(1 for item in active_items if item.get("tipo_custodia") != "permanente")
        overdue_count = sum(1 for item in active_items if bool(item.get("is_alert")))
        damage_count = sum(1 for item in occurrences if item.get("title") == "Quebra / perda")
        repair_count = sum(1 for item in occurrences if item.get("title") == "Reparo")
        return_count = sum(1 for item in occurrences if item.get("title") == "Devolução")

        family_summary: dict[str, dict[str, Any]] = {}
        for family in cls._FAMILY_LABELS:
            family_items = [item for item in active_items if item.get("family") == family]
            family_summary[family] = {
                "label": cls._FAMILY_LABELS[family],
                "entries": len(family_items),
                "quantity": sum(cls._to_float(item.get("quantidade")) for item in family_items),
                "quantity_display": cls._format_quantity(
                    sum(cls._to_float(item.get("quantidade")) for item in family_items)
                ),
                "value": round(sum(cls._to_float(item.get("valor_total")) for item in family_items), 2),
            }

        group_label = cls._resolve_group(usuario, active_items)
        status_label = "Em operação"
        status_tone = "success"
        if overdue_count > 0:
            status_label = "Pendências abertas"
            status_tone = "warning"
        elif bolsa_chave is None:
            status_label = "Sem bolsa-chave"
            status_tone = "secondary"

        latest_movement = None
        candidate_dates = [item.get("data_saida") for item in active_items if item.get("data_saida") is not None]
        candidate_dates.extend(item.get("data") for item in occurrences if item.get("data") is not None)
        if candidate_dates:
            latest_movement = max(candidate_dates)

        return {
            "matricula": usuario.matricula,
            "nome": usuario.nome,
            "setor": usuario.setor or "N/D",
            "cargo": usuario.cargo or "N/D",
            "group": group_label,
            "bolsa_chave": bolsa_chave,
            "has_bolsa_chave": bolsa_chave is not None,
            "status_label": status_label,
            "status_tone": status_tone,
            "active_items": active_items,
            "occurrences": occurrences,
            "family_summary": family_summary,
            "total_entries": len(active_items),
            "total_quantity": total_quantity,
            "total_quantity_display": cls._format_quantity(total_quantity),
            "total_value": total_value,
            "permanent_count": permanent_count,
            "temporary_count": temporary_count,
            "overdue_count": overdue_count,
            "damage_count": damage_count,
            "repair_count": repair_count,
            "return_count": return_count,
            "critical_occurrences": damage_count + repair_count,
            "last_movement": latest_movement,
            "last_movement_label": TimeService.format_local(latest_movement, "%d/%m/%Y %H:%M") if latest_movement else "Sem histórico recente",
        }

    @classmethod
    def _load_candidate_users(cls) -> list[Usuario]:
        users = (
            db.session.query(Usuario)
            .join(Saida, Usuario.matricula == Saida.matricula)
            .join(Item, Saida.codigo_item == Item.codigo_item)
            .filter(
                or_(
                    Item.categoria.ilike("%ferrament%"),
                    Item.categoria.ilike("%epi%"),
                    and_(Item.categoria.ilike("%material%"), Item.categoria.ilike("%ep%")),
                    Item.descricao.ilike("%bolsa%"),
                    Item.descricao.ilike("%wonder%"),
                )
            )
            .distinct()
            .order_by(Usuario.nome.asc())
            .all()
        )
        return [usuario for usuario in users if cls._is_allowed_employee_for_kits(usuario)]

    @classmethod
    def get_dashboard(cls, *, search: str = "", group_filter: str = "todos", custody_filter: str = "todos", alert_only: bool = False) -> dict[str, Any]:
        all_kits: list[dict[str, Any]] = []
        for usuario in cls._load_candidate_users():
            active_items = cls._load_active_items_for_employee(usuario.matricula)
            if not active_items:
                continue
            occurrences = cls._load_recent_occurrences(usuario.matricula, days=30)
            all_kits.append(cls._build_kit_payload(usuario, active_items, occurrences))

        groups = sorted({kit["group"] for kit in all_kits})

        filtered_kits = all_kits
        search_text = cls._normalize_text(search)
        if search_text:
            filtered_kits = [
                kit
                for kit in filtered_kits
                if search_text in cls._normalize_text(kit.get("nome"))
                or search_text in cls._normalize_text(kit.get("matricula"))
                or search_text in cls._normalize_text((kit.get("bolsa_chave") or {}).get("descricao"))
            ]

        if group_filter and group_filter != "todos":
            filtered_kits = [kit for kit in filtered_kits if kit.get("group") == group_filter]

        if custody_filter == "permanente":
            filtered_kits = [kit for kit in filtered_kits if kit.get("permanent_count", 0) > 0]
        elif custody_filter == "diaria":
            filtered_kits = [kit for kit in filtered_kits if kit.get("temporary_count", 0) > 0]

        if alert_only:
            filtered_kits = [
                kit for kit in filtered_kits if kit.get("overdue_count", 0) > 0 or not kit.get("has_bolsa_chave", False)
            ]

        stats = {
            "total_kits": len(filtered_kits),
            "total_items": cls._format_quantity(sum(kit.get("total_quantity", 0.0) for kit in filtered_kits)),
            "total_value": round(sum(cls._to_float(kit.get("total_value")) for kit in filtered_kits), 2),
            "bags_ready": sum(1 for kit in filtered_kits if kit.get("has_bolsa_chave")),
            "total_alerts": sum(int(kit.get("overdue_count", 0)) for kit in filtered_kits),
            "critical_occurrences": sum(int(kit.get("critical_occurrences", 0)) for kit in filtered_kits),
            "all_total_kits": len(all_kits),
        }

        return {
            "kits": filtered_kits,
            "stats": stats,
            "groups": groups,
        }

    @classmethod
    def get_kit_detail(cls, matricula: str) -> dict[str, Any] | None:
        usuario = Usuario.query.get(matricula)
        if usuario is None:
            return None
        if not cls._is_allowed_employee_for_kits(usuario):
            return None

        active_items = cls._load_active_items_for_employee(matricula)
        occurrences = cls._load_recent_occurrences(matricula, days=90)
        if not active_items and not occurrences:
            return None

        payload = cls._build_kit_payload(usuario, active_items, occurrences)
        payload.update(
            {
                "initials": ToolCustodyService._build_employee_initials(usuario.nome),
                "photo_path": ToolCustodyService.get_employee_photo_path(usuario.matricula),
                "tools": [item for item in active_items if item.get("family") == "ferramenta"],
                "epis": [item for item in active_items if item.get("family") == "epi"],
                "extras": [item for item in active_items if item.get("family") == "extra"],
                "bags": [item for item in active_items if item.get("family") == "bolsa"],
                "timeline": occurrences[:12],
                "custody_url": "/controle-ferramentas/funcionario/" + usuario.matricula,
                "pdf_url": f"/controle-ferramentas/api/funcionario/{usuario.matricula}/relatorio.pdf?aba=all",
            }
        )
        return payload

    @classmethod
    def get_assignment_modal_payload(cls, matricula: str, *, search: str = "") -> dict[str, Any] | None:
        kit = cls.get_kit_detail(matricula)
        if kit is None:
            return None

        responsibility_tools = cls._get_assignment_responsibility_tools(matricula, kit)

        search_text = cls._normalize_text(search)
        epi_query_hints = (*cls._EPI_KEYWORDS, *cls._EPI_GLOVE_HINTS)
        epi_description_filters = [Item.descricao.ilike(f"%{keyword}%") for keyword in epi_query_hints if len(keyword) >= 3]
        query = db.session.query(Item).filter(
            or_(
                Item.categoria.ilike("%ferrament%"),
                Item.categoria.ilike("%epi%"),
                and_(Item.categoria.ilike("%material%"), Item.categoria.ilike("%ep%")),
                *epi_description_filters,
            )
        )
        if search_text:
            query = query.filter(
                or_(
                    Item.codigo_item.ilike(f"%{search}%"),
                    Item.descricao.ilike(f"%{search}%"),
                    Item.marca.ilike(f"%{search}%"),
                )
            )

        available_tools: list[dict[str, Any]] = []
        for item in query.order_by(Item.descricao.asc()).limit(500).all():
            if not cls._is_assignment_stock_item(item):
                continue
            payload = cls._build_available_tool_payload(item)
            if cls._to_float(payload.get("saldo_disponivel")) <= 0:
                continue
            available_tools.append(payload)

        assigned_tools = [
            {
                "entry_id": f"saida:{tool.get('saida_id')}" if tool.get("saida_id") is not None else f"tool:{tool.get('codigo_item') or tool.get('codigo')}",
                "saida_id": tool.get("saida_id"),
                "codigo": tool.get("codigo_item") or tool.get("codigo"),
                "descricao": tool.get("descricao"),
                "categoria": tool.get("categoria"),
                "marca": tool.get("marca"),
                "family": tool.get("family") or "ferramenta",
                "family_label": tool.get("family_label") or "Ferramenta",
                "quantidade": cls._to_float(tool.get("quantidade")),
                "quantidade_display": tool.get("quantidade_display") or cls._format_quantity(tool.get("quantidade")),
                "tipo_custodia": tool.get("tipo_custodia"),
                "tipo_custodia_label": tool.get("tipo_custodia_label") or ("Permanente" if str(tool.get("tipo_custodia") or "").strip().lower() == "permanente" else "Temporária"),
                "local_servico": tool.get("local_servico"),
                "foto_path": tool.get("foto_path"),
                "status_label": tool.get("status_label") or ("Atenção" if bool(tool.get("is_alert")) else "Em posse"),
            }
            for tool in responsibility_tools
        ]

        return {
            "employee": {
                "matricula": kit.get("matricula"),
                "nome": kit.get("nome"),
                "cargo": kit.get("cargo"),
                "setor": kit.get("setor"),
            },
            "available_tools": available_tools,
            "assigned_tools": assigned_tools,
            "search": search,
        }

    @classmethod
    def apply_assignment_changes(
        cls,
        matricula: str,
        *,
        additions: list[dict[str, Any]] | None = None,
        removals: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        kit = cls.get_kit_detail(matricula)
        if kit is None:
            raise ValueError("Kit não encontrado para este colaborador")

        additions = additions or []
        removals = removals or []

        responsibility_tools = cls._get_assignment_responsibility_tools(matricula, kit)

        existing_tools_by_saida_id = {
            int(tool.get("saida_id")): tool
            for tool in responsibility_tools
            if tool.get("saida_id") is not None
        }

        removal_results: list[dict[str, Any]] = []
        addition_results: list[dict[str, Any]] = []
        errors: list[str] = []

        for raw_row in removals:
            try:
                saida_id = int((raw_row or {}).get("saida_id"))
            except (TypeError, ValueError):
                continue

            tool_row = existing_tools_by_saida_id.get(saida_id)
            if tool_row is None:
                errors.append(f"Item ativo {saida_id} não pertence mais a este colaborador.")
                continue

            try:
                codigo_item = str(tool_row.get("codigo_item") or tool_row.get("codigo") or "").strip()
                item = Item.query.get(codigo_item)
                if item is None:
                    raise ValueError(f"Item {codigo_item or saida_id} não encontrado.")

                if cls._is_tool_item(item):
                    ToolCustodyService.register_return(saida_id, "Reorganização via Central de Kits")
                else:
                    inventory_service.registrar_devolucao_material(
                        codigo=item.codigo_item,
                        quantidade=cls._to_float(tool_row.get("quantidade")) or 1.0,
                        matricula=matricula,
                        observacao="Reorganização via Central de Kits",
                    )
                removal_results.append({"saida_id": saida_id, "codigo": codigo_item})
            except ValueError as exc:
                errors.append(str(exc))

        grouped_additions: dict[str, int] = {}
        for raw_row in additions:
            codigo = str((raw_row or {}).get("codigo") or "").strip()
            try:
                quantidade = int((raw_row or {}).get("quantidade") or 0)
            except (TypeError, ValueError):
                quantidade = 0

            if not codigo or quantidade <= 0:
                continue
            grouped_additions[codigo] = grouped_additions.get(codigo, 0) + quantidade

        for codigo, quantidade in grouped_additions.items():
            item = Item.query.get(codigo)
            if item is None:
                errors.append(f"Item {codigo} não encontrado.")
                continue

            if not cls._is_assignment_stock_item(item):
                errors.append(f"Item {codigo} não é elegível para a Central de Kits.")
                continue

            try:
                inventory_service.registrar_saida(
                    MovimentoPayload(
                        codigo=codigo,
                        quantidade=float(quantidade),
                        matricula=matricula,
                        observacao="Associado via Central de Kits",
                        local_servico="Central de Kits",
                        tipo_custodia="permanente",
                    ),
                    skip_notification=True,
                )
                addition_results.append({"codigo": codigo, "quantidade": quantidade})
            except ValueError as exc:
                errors.append(str(exc))

        return {
            "removed": removal_results,
            "added": addition_results,
            "errors": errors,
            "applied_changes": len(removal_results) + len(addition_results),
        }


central_kits_service = CentralKitsService()