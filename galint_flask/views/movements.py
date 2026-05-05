"""Rotas de lançamentos de estoque (entradas e saídas)."""
from __future__ import annotations

import unicodedata
import re
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for, send_file
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Item, Saida, RetiradaFerramenta
from ..services.auth import create_mirror_panel_token, get_mirror_panel_user
from ..services.inventory import (
    OPERATIONAL_ACTIVITY_OPTIONS,
    MovimentoPayload,
    apply_operational_context,
    inventory_service,
    normalize_operational_activity,
    normalize_operational_text,
)
from ..services.unit_conversion_engine import UnitConversionError, unit_conversion_engine
from ..services.mirror_state_service import mirror_state_service
from ..services.notification_router import NotificationRouterService
from ..services.mirror_insights_service import mirror_insights_service
from ..services.native_panel_launcher import launch_panel as launch_native_panel
from ..services.legacy_stock_normalizer import infer_packaging_measure, resolve_canonical_unit, resolve_packaging_factor
from ..services.operation_visual_payload import operation_visual_payload_service
from ..services.users import user_service
from ..services.entrada_service import entrada_service
from ..services.telegram_service import TelegramService
from ..mako_renderer import render_mako_template
from ..utils.time_service import TimeService

blueprint = Blueprint("movements", __name__, url_prefix="/movimentos")


@blueprint.get("/api/buscar-item")
@login_required
def buscar_item():
    """API: Busca itens por código ou nome (parcial)."""
    query = (request.args.get("q") or "").strip()
    only_available = (request.args.get("only_available") or "").strip().lower() in {"1", "true", "yes", "sim"}
    
    if not query or len(query) < 1:
        return jsonify({"items": [], "itens": []})
    
    resultados = inventory_service.search_items_for_autocomplete(query, limit=20)
    if only_available:
        resultados = [item for item in resultados if item.get("is_available") is not False]

    item_codes = [str(item.get("codigo") or "").strip() for item in resultados if str(item.get("codigo") or "").strip()]
    item_models = {
        item.codigo_item: item
        for item in Item.query.filter(Item.codigo_item.in_(item_codes)).all()
    } if item_codes else {}

    enriched_results: list[dict[str, Any]] = []
    for item_payload in resultados:
        item_code = str(item_payload.get("codigo") or "").strip()
        item_model = item_models.get(item_code)
        unit_context = _build_saida_unit_context(item_payload, item_model)
        financial_reference = operation_visual_payload_service.resolve_item_financial_reference(item_model)
        movement_balance_display = _build_saida_balance_display(
            item_payload,
            unit_context,
            balance_key="saldo",
            fallback_key="saldo_display",
        )
        enriched_results.append({
            **item_payload,
            **unit_context,
            "unidade_cadastro": item_payload.get("unidade"),
            "unidade": unit_context.get("devolucao_unidade_label") or item_payload.get("unidade"),
            "saldo_display": movement_balance_display,
            "valor_referencia": financial_reference,
        })
    return jsonify({"items": enriched_results, "itens": enriched_results})


@blueprint.after_request
def flush_withdrawal_notifications(response):
    """Finaliza e envia notificações agrupadas de saídas após cada requisição."""
    try:
        # Apenas processar em requisições POST bem-sucedidas (status 2xx ou 3xx redirect)
        if request.method == 'POST' and 200 <= response.status_code < 400:
            TelegramService.flush_pending_withdrawals()
    except Exception:
        # Não bloquear a resposta por erro nas notificações
        pass
    return response


LIQUID_PRODUCT_TYPES: list[dict[str, Any]] = [
    {
        "id": "massa_acrilica",
        "label": "Massa Acrílica / Massa Corrida",
        "default_unit": "quilo",
        "keywords": ["massa acrilica", "massa corrida"],
    },
    {
        "id": "tinta_piso_base_agua",
        "label": "Tinta para Piso (base água / acrílica)",
        "default_unit": "litro",
        "keywords": ["tinta piso", "piso acrilica", "piso base agua"],
    },
    {
        "id": "tinta_asfaltica",
        "label": "Tinta Asfáltica",
        "default_unit": "litro",
        "keywords": ["tinta asfaltica", "asfaltica"],
    },
    {
        "id": "tinta_epoxi_piso",
        "label": "Tinta Epóxi para Piso (bicomp / industrial)",
        "default_unit": "litro",
        "keywords": ["epoxi", "epóxi", "bicomp", "epoxi piso"],
    },
    {
        "id": "tinta_acrilica",
        "label": "Tinta Acrílica (padrão, PVA, semi-brilho, fosca)",
        "default_unit": "litro",
        "keywords": ["tinta acrilica", "tinta pva", "tinta fosca", "tinta semi"],
    },
    {
        "id": "resina_multuso",
        "label": "Resina Multiuso (base água)",
        "default_unit": "litro",
        "keywords": ["resina", "multiuso"],
    },
    {
        "id": "tinta_esmalte",
        "label": "Tinta Esmalte (base solvente)",
        "default_unit": "litro",
        "keywords": ["tinta esmalte", "esmalte"],
    },
    {
        "id": "impermeabilizante",
        "label": "Impermeabilizante (acrílico / borracha líquida)",
        "default_unit": "litro",
        "keywords": ["impermeabilizante", "borracha liquida", "acrilico"],
    },
    {
        "id": "cloro_granulado",
        "label": "Cloro Granulado HTH (hipoclorito de cálcio 65%)",
        "default_unit": "quilo",
        "keywords": ["cloro", "cloro granulado", "hipoclorito", "hth"],
    },
]

LIQUID_PRODUCT_TYPES_BY_ID = {entry["id"]: entry for entry in LIQUID_PRODUCT_TYPES}
LIQUID_FRACTIONS: list[tuple[int, int]] = [(1, divisor) for divisor in range(2, 21)]
FRACTIONABLE_PACKAGING_TYPES = {"lata", "rolo", "pacote", "caixa", "fardo", "litro", "balde", "bombona", "saco"}
FRACTIONABLE_LIQUID_HINTS = (
    "tinta",
    "resina",
    "verniz",
    "solvente",
    "thinner",
    "selador",
    "impermeabilizante",
    "esmalte",
)
FRACTIONABLE_WEIGHT_HINTS = (
    "massa",
    "argamassa",
    "rejunte",
    "cloro",
    "cimento",
    "gesso",
)
EXPRESS_RETURN_CUTOFF_HOUR = 17


def _require_admin() -> None:
    if not bool(getattr(current_user, "is_admin", False)):
        abort(403)


def _normalize_mirror_mode(value: str | None) -> str:
    mode = (value or "").strip().lower()
    if mode not in {"", "saida", "entrada", "ferramenta", "fracionada"}:
        abort(404)
    return mode


def _is_admin_session() -> bool:
    return bool(getattr(current_user, "is_authenticated", False)) and bool(getattr(current_user, "is_admin", False))


def _get_mirror_token() -> str:
    return str(request.args.get("native_token") or request.headers.get("X-Galint-Mirror-Token") or "").strip()


def _authorize_mirror_token_user(mode: str):
    token = _get_mirror_token()
    if not token:
        return None
    usuario = get_mirror_panel_user(token, mode=mode)
    if usuario and bool(getattr(usuario, "is_admin", False)):
        return usuario
    abort(403)


def _ensure_mirror_panel_json_access(mode: str) -> None:
    if _is_admin_session():
        return
    if _authorize_mirror_token_user(mode) is not None:
        return
    if bool(getattr(current_user, "is_authenticated", False)):
        abort(403)
    abort(401)


def _ensure_mirror_panel_html_access(mode: str):
    if _is_admin_session():
        return None
    if _authorize_mirror_token_user(mode) is not None:
        return None
    if bool(getattr(current_user, "is_authenticated", False)):
        abort(403)
    return redirect(url_for("auth.login_form", next=request.url))


def _ensure_utc(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _normalize_text(value: str | None) -> str:
    value = (value or "").strip().lower()
    if not value:
        return ""
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _collect_operational_context(source: Any) -> dict[str, str | None]:
    getter = getattr(source, "get", None)
    if getter is None:
        return {
            "atividade_operacional": None,
            "ordem_servico": None,
            "centro_custo": None,
        }
    return {
        "atividade_operacional": normalize_operational_activity(getter("atividade_operacional")),
        "ordem_servico": normalize_operational_text(getter("ordem_servico"), max_length=120),
        "centro_custo": normalize_operational_text(getter("centro_custo"), max_length=120),
    }


def _merge_operational_context(primary: dict[str, str | None], fallback: dict[str, str | None]) -> dict[str, str | None]:
    return {
        key: primary.get(key) or fallback.get(key)
        for key in ("atividade_operacional", "ordem_servico", "centro_custo")
    }


def _detect_liquid_type(*, categoria: str | None, descricao: str | None) -> dict[str, Any] | None:
    texto = f"{_normalize_text(categoria)} {_normalize_text(descricao)}"
    if not texto.strip():
        return None
    for entry in LIQUID_PRODUCT_TYPES:
        if any(keyword in texto for keyword in entry["keywords"]):
            return entry
    return None


def _infer_unidade(unidade: str | None) -> str:
    normalized = _normalize_text(unidade)
    if not normalized:
        return ""
    # Evita interpretar termos como "lata 18l" como litro
    if re.search(r"\b(par|pares)\b", normalized):
        return "par"
    if re.search(r"\b(litro|litros|lt|lts)\b", normalized):
        return "litro"
    if re.search(r"\b(kg|quilo|quilos)\b", normalized):
        return "quilo"
    if re.search(r"\b(m|mt|mts|metro|metros)\b", normalized):
        return "metro"
    if re.search(r"\b(un|und|unidade|unidades|peca|pecas|peça|peças)\b", normalized):
        return "unidade"
    return normalized


def _normalize_saida_unit_code(value: str | None) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        return ""
    if re.search(r"\b(par|pares)\b", normalized):
        return "par"
    if re.search(r"\b(cm|centimetro|centimetros)\b", normalized):
        return "cm"
    if re.search(r"\b(m|mt|mts|metro|metros)\b", normalized):
        return "metro"
    if re.search(r"\b(litro|litros|lt|lts)\b", normalized):
        return "litro"
    if re.search(r"\b(kg|quilo|quilos)\b", normalized):
        return "kg"
    return normalized


def _as_positive_float(value: Any) -> float:
    try:
        parsed = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return parsed if parsed > 0 else 0.0


def _extract_measurement_from_text(text: str, unit_pattern: str) -> float:
    if not text:
        return 0.0
    match = re.search(rf"(\d+(?:[.,]\d+)?)\s*({unit_pattern})\b", text)
    if not match:
        return 0.0
    raw_value = match.group(1).replace(",", ".")
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return 0.0


def _infer_package_name(item: dict[str, Any]) -> str:
    tipo_embalagem = _normalize_text(item.get("tipo_embalagem_novo"))
    unidade = _normalize_text(item.get("unidade"))
    descricao = _normalize_text(item.get("descricao"))
    if tipo_embalagem in FRACTIONABLE_PACKAGING_TYPES:
        return tipo_embalagem
    if unidade in FRACTIONABLE_PACKAGING_TYPES:
        return unidade
    for candidate in ("lata", "balde", "bombona", "rolo", "pacote", "caixa", "fardo", "saco"):
        if candidate in descricao:
            return candidate
    if "tinta" in descricao or "resina" in descricao or "verniz" in descricao:
        return "lata"
    return "embalagem"


def _pluralize_package_name(package_name: str) -> str:
    package_name = _normalize_text(package_name)
    mapping = {
        "lata": "latas",
        "balde": "baldes",
        "bombona": "bombonas",
        "rolo": "rolos",
        "pacote": "pacotes",
        "caixa": "caixas",
        "fardo": "fardos",
        "saco": "sacos",
        "litro": "litros",
        "embalagem": "embalagens",
    }
    return mapping.get(package_name, f"{package_name}s" if package_name else "embalagens")


def _infer_package_capacity(item: dict[str, Any], *, fractional_info: dict[str, Any]) -> float:
    return _infer_package_capacity_for_unit(item, fractional_info=fractional_info, primary_unit_code=None)


def _infer_package_capacity_for_unit(
    item: dict[str, Any],
    *,
    fractional_info: dict[str, Any],
    primary_unit_code: str | None,
) -> float:
    unidades_por_embalagem = _as_positive_float(item.get("unidades_por_embalagem"))
    if unidades_por_embalagem > 0:
        return unidades_por_embalagem

    effective_unit = _normalize_text(primary_unit_code) or _normalize_text(fractional_info.get("default_unit"))

    if effective_unit == "unidade":
        return 0.0

    litros_por_embalagem = _as_positive_float(item.get("litros_por_embalagem"))
    if effective_unit == "litro" and litros_por_embalagem > 0:
        return litros_por_embalagem

    grandeza_referencia = _as_positive_float(item.get("grandeza_referencia"))
    if effective_unit in {"quilo", "metro"} and grandeza_referencia > 0:
        return grandeza_referencia

    texto = f"{_normalize_text(item.get('descricao'))} {_normalize_text(item.get('categoria'))}".strip()
    if effective_unit == "litro":
        return _extract_measurement_from_text(texto, r"l|lt|lts|litro|litros")
    if effective_unit == "quilo":
        return _extract_measurement_from_text(texto, r"kg|quilo|quilos")
    if effective_unit == "metro":
        return _extract_measurement_from_text(texto, r"m|mt|mts|metro|metros")
    return 0.0


def _resolve_primary_return_unit_option(
    *,
    item_model: Item | None,
    fallback_config: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return_unit_options = inventory_service.get_material_return_unit_options(item=item_model)
    if not return_unit_options:
        return_unit_options = [dict(fallback_config)]

    primary_option = dict(return_unit_options[0]) if return_unit_options else {}
    primary_option.setdefault("unit_code", fallback_config.get("unit_code") or "unidade")
    primary_option.setdefault("unit_display", fallback_config.get("unit_display") or "un")
    primary_option.setdefault("unit_label", fallback_config.get("unit_label") or "Unidade")
    primary_option.setdefault("allow_decimal", bool(fallback_config.get("allow_decimal")))
    primary_option.setdefault("input_step", fallback_config.get("input_step") or (0.001 if primary_option.get("allow_decimal") else 1))
    primary_option.setdefault("input_min", fallback_config.get("input_min") or (0.001 if primary_option.get("allow_decimal") else 1))
    return return_unit_options, primary_option


def _resolve_unit_factor_base(item_model: Item | None, unit_code: str) -> float:
    unit_code = (unit_code or "").strip().lower()
    if not item_model or not unit_code:
        return 1.0

    raw_unit = _infer_unidade(getattr(item_model, "unidade", None))
    canonical_unit = (resolve_canonical_unit(item_model) or "").strip().lower()

    if unit_code == "unidade" and canonical_unit == "un":
        return 1.0
    if unit_code == "par" and canonical_unit == "par":
        return 1.0

    if unit_code == "unidade":
        inferred_measure = infer_packaging_measure(item_model)
        inferred_measure_unit = inferred_measure[1] if inferred_measure is not None else None
        if canonical_unit == "un" and inferred_measure_unit in {"kg", "l", "m"}:
            packaging_factor = float(resolve_packaging_factor(item_model) or 0.0)
            if packaging_factor > 0:
                return packaging_factor

    if unit_code == "unidade" and raw_unit in {"quilo", "litro", "metro"}:
        packaging_factor = float(resolve_packaging_factor(item_model) or 0.0)
        if packaging_factor > 0:
            return packaging_factor

    try:
        conversion = unit_conversion_engine.convert_item_to_base(item_model, 1.0, unit_code)
        quantity_base = float(conversion.quantity_base or 0.0)
        return quantity_base if quantity_base > 0 else 1.0
    except (UnitConversionError, TypeError, ValueError):
        return 1.0


def _build_fractional_unit_factors(item_model: Item | None, default_unit_code: str) -> dict[str, float]:
    normalized_default = (default_unit_code or "").strip().lower()
    if item_model is None or not normalized_default:
        return {}

    if normalized_default == "metro":
        candidates = ["metro", "cm"]
    elif normalized_default in {"quilo", "kg", "litro"}:
        candidates = ["kg", "litro"]
    else:
        candidates = [normalized_default]

    factors: dict[str, float] = {}
    for candidate in candidates:
        try:
            conversion = unit_conversion_engine.convert_item_to_base(item_model, 1.0, candidate)
            quantity_base = float(conversion.quantity_base or 0.0)
        except (UnitConversionError, TypeError, ValueError):
            quantity_base = 0.0
        if quantity_base > 0:
            key = "kg" if candidate in {"quilo", "kg"} else candidate
            factors[key] = quantity_base

    if normalized_default in {"quilo", "kg"}:
        factors.setdefault("kg", 1.0)
    elif normalized_default == "litro":
        factors.setdefault("litro", 1.0)
    elif normalized_default == "metro":
        factors.setdefault("metro", 1.0)

    return factors


def _build_saida_unit_context(item: dict[str, Any], item_model: Item | None) -> dict[str, Any]:
    fractional_info = _infer_fractional_item(item)
    return_quantity_config = _resolve_return_quantity_config(item, fractional_info=fractional_info)
    return_unit_options, primary_option = _resolve_primary_return_unit_option(
        item_model=item_model,
        fallback_config=return_quantity_config,
    )

    unit_code = str(primary_option.get("unit_code") or return_quantity_config.get("unit_code") or "unidade").strip().lower() or "unidade"
    unit_display = primary_option.get("unit_display") or return_quantity_config.get("unit_display") or "un"
    unit_label = primary_option.get("unit_label") or return_quantity_config.get("unit_label") or "Unidade"
    package_capacity = _infer_package_capacity_for_unit(
        item,
        fractional_info=fractional_info,
        primary_unit_code=unit_code,
    )
    package_name = _infer_package_name(item)

    return {
        "fracao_unidade_padrao": unit_code,
        "devolucao_unidade_codigo": unit_code,
        "devolucao_unidade_exibicao": unit_display,
        "devolucao_unidade_label": unit_label,
        "devolucao_permite_decimal": bool(primary_option.get("allow_decimal")),
        "devolucao_step": primary_option.get("input_step") or (0.001 if primary_option.get("allow_decimal") else 1),
        "devolucao_min": primary_option.get("input_min") or (0.001 if primary_option.get("allow_decimal") else 1),
        "devolucao_unidade_fator_base": _resolve_unit_factor_base(item_model, unit_code),
        "devolucao_unidades_opcoes": return_unit_options,
        "unidade_exibicao_total": unit_display,
        "capacidade_embalagem": package_capacity,
        "permite_saida_em_embalagens": bool(package_capacity > 0 and package_name in FRACTIONABLE_PACKAGING_TYPES),
    }


def _format_saida_quantity_display(
    quantity: float | int | None,
    *,
    unit_code: str,
    unit_display: str | None,
    unit_label: str | None,
    allow_decimal: bool,
) -> str:
    try:
        numeric_quantity = float(quantity or 0.0)
    except (TypeError, ValueError):
        numeric_quantity = 0.0

    if allow_decimal or abs(numeric_quantity - round(numeric_quantity)) > 1e-6:
        quantity_text = f"{numeric_quantity:.3f}".rstrip("0").rstrip(".")
    else:
        quantity_text = str(int(round(numeric_quantity)))

    normalized_unit_code = (unit_code or "").strip().lower()
    if normalized_unit_code == "unidade":
        unit_text = "unidade" if abs(numeric_quantity - 1.0) <= 1e-6 else "unidades"
        return f"{quantity_text} {unit_text}"
    if normalized_unit_code == "par":
        unit_text = "par" if abs(numeric_quantity - 1.0) <= 1e-6 else "pares"
        return f"{quantity_text} {unit_text}"
    if normalized_unit_code == "litro":
        unit_text = "litro" if abs(numeric_quantity - 1.0) <= 1e-6 else "litros"
        return f"{quantity_text} {unit_text}"
    if normalized_unit_code == "metro":
        unit_text = "metro" if abs(numeric_quantity - 1.0) <= 1e-6 else "metros"
        return f"{quantity_text} {unit_text}"
    if normalized_unit_code in {"quilo", "kg"}:
        return f"{quantity_text} kg"

    fallback_unit = str(unit_display or unit_label or normalized_unit_code or "un").strip()
    return f"{quantity_text} {fallback_unit}"


def _build_saida_balance_display(
    item: dict[str, Any],
    unit_context: dict[str, Any],
    *,
    balance_key: str,
    fallback_key: str | None = None,
) -> str:
    raw_balance = _as_positive_float(item.get(balance_key))
    unit_code = str(unit_context.get("devolucao_unidade_codigo") or "").strip().lower()
    unit_factor_base = _as_positive_float(unit_context.get("devolucao_unidade_fator_base")) or 1.0

    if unit_code:
        operational_balance = raw_balance / unit_factor_base if unit_factor_base > 0 else raw_balance
        return _format_saida_quantity_display(
            operational_balance,
            unit_code=unit_code,
            unit_display=unit_context.get("devolucao_unidade_exibicao"),
            unit_label=unit_context.get("devolucao_unidade_label"),
            allow_decimal=bool(unit_context.get("devolucao_permite_decimal")),
        )

    fallback_value = item.get(fallback_key) if fallback_key else None
    return str(fallback_value or item.get(balance_key) or "").strip()


def _infer_fractional_item(item: dict[str, Any]) -> dict[str, Any]:
    tipo_embalagem = _normalize_text(item.get("tipo_embalagem_novo"))
    descricao = _normalize_text(item.get("descricao"))
    categoria = _normalize_text(item.get("categoria"))
    unidade = _infer_unidade(item.get("unidade"))
    grandeza_referencia = _as_positive_float(item.get("grandeza_referencia"))
    litros_por_embalagem = _as_positive_float(item.get("litros_por_embalagem"))
    texto = f"{categoria} {descricao}".strip()

    liquid_type = _detect_liquid_type(categoria=item.get("categoria"), descricao=item.get("descricao"))
    if tipo_embalagem in FRACTIONABLE_PACKAGING_TYPES:
        if tipo_embalagem == "rolo":
            default_unit = "metro"
        elif tipo_embalagem in {"caixa", "fardo"}:
            default_unit = "unidade"
        elif tipo_embalagem in {"pacote", "saco"}:
            if grandeza_referencia > 0 or unidade == "quilo":
                default_unit = "quilo"
            elif litros_por_embalagem > 0 or unidade == "litro":
                default_unit = "litro"
            elif liquid_type:
                default_unit = liquid_type.get("default_unit") or "unidade"
            else:
                default_unit = "unidade"
        elif tipo_embalagem == "litro" or litros_por_embalagem > 0:
            default_unit = "litro"
        elif tipo_embalagem in {"lata", "balde", "bombona"}:
            if unidade in {"litro", "quilo"}:
                default_unit = unidade
            elif litros_por_embalagem > 0:
                default_unit = "litro"
            elif grandeza_referencia > 0:
                default_unit = "quilo"
            elif liquid_type:
                default_unit = liquid_type.get("default_unit") or "unidade"
            else:
                default_unit = "unidade"
        else:
            default_unit = unidade or (liquid_type.get("default_unit") if liquid_type else "") or "unidade"
        return {
            "enabled": True,
            "default_unit": default_unit,
            "source": "tipo_embalagem_novo",
        }

    if liquid_type:
        return {
            "enabled": True,
            "default_unit": liquid_type.get("default_unit") or "litro",
            "source": "liquid_type",
        }

    if litros_por_embalagem > 0:
        return {
            "enabled": True,
            "default_unit": "litro",
            "source": "litros_por_embalagem",
        }

    if grandeza_referencia > 0:
        return {
            "enabled": True,
            "default_unit": "quilo",
            "source": "grandeza_referencia",
        }

    if re.search(r"\b\d+(?:[.,]\d+)?\s*(l|lt|lts|litro|litros)\b", texto) and any(
        hint in texto for hint in FRACTIONABLE_LIQUID_HINTS
    ):
        return {
            "enabled": True,
            "default_unit": "litro",
            "source": "descricao_liquida",
        }

    if re.search(r"\b\d+(?:[.,]\d+)?\s*(kg|quilo|quilos)\b", texto) and any(
        hint in texto for hint in FRACTIONABLE_WEIGHT_HINTS
    ):
        return {
            "enabled": True,
            "default_unit": "quilo",
            "source": "descricao_pesavel",
        }

    return {
        "enabled": False,
        "default_unit": "quilo",
        "source": None,
    }


def _resolve_return_quantity_config(item: dict[str, Any], *, fractional_info: dict[str, Any]) -> dict[str, Any]:
    inferred_unit = _infer_unidade(item.get("unidade"))
    fallback_unit = _normalize_text(fractional_info.get("default_unit"))

    if inferred_unit in {"litro", "quilo", "metro", "unidade", "par"}:
        unit_code = inferred_unit
    elif bool(fractional_info.get("enabled")):
        unit_code = fallback_unit
    else:
        unit_code = "unidade"

    if unit_code not in {"litro", "quilo", "metro", "unidade", "par"}:
        unit_code = inferred_unit if inferred_unit in {"litro", "quilo", "metro", "unidade", "par"} else "unidade"

    if unit_code == "litro":
        unit_display = "L"
        unit_label = "Litro"
        allow_decimal = True
    elif unit_code == "quilo":
        unit_display = "kg"
        unit_label = "Kg"
        allow_decimal = True
    elif unit_code == "metro":
        unit_display = "m"
        unit_label = "Metro"
        allow_decimal = True
    elif unit_code == "par":
        unit_display = "par"
        unit_label = "Par"
        allow_decimal = False
    else:
        unit_display = "un"
        unit_label = "Unidade"
        allow_decimal = False

    return {
        "unit_code": unit_code,
        "unit_display": unit_display,
        "unit_label": unit_label,
        "allow_decimal": allow_decimal,
        "input_step": 0.001 if allow_decimal else 1,
        "input_min": 0.001 if allow_decimal else 1,
    }


def _resolve_usuario(identificador: str | None):
    identificador = (identificador or "").strip()
    if identificador:
        # Aceita:
        # - matrícula (13 dígitos)
        # - barcode_token
        # - nome (com autocomplete)
        # - formato "Nome — 0000000000000" (extraímos a matrícula)
        candidato = identificador
        match = re.search(r"\b\d{13}\b", identificador)
        if match:
            candidato = match.group(0)

        usuario = user_service.find_by_identifier(candidato)
        if not usuario and not match:
            sugestoes = user_service.search_by_name(identificador, limit=6)
            if len(sugestoes) == 1:
                usuario = sugestoes[0]
            elif len(sugestoes) > 1:
                lista = ", ".join(f"{u.nome} ({u.matricula})" for u in sugestoes[:6])
                raise ValueError(
                    f"Múltiplos usuários encontrados. Seja mais específico ou use a matrícula. Sugestões: {lista}"
                )

        if not usuario:
            raise ValueError("Usuário não encontrado pelo identificador informado")

        # A matrícula/nome informado aqui é de quem está retirando/devolvendo.
        # (Não confundir com o usuário logado que está registrando.)
        return usuario
    if current_user.is_authenticated:
        return current_user
    raise ValueError("Sessão inválida")


def _parse_quantidade(raw: str | None) -> int:
    try:
        quantidade = float(raw or 0)
    except (TypeError, ValueError):
        quantidade = 0.0
    return quantidade


def _resolve_devolucao_operadores(source: Any) -> tuple[str | None, Any]:
    getter = getattr(source, "get", None)
    if getter is None:
        raise ValueError("Fonte inválida para leitura da devolução")

    identificador_devolucao = (
        getter("devolvido_por")
        or getter("devolvedor")
        or getter("devolvido_por_matricula")
        or ""
    ).strip()
    identificador_legado = (getter("usuario") or getter("matricula") or "").strip()
    retirada_matricula = (getter("retirada_matricula") or getter("matricula_retirada") or "").strip() or None

    if identificador_devolucao:
        return retirada_matricula, _resolve_usuario(identificador_devolucao)

    if identificador_legado:
        usuario = _resolve_usuario(identificador_legado)
        return retirada_matricula or usuario.matricula, usuario

    raise ValueError("Informe quem está devolvendo.")


def _build_express_return_window(*, cutoff_hour: int = EXPRESS_RETURN_CUTOFF_HOUR) -> dict[str, Any]:
    now_local = TimeService.now_local()
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_local = now_local.replace(hour=cutoff_hour, minute=0, second=0, microsecond=0)
    window_open = now_local < cutoff_local
    effective_end_local = now_local if window_open else cutoff_local
    start_utc = TimeService.to_utc(start_local).replace(tzinfo=None)
    end_utc = TimeService.to_utc(effective_end_local).replace(tzinfo=None)
    return {
        "window_open": window_open,
        "now_local": now_local,
        "start_local": start_local,
        "cutoff_local": cutoff_local,
        "effective_end_local": effective_end_local,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "cutoff_label": cutoff_local.strftime("%H:%M"),
        "today_label": now_local.strftime("%d/%m/%Y"),
    }


@blueprint.get("/")
@login_required
def index():
    """Mantém compatibilidade com a raiz de movimentos."""
    return redirect(url_for("movements.saidas_hub"))


@blueprint.get("/registro-de-saidas")
@login_required
def saidas_hub():
    """Exibe o hub de registro de saídas com os fluxos disponíveis."""
    return render_mako_template("movements/saidas_hub.mako")


# Página antiga "Controle de Saídas e Devoluções" removida - era inútil
# @blueprint.get("/")
# @login_required
# def index_OLD():
#     itens = inventory_service.list_items()
#     entradas = inventory_service.list_entradas(limit=25)
#     saidas = inventory_service.list_saidas(limit=25)
#     usuarios = user_service.list_users()
#     can_manage = bool(getattr(current_user, "is_admin", False))
#     devolucoes = [
#         entrada
#         for entrada in entradas
#         if (entrada.get("categoria") or "").strip().lower() == "ferramentas"
#     ]
#     return render_mako_template(
#         "movements/index.mako",
#         itens=itens,
#         entradas=devolucoes,
#         saidas=saidas,
#         usuarios=usuarios,
#         can_manage=can_manage,
#         liquid_types=LIQUID_PRODUCT_TYPES,
#         liquid_fractions=LIQUID_FRACTIONS,
#     )


@blueprint.post("/saida-multipla")
@login_required
def registrar_saida_multipla():
    """Registra múltiplas saídas de uma vez com notificação agrupada no Telegram."""
    _require_admin()
    
    try:
        data = request.get_json() or {}
        itens = data.get("itens", [])
        
        if not itens or not isinstance(itens, list):
            return jsonify({"success": False, "message": "Lista de itens é obrigatória"}), 400
        
        # Validar usuário comum para todos os itens
        identificador = data.get("usuario")
        usuario = _resolve_usuario(identificador)
        local_servico_geral = data.get("local_servico", "")
        operational_context_geral = _collect_operational_context(data)
        
        saidas_criadas = []
        ledger_results = []
        resultados = []
        
        # Processar cada item
        for idx, item_data in enumerate(itens, 1):
            codigo = (item_data.get("codigo") or "").strip()
            quantidade = _parse_quantidade(item_data.get("quantidade"))
            observacao = (item_data.get("observacao") or "").strip() or None
            operational_context = _merge_operational_context(
                _collect_operational_context(item_data),
                operational_context_geral,
            )
            em_embalagens_raw = item_data.get("em_embalagens")
            em_embalagens = None
            if em_embalagens_raw is not None:
                em_embalagens = em_embalagens_raw == "1" if isinstance(em_embalagens_raw, str) else bool(em_embalagens_raw)
            
            if not codigo:
                resultados.append({"index": idx, "success": False, "message": "Código não informado"})
                continue
            
            if quantidade <= 0:
                resultados.append({"index": idx, "codigo": codigo, "success": False, "message": "Quantidade inválida"})
                continue
            
            savepoint = None
            try:
                savepoint = db.session.begin_nested()

                item = Item.query.filter_by(codigo_item=codigo).first()
                if not item:
                    raise ValueError("Item não encontrado")

                categoria_text = (item.categoria or '').lower()
                is_tool_item = 'ferrament' in categoria_text

                if is_tool_item:
                    raise ValueError("Ferramentas só podem sair pelo fluxo de Ferramentas/Custódia.")

                payload_saida = MovimentoPayload(
                    codigo=item.codigo_item,
                    quantidade=float(quantidade),
                    matricula=usuario.matricula,
                    observacao=str(observacao or "").upper() if observacao else None,
                    local_servico=str(local_servico_geral or "").upper() if local_servico_geral else None,
                    atividade_operacional=operational_context.get("atividade_operacional"),
                    ordem_servico=operational_context.get("ordem_servico"),
                    centro_custo=operational_context.get("centro_custo"),
                    em_embalagens=em_embalagens,
                    canal_saida="materiais",
                )
                inventory_service.validate_exit_payload_policy(item, payload_saida)
                
                # Verificar saldo considerando sistema de embalagens
                from galint_flask.services.embalagem_service import EmbalagemService

                usa_embalagens = EmbalagemService.tem_embalagem(item) and em_embalagens is not None
                saldo_atual = 0.0

                if not usa_embalagens:
                    # Sistema tradicional (sem embalagens) OU saída sem informar em_embalagens
                    try:
                        saldo_atual = float(item.get_saldo_atual() or 0)
                    except Exception:
                        saldo_atual = 0.0

                    if saldo_atual < quantidade:
                        raise ValueError(f"Saldo insuficiente. Disponível: {int(saldo_atual)}")

                ledger_result = inventory_service.mirror_legacy_movement(
                    product_id=item.codigo_item,
                    movement_type="saida",
                    quantity=float(quantidade),
                    payload=payload_saida,
                    metadata={
                        "reference_type": "movements_saida_multipla",
                    },
                )

                # Criar saída diretamente
                saida = Saida()
                saida.codigo_item = item.codigo_item
                saida.quantidade = quantidade
                saida.matricula = usuario.matricula
                saida.data_saida = datetime.now(timezone.utc)
                saida.observacao = str(observacao or "").upper() if observacao else None
                saida.local_servico = str(local_servico_geral or "").upper() if local_servico_geral else None
                apply_operational_context(
                    saida,
                    activity=operational_context.get("atividade_operacional"),
                    order=operational_context.get("ordem_servico"),
                    cost_center=operational_context.get("centro_custo"),
                )

                # Se tiver parâmetro de embalagem, adicionar (caso modelo suporte)
                if em_embalagens is not None and hasattr(saida, 'em_embalagens'):
                    saida.em_embalagens = em_embalagens

                db.session.add(saida)
                ledger_results.append((ledger_result, saida))
                
                # Se for ferramenta, criar registro em retiradas_ferramentas
                try:
                    if is_tool_item:
                        retirada = RetiradaFerramenta(
                            codigo_item=item.codigo_item,
                            matricula=usuario.matricula,
                            quantidade=int(quantidade or 1),
                            local_servico=str(local_servico_geral or '').upper() if local_servico_geral else None,
                            observacao=str(observacao or '').upper() if observacao else None,
                            status='em_uso',
                        )
                        db.session.add(retirada)
                except ValueError as ve:
                    # Exceção de validação deve retornar erro
                    raise ve
                except Exception as e:
                    # Outros erros apenas logam mas não interrompem
                    current_app.logger.warning(f"Erro ao criar RetiradaFerramenta para {item.codigo_item}: {e}")
                
                db.session.flush()

                # Confirma o savepoint deste item (outer commit acontece ao final)
                try:
                    savepoint.commit()
                except Exception:
                    # Se falhar aqui, cai no except geral abaixo
                    raise
                
                saida_id = saida.id_saida
                if saida_id:
                    saidas_criadas.append(saida_id)
                    resultados.append({
                        "index": idx,
                        "codigo": codigo,
                        "success": True,
                        "descricao": item.descricao,
                        "quantidade": quantidade
                    })
                else:
                    resultados.append({
                        "index": idx,
                        "codigo": codigo,
                        "success": False,
                        "message": "Erro ao criar saída"
                    })
            except Exception as e:
                if savepoint is not None:
                    try:
                        savepoint.rollback()
                    except Exception:
                        pass
                resultados.append({
                    "index": idx,
                    "codigo": codigo,
                    "success": False,
                    "message": str(e)
                })
        
        if not saidas_criadas:
            return jsonify({
                "success": False,
                "message": "Nenhum item foi processado com sucesso",
                "resultados": resultados
            }), 400
        
        # Commit das saídas
        db.session.commit()
        for ledger_result, saida in ledger_results:
            if ledger_result is not None:
                ledger_result.metadata["reference_id"] = str(saida.id_saida)
                inventory_service.finalize_ledger_mirror(ledger_result)
        
        # Enviar notificação via router (Telegram -> failover GalintNotify)
        try:
            from ..services.notification_router import NotificationRouterService

            if len(saidas_criadas) > 1:
                NotificationRouterService.route_multiple_withdrawal(saidas_criadas)
            elif len(saidas_criadas) == 1:
                NotificationRouterService.route_withdrawal(saidas_criadas[0], force_single=True)
        except Exception as e:
            # Não bloquear a operação por falha na notificação
            pass
        
        return jsonify({
            "success": True,
            "message": f"{len(saidas_criadas)} item(ns) registrado(s) com sucesso",
            "resultados": resultados
        }), 201
        
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Erro interno: {str(exc)}"}), 500


@blueprint.post("/saida")
@login_required
def registrar_saida():
    _require_admin()
    codigo_raw = request.form.get("codigo")
    codigo = (codigo_raw or "").strip() if codigo_raw is not None else ""
    identificador = request.form.get("usuario")
    quantidade = _parse_quantidade(request.form.get("quantidade"))
    obs_raw = request.form.get("observacao")
    observacao = (obs_raw or "").strip() if obs_raw is not None else None
    local_raw = request.form.get("local_servico")
    local_servico = (local_raw or "").strip() if local_raw is not None else None
    operational_context = _collect_operational_context(request.form)
    
    # Novo: processar sistema de embalagens
    em_embalagens_raw = request.form.get("em_embalagens")
    em_embalagens = None
    if em_embalagens_raw is not None:
        em_embalagens = em_embalagens_raw == "1"
    
    # Novo: processar unidade fracionada (kg ou litro)
    unidade_fracionada = _normalize_saida_unit_code(request.form.get("unidade_fracionada"))

    try:
        usuario = _resolve_usuario(identificador)
        item_info = inventory_service.get_item(codigo)
        if not item_info:
            raise ValueError("Item não encontrado")
        item_model = db.session.get(Item, codigo)

        # Obter categoria para uso posterior (notificações e alertas)
        categoria = (item_info.get("categoria") or "").strip().lower()
        
        # Processar unidade fracionada (kg ou litro)
        # IMPORTANTE: Não converter para embalagens! O serviço de embalagens já faz isso automaticamente
        quantidade_convertida = quantidade
        modo_fracionado = bool(unidade_fracionada)
        quantidade_retirada_em_litros = None
        quantidade_retirada_em_quilos = None
        if unidade_fracionada:
            # Para kg: enviar direto em kg (unidades base)
            if unidade_fracionada == 'kg':
                quantidade_convertida = quantidade  # Ex: 0.4 kg
                em_embalagens = False  # Indicar que é em unidades base (kg, não baldes)
                quantidade_retirada_em_quilos = quantidade
                if not observacao:
                    observacao = f"Retirada fracionada: {quantidade} kg"
            # Para litros: enviar direto em litros (unidades base)
            elif unidade_fracionada == 'litro':
                quantidade_convertida = quantidade  # Ex: 2.5 litros
                em_embalagens = False  # Indicar que é em unidades base (litros, não latas)
                quantidade_retirada_em_litros = quantidade
                if not observacao:
                    observacao = f"Retirada fracionada: {quantidade} L"
            elif unidade_fracionada in {'metro', 'cm'}:
                if item_model is None:
                    raise ValueError("Item não encontrado")
                from_unit = 'cm' if unidade_fracionada == 'cm' else 'm'
                try:
                    conversion = unit_conversion_engine.convert_item_to_base(item_model, quantidade, from_unit)
                except UnitConversionError as exc:
                    raise ValueError(str(exc)) from exc
                quantidade_convertida = float(conversion.quantity_base or 0.0)
                em_embalagens = False
                if unidade_fracionada == 'cm':
                    observacao = (
                        f"Retirada fracionada: {quantidade_convertida:g} M | "
                        f"quantidade original informada: {quantidade:g} CM"
                    )
                elif not observacao or str(observacao).strip().lower().startswith('retirada fracionada:'):
                    observacao = f"Retirada fracionada: {quantidade_convertida:g} M"

        payload_kwargs: dict[str, Any] = {
            "codigo": codigo,
            "quantidade": quantidade_convertida,
            "matricula": usuario.id,
            "observacao": observacao,
            "local_servico": local_servico,
            "atividade_operacional": operational_context.get("atividade_operacional"),
            "ordem_servico": operational_context.get("ordem_servico"),
            "centro_custo": operational_context.get("centro_custo"),
            "em_embalagens": em_embalagens,
            "modo_fracionado": modo_fracionado,
            "quantidade_retirada_em_litros": quantidade_retirada_em_litros,
            "quantidade_retirada_em_quilos": quantidade_retirada_em_quilos,
            "canal_saida": "fracionado" if modo_fracionado else "materiais",
        }

        payload = MovimentoPayload(**payload_kwargs)
        saida_id = inventory_service.registrar_saida(payload)
        
        # Notificação Telegram já é enviada automaticamente dentro de inventory_service.registrar_saida()
        
        # Se for requisição AJAX (feita pelo JavaScript), retornar JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
            return jsonify({"success": True, "message": "Saída registrada com sucesso."}), 200
        
        flash("Saída registrada com sucesso.", "success")
    except ValueError as exc:
        # Se for requisição AJAX, retornar erro em JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
            return jsonify({"success": False, "error": str(exc)}), 400
        
        flash(str(exc), "danger")
    referrer = str(request.referrer or "")
    if "/movimentos/saida-fracionada/page" in referrer:
        return redirect(url_for("movements.saida_fracionada_page"))
    return redirect(url_for("movements.saida_page"))


@blueprint.get("/item-info/<codigo>")
@login_required
def item_info(codigo: str):
    """Retorna informações do item (para modal de embalagens e detalhes de líquidos)."""
    _require_admin()
    codigo = (codigo or "").strip()
    if not codigo:
        return jsonify({"found": False}), 400
    item = inventory_service.get_item(codigo)
    if not item:
        return jsonify({"found": False}), 404
    canonical_code = str(item.get("codigo") or codigo).strip() or codigo
    item_model = db.session.get(Item, canonical_code)
    
    liquid_type = _detect_liquid_type(categoria=item.get("categoria"), descricao=item.get("descricao"))
    fractional_info = _infer_fractional_item(item)
    return_quantity_config = _resolve_return_quantity_config(item, fractional_info=fractional_info)
    return_unit_options, primary_return_unit = _resolve_primary_return_unit_option(
        item_model=item_model,
        fallback_config=return_quantity_config,
    )
    default_return_unit = str(primary_return_unit.get("unit_code") or return_quantity_config.get("unit_code") or "unidade")
    package_name = _infer_package_name(item)
    unit_context = _build_saida_unit_context(item, item_model)
    package_capacity = float(unit_context.get("capacidade_embalagem") or 0.0)
    package_name_plural = _pluralize_package_name(package_name)
    saldo_total = _as_positive_float(item.get("saldo"))
    foto_path = item.get("foto_path")
    fractional_unit_factors = _build_fractional_unit_factors(item_model, default_return_unit)
    categoria_norm = _normalize_text(item.get("categoria"))
    supports_material_return = "ferrament" not in categoria_norm
    pending_return = None
    pending_return_by_unit: dict[str, float] = {}
    usuario_encontrado = None
    identificador = (request.args.get("matricula") or request.args.get("usuario") or "").strip()
    retirada_pendente = None
    retirada_pendente_por_unidade: dict[str, float] = {}
    if identificador and supports_material_return:
        try:
            usuario = _resolve_usuario(identificador)
            usuario_encontrado = True
            pending_return_by_unit = {
                str(option.get("unit_code") or ""): inventory_service.get_material_return_pending(
                    codigo=canonical_code,
                    matricula=usuario.matricula,
                    unit_code=str(option.get("unit_code") or ""),
                )
                for option in return_unit_options
                if str(option.get("unit_code") or "")
            }
            pending_return = pending_return_by_unit.get(default_return_unit, 0.0)
        except ValueError:
            pending_return = 0.0
            usuario_encontrado = False

    if supports_material_return:
        retirada_pendente = inventory_service.get_latest_material_return_holder(
            codigo=canonical_code,
            unit_code=default_return_unit,
        )
        if retirada_pendente:
            retirada_pendente_por_unidade = {
                str(option.get("unit_code") or ""): inventory_service.get_material_return_pending(
                    codigo=canonical_code,
                    matricula=str(retirada_pendente.get("matricula") or ""),
                    unit_code=str(option.get("unit_code") or ""),
                )
                for option in return_unit_options
                if str(option.get("unit_code") or "")
            }
            if not identificador:
                pending_return_by_unit = dict(retirada_pendente_por_unidade)
                pending_return = pending_return_by_unit.get(default_return_unit, 0.0)

    movement_unit_label = unit_context.get("devolucao_unidade_label") or item.get("unidade")
    financial_reference = operation_visual_payload_service.resolve_item_financial_reference(item_model)
    movement_balance_display = _build_saida_balance_display(
        item,
        unit_context,
        balance_key="saldo",
        fallback_key="saldo_display",
    )
    movement_available_display = _build_saida_balance_display(
        item,
        unit_context,
        balance_key="saldo_disponivel",
        fallback_key="saldo_disponivel_display",
    )

    response = {
        "found": True,
        "codigo": canonical_code,
        "descricao": item.get("descricao"),
        "categoria": item.get("categoria"),
        "marca": item.get("marca"),
        "unidade": movement_unit_label,
        "unidade_cadastro": item.get("unidade"),
        "saldo": item.get("saldo"),
        "saldo_display": movement_balance_display,
        "saldo_disponivel": item.get("saldo_disponivel"),
        "saldo_disponivel_display": movement_available_display,
        "is_available": item.get("is_available"),
        "unavailable_reason": item.get("unavailable_reason"),
        "unavailable_detail": item.get("unavailable_detail"),
        "has_open_repair": item.get("has_open_repair"),
        "saldo_total_fracionado": saldo_total,
        "tipo_embalagem_novo": item.get("tipo_embalagem_novo"),
        "unidades_por_embalagem": item.get("unidades_por_embalagem"),
        "grandeza_referencia": item.get("grandeza_referencia"),
        "litros_por_embalagem": item.get("litros_por_embalagem"),
        "saldo_embalagens": item.get("saldo_embalagens"),
        "saldo_unidades_soltas": item.get("saldo_unidades_soltas"),
        "permite_saida_fracionada": str(unit_context.get("devolucao_unidade_codigo") or "") in {"litro", "quilo", "metro"},
        "fracao_unidade_padrao": unit_context.get("fracao_unidade_padrao"),
        "fracao_origem": fractional_info.get("source"),
        "nome_embalagem": item_model.get_nome_embalagem() if item_model and item_model.tipo_embalagem_novo else package_name,
        "nome_embalagem_plural": item_model.get_nome_embalagem_plural() if item_model and item_model.tipo_embalagem_novo else package_name_plural,
        "capacidade_embalagem": package_capacity,
        "devolucao_permite_decimal": unit_context.get("devolucao_permite_decimal"),
        "devolucao_unidade_codigo": unit_context.get("devolucao_unidade_codigo") or default_return_unit,
        "devolucao_unidade_exibicao": unit_context.get("devolucao_unidade_exibicao") or primary_return_unit.get("unit_display") or return_quantity_config.get("unit_display"),
        "devolucao_unidade_label": unit_context.get("devolucao_unidade_label") or primary_return_unit.get("unit_label") or return_quantity_config.get("unit_label"),
        "devolucao_step": unit_context.get("devolucao_step") or primary_return_unit.get("input_step") or return_quantity_config.get("input_step"),
        "devolucao_min": unit_context.get("devolucao_min") or primary_return_unit.get("input_min") or return_quantity_config.get("input_min"),
        "devolucao_unidade_fator_base": unit_context.get("devolucao_unidade_fator_base"),
        "devolucao_pendente": pending_return,
        "devolucao_pendente_por_unidade": pending_return_by_unit,
        "retirada_pendente": {
            "matricula": retirada_pendente.get("matricula"),
            "nome": retirada_pendente.get("nome"),
            "label": retirada_pendente.get("label"),
            "ultima_saida_em": TimeService.isoformat_utc(retirada_pendente.get("ultima_saida_em")),
            "ultima_saida_label": retirada_pendente.get("ultima_saida_label"),
            "local_servico": retirada_pendente.get("local_servico"),
            "atividade_operacional": retirada_pendente.get("atividade_operacional"),
            "pendente_por_unidade": retirada_pendente_por_unidade,
            "pendente": retirada_pendente_por_unidade.get(default_return_unit, retirada_pendente.get("pendente")),
        } if retirada_pendente else None,
        "devolucao_unidades_opcoes": return_unit_options,
        "usuario_encontrado": usuario_encontrado,
        "suporta_devolucao_material": supports_material_return,
        "unidade_exibicao_total": unit_context.get("unidade_exibicao_total") or primary_return_unit.get("unit_display") or return_quantity_config.get("unit_display") or (item.get("unidade") or "un"),
        "permite_saida_em_embalagens": unit_context.get("permite_saida_em_embalagens"),
        "foto_path": foto_path,
        "foto_url": url_for("static", filename=foto_path) if foto_path else None,
        "fracao_fatores_base": fractional_unit_factors,
        "valor_referencia": financial_reference,
        "preco_reposicao_fonte": item.get("preco_reposicao_fonte"),
        "preco_reposicao_uf": item.get("preco_reposicao_uf"),
        "preco_reposicao_query": item.get("preco_reposicao_query"),
        "preco_reposicao_url": item.get("preco_reposicao_url"),
    }
    if liquid_type:
        response.update(
            {
                "tipo_id": liquid_type["id"],
                "tipo_label": liquid_type["label"],
            }
        )
    return jsonify(response)


@blueprint.get('/saida/page')
@login_required
def saida_page():
    """Página separada para Registro de Saída (formulário com campo de observações)."""
    _require_admin()
    return render_mako_template(
        'movements/saida.mako',
        usuarios=user_service.list_users(),
        itens=[],
        liquid_types=LIQUID_PRODUCT_TYPES,
        liquid_fractions=LIQUID_FRACTIONS,
    )


@blueprint.get('/painel-espelho')
def painel_espelho_page():
    """Tela dedicada para segundo monitor com o estado visual da operação."""
    mode = _normalize_mirror_mode(request.args.get("mode"))
    access_response = _ensure_mirror_panel_html_access(mode)
    if access_response is not None:
        return access_response
    return render_template('movements/painel_espelho.html', mirror_mode=mode)


@blueprint.get('/painel-espelho/insights')
def painel_espelho_insights_api():
    """Retorna os destaques operacionais rotativos do painel espelho."""
    mode = _normalize_mirror_mode(request.args.get("mode"))
    _ensure_mirror_panel_json_access(mode)
    return jsonify(mirror_insights_service.build_payload(mode=mode))


@blueprint.get('/painel-espelho/state')
def painel_espelho_state_api():
    """Retorna o ultimo estado visual compartilhado com o painel espelho."""
    mode = _normalize_mirror_mode(request.args.get("mode"))
    _ensure_mirror_panel_json_access(mode)
    return jsonify(mirror_state_service.get_state(mode=mode))


@blueprint.get('/painel-espelho/custody-active')
def painel_espelho_custody_active_api():
    """Retorna a custodia diaria ativa para exibicao no painel espelho."""
    mode = _normalize_mirror_mode(request.args.get("mode"))
    _ensure_mirror_panel_json_access(mode)

    from ..services.tool_custody_service import tool_custody_service

    itens = tool_custody_service.get_daily_custody_feed_items()
    for item in itens:
        foto_path = item.pop("foto_path", None)
        item["foto_url"] = url_for("static", filename=foto_path) if foto_path else None

    return jsonify({"items": itens})


@blueprint.post('/painel-espelho/state')
@login_required
def painel_espelho_state_publish_api():
    """Recebe o estado visual da operacao para navegadores e janela nativa."""
    _require_admin()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "message": "Payload invalido"}), 400

    mode = str(payload.get("kind") or "").strip().lower()
    if mode not in {"saida", "entrada", "ferramenta", "fracionada"}:
        return jsonify({"success": False, "message": "Tipo de operacao invalido"}), 400

    state = mirror_state_service.publish(payload)
    return jsonify({"success": True, "state": state})


@blueprint.post('/painel-espelho/native-open')
@login_required
def painel_espelho_native_open_api():
    """Abre o painel espelho em janela nativa na maquina local."""
    _require_admin()
    payload = request.get_json(silent=True)
    request_data = payload if isinstance(payload, dict) else request.form
    mode = _normalize_mirror_mode((request_data or {}).get("mode"))

    token = create_mirror_panel_token(current_user, mode=mode)
    panel_kwargs: dict[str, Any] = {"_external": True, "native_token": token}
    if mode:
        panel_kwargs["mode"] = mode
    panel_url = url_for('movements.painel_espelho_page', **panel_kwargs)
    title = f"{current_app.config.get('SYSTEM_NAME', 'GALINT')} - Painel do colaborador"
    result = launch_native_panel(panel_url, title)
    status_code = 200 if result.get("success") else 503
    return jsonify(result), status_code


@blueprint.get('/saida-fracionada/page')
@login_required
def saida_fracionada_page():
    """Página separada para Registro de Saída Fracionada (entrada manual via balança/pesagem)."""
    can_manage = bool(getattr(current_user, "is_admin", False))
    return render_mako_template(
        'movements/saida_fracionada.mako',
        usuarios=user_service.list_users(),
        itens=[],
        can_manage=can_manage,
        operational_activity_options=OPERATIONAL_ACTIVITY_OPTIONS,
    )


@blueprint.get('/entrada/page')
@login_required
def entrada_page():
    """Página separada para Registro de Devolução."""
    _require_admin()
    codigo_prefill = (request.args.get("codigo") or "").strip()
    return render_template(
        'movements/entrada.html',
        codigo_prefill=codigo_prefill,
        usuarios=user_service.list_users(),
        itens=[],
    )


@blueprint.get('/api/devolucao-expressa/colaboradores')
@login_required
def devolucao_expressa_collaborators_payload():
    _require_admin()
    scope = (request.args.get("scope") or "").strip() or "todos"
    window = _build_express_return_window()
    payload: dict[str, Any] = {
        "success": True,
        "scope": scope,
        "window_open": bool(window["window_open"]),
        "window_cutoff_label": window["cutoff_label"],
        "today_label": window["today_label"],
        "collaborators": [],
        "collaborators_count": 0,
        "message": None,
    }

    if not window["window_open"]:
        payload["message"] = f"A janela da devolução expressa encerrou às {window['cutoff_label']}."
        return jsonify(payload)

    collaborators = inventory_service.list_express_material_return_collaborators(
        start_datetime=window["start_utc"],
        end_datetime=window["end_utc"],
        scope=scope,
    )
    payload["collaborators"] = collaborators
    payload["collaborators_count"] = len(collaborators)
    if not collaborators:
        payload["message"] = "Nenhum colaborador com retirada elegível foi encontrado para devolução expressa hoje."
    return jsonify(payload)


@blueprint.get('/api/devolucao-expressa')
@login_required
def devolucao_expressa_payload():
    _require_admin()
    identificador = (request.args.get("usuario") or request.args.get("matricula") or "").strip()
    scope = (request.args.get("scope") or "").strip() or "todos"
    window = _build_express_return_window()
    payload: dict[str, Any] = {
        "success": True,
        "scope": scope,
        "window_open": bool(window["window_open"]),
        "window_cutoff_label": window["cutoff_label"],
        "today_label": window["today_label"],
        "items": [],
        "items_count": 0,
        "usuario": None,
        "message": None,
    }

    if not identificador:
        payload["message"] = "Informe o colaborador para carregar as retiradas elegíveis para devolução expressa."
        return jsonify(payload)

    try:
        usuario = _resolve_usuario(identificador)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    payload["usuario"] = {
        "nome": getattr(usuario, "nome", None) or f"Matrícula {usuario.matricula}",
        "matricula": usuario.matricula,
    }

    if not window["window_open"]:
        payload["message"] = f"A janela da devolução expressa encerrou às {window['cutoff_label']}."
        return jsonify(payload)

    items = inventory_service.list_express_material_return_candidates(
        matricula=usuario.matricula,
        start_datetime=window["start_utc"],
        end_datetime=window["end_utc"],
        scope=scope,
    )
    payload["items"] = items
    payload["items_count"] = len(items)
    if not items:
        payload["message"] = "Nenhum material retirado hoje ficou elegível para devolução expressa neste colaborador."
    return jsonify(payload)


@blueprint.post('/api/devolucao-expressa')
@login_required
def registrar_devolucao_expressa():
    _require_admin()
    data = request.get_json(silent=True)
    source = data if isinstance(data, dict) else request.form

    identificador = (source.get("usuario") or source.get("matricula") or "").strip()
    codigo = (source.get("codigo") or "").strip()
    observacao = (source.get("observacao") or "").strip() or "Devolução expressa via tela de saída"
    from_unit = (source.get("from_unit") or source.get("unidade_devolucao") or "").strip() or None
    quantidade = _parse_quantidade(source.get("quantidade"))

    if not identificador:
        return jsonify({"success": False, "error": "Informe o colaborador da devolução expressa."}), 400
    if not codigo:
        return jsonify({"success": False, "error": "Informe o item que será devolvido."}), 400

    window = _build_express_return_window()
    if not window["window_open"]:
        return jsonify({"success": False, "error": f"A janela da devolução expressa encerrou às {window['cutoff_label']}."}), 400

    try:
        retirada_matricula, devolvedor = _resolve_devolucao_operadores(source)
        usuario = _resolve_usuario(identificador)
        unit_options = inventory_service.get_material_return_unit_options(codigo=codigo)
        selected_unit = from_unit or str(unit_options[0].get("unit_code") or "unidade") if unit_options else (from_unit or "unidade")
        unit_meta = next(
            (option for option in unit_options if str(option.get("unit_code") or "") == selected_unit),
            unit_options[0] if unit_options else {"unit_code": selected_unit, "unit_display": selected_unit, "unit_label": selected_unit.title()},
        )
        pendente_express = inventory_service.get_material_return_pending_in_window(
            codigo=codigo,
            matricula=usuario.matricula,
            start_datetime=window["start_utc"],
            end_datetime=window["end_utc"],
            unit_code=selected_unit,
        )
        if pendente_express <= 1e-9:
            raise ValueError("Este item não está mais elegível para devolução expressa hoje.")

        quantidade_final = float(quantidade or 0.0)
        if quantidade_final <= 0:
            quantidade_final = pendente_express
        if quantidade_final > pendente_express + 1e-9:
            raise ValueError(
                f"A devolução expressa excede o pendente de hoje. Limite: {pendente_express:g} {unit_meta.get('unit_display')}."
            )

        evento = inventory_service.registrar_devolucao_material(
            codigo=codigo,
            quantidade=quantidade_final,
            matricula=usuario.matricula,
            retirada_matricula=retirada_matricula or usuario.matricula,
            devolvido_por_matricula=devolvedor.matricula,
            from_unit=selected_unit,
            observacao=observacao,
            commit=True,
        )
        try:
            NotificationRouterService.route_inventory_event(evento.id_evento)
        except Exception:
            pass

        pendente_restante = inventory_service.get_material_return_pending_in_window(
            codigo=codigo,
            matricula=usuario.matricula,
            start_datetime=window["start_utc"],
            end_datetime=window["end_utc"],
            unit_code=selected_unit,
        )
        return jsonify(
            {
                "success": True,
                "message": "Devolução expressa registrada com sucesso.",
                "codigo": codigo,
                "matricula": usuario.matricula,
                "quantidade_registrada": round(float(quantidade_final), 3),
                "unidade": unit_meta.get("unit_display"),
                "pendente_restante": round(float(pendente_restante), 3),
            }
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@blueprint.post("/entrada")
@login_required
def registrar_entrada():
    """Registra entrada e garante atualização no histórico de entradas."""
    _require_admin()
    codigo = (request.form.get("codigo") or "").strip()
    identificador = request.form.get("usuario")
    quantidade = _parse_quantidade(request.form.get("quantidade"))
    nota_fiscal = (request.form.get("nota_fiscal") or "").strip() or None
    
    # Capturar tipo de entrada para unidades dinâmicas
    tipo_entrada = request.form.get("tipo_entrada")  # "embalagem" ou "unidades"
    em_embalagens = None
    if tipo_entrada == "embalagem":
        em_embalagens = True
    elif tipo_entrada == "unidades":
        em_embalagens = False
    # Se tipo_entrada não foi enviado (item sem unidades dinâmicas), em_embalagens fica None

    try:
        usuario = _resolve_usuario(identificador)
        inventory_service.registrar_entrada(
            MovimentoPayload(
                codigo=codigo,
                quantidade=quantidade,
                matricula=usuario.id,
                nota_fiscal=nota_fiscal,
                em_embalagens=em_embalagens,
            )
        )
        flash("Entrada registrada.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("movements.entrada_page"))


@blueprint.post("/devolucao")
@login_required
def registrar_devolucao():
    _require_admin()
    codigo_raw = request.form.get("codigo")
    codigo = (codigo_raw or "").strip() if codigo_raw is not None else ""
    quantidade = _parse_quantidade(request.form.get("quantidade"))
    from_unit_raw = request.form.get("from_unit") or request.form.get("unidade_devolucao")
    from_unit = (from_unit_raw or "").strip() if from_unit_raw is not None else None
    obs_raw = request.form.get("observacao")
    observacao = (obs_raw or "").strip() if obs_raw is not None else None

    try:
        retirada_matricula, devolvedor = _resolve_devolucao_operadores(request.form)
        evento = inventory_service.registrar_devolucao_material(
            codigo=codigo,
            quantidade=quantidade,
            matricula=retirada_matricula or devolvedor.matricula,
            retirada_matricula=retirada_matricula,
            devolvido_por_matricula=devolvedor.matricula,
            from_unit=from_unit,
            observacao=observacao,
            commit=True,
        )
        try:
            NotificationRouterService.route_inventory_event(evento.id_evento)
        except Exception:
            pass

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.accept_json:
            return jsonify({"success": True, "message": "Devolução registrada com sucesso."}), 200

        flash("Devolução registrada com sucesso.", "success")
    except ValueError as exc:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.accept_json:
            return jsonify({"success": False, "error": str(exc)}), 400
        flash(str(exc), "danger")

    return redirect(url_for("movements.entrada_page", codigo=codigo or None))





@blueprint.get('/alertas-estoque/pdf')
@login_required
def gerar_pdf_alertas_estoque():
    """Gera e faz download de PDF com alertas de estoque."""
    _require_admin()
    
    try:
        pdf_info = entrada_service.generate_alertas_estoque_pdf()
        
        return send_file(
            pdf_info['path'],
            as_attachment=True,
            download_name=pdf_info['filename']
        )
    
    except Exception as e:
        flash(f'Erro ao gerar PDF: {str(e)}', 'danger')
        return redirect(url_for('dashboard.index'))

