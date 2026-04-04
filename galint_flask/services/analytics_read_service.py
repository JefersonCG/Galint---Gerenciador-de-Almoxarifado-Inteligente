from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from time import monotonic
from typing import Any
from unicodedata import normalize as unicode_normalize

from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import Entrada, Item, Saida, Usuario
from .finance_service import FinanceService
from .inventory import OPERATIONAL_ACTIVITY_LABELS, inventory_service, normalize_operational_activity


class AnalyticsReadService:
    _runtime_cache: dict[str, tuple[float, Any]] = {}
    _PERIOD_PRESET_OPTIONS: tuple[dict[str, str], ...] = (
        {"value": "today", "label": "Hoje"},
        {"value": "last_7_days", "label": "7 dias"},
        {"value": "last_30_days", "label": "30 dias"},
        {"value": "current_month", "label": "Mes atual"},
    )
    _PERIOD_PRESET_LABELS = {
        row["value"]: row["label"]
        for row in _PERIOD_PRESET_OPTIONS
    }

    _ACTIVITY_RULES: tuple[dict[str, Any], ...] = (
        {
            "key": "central_kits",
            "label": "Central de Kits",
            "keywords": ("CENTRAL DE KITS", "ASSOCIADO VIA CENTRAL DE KITS"),
        },
        {
            "key": "piscina",
            "label": "Piscina e espelho d'agua",
            "keywords": ("PISCINA", "LAGUINHO", "CASA DE MAQUINA", "CASA DE MAQUINA", "FILTRO", "CASA DE BOMBA"),
        },
        {
            "key": "hidraulica",
            "label": "Manutencao hidraulica",
            "keywords": ("HIDRAUL", "VAZAMENTO", "REGISTRO", "TUBO", "ESGOTO", "CAIXA DAGUA", "BOMBA", "SOLDAVEL", "ROSCA"),
        },
        {
            "key": "eletrica",
            "label": "Manutencao eletrica",
            "keywords": ("ELETR", "LAMPADA", "LUMINARIA", "DISJUNTOR", "FIA", "FIACAO", "CABO", "ILUMINACAO"),
        },
        {
            "key": "pintura_acabamento",
            "label": "Pintura e acabamento",
            "keywords": ("PINTURA", "DRYWALL", "MASSA", "PAREDE", "TETO", "ACABAMENTO"),
        },
        {
            "key": "jardins",
            "label": "Jardins e paisagismo",
            "keywords": ("JARDIM", "PAISAG", "GRAMA", "PODA"),
        },
        {
            "key": "areas_comuns",
            "label": "Areas comuns e apoio",
            "keywords": ("AREAS COMUNS", "AREA COMUM", "REFEITORIO", "CHURRASQUEIRA", "BANHEIRO", "GUARITA", "HALL", "COPA", "SALA"),
        },
        {
            "key": "blocos_apartamentos",
            "label": "Blocos e apartamentos",
            "keywords": ("BLOCO", "APARTAMENTO", "APTO", "TORRE", "UNIDADE"),
        },
        {
            "key": "limpeza",
            "label": "Limpeza operacional",
            "keywords": ("LIMPEZA", "PANO", "VASSOURA", "RODO", "MOP", "DETERGENTE", "DESINFETANTE", "SABAO"),
        },
    )

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
    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _normalize_spaces(value: str | None) -> str:
        return " ".join(str(value or "").strip().split())

    @classmethod
    def _fold_text(cls, value: str | None) -> str:
        normalized = cls._normalize_spaces(value).upper()
        return unicode_normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")

    @classmethod
    def _normalize_search(cls, value: str | None) -> str:
        return cls._fold_text(value).lower()

    @classmethod
    def _normalize_local(cls, value: str | None) -> str:
        normalized = cls._fold_text(value)
        return normalized or "SEM LOCAL"

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return None

    @classmethod
    def _normalize_period_preset(cls, value: str | None) -> str | None:
        raw = cls._normalize_spaces(value).lower()
        aliases = {
            "hoje": "today",
            "today": "today",
            "7d": "last_7_days",
            "7_dias": "last_7_days",
            "7 dias": "last_7_days",
            "last_7_days": "last_7_days",
            "30d": "last_30_days",
            "30_dias": "last_30_days",
            "30 dias": "last_30_days",
            "last_30_days": "last_30_days",
            "mes_atual": "current_month",
            "mes atual": "current_month",
            "current_month": "current_month",
        }
        return aliases.get(raw)

    @classmethod
    def _resolve_period_preset(cls, preset_value: str | None) -> dict[str, Any] | None:
        normalized = cls._normalize_period_preset(preset_value)
        if not normalized:
            return None
        today = datetime.utcnow().date()
        if normalized == "today":
            start_date = today
            end_date = today
        elif normalized == "last_7_days":
            start_date = today.fromordinal(today.toordinal() - 6)
            end_date = today
        elif normalized == "last_30_days":
            start_date = today.fromordinal(today.toordinal() - 29)
            end_date = today
        elif normalized == "current_month":
            start_date = today.replace(day=1)
            end_date = today
        else:
            return None
        return {
            "value": normalized,
            "label": cls._PERIOD_PRESET_LABELS.get(normalized) or "Periodo rapido",
            "start_date": start_date,
            "end_date": end_date,
        }

    @classmethod
    def resolve_period(
        cls,
        *,
        exercise_label: str | None = None,
        period_preset: str | None = None,
        start_date_value: str | None = None,
        end_date_value: str | None = None,
    ) -> dict[str, Any]:
        parsed_start = cls._parse_date(start_date_value)
        parsed_end = cls._parse_date(end_date_value)
        preset = cls._resolve_period_preset(period_preset)
        reference_date = parsed_start or parsed_end or (preset.get("end_date") if preset else None)

        if exercise_label:
            base_exercise = FinanceService.resolve_exercise(exercise_label)
        elif reference_date:
            base_exercise = FinanceService.get_exercise_for_date(reference_date)
        else:
            base_exercise = FinanceService.get_exercise_for_date()

        if parsed_start or parsed_end:
            start_date = parsed_start or base_exercise["start_date"]
            end_date = parsed_end or base_exercise["end_date"]
            if end_date < start_date:
                start_date, end_date = end_date, start_date
            label = f"{start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}"
            mode = "custom"
            selected_period_preset = ""
        elif preset:
            start_date = preset["start_date"]
            end_date = preset["end_date"]
            label = preset["label"]
            mode = "preset"
            selected_period_preset = str(preset["value"])
        else:
            start_date = base_exercise["start_date"]
            end_date = base_exercise["end_date"]
            label = base_exercise["label"]
            mode = "exercise"
            selected_period_preset = ""

        return {
            "label": label,
            "mode": mode,
            "exercise_label": base_exercise.get("label") or "Atual",
            "start_date": start_date,
            "end_date": end_date,
            "start_dt": datetime.combine(start_date, time.min),
            "end_dt": datetime.combine(end_date, time.max),
            "start_date_label": start_date.strftime("%d/%m/%Y"),
            "end_date_label": end_date.strftime("%d/%m/%Y"),
            "selected_start_date": start_date.isoformat() if mode in {"custom", "preset"} else str(start_date_value or "").strip(),
            "selected_end_date": end_date.isoformat() if mode in {"custom", "preset"} else str(end_date_value or "").strip(),
            "selected_period_preset": selected_period_preset,
        }

    @classmethod
    def get_filter_options(cls) -> dict[str, Any]:
        cached = cls._get_cached("analytics:filter_options")
        if cached is not None:
            return dict(cached)

        location_rows = db.session.query(Saida.local_servico).distinct().all()
        locations = [
            {"local": local}
            for local in sorted({cls._normalize_local(row[0]) for row in location_rows if cls._normalize_local(row[0]) != "SEM LOCAL"})
        ]

        category_rows = (
            db.session.query(Item.categoria)
            .join(Saida, Saida.codigo_item == Item.codigo_item)
            .distinct()
            .order_by(Item.categoria.asc())
            .all()
        )
        categories = [
            {"categoria": cls._normalize_spaces(row[0])}
            for row in category_rows
            if cls._normalize_spaces(row[0])
        ]

        employee_rows = (
            db.session.query(Usuario.matricula, Usuario.nome)
            .join(Saida, Saida.matricula == Usuario.matricula)
            .distinct()
            .order_by(Usuario.nome.asc(), Usuario.matricula.asc())
            .all()
        )
        employees = [
            {
                "matricula": str(row[0] or "").strip(),
                "nome": cls._normalize_spaces(row[1]) or str(row[0] or "").strip(),
            }
            for row in employee_rows
            if str(row[0] or "").strip()
        ]

        payload = {
            "exercise_options": FinanceService.get_available_exercises(),
            "period_preset_options": list(cls._PERIOD_PRESET_OPTIONS),
            "locations": locations,
            "categories": categories,
            "employees": employees,
            "sort_options": [
                {"value": "data", "label": "Data"},
                {"value": "colaborador", "label": "Colaborador"},
                {"value": "item", "label": "Item"},
                {"value": "categoria", "label": "Categoria"},
                {"value": "local", "label": "Local"},
                {"value": "atividade", "label": "Atividade derivada"},
                {"value": "quantidade", "label": "Quantidade"},
                {"value": "valor", "label": "Valor"},
                {"value": "tipo", "label": "Tipo"},
            ],
            "per_page_options": [25, 50, 100],
        }
        return cls._set_cached("analytics:filter_options", dict(payload), ttl_seconds=180.0)

    @classmethod
    def _resolve_unit_price(cls, item: Item | None) -> float:
        if item is None:
            return 0.0
        for field_name in ("preco_compra_unitario_base", "preco_reposicao_unitario_base", "preco_compra_unitario", "preco_reposicao_unitario"):
            value = cls._safe_float(getattr(item, field_name, 0.0))
            if value > 0:
                return value
        return 0.0

    @classmethod
    def _resolve_quantity_base(cls, saida: Saida) -> tuple[float, float, float]:
        retirada_l = abs(cls._safe_float(getattr(saida, "quantidade_retirada_em_litros", 0.0)))
        retirada_kg = abs(cls._safe_float(getattr(saida, "quantidade_retirada_em_quilos", 0.0)))
        if retirada_l > 0:
            return retirada_l, retirada_l, 0.0
        if retirada_kg > 0:
            return retirada_kg, 0.0, retirada_kg
        quantidade = abs(cls._safe_float(getattr(saida, "quantidade", 0.0)))
        return quantidade, 0.0, 0.0

    @classmethod
    def _resolve_unit_base(cls, saida: Saida, item: Item | None, *, retirada_l: float, retirada_kg: float) -> str:
        if retirada_l > 0:
            return "L"
        if retirada_kg > 0:
            return "Kg"
        raw_unit = cls._normalize_spaces(getattr(item, "unidade", None) if item is not None else None)
        return raw_unit or "un"

    @classmethod
    def _format_quantity_display(cls, row: dict[str, Any]) -> str:
        litros = cls._safe_float(row.get("quantidade_litros"))
        if litros > 0:
            return f"{litros:g} L"
        quilos = cls._safe_float(row.get("quantidade_quilos"))
        if quilos > 0:
            return f"{quilos:g} Kg"
        quantidade = cls._safe_float(row.get("quantidade_base"))
        unit_base = cls._normalize_spaces(row.get("unit_base")) or "un"
        return f"{quantidade:g} {unit_base}"

    @classmethod
    def _derive_activity(cls, *, local: str, observacao: str) -> dict[str, str]:
        combined = " | ".join(part for part in (local, observacao) if part)
        folded = cls._fold_text(combined)
        for rule in cls._ACTIVITY_RULES:
            for keyword in rule["keywords"]:
                if keyword in folded:
                    return {
                        "key": str(rule["key"]),
                        "label": str(rule["label"]),
                        "confidence": "alta",
                    }

        if local and local != "SEM LOCAL":
            return {
                "key": "uso_direto",
                "label": "Uso operacional direto",
                "confidence": "media",
            }

        return {
            "key": "nao_classificado",
            "label": "Nao classificado",
            "confidence": "baixa",
        }

    @classmethod
    def _resolve_structured_activity(cls, saida: Saida) -> dict[str, str] | None:
        activity_key = normalize_operational_activity(getattr(saida, "atividade_operacional", None))
        if not activity_key:
            return None
        return {
            "key": activity_key,
            "label": OPERATIONAL_ACTIVITY_LABELS.get(activity_key) or "Atividade estruturada",
            "confidence": "estruturada",
            "source": "structured",
        }

    @classmethod
    def _build_exit_row(cls, saida: Saida) -> dict[str, Any] | None:
        quantidade_base, retirada_l, retirada_kg = cls._resolve_quantity_base(saida)
        if quantidade_base <= 0:
            return None

        item = getattr(saida, "item", None)
        usuario = getattr(saida, "usuario", None)
        local = cls._normalize_local(getattr(saida, "local_servico", None))
        observacao = cls._normalize_spaces(getattr(saida, "observacao", None))
        ordem_servico = cls._normalize_spaces(getattr(saida, "ordem_servico", None))
        centro_custo = cls._normalize_spaces(getattr(saida, "centro_custo", None))
        atividade_estruturada = cls._resolve_structured_activity(saida)
        atividade = atividade_estruturada or cls._derive_activity(local=local, observacao=observacao)
        unit_base = cls._resolve_unit_base(saida, item, retirada_l=retirada_l, retirada_kg=retirada_kg)
        unit_price_base = cls._resolve_unit_price(item)
        contexto_operacional = [local]
        if centro_custo:
            contexto_operacional.append(f"CC {centro_custo}")
        if ordem_servico:
            contexto_operacional.append(f"OS {ordem_servico}")
        if observacao:
            contexto_operacional.append(observacao)

        row = {
            "saida_id": getattr(saida, "id_saida", None),
            "codigo_item": cls._normalize_spaces(getattr(saida, "codigo_item", None)),
            "descricao_item": cls._normalize_spaces(getattr(item, "descricao", None)) or cls._normalize_spaces(getattr(saida, "codigo_item", None)),
            "categoria": cls._normalize_spaces(getattr(item, "categoria", None)) or "Sem categoria",
            "unidade_item": cls._normalize_spaces(getattr(item, "unidade", None)) or "un",
            "matricula": cls._normalize_spaces(getattr(saida, "matricula", None)),
            "colaborador_nome": cls._normalize_spaces(getattr(usuario, "nome", None)) or "Nao informado",
            "cargo": cls._normalize_spaces(getattr(usuario, "cargo", None)) or "Sem cargo",
            "local": local,
            "observacao": observacao,
            "ordem_servico": ordem_servico,
            "centro_custo": centro_custo,
            "atividade_estruturada_label": atividade_estruturada["label"] if atividade_estruturada else None,
            "atividade_source": atividade.get("source") or "heuristic",
            "contexto_uso": " | ".join(part for part in contexto_operacional if part),
            "data_saida": getattr(saida, "data_saida", None),
            "data_saida_label": saida.data_saida.strftime("%d/%m/%Y %H:%M") if getattr(saida, "data_saida", None) else "-",
            "quantidade_base": round(quantidade_base, 3),
            "unit_base": unit_base,
            "quantidade_litros": round(retirada_l, 3),
            "quantidade_quilos": round(retirada_kg, 3),
            "valor_unitario_base": round(unit_price_base, 6),
            "valor_total": round(quantidade_base * unit_price_base, 2) if unit_price_base > 0 else 0.0,
            "tipo_consumo": "fracionado" if (retirada_l > 0 or retirada_kg > 0) else "padrao",
            "atividade_key": atividade["key"],
            "atividade_label": atividade["label"],
            "atividade_confianca": atividade["confidence"],
        }
        row["quantidade_display"] = cls._format_quantity_display(row)
        return row

    @classmethod
    def _matches_search(cls, row: dict[str, Any], search: str) -> bool:
        query = cls._normalize_search(search)
        if not query:
            return True
        haystack = cls._normalize_search(
            " ".join(
                [
                    str(row.get("descricao_item") or ""),
                    str(row.get("codigo_item") or ""),
                    str(row.get("categoria") or ""),
                    str(row.get("colaborador_nome") or ""),
                    str(row.get("cargo") or ""),
                    str(row.get("local") or ""),
                    str(row.get("observacao") or ""),
                    str(row.get("ordem_servico") or ""),
                    str(row.get("centro_custo") or ""),
                    str(row.get("atividade_label") or ""),
                    str(row.get("atividade_estruturada_label") or ""),
                ]
            )
        )
        return query in haystack

    @classmethod
    def _load_exit_rows(cls, period: dict[str, Any]) -> list[dict[str, Any]]:
        rows = (
            Saida.query.options(joinedload(Saida.item), joinedload(Saida.usuario))
            .filter(Saida.data_saida >= period["start_dt"])
            .filter(Saida.data_saida <= period["end_dt"])
            .all()
        )
        result: list[dict[str, Any]] = []
        for saida in rows:
            row = cls._build_exit_row(saida)
            if row is not None:
                result.append(row)
        return result

    @classmethod
    def _load_entry_rows(
        cls,
        period: dict[str, Any],
        *,
        category_name: str | None = None,
        search: str = "",
    ) -> list[dict[str, Any]]:
        query = (
            Entrada.query.options(joinedload(Entrada.item))
            .filter(Entrada.data_entrada >= period["start_dt"])
            .filter(Entrada.data_entrada <= period["end_dt"])
        )
        if category_name:
            query = query.join(Item, Entrada.codigo_item == Item.codigo_item).filter(Item.categoria == category_name)

        rows: list[dict[str, Any]] = []
        search_query = cls._normalize_search(search)
        for entrada in query.all():
            item = getattr(entrada, "item", None)
            quantity = abs(cls._safe_float(getattr(entrada, "quantidade", 0.0)))
            if quantity <= 0:
                continue
            row = {
                "entrada_id": getattr(entrada, "id_entrada", None),
                "codigo_item": cls._normalize_spaces(getattr(entrada, "codigo_item", None)),
                "descricao_item": cls._normalize_spaces(getattr(item, "descricao", None)) or cls._normalize_spaces(getattr(entrada, "codigo_item", None)),
                "categoria": cls._normalize_spaces(getattr(item, "categoria", None)) or "Sem categoria",
                "data_entrada": getattr(entrada, "data_entrada", None),
                "quantidade": round(quantity, 3),
                "valor_total": round(quantity * cls._resolve_unit_price(item), 2),
                "nota_fiscal": cls._normalize_spaces(getattr(entrada, "nota_fiscal", None)),
            }
            if search_query:
                haystack = cls._normalize_search(
                    " ".join(
                        [
                            str(row.get("codigo_item") or ""),
                            str(row.get("descricao_item") or ""),
                            str(row.get("categoria") or ""),
                            str(row.get("nota_fiscal") or ""),
                        ]
                    )
                )
                if search_query not in haystack:
                    continue
            rows.append(row)
        return rows

    @classmethod
    def _build_overview(cls, rows: list[dict[str, Any]]) -> dict[str, Any]:
        local_fill = sum(1 for row in rows if str(row.get("local") or "") != "SEM LOCAL")
        return {
            "saidas": len(rows),
            "quantidade_total": round(sum(cls._safe_float(row.get("quantidade_base")) for row in rows), 3),
            "valor_total": round(sum(cls._safe_float(row.get("valor_total")) for row in rows), 2),
            "colaboradores": len({str(row.get("matricula") or "").strip() for row in rows if str(row.get("matricula") or "").strip()}),
            "itens": len({str(row.get("codigo_item") or "").strip() for row in rows if str(row.get("codigo_item") or "").strip()}),
            "locais": len({str(row.get("local") or "").strip() for row in rows if str(row.get("local") or "").strip() and str(row.get("local") or "") != "SEM LOCAL"}),
            "categorias": len({str(row.get("categoria") or "").strip() for row in rows if str(row.get("categoria") or "").strip()}),
            "local_fill_rate": (local_fill / len(rows)) if rows else 0.0,
        }

    @classmethod
    def _build_employee_opinion(cls, summary: dict[str, Any]) -> dict[str, Any]:
        total_saidas = int(summary.get("saidas") or 0)
        total_locais = int(summary.get("locais") or 0)
        total_categorias = int(summary.get("categorias") or 0)
        local_fill_rate = float(summary.get("local_fill_rate") or 0.0)
        cargo_present = bool(cls._normalize_spaces(summary.get("cargo")))

        if total_saidas <= 0:
            return {
                "score": 0,
                "label": "Sem base",
                "tone": "secondary",
                "text": "Ainda nao ha retiradas suficientes para formar um parecer administrativo confiavel.",
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
            label = "Atencao"
            tone = "warning"
        else:
            label = "Critico"
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

        return {
            "score": score,
            "label": label,
            "tone": tone,
            "text": (
                f"Parecer administrativo operacional: {quality_text}, com {fill_percent}% dos lancamentos "
                f"informando o local de uso, atuacao em {max(total_locais, 1)} local(is) e "
                f"{max(total_categorias, 1)} categoria(s)."
            ),
        }

    @classmethod
    def _aggregate_locations(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            local = str(row.get("local") or "SEM LOCAL")
            bucket = buckets.setdefault(
                local,
                {
                    "local": local,
                    "saidas": 0,
                    "quantidade_total": 0.0,
                    "total_valor": 0.0,
                    "_materials": defaultdict(float),
                    "_activities": defaultdict(float),
                },
            )
            bucket["saidas"] += 1
            bucket["quantidade_total"] += cls._safe_float(row.get("quantidade_base"))
            value = cls._safe_float(row.get("valor_total"))
            bucket["total_valor"] += value
            bucket["_materials"][str(row.get("descricao_item") or "Sem item")] += value
            bucket["_activities"][str(row.get("atividade_label") or "Nao classificado")] += value

        result = []
        for bucket in buckets.values():
            materials = dict(bucket.pop("_materials"))
            activities = dict(bucket.pop("_activities"))
            bucket["material_destaque"] = max(materials.items(), key=lambda entry: entry[1])[0] if materials else None
            bucket["atividade_destaque"] = max(activities.items(), key=lambda entry: entry[1])[0] if activities else None
            bucket["quantidade_total"] = round(float(bucket.get("quantidade_total") or 0.0), 3)
            bucket["total_valor"] = round(float(bucket.get("total_valor") or 0.0), 2)
            result.append(bucket)
        return sorted(result, key=lambda row: (-cls._safe_float(row.get("total_valor")), str(row.get("local") or "")))

    @classmethod
    def _aggregate_categories(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            category = str(row.get("categoria") or "Sem categoria")
            bucket = buckets.setdefault(
                category,
                {
                    "categoria": category,
                    "saidas": 0,
                    "quantidade_total": 0.0,
                    "total_valor": 0.0,
                },
            )
            bucket["saidas"] += 1
            bucket["quantidade_total"] += cls._safe_float(row.get("quantidade_base"))
            bucket["total_valor"] += cls._safe_float(row.get("valor_total"))

        return sorted(
            [
                {
                    **bucket,
                    "quantidade_total": round(float(bucket.get("quantidade_total") or 0.0), 3),
                    "total_valor": round(float(bucket.get("total_valor") or 0.0), 2),
                }
                for bucket in buckets.values()
            ],
            key=lambda row: (-cls._safe_float(row.get("total_valor")), str(row.get("categoria") or "")),
        )

    @classmethod
    def _aggregate_employees(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            employee_id = str(row.get("matricula") or "").strip() or "SEM MATRICULA"
            bucket = buckets.setdefault(
                employee_id,
                {
                    "matricula": employee_id,
                    "nome": row.get("colaborador_nome") or employee_id,
                    "cargo": row.get("cargo") or "Sem cargo",
                    "saidas": 0,
                    "quantidade_total": 0.0,
                    "total_valor": 0.0,
                    "_locais": set(),
                    "_categorias": set(),
                    "_local_fill": 0,
                },
            )
            bucket["saidas"] += 1
            bucket["quantidade_total"] += cls._safe_float(row.get("quantidade_base"))
            bucket["total_valor"] += cls._safe_float(row.get("valor_total"))
            if str(row.get("local") or "") != "SEM LOCAL":
                bucket["_locais"].add(str(row.get("local") or ""))
                bucket["_local_fill"] += 1
            if str(row.get("categoria") or ""):
                bucket["_categorias"].add(str(row.get("categoria") or ""))

        result = []
        for bucket in buckets.values():
            locais = bucket.pop("_locais")
            categorias = bucket.pop("_categorias")
            local_fill = int(bucket.pop("_local_fill") or 0)
            saidas = int(bucket.get("saidas") or 0)
            summary = {
                "saidas": saidas,
                "locais": len(locais),
                "categorias": len(categorias),
                "local_fill_rate": (local_fill / saidas) if saidas else 0.0,
                "cargo": bucket.get("cargo"),
            }
            opinion = cls._build_employee_opinion(summary)
            result.append(
                {
                    **bucket,
                    "quantidade_total": round(float(bucket.get("quantidade_total") or 0.0), 3),
                    "total_valor": round(float(bucket.get("total_valor") or 0.0), 2),
                    "locais": len(locais),
                    "categorias": len(categorias),
                    "parecer_administrativo": opinion.get("label"),
                    "parecer_tone": opinion.get("tone"),
                    "parecer_texto": opinion.get("text"),
                    "parecer_score": opinion.get("score"),
                }
            )
        return sorted(result, key=lambda row: (-cls._safe_float(row.get("total_valor")), str(row.get("nome") or "")))

    @classmethod
    def _build_scope_context(
        cls,
        *,
        period: dict[str, Any],
        local_name: str | None,
        category_name: str | None,
        employee_id: str | None,
        search: str,
        filter_options: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_local = cls._normalize_local(local_name) if local_name else None
        normalized_category = cls._normalize_spaces(category_name)
        normalized_employee = cls._normalize_spaces(employee_id)
        search_value = cls._normalize_spaces(search)

        employee_label = normalized_employee
        if normalized_employee:
            employee_label = next(
                (
                    str(option.get("nome") or normalized_employee)
                    for option in filter_options.get("employees") or []
                    if str(option.get("matricula") or "").strip() == normalized_employee
                ),
                normalized_employee,
            )

        if normalized_employee:
            return {
                "scope_title": f"Consumo de {employee_label}",
                "scope_subtitle": f"Historico individual consolidado para o periodo {period['label']}, com atividade derivada, valor e rastreabilidade operacional.",
            }
        if normalized_local:
            return {
                "scope_title": f"Atividade no local {normalized_local}",
                "scope_subtitle": f"Leitura analitica do local selecionado em {period['label']}, unificando consumo, tipos de movimentacao e atividade derivada.",
            }
        if normalized_category:
            return {
                "scope_title": f"Consumo da categoria {normalized_category}",
                "scope_subtitle": f"Recorte analitico da categoria no periodo {period['label']}, com impacto financeiro, distribuicao e tabela detalhada.",
            }
        if search_value:
            return {
                "scope_title": f"Busca analitica: {search_value}",
                "scope_subtitle": f"Resultados filtrados por busca livre no periodo {period['label']}, mantendo drill-down, ordenacao e atividade derivada.",
            }
        return {
            "scope_title": "Central Analitica",
            "scope_subtitle": f"Camada analitica operacional do almoxarifado para o periodo {period['label']}, com leitura executiva, detalhamento e atividade derivada.",
        }

    @classmethod
    def _build_maintenance_payload(cls, rows: list[dict[str, Any]]) -> dict[str, Any]:
        total_rows = len(rows)
        noise_rows = [row for row in rows if str(row.get("atividade_key") or "") == "central_kits"]
        relevant_rows = [row for row in rows if str(row.get("atividade_key") or "") != "central_kits"]
        classified_rows = [row for row in relevant_rows if str(row.get("atividade_key") or "") != "nao_classificado"]
        unclassified_rows = [row for row in relevant_rows if str(row.get("atividade_key") or "") == "nao_classificado"]
        structured_rows = [row for row in classified_rows if str(row.get("atividade_source") or "") == "structured"]
        heuristic_rows = [row for row in classified_rows if str(row.get("atividade_source") or "") != "structured"]

        buckets: dict[str, dict[str, Any]] = {}
        for row in relevant_rows:
            activity_key = str(row.get("atividade_key") or "nao_classificado")
            label = str(row.get("atividade_label") or "Nao classificado")
            bucket = buckets.setdefault(
                activity_key,
                {
                    "key": activity_key,
                    "label": label,
                    "count": 0,
                    "value": 0.0,
                    "quantity": 0.0,
                },
            )
            bucket["count"] += 1
            bucket["value"] += cls._safe_float(row.get("valor_total"))
            bucket["quantity"] += cls._safe_float(row.get("quantidade_base"))

        groups = sorted(
            [
                {
                    **bucket,
                    "value": round(float(bucket.get("value") or 0.0), 2),
                    "quantity": round(float(bucket.get("quantity") or 0.0), 3),
                }
                for bucket in buckets.values()
            ],
            key=lambda row: (-cls._safe_float(row.get("value")), -int(row.get("count") or 0), str(row.get("label") or "")),
        )

        raw_fronts: dict[str, dict[str, Any]] = {}
        for row in relevant_rows:
            local = str(row.get("local") or "SEM LOCAL")
            if local in {"SEM LOCAL", "CENTRAL DE KITS"}:
                continue
            bucket = raw_fronts.setdefault(local, {"label": local, "count": 0, "value": 0.0})
            bucket["count"] += 1
            bucket["value"] += cls._safe_float(row.get("valor_total"))

        fronts = sorted(
            [
                {
                    **bucket,
                    "value": round(float(bucket.get("value") or 0.0), 2),
                }
                for bucket in raw_fronts.values()
            ],
            key=lambda row: (-cls._safe_float(row.get("value")), -int(row.get("count") or 0), str(row.get("label") or "")),
        )[:6]

        denominator = len(relevant_rows)
        coverage_percent = round((len(classified_rows) / denominator) * 100, 1) if denominator else 0.0
        noise_percent = round((len(noise_rows) / total_rows) * 100, 1) if total_rows else 0.0
        unclassified_percent = round((len(unclassified_rows) / denominator) * 100, 1) if denominator else 0.0
        structured_percent = round((len(structured_rows) / denominator) * 100, 1) if denominator else 0.0
        heuristic_percent = round((len(heuristic_rows) / denominator) * 100, 1) if denominator else 0.0

        notes: list[str] = []
        if groups:
            lead_group = groups[0]
            notes.append(
                f"A atividade operacional mais representativa no recorte atual e {lead_group['label']}, com {lead_group['count']} saida(s)."
            )
        if structured_rows:
            notes.append(
                f"{structured_percent:.1f}% das linhas operacionais ja usam atividade estruturada, reduzindo dependencia de heuristica na Central Analitica."
            )
        if heuristic_rows:
            notes.append(
                f"{heuristic_percent:.1f}% das linhas ainda dependem de leitura heuristica baseada em local e observacao."
            )
        if noise_rows:
            notes.append(
                f"{noise_percent:.1f}% das linhas analisadas pertencem a Central de Kits e foram tratadas como ruido operacional nesta leitura."
            )
        if unclassified_rows:
            notes.append(
                f"{unclassified_percent:.1f}% das linhas fora da Central de Kits seguem sem atividade, local ou contexto suficiente para classificar a operacao."
            )
        if not notes:
            notes.append("A base atual nao apresentou padrao suficiente para destacar uma frente operacional dominante.")

        recent_rows = sorted(relevant_rows, key=lambda row: (row.get("data_saida") or datetime.min, int(row.get("saida_id") or 0)), reverse=True)[:8]
        return {
            "coverage_percent": coverage_percent,
            "noise_percent": noise_percent,
            "unclassified_percent": unclassified_percent,
            "structured_percent": structured_percent,
            "heuristic_percent": heuristic_percent,
            "total_rows": total_rows,
            "relevant_rows": len(relevant_rows),
            "classified_rows": len(classified_rows),
            "structured_rows": len(structured_rows),
            "heuristic_rows": len(heuristic_rows),
            "noise_rows": len(noise_rows),
            "groups": groups,
            "fronts": fronts,
            "recent_rows": recent_rows,
            "notes": notes,
        }

    @classmethod
    def _resolve_sort(cls, sort_by: str | None, sort_dir: str | None) -> tuple[str, str]:
        field = cls._normalize_spaces(sort_by).lower() or "data"
        if field not in {"data", "colaborador", "item", "categoria", "local", "atividade", "quantidade", "valor", "tipo"}:
            field = "data"
        direction = cls._normalize_spaces(sort_dir).lower() or ("desc" if field in {"data", "quantidade", "valor"} else "asc")
        if direction not in {"asc", "desc"}:
            direction = "desc"
        return field, direction

    @classmethod
    def _sort_rows(cls, rows: list[dict[str, Any]], *, sort_by: str, sort_dir: str) -> list[dict[str, Any]]:
        reverse = sort_dir == "desc"

        def sort_key(row: dict[str, Any]):
            if sort_by == "data":
                return (row.get("data_saida") or datetime.min, int(row.get("saida_id") or 0))
            if sort_by == "colaborador":
                return (cls._normalize_search(row.get("colaborador_nome")), cls._normalize_search(row.get("cargo")))
            if sort_by == "item":
                return (cls._normalize_search(row.get("descricao_item")), cls._normalize_search(row.get("codigo_item")))
            if sort_by == "categoria":
                return (cls._normalize_search(row.get("categoria")), cls._normalize_search(row.get("descricao_item")))
            if sort_by == "local":
                return (cls._normalize_search(row.get("local")), cls._normalize_search(row.get("descricao_item")))
            if sort_by == "atividade":
                return (cls._normalize_search(row.get("atividade_label")), cls._normalize_search(row.get("local")))
            if sort_by == "quantidade":
                return (cls._safe_float(row.get("quantidade_base")), cls._normalize_search(row.get("descricao_item")))
            if sort_by == "valor":
                return (cls._safe_float(row.get("valor_total")), cls._normalize_search(row.get("descricao_item")))
            if sort_by == "tipo":
                return (cls._normalize_search(row.get("tipo_consumo")), cls._normalize_search(row.get("descricao_item")))
            return (row.get("data_saida") or datetime.min, int(row.get("saida_id") or 0))

        return sorted(rows, key=sort_key, reverse=reverse)

    @classmethod
    def get_dataset(
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
        resolved_sort_by, resolved_sort_dir = cls._resolve_sort(sort_by, sort_dir)
        period = cls.resolve_period(
            exercise_label=exercise_label,
            period_preset=period_preset,
            start_date_value=start_date_value,
            end_date_value=end_date_value,
        )
        normalized_local = cls._normalize_local(local_name) if local_name else None
        normalized_category = cls._normalize_spaces(category_name) or None
        normalized_employee = cls._normalize_spaces(employee_id) or None
        normalized_search = cls._normalize_spaces(search)

        cache_key = (
            "analytics:dataset:"
            f"{period['label']}:"
            f"{period.get('selected_period_preset') or ''}:"
            f"{normalized_local or ''}:"
            f"{normalized_category or ''}:"
            f"{normalized_employee or ''}:"
            f"{cls._normalize_search(normalized_search)}:"
            f"{resolved_sort_by}:{resolved_sort_dir}:"
            f"{normalized_page}:{normalized_per_page}"
        )
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return dict(cached)

        filter_options = cls.get_filter_options()
        exit_rows = cls._load_exit_rows(period)
        filtered_rows = []
        for row in exit_rows:
            if normalized_local and str(row.get("local") or "") != normalized_local:
                continue
            if normalized_category and str(row.get("categoria") or "") != normalized_category:
                continue
            if normalized_employee and str(row.get("matricula") or "").strip() != normalized_employee:
                continue
            if not cls._matches_search(row, normalized_search):
                continue
            filtered_rows.append(row)

        sorted_rows = cls._sort_rows(filtered_rows, sort_by=resolved_sort_by, sort_dir=resolved_sort_dir)
        total_rows = len(sorted_rows)
        total_pages = max((total_rows + normalized_per_page - 1) // normalized_per_page, 1)
        page_value = min(normalized_page, total_pages)
        start_idx = (page_value - 1) * normalized_per_page
        end_idx = start_idx + normalized_per_page

        overview = cls._build_overview(filtered_rows)
        locations = cls._aggregate_locations(filtered_rows)
        categories = cls._aggregate_categories(filtered_rows)
        employees = cls._aggregate_employees(filtered_rows)
        maintenance = cls._build_maintenance_payload(filtered_rows)
        entry_rows = cls._load_entry_rows(period, category_name=normalized_category, search=normalized_search)

        stock_snapshot = inventory_service.dashboard_snapshot()
        low_stock_count = sum(1 for row in stock_snapshot.get("resumo") or [] if str(row.get("status") or "").lower() != "ok")

        payload = {
            "period": period,
            "filters": {
                "selected_exercise": cls._normalize_spaces(exercise_label) or period.get("exercise_label"),
                "selected_start_date": period.get("selected_start_date") or "",
                "selected_end_date": period.get("selected_end_date") or "",
                "selected_local": normalized_local or "",
                "selected_category": normalized_category or "",
                "selected_employee": normalized_employee or "",
                "search": normalized_search,
                "sort_by": resolved_sort_by,
                "sort_dir": resolved_sort_dir,
                "per_page": normalized_per_page,
                **filter_options,
            },
            "context": cls._build_scope_context(
                period=period,
                local_name=normalized_local,
                category_name=normalized_category,
                employee_id=normalized_employee,
                search=normalized_search,
                filter_options=filter_options,
            ),
            "overview": overview,
            "locations": locations,
            "categories": categories,
            "employees": employees,
            "maintenance": maintenance,
            "entry_rows": entry_rows,
            "stock": {
                "total_quantity": stock_snapshot.get("total_quantity") or 0,
                "low_count": low_stock_count,
            },
            "table": {
                "rows": sorted_rows[start_idx:end_idx],
                "all_rows": sorted_rows,
                "page": page_value,
                "per_page": normalized_per_page,
                "total_rows": total_rows,
                "total_pages": total_pages,
                "sort_by": resolved_sort_by,
                "sort_dir": resolved_sort_dir,
            },
        }
        return cls._set_cached(cache_key, dict(payload), ttl_seconds=20.0)


analytics_read_service = AnalyticsReadService()