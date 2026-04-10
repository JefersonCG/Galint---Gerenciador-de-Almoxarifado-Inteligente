"""Inventory CRUD routes."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import json

from io import BytesIO

from flask import Blueprint, abort, current_app, flash, jsonify, make_response, redirect, render_template, request, send_file, session, url_for
from flask_login import login_required, current_user
from sqlalchemy import and_, func, or_

from ..extensions import db
from ..models import DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, FinanceLedgerEntry, Item, Usuario
from ..services.category_catalog import (
    DEFAULT_INVENTORY_CATEGORY_NAME,
    category_catalog_service,
)
from ..services.config_service import ConfigService
from ..services.finance_service import _build_document_item_display_metadata, finance_service
from ..services.inventory import (
    BASE_ITEM_UNIT_OPTIONS,
    OPERATIONAL_ACTIVITY_OPTIONS,
    MovimentoPayload,
    inventory_service,
    normalize_operational_activity,
    normalize_operational_text,
    resolve_item_base_unit_label,
)
from ..services.item_foto_service import ItemFotoService
from ..services.price_normalization import infer_price_unit_for_item, normalize_item_price
from ..services.price_suggestion_service import price_suggestion_service
from ..services.telegram_service import TelegramService
from ..services.inventory_category_summary import build_category_balance_summary, build_category_value_summary
from ..utils.barcode_generator import generate_barcode, get_barcode_path
from ..utils.time_service import TimeService
from .movements import LIQUID_PRODUCT_TYPES

blueprint = Blueprint("inventory", __name__, url_prefix="/itens")


def _uses_packaging_system(item_data: dict | None) -> bool:
    if not item_data:
        return False
    tipo = (item_data.get("tipo_embalagem_novo") or "").strip().lower()
    if tipo not in {"lata", "rolo", "pacote", "caixa", "fardo", "litro", "balde", "bombona", "saco"}:
        return False
    for key in ("unidades_por_embalagem", "litros_por_embalagem", "grandeza_referencia"):
        try:
            if float(item_data.get(key) or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _collect_operational_context(source) -> dict[str, str | None]:
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


def _require_admin() -> None:
    if not bool(getattr(current_user, "is_admin", False)):
        abort(403)


def _is_admin(user) -> bool:
    if not user:
        return False
    value = getattr(user, "is_admin", False)
    if isinstance(value, str):
        return value.strip() in ("1", "true", "True", "TRUE")
    return bool(value)


def _is_supervisor(user) -> bool:
    if not user:
        return False
    setor = (getattr(user, "setor", "") or "").strip().lower()
    cargo = (getattr(user, "cargo", "") or "").strip().lower()
    return "supervisor" in setor or "supervisor" in cargo


def _require_admin_or_supervisor() -> None:
    if not (_is_admin(current_user) or _is_supervisor(current_user)):
        abort(403)


def _finance_unlock_session_key() -> str:
    return "inventory_finance_unlocks"


def _get_finance_unlocks() -> dict[str, bool]:
    raw = session.get(_finance_unlock_session_key())
    if not isinstance(raw, dict):
        return {}
    return {str(key): bool(value) for key, value in raw.items() if key}


def _set_finance_unlock(codigo: str, unlocked: bool = True) -> None:
    codigo_norm = (codigo or "").strip()
    if not codigo_norm:
        return
    unlocks = _get_finance_unlocks()
    if unlocked:
        unlocks[codigo_norm] = True
    else:
        unlocks.pop(codigo_norm, None)
    session[_finance_unlock_session_key()] = unlocks
    session.modified = True


def _can_edit_finance_section(codigo: str | None, *, user=None) -> bool:
    if _is_admin(user or current_user):
        return True
    codigo_norm = (codigo or "").strip()
    if not codigo_norm:
        return False
    return bool(_get_finance_unlocks().get(codigo_norm))


def _clear_document_runtime_cache(document_numbers: list[str] | None = None) -> None:
    try:
        inventory_service.clear_runtime_cache("list_items")
        inventory_service.clear_runtime_cache("dashboard_snapshot")
        inventory_service.clear_runtime_cache("list_notas_fiscais:")
        finance_service.clear_runtime_cache("list_stock_documents:")
        if document_numbers:
            for numero in document_numbers:
                numero_norm = str(numero or "").strip()
                if not numero_norm:
                    continue
                inventory_service.clear_runtime_cache(f"get_nota_fiscal:{numero_norm}")
                finance_service.clear_runtime_cache(f"get_stock_document_by_number:{numero_norm}")
        else:
            inventory_service.clear_runtime_cache("get_nota_fiscal:")
            finance_service.clear_runtime_cache("get_stock_document_by_number:")
    except Exception:
        pass


def _json_no_store(payload: dict[str, object]):
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _load_linked_document_context(item_data: dict | None) -> dict[str, object]:
    if not item_data:
        return {}

    raw_document_item_id = item_data.get("pre_cadastro_documento_item_id")
    try:
        document_item_id = int(raw_document_item_id)
    except (TypeError, ValueError):
        return {}

    document_item = db.session.get(DocumentoEntradaEstoqueItem, document_item_id)
    if document_item is None or document_item.documento is None:
        return {}

    documento = document_item.documento
    return {
        "nota_fiscal": documento.numero_documento,
        "preco_compra_documento": documento.numero_documento,
        "preco_compra_chave_acesso": documento.chave_acesso,
        "preco_compra_data_emissao": documento.data_emissao.isoformat() if documento.data_emissao else None,
        "preco_compra_data_recebimento": documento.data_recebimento.isoformat() if documento.data_recebimento else None,
        "finance_tipo_documento": documento.tipo_documento,
    }


def _current_actor_name() -> str | None:
    return (
        getattr(current_user, "nome", None)
        or getattr(current_user, "matricula", None)
        or getattr(current_user, "id", None)
    )


def _inventory_category_options(selected_name: str | None = None) -> list[str]:
    try:
        return category_catalog_service.list_form_choices(selected_name=selected_name)
    except Exception:
        fallback = (selected_name or "").strip() or DEFAULT_INVENTORY_CATEGORY_NAME
        return [fallback]


def _build_category_admin_rows() -> list[dict[str, object]]:
    stats: dict[str, dict[str, float | int]] = defaultdict(lambda: {"total": 0, "saldo_total": 0.0})
    for item in inventory_service.list_items():
        category_name = str(item.get("categoria") or "Sem categoria").strip() or "Sem categoria"
        stats[category_name]["total"] = int(stats[category_name]["total"] or 0) + 1
        try:
            stats[category_name]["saldo_total"] = float(stats[category_name]["saldo_total"] or 0.0) + float(item.get("saldo") or 0.0)
        except (TypeError, ValueError):
            pass

    rows: list[dict[str, object]] = []
    for category in category_catalog_service.list_categories(include_inactive=True):
        row_stats = stats.get(category.nome, {"total": 0, "saldo_total": 0.0})
        rows.append(
            {
                "id": category.id,
                "nome": category.nome,
                "descricao": category.descricao,
                "ordem": int(category.ordem or 0),
                "ativa": bool(category.ativa),
                "sistema": bool(category.sistema),
                "criada_por": category.criada_por,
                "atualizada_por": category.atualizada_por,
                "total_itens": int(row_stats.get("total") or 0),
                "saldo_total": round(float(row_stats.get("saldo_total") or 0.0), 1),
            }
        )
    return rows


def _reset_inventory_category_cache() -> None:
    inventory_service.clear_runtime_cache()




def _sync_finance_section_snapshot(
    *,
    codigo: str,
    categoria: str,
    preco_compra_unitario: object,
    usuario_id: str | None,
    finance_payload: dict[str, object],
) -> None:
    finance_service.set_item_supplier_preference(
        codigo,
        int(finance_payload["supplier_id"]) if finance_payload.get("supplier_id") else None,
        origem=str(finance_payload.get("origem_valor") or ""),
        atualizado_por=usuario_id,
    )

    item_model = Item.query.get(codigo)

    latest_entry = (
        FinanceLedgerEntry.query
        .filter(FinanceLedgerEntry.codigo_item == codigo)
        .order_by(FinanceLedgerEntry.data_lancamento.desc(), FinanceLedgerEntry.id.desc())
        .first()
    )

    try:
        unit_price = float(preco_compra_unitario) if preco_compra_unitario not in (None, "") else None
    except (TypeError, ValueError):
        unit_price = None

    unit_price_base = unit_price
    unidade_preco = None
    fator_preco_base = None
    if item_model is not None and unit_price is not None:
        unidade_preco = (getattr(item_model, "preco_compra_unidade_preco", None) or "").strip().lower() or infer_price_unit_for_item(item_model)
        try:
            normalized = normalize_item_price(
                item_model,
                unit_price=unit_price,
                price_unit=unidade_preco,
            )
            unit_price_base = float(normalized.unit_price_base)
            unidade_preco = normalized.price_unit
            fator_preco_base = float(normalized.factor_to_base)
        except Exception:
            fallback_unidade_preco = infer_price_unit_for_item(item_model)
            if fallback_unidade_preco != unidade_preco:
                try:
                    normalized = normalize_item_price(
                        item_model,
                        unit_price=unit_price,
                        price_unit=fallback_unidade_preco,
                    )
                    unit_price_base = float(normalized.unit_price_base)
                    unidade_preco = normalized.price_unit
                    fator_preco_base = float(normalized.factor_to_base)
                except Exception:
                    unit_price_base = unit_price
                    fator_preco_base = 1.0
            else:
                unit_price_base = unit_price
                fator_preco_base = 1.0

    if latest_entry is None:
        latest_entry = FinanceLedgerEntry(
            codigo_item=codigo,
            categoria_nome=str(categoria or "Sem categoria"),
            usuario_matricula=usuario_id,
            quantidade=0.0,
            valor_total=0.0,
            data_lancamento=datetime.utcnow(),
        )
        db.session.add(latest_entry)

    latest_entry.fornecedor_id = int(finance_payload["supplier_id"]) if finance_payload.get("supplier_id") else None
    latest_entry.usuario_matricula = usuario_id
    latest_entry.categoria_nome = str(categoria or latest_entry.categoria_nome or "Sem categoria")
    latest_entry.data_lancamento = datetime.utcnow()
    latest_entry.valor_unitario = unit_price
    latest_entry.valor_unitario_base = unit_price_base
    latest_entry.unidade_preco = unidade_preco
    latest_entry.fator_preco_base = fator_preco_base
    if latest_entry.unidade_quantidade in (None, "") and item_model is not None:
        latest_entry.unidade_quantidade = (item_model.unidade or "").strip() or None
    if latest_entry.quantidade_base in (None, ""):
        latest_entry.quantidade_base = float(latest_entry.quantidade or 0.0)
    latest_entry.origem_valor = str(finance_payload.get("origem_valor") or "inventario_inicial")
    latest_entry.tipo_documento = finance_payload.get("tipo_documento")
    latest_entry.numero_documento = finance_payload.get("numero_documento")
    latest_entry.chave_acesso = finance_payload.get("chave_acesso")
    latest_entry.data_emissao_documento = finance_payload.get("data_emissao_documento")
    latest_entry.data_recebimento_documento = finance_payload.get("data_recebimento_documento")
    latest_entry.comprovacao_status = str(finance_payload.get("comprovacao_status") or "sem_comprovacao")
    latest_entry.observacao = finance_payload.get("observacao")
    if latest_entry.quantidade and unit_price is not None:
        latest_entry.valor_total = float(latest_entry.quantidade or 0) * float(unit_price)
    elif latest_entry.quantidade_base and unit_price_base is not None:
        latest_entry.valor_total = float(latest_entry.quantidade_base or 0) * float(unit_price_base)
    elif not latest_entry.quantidade:
        latest_entry.valor_total = 0.0
    db.session.commit()


def _safe_float(value: str | int | float | None) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_text(value) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _parse_advanced_unit_settings(raw_value: str | None) -> dict:
    raw = (raw_value or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _validate_packaging_type_value(tipo_novo: str | None, unidades_var: float | None) -> None:
    tipo_normalizado = (tipo_novo or "").strip().lower()
    try:
        quantidade_por_embalagem = float(unidades_var or 0)
    except (TypeError, ValueError):
        quantidade_por_embalagem = 0.0

    if tipo_normalizado == "litro" and quantidade_por_embalagem > 1.0:
        raise ValueError(
            "Tipo de embalagem invalido para este conteudo. Para recipientes acima de 1 litro, use Lata, Balde ou Bombona em vez de Litro."
        )


def _sanitize_filename_component(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "categoria"
    # manter apenas caracteres seguros para nome de arquivo
    sanitized = []
    for ch in value:
        if ch.isalnum() or ch in ("_", "-", "."):
            sanitized.append(ch)
        elif ch.isspace() or ch in ("/", "\\", ":"):
            sanitized.append("_")
        # ignora o resto
    result = "".join(sanitized).strip("_-")
    return result or "categoria"


def _resolve_replacement_price_uf(raw_uf: str | None = None) -> str:
    uf = (raw_uf or "").strip().upper()
    if uf:
        return uf
    try:
        return (ConfigService.get_empresa_config().endereco_estado or "").strip().upper()
    except Exception:
        return ""


def _build_replacement_price_query(item: Item | dict | None) -> str:
    if isinstance(item, dict):
        descricao = _safe_text(item.get("descricao")).strip()
        marca = _safe_text(item.get("marca")).strip()
        tipo_embalagem = _safe_text(item.get("tipo_embalagem_novo")).strip()
        unidades_por_embalagem = _safe_float(item.get("unidades_por_embalagem"))
    else:
        descricao = _safe_text(getattr(item, "descricao", "")).strip()
        marca = _safe_text(getattr(item, "marca", "")).strip()
        tipo_embalagem = _safe_text(getattr(item, "tipo_embalagem_novo", "")).strip()
        unidades_por_embalagem = _safe_float(getattr(item, "unidades_por_embalagem", 0))

    extra = f" {tipo_embalagem} {int(unidades_por_embalagem) if unidades_por_embalagem.is_integer() else unidades_por_embalagem}" if tipo_embalagem and unidades_por_embalagem > 0 else ""
    return f"{descricao}{f' {marca}' if marca else ''}{extra}".strip()


def _serialize_batch_price_item(item: Item) -> dict[str, object]:
    return {
        "codigo": item.codigo_item,
        "descricao": item.descricao,
        "categoria": item.categoria,
        "marca": item.marca,
        "unidade": item.unidade,
        "tipo_embalagem_novo": item.tipo_embalagem_novo,
        "unidades_por_embalagem": item.unidades_por_embalagem,
        "product_units": [
            {
                "unit_code": unit.unit_code,
                "unit_label": unit.unit_label,
                "dimension": unit.dimension,
                "is_base": bool(unit.is_base),
                "active": bool(unit.active),
            }
            for unit in sorted(item.product_units, key=lambda row: (not bool(row.is_base), (row.unit_code or ""), row.id or 0))
        ],
        "preco_compra_unidade_preco": item.preco_compra_unidade_preco,
        "preco_reposicao_unitario": item.preco_reposicao_unitario,
        "preco_reposicao_unitario_base": item.preco_reposicao_unitario_base,
        "preco_reposicao_unidade_preco": item.preco_reposicao_unidade_preco,
        "preco_reposicao_fator_base": item.preco_reposicao_fator_base,
        "preco_reposicao_fonte": item.preco_reposicao_fonte,
        "preco_reposicao_uf": item.preco_reposicao_uf,
        "preco_reposicao_query": item.preco_reposicao_query,
        "preco_reposicao_url": item.preco_reposicao_url,
        "preco_reposicao_atualizado_em": TimeService.isoformat_utc(item.preco_reposicao_atualizado_em),
        "preco_reposicao_atualizado_por": item.preco_reposicao_atualizado_por,
    }


def _extract_finance_payload(
    form,
    *,
    current_item: dict | None = None,
    inherit_document_metadata: bool = False,
) -> dict[str, object]:
    def _parse_iso_date(value: str | None) -> date | None:
        raw = (value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None

    supplier_raw = (form.get("finance_supplier_id") or "").strip()
    supplier_id = int(supplier_raw) if supplier_raw.isdigit() else None
    origem_valor = (form.get("finance_origem_valor") or "").strip() or "inventario_inicial"
    tipo_documento = (form.get("finance_tipo_documento") or "").strip() or None
    comprovacao = (form.get("finance_comprovacao_status") or "").strip() or None
    observacao = (form.get("finance_observacao") or "").strip() or None
    chave_acesso = (form.get("preco_compra_chave_acesso") or "").strip() or None
    data_emissao = _parse_iso_date(form.get("preco_compra_data_emissao"))
    data_recebimento = _parse_iso_date(form.get("preco_compra_data_recebimento"))

    if current_item:
        if supplier_id is None:
            current_supplier_id = current_item.get("finance_supplier_id")
            try:
                supplier_id = int(current_supplier_id) if current_supplier_id not in (None, "") else None
            except (TypeError, ValueError):
                supplier_id = None
        if not (form.get("finance_origem_valor") or "").strip():
            origem_valor = (current_item.get("finance_origem_valor") or origem_valor)
        if not (form.get("finance_tipo_documento") or "").strip():
            tipo_documento = (current_item.get("finance_tipo_documento") or tipo_documento)
        if not (form.get("finance_comprovacao_status") or "").strip():
            comprovacao = (current_item.get("finance_comprovacao_status") or comprovacao)
        if not observacao:
            observacao = (current_item.get("finance_observacao") or None)
        if inherit_document_metadata and not chave_acesso:
            chave_acesso = (current_item.get("preco_compra_chave_acesso") or None)
        if inherit_document_metadata and data_emissao is None:
            data_emissao = _parse_iso_date(current_item.get("preco_compra_data_emissao"))
        if inherit_document_metadata and data_recebimento is None:
            data_recebimento = _parse_iso_date(current_item.get("preco_compra_data_recebimento"))

    if not comprovacao:
        comprovacao = "comprovado" if tipo_documento in {"nf", "cupom"} else "sem_comprovacao"
    numero_nf = (form.get("nota_fiscal") or "").strip()
    numero_documento = (
        numero_nf
        or (form.get("preco_compra_documento") or "").strip()
        or ((current_item.get("nota_fiscal") if current_item else "") if inherit_document_metadata else "")
        or ((current_item.get("preco_compra_documento") if current_item else "") if inherit_document_metadata else "")
        or None
    )
    return {
        "supplier_id": supplier_id,
        "origem_valor": origem_valor,
        "tipo_documento": tipo_documento,
        "comprovacao_status": comprovacao,
        "observacao": observacao,
        "numero_documento": numero_documento,
        "chave_acesso": chave_acesso,
        "data_emissao_documento": data_emissao,
        "data_recebimento_documento": data_recebimento,
    }


def _should_seed_nf_pre_registration(finance_payload: dict[str, object]) -> bool:
    numero_documento = str(finance_payload.get("numero_documento") or "").strip()
    tipo_documento = str(finance_payload.get("tipo_documento") or "").strip().lower()
    origem_valor = str(finance_payload.get("origem_valor") or "").strip().lower()
    if not numero_documento:
        return False
    if tipo_documento in {"nf", "cupom", "manual", "recibo"}:
        return True
    return origem_valor in {"compra_nf", "compra_cupom", "compra_documento", "valor_estimado"}


def _validate_stock_entry_policy(
    *,
    codigo: str,
    quantidade: float,
    finance_payload: dict[str, object],
    allow_new_document_item: bool = False,
) -> None:
    qty = float(quantidade or 0.0)
    if qty <= 0:
        return

    tipo_documento = (str(finance_payload.get("tipo_documento") or "")).strip().lower()
    comprovacao = (str(finance_payload.get("comprovacao_status") or "sem_comprovacao")).strip().lower() or "sem_comprovacao"
    numero_documento = (str(finance_payload.get("numero_documento") or "")).strip()
    observacao = (str(finance_payload.get("observacao") or "")).strip()
    data_emissao = finance_payload.get("data_emissao_documento")

    if comprovacao in {"sem_comprovacao", "parcial"} and not observacao:
        raise ValueError("Entradas sem comprovação ou parciais exigem observação obrigatória.")

    if comprovacao == "comprovado" and tipo_documento in {"nf", "cupom"}:
        if not numero_documento:
            raise ValueError("Informe o número da NF/cupom para conciliar a entrada no estoque.")
        finance_service.validate_document_backed_stock_entry(
            codigo_item=codigo,
            quantidade=qty,
            numero_documento=numero_documento,
            tipo_documento=tipo_documento,
            data_emissao=data_emissao if isinstance(data_emissao, date) else None,
            allow_new_document_item=allow_new_document_item,
        )


def _validate_document_bridge_request(finance_payload: dict[str, object]) -> None:
    numero_documento = (str(finance_payload.get("numero_documento") or "")).strip()
    tipo_documento = (str(finance_payload.get("tipo_documento") or "")).strip().lower()
    supplier_id = finance_payload.get("supplier_id")
    chave_acesso = (str(finance_payload.get("chave_acesso") or "")).strip()
    data_emissao = finance_payload.get("data_emissao_documento")
    data_recebimento = finance_payload.get("data_recebimento_documento")
    comprovacao_status = (str(finance_payload.get("comprovacao_status") or "")).strip().lower()
    observacao = (str(finance_payload.get("observacao") or "")).strip()

    informed_bridge_data = bool(
        numero_documento
        or tipo_documento
        or chave_acesso
        or data_emissao
        or data_recebimento
        or supplier_id
        or observacao
    )
    if not informed_bridge_data:
        return

    missing_fields: list[str] = []
    if not numero_documento:
        missing_fields.append("número do documento")
    if not tipo_documento:
        missing_fields.append("tipo documental")
    if not supplier_id:
        missing_fields.append("fornecedor")
    if not isinstance(data_recebimento, date):
        missing_fields.append("data de recebimento")
    if tipo_documento == "nf" and not isinstance(data_emissao, date):
        missing_fields.append("data de emissão")
    if tipo_documento == "nf" and not chave_acesso:
        missing_fields.append("chave de acesso")
    if comprovacao_status in {"sem_comprovacao", "parcial"} and not observacao:
        missing_fields.append("observação financeira")

    if missing_fields:
        raise ValueError(
            "Para vincular automaticamente esse documento ao item, informe: "
            + ", ".join(missing_fields)
            + "."
        )

    existing_document = finance_service.get_stock_document_by_number(numero_documento)
    if existing_document:
        return


def _sync_item_financial_history(
    *,
    codigo: str,
    categoria: str,
    quantidade: float,
    preco_compra_unitario: object,
    data_lancamento: object,
    usuario_id: str | None,
    finance_payload: dict[str, object],
    entrada_id: int | None = None,
) -> bool:
    metadata_recorded = False

    if finance_payload.get("supplier_id"):
        finance_service.set_item_supplier_preference(
            codigo,
            int(finance_payload["supplier_id"]),
            origem=str(finance_payload.get("origem_valor") or ""),
            atualizado_por=usuario_id,
        )

    try:
        unit_price = float(preco_compra_unitario) if preco_compra_unitario not in (None, "") else None
    except (TypeError, ValueError):
        unit_price = None

    when = None
    if isinstance(data_lancamento, datetime):
        when = data_lancamento
    elif hasattr(data_lancamento, "year") and hasattr(data_lancamento, "month") and hasattr(data_lancamento, "day"):
        when = data_lancamento

    has_document_metadata = bool(
        (finance_payload.get("numero_documento") or "").strip()
        and ((finance_payload.get("tipo_documento") or "").strip() or "nf")
    )
    if has_document_metadata:
        finance_service.register_stock_document_entry(
            codigo_item=codigo,
            quantidade=float(quantidade or 0),
            tipo_documento=str(finance_payload.get("tipo_documento") or "nf"),
            numero_documento=str(finance_payload.get("numero_documento") or ""),
            data_emissao=finance_payload.get("data_emissao_documento"),
            data_recebimento=finance_payload.get("data_recebimento_documento"),
            chave_acesso=finance_payload.get("chave_acesso"),
            supplier_id=finance_payload.get("supplier_id"),
            entrada_id=entrada_id,
            valor_unitario=unit_price,
            observacao=finance_payload.get("observacao"),
            usuario_matricula=usuario_id,
            origem_valor=str(finance_payload.get("origem_valor") or "inventario_inicial"),
        )
        metadata_recorded = True

    has_financial_metadata = bool(
        (finance_payload.get("numero_documento") or "").strip()
        or (finance_payload.get("tipo_documento") or "").strip()
        or (finance_payload.get("comprovacao_status") or "").strip()
        or (finance_payload.get("observacao") or "").strip()
        or (finance_payload.get("chave_acesso") or "").strip()
        or finance_payload.get("data_emissao_documento")
        or finance_payload.get("data_recebimento_documento")
    )

    if quantidade <= 0 and not has_financial_metadata:
        return metadata_recorded

    if unit_price is None and not has_financial_metadata:
        return metadata_recorded

    finance_service.register_financial_entry(
        codigo_item=codigo,
        categoria_nome=categoria,
        quantidade=float(quantidade),
        valor_unitario=unit_price,
        valor_total=0.0 if unit_price is None else None,
        data_lancamento=when,
        fornecedor_id=finance_payload.get("supplier_id"),
        entrada_id=entrada_id,
        usuario_matricula=usuario_id,
        origem_valor=str(finance_payload.get("origem_valor") or "inventario_inicial"),
        tipo_documento=finance_payload.get("tipo_documento"),
        numero_documento=finance_payload.get("numero_documento"),
        chave_acesso=finance_payload.get("chave_acesso"),
        data_emissao_documento=finance_payload.get("data_emissao_documento"),
        data_recebimento_documento=finance_payload.get("data_recebimento_documento"),
        comprovacao_status=str(finance_payload.get("comprovacao_status") or "sem_comprovacao"),
        observacao=finance_payload.get("observacao"),
    )
    return True


def _build_nf_autofill_payload(numero_documento: str) -> dict[str, object] | None:
    numero = (numero_documento or "").strip()
    if not numero:
        return None

    document = finance_service.get_stock_document_by_number(numero)
    latest_entry = (
        FinanceLedgerEntry.query
        .filter(FinanceLedgerEntry.numero_documento == numero)
        .order_by(FinanceLedgerEntry.data_lancamento.desc(), FinanceLedgerEntry.id.desc())
        .first()
    )
    matched_item = latest_entry.item if latest_entry and latest_entry.item else None
    if matched_item is None:
        matched_item = (
            Item.query
            .filter((Item.nota_fiscal == numero) | (Item.preco_compra_documento == numero))
            .order_by(Item.preco_compra_atualizado_em.desc(), Item.codigo_item.desc())
            .first()
        )

    if not document and not latest_entry and not matched_item:
        return None

    def _to_iso(value) -> str | None:
        return value.isoformat() if value else None

    observacao = None
    if latest_entry and latest_entry.observacao:
        observacao = latest_entry.observacao
    elif document and document.get("observacao"):
        observacao = document.get("observacao")

    data_emissao = None
    if latest_entry and latest_entry.data_emissao_documento:
        data_emissao = latest_entry.data_emissao_documento
    elif matched_item and matched_item.preco_compra_data_emissao:
        data_emissao = matched_item.preco_compra_data_emissao
    elif document:
        data_emissao = document.get("data_emissao")

    data_entrada = None
    if matched_item and matched_item.data_entrada:
        data_entrada = matched_item.data_entrada
    elif latest_entry and latest_entry.data_recebimento_documento:
        data_entrada = latest_entry.data_recebimento_documento
    elif document and document.get("data_recebimento"):
        data_entrada = document.get("data_recebimento")
    elif document and document.get("data_emissao"):
        data_entrada = document.get("data_emissao")

    documento_compra = numero

    return {
        "numero_documento": numero,
        "origem_valor": (
            latest_entry.origem_valor
            if latest_entry and latest_entry.origem_valor
            else "inventario_inicial"
        ),
        "tipo_documento": (
            latest_entry.tipo_documento
            if latest_entry and latest_entry.tipo_documento
            else (document.get("tipo_documento") if document else None)
            or ""
        ),
        "comprovacao_status": (
            latest_entry.comprovacao_status
            if latest_entry and latest_entry.comprovacao_status
            else "sem_comprovacao"
        ),
        "preco_compra_fonte": matched_item.preco_compra_fonte if matched_item else None,
        "chave_acesso": (
            latest_entry.chave_acesso
            if latest_entry and latest_entry.chave_acesso
            else (document.get("chave_acesso") if document else (matched_item.preco_compra_chave_acesso if matched_item else None))
        ),
        "data_emissao": _to_iso(data_emissao),
        "data_entrada": _to_iso(data_entrada),
        "documento_compra": documento_compra,
        "observacao": observacao,
    }


def _format_pre_registered_document_type(tipo_documento: str | None) -> str:
    raw = (tipo_documento or "").strip().lower()
    labels = {
        "nf": "NF",
        "nota_fiscal": "NF",
        "nfe": "NF",
        "cupom": "Cupom",
        "cupom_fiscal": "Cupom",
        "sem_comprovacao": "Sem comprovação",
        "sem-comprovacao": "Sem comprovação",
        "sem comprovacao": "Sem comprovação",
    }
    if raw in labels:
        return labels[raw]
    cleaned = (tipo_documento or "").strip()
    return cleaned.upper() if cleaned else "Documento"


def _repair_pending_pre_registered_links() -> int:
    repaired = 0
    candidate_items = (
        Item.query
        .filter(
            or_(
                Item.pre_cadastro_pendente.is_(True),
                and_(
                    Item.pre_cadastro_origem == "nf",
                    Item.pre_cadastro_pendente.is_(False),
                    Item.pre_cadastro_finalizado_em.is_(None),
                    or_(
                        Item.pre_cadastro_criado_em.is_not(None),
                        Item.pre_cadastro_documento_item_id.is_not(None),
                    ),
                ),
            )
        )
        .all()
    )

    for item_model in candidate_items:
        origem = (getattr(item_model, "pre_cadastro_origem", "") or "").strip().lower()
        if origem != "nf":
            continue

        if (
            not bool(getattr(item_model, "pre_cadastro_pendente", False))
            and getattr(item_model, "pre_cadastro_finalizado_em", None) is None
        ):
            item_model.pre_cadastro_pendente = True
            repaired += 1

        candidate_numbers = {
            str(getattr(item_model, "nota_fiscal", "") or "").strip(),
            str(getattr(item_model, "preco_compra_documento", "") or "").strip(),
        }
        candidate_numbers.discard("")
        if not candidate_numbers:
            continue

        row = None
        if item_model.pre_cadastro_documento_item_id is not None:
            row = db.session.get(DocumentoEntradaEstoqueItem, item_model.pre_cadastro_documento_item_id)

        if row is None:
            rows = (
                DocumentoEntradaEstoqueItem.query
                .join(DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem.documento_id == DocumentoEntradaEstoque.id_documento)
                .filter(DocumentoEntradaEstoqueItem.codigo_item == item_model.codigo_item)
                .filter(DocumentoEntradaEstoque.numero_documento.in_(sorted(candidate_numbers)))
                .order_by(DocumentoEntradaEstoqueItem.id_documento_item.desc())
                .all()
            )
            if len(rows) != 1:
                continue
            row = rows[0]

        if item_model.pre_cadastro_documento_item_id != row.id_documento_item:
            item_model.pre_cadastro_documento_item_id = row.id_documento_item
            repaired += 1

        if row.documento is not None and not bool(getattr(row.documento, "movimenta_estoque", True)):
            row.documento.movimenta_estoque = True
            repaired += 1

    if repaired:
        db.session.commit()
    return repaired


def _serialize_pre_registered_item(item_model: Item, documento_item: DocumentoEntradaEstoqueItem) -> dict[str, object]:
    saldo_atual = float(item_model.get_saldo_fisico_total() or 0.0)
    valor_total = documento_item.valor_total
    if valor_total in (None, "") and documento_item.valor_unitario not in (None, ""):
        valor_total = round(float(documento_item.quantidade or 0.0) * float(documento_item.valor_unitario or 0.0), 2)
    display_metadata = _build_document_item_display_metadata(documento_item)
    return {
        "codigo": item_model.codigo_item,
        "descricao": item_model.descricao,
        "categoria": item_model.categoria,
        "marca": item_model.marca,
        "unidade": item_model.unidade,
        "saldo": saldo_atual,
        "saldo_display": item_model.get_saldo_fisico_display(),
        "quantidade_documento": float(documento_item.quantidade or 0.0),
        "quantidade_documento_display": display_metadata.get("quantidade_documento_display"),
        "quantidade_base_display": display_metadata.get("quantidade_base_display"),
        "conversao_display": display_metadata.get("conversao_display"),
        "valor_unitario": documento_item.valor_unitario,
        "valor_total": valor_total,
        "documento_item_id": documento_item.id_documento_item,
        "edit_url": url_for("inventory.edit_item_form", codigo=item_model.codigo_item),
        "pre_cadastro_criado_em": TimeService.isoformat_utc(item_model.pre_cadastro_criado_em),
    }


def _build_pre_registered_items_payload(numero_documento: str) -> dict[str, object] | None:
    _repair_pending_pre_registered_links()

    numero = (numero_documento or "").strip()
    if not numero:
        return None

    documento = (
        DocumentoEntradaEstoque.query
        .filter(DocumentoEntradaEstoque.numero_documento == numero)
        .order_by(DocumentoEntradaEstoque.id_documento.desc())
        .first()
    )
    if documento is None:
        return None

    rows = (
        db.session.query(Item, DocumentoEntradaEstoqueItem)
        .join(
            DocumentoEntradaEstoqueItem,
            Item.pre_cadastro_documento_item_id == DocumentoEntradaEstoqueItem.id_documento_item,
        )
        .join(
            DocumentoEntradaEstoque,
            DocumentoEntradaEstoqueItem.documento_id == DocumentoEntradaEstoque.id_documento,
        )
        .filter(
            DocumentoEntradaEstoque.numero_documento == numero,
            Item.pre_cadastro_pendente.is_(True),
        )
        .order_by(Item.descricao.asc(), Item.codigo_item.asc())
        .all()
    )

    items_payload = [_serialize_pre_registered_item(item_model, documento_item) for item_model, documento_item in rows]

    return {
        "numero_documento": documento.numero_documento,
        "tipo_documento": documento.tipo_documento,
        "tipo_documento_label": _format_pre_registered_document_type(documento.tipo_documento),
        "data_emissao": documento.data_emissao.isoformat() if documento.data_emissao else None,
        "data_recebimento": documento.data_recebimento.isoformat() if documento.data_recebimento else None,
        "fornecedor_nome": documento.fornecedor.nome_exibicao() if documento.fornecedor else (documento.fornecedor_nome or None),
        "items_count": len(items_payload),
        "items": items_payload,
    }


def _build_all_pre_registered_documents_payload() -> list[dict[str, object]]:
    _repair_pending_pre_registered_links()

    rows = (
        db.session.query(Item, DocumentoEntradaEstoqueItem, DocumentoEntradaEstoque)
        .join(
            DocumentoEntradaEstoqueItem,
            Item.pre_cadastro_documento_item_id == DocumentoEntradaEstoqueItem.id_documento_item,
        )
        .join(
            DocumentoEntradaEstoque,
            DocumentoEntradaEstoqueItem.documento_id == DocumentoEntradaEstoque.id_documento,
        )
        .filter(Item.pre_cadastro_pendente.is_(True))
        .order_by(
            DocumentoEntradaEstoque.data_recebimento.desc(),
            DocumentoEntradaEstoque.id_documento.desc(),
            Item.descricao.asc(),
            Item.codigo_item.asc(),
        )
        .all()
    )

    documents_by_id: dict[int, dict[str, object]] = {}
    for item_model, documento_item, documento in rows:
        payload = documents_by_id.get(documento.id_documento)
        if payload is None:
            payload = {
                "numero_documento": documento.numero_documento,
                "tipo_documento": documento.tipo_documento,
                "tipo_documento_label": _format_pre_registered_document_type(documento.tipo_documento),
                "data_emissao": documento.data_emissao.isoformat() if documento.data_emissao else None,
                "data_recebimento": documento.data_recebimento.isoformat() if documento.data_recebimento else None,
                "fornecedor_nome": documento.fornecedor.nome_exibicao() if documento.fornecedor else (documento.fornecedor_nome or None),
                "items_count": 0,
                "items": [],
            }
            documents_by_id[documento.id_documento] = payload

        payload["items"].append(_serialize_pre_registered_item(item_model, documento_item))
        payload["items_count"] = int(payload.get("items_count") or 0) + 1

    return list(documents_by_id.values())


def _build_pre_registered_counters() -> dict[str, int]:
    _repair_pending_pre_registered_links()

    pending_items = int(
        db.session.query(func.count(Item.codigo_item))
        .filter(Item.pre_cadastro_pendente.is_(True))
        .scalar()
        or 0
    )
    pending_documents = int(
        db.session.query(func.count(func.distinct(DocumentoEntradaEstoque.id_documento)))
        .join(
            DocumentoEntradaEstoqueItem,
            DocumentoEntradaEstoqueItem.documento_id == DocumentoEntradaEstoque.id_documento,
        )
        .join(
            Item,
            Item.pre_cadastro_documento_item_id == DocumentoEntradaEstoqueItem.id_documento_item,
        )
        .filter(Item.pre_cadastro_pendente.is_(True))
        .scalar()
        or 0
    )
    return {
        "documents": pending_documents,
        "items": pending_items,
    }


@blueprint.get("/")
@login_required
def list_items():
    raw_itens = inventory_service.list_items()
    itens: list[dict] = []
    for raw in raw_itens:
        item = dict(raw)
        codigo = item.get("codigo")
        if codigo:
            item["edit_url"] = url_for("inventory.edit_item_form", codigo=codigo)
        itens.append(item)
    can_manage = _is_admin(current_user)
    can_edit_items = can_manage or _is_supervisor(current_user)
    can_create = can_manage or _is_supervisor(current_user)
    
    # Carregar lista de usuários para modal de atribuição (apenas se admin)
    users_list = []
    if can_manage:
        try:
            users_query = Usuario.query.order_by(Usuario.nome).all()
            users_list = [
                {
                    "matricula": u.matricula,
                    "nome": u.nome,
                    "setor": (u.setor or "").strip() or "Sem setor",
                }
                for u in users_query
            ]
        except Exception:
            pass

    category_groups: dict[str, list[dict]] = defaultdict(list)
    for item in itens:
        category = item.get("categoria") or "Sem categoria"
        category_groups[category].append(item)
    category_cards: list[dict] = []
    for category, items in sorted(category_groups.items()):
        balance_summary = build_category_balance_summary(items)
        value_summary = build_category_value_summary(items)
        category_cards.append(
            {
                "categoria": category,
                "total": len(items),
                "balance_summary": balance_summary,
                "balance_summary_preview": balance_summary[:3],
                "balance_summary_hidden": max(len(balance_summary) - 3, 0),
                "valor_estoque_compra_total": value_summary["total_compra"],
                "valor_estoque_reposicao_total": value_summary["total_reposicao"],
                "itens_com_preco_compra": value_summary["with_compra"],
                "itens_sem_preco_compra": value_summary["missing_compra"],
                "itens_sem_preco_reposicao": value_summary["missing_reposicao"],
                "entries": items,
            }
        )
    pre_registered_counts = _build_pre_registered_counters() if can_create else {"documents": 0, "items": 0}
    return render_template(
        "inventory/list.html",
        itens=itens,
        can_manage=can_manage,
        can_edit_items=can_edit_items,
        can_create=can_create,
        pre_registered_counts=pre_registered_counts,
        category_cards=category_cards,
        selected_category=request.args.get("categoria", "").strip(),
        users_list=users_list,
        operational_activity_options=OPERATIONAL_ACTIVITY_OPTIONS,
    )


@blueprint.get("/valor-estoque")
@login_required
def valor_estoque():
    _require_admin()
    report = finance_service.get_stock_value_report(request.args.get("exercicio"))

    uf_empresa = ""
    try:
        uf_empresa = (ConfigService.get_empresa_config().endereco_estado or "").strip().upper()
    except Exception:
        uf_empresa = ""

    return render_template(
        "inventory/stock_value.html",
        itens=report["items"],
        category_cards=report["category_cards"],
        total_compra=report["total_compra"],
        total_reposicao=report["total_reposicao"],
        missing_compra=report["missing_compra"],
        missing_reposicao=report["missing_reposicao"],
        total_investido_exercicio=report["total_investido_exercicio"],
        total_consumido_exercicio=report["total_consumido_exercicio"],
        total_sem_comprovacao_exercicio=report["total_sem_comprovacao_exercicio"],
        consumo_fracionado_por_local=report.get("consumo_fracionado_por_local") or [],
        total_fracionado_valor=report.get("total_fracionado_valor"),
        total_fracionado_litros=report.get("total_fracionado_litros"),
        total_fracionado_quilos=report.get("total_fracionado_quilos"),
        fracionado_linhas_ignoradas=report.get("fracionado_linhas_ignoradas"),
        consumo_analitico=report.get("consumo_analitico") or {},
        consumo_dashboard_url=url_for("inventory.consumption_dashboard") if request else None,
        exercise=report["exercise"],
        exercise_options=report["exercise_options"],
        uf_empresa=uf_empresa,
    )


@blueprint.get("/valor-estoque/pdf")
@login_required
def valor_estoque_pdf():
    _require_admin()
    exercise_label = (request.args.get("exercicio") or "").strip() or None
    pdf_buffer = finance_service.build_stock_value_pdf(exercise_label)
    exercise = finance_service.resolve_exercise(exercise_label)
    filename = f"prestacao_contas_almoxarifado_{exercise['label'].replace('/', '_')}.pdf"
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)


@blueprint.get("/consumo")
@login_required
def consumption_dashboard():
    _require_admin()
    panel = finance_service.get_consumption_panel_report(request.args.get("exercicio"))
    return render_template("inventory/consumption_panel.html", panel=panel)


@blueprint.get("/consumo/local")
@login_required
def consumption_by_local():
    _require_admin()
    local_name = (request.args.get("local") or "").strip()
    exercise_label = (request.args.get("exercicio") or "").strip() or None
    if not local_name:
        flash("Informe o local para abrir a subpágina de consumo.", "warning")
        return redirect(url_for("inventory.consumption_dashboard", exercicio=exercise_label))

    panel = finance_service.get_consumption_panel_report(exercise_label, local_name=local_name)
    if not panel.get("entries"):
        flash(f"Nenhum consumo encontrado para o local '{local_name}'.", "warning")
        return redirect(url_for("inventory.consumption_dashboard", exercicio=exercise_label))
    return render_template("inventory/consumption_panel.html", panel=panel)


@blueprint.get("/consumo/categoria")
@login_required
def consumption_by_category():
    _require_admin()
    category_name = (request.args.get("categoria") or "").strip()
    exercise_label = (request.args.get("exercicio") or "").strip() or None
    if not category_name:
        flash("Informe a categoria para abrir a subpágina de consumo.", "warning")
        return redirect(url_for("inventory.consumption_dashboard", exercicio=exercise_label))

    panel = finance_service.get_consumption_panel_report(exercise_label, category_name=category_name)
    if not panel.get("entries"):
        flash(f"Nenhum consumo encontrado para a categoria '{category_name}'.", "warning")
        return redirect(url_for("inventory.consumption_dashboard", exercicio=exercise_label))
    return render_template("inventory/consumption_panel.html", panel=panel)


@blueprint.get("/consumo/funcionario/<matricula>")
@login_required
def consumption_by_employee(matricula: str):
    _require_admin()
    employee_id = (matricula or "").strip()
    exercise_label = (request.args.get("exercicio") or "").strip() or None
    if not employee_id:
        flash("Informe o colaborador para abrir a subpágina de consumo.", "warning")
        return redirect(url_for("inventory.consumption_dashboard", exercicio=exercise_label))

    panel = finance_service.get_consumption_panel_report(exercise_label, employee_id=employee_id)
    if not panel.get("entries"):
        flash(f"Nenhum consumo encontrado para o colaborador '{employee_id}'.", "warning")
        return redirect(url_for("inventory.consumption_dashboard", exercicio=exercise_label))
    return render_template("inventory/consumption_panel.html", panel=panel)


@blueprint.get("/consumo/relatorio/pdf")
@login_required
def consumption_report_pdf():
    _require_admin()
    exercise_label = (request.args.get("exercicio") or "").strip() or None
    local_name = (request.args.get("local") or "").strip() or None
    category_name = (request.args.get("categoria") or "").strip() or None
    employee_id = (request.args.get("matricula") or "").strip() or None

    panel = finance_service.get_consumption_panel_report(
        exercise_label,
        local_name=local_name,
        category_name=category_name,
        employee_id=employee_id,
    )
    if not panel.get("entries"):
        flash("Não há dados de consumo para gerar o relatório solicitado.", "warning")
        return redirect(url_for("inventory.consumption_dashboard", exercicio=exercise_label))

    pdf_buffer = finance_service.build_consumption_panel_pdf(
        exercise_label,
        local_name=local_name,
        category_name=category_name,
        employee_id=employee_id,
    )

    scope_type = panel.get("scope_type") or "geral"
    if scope_type == "local":
        scope_value = panel.get("filters", {}).get("local") or "local"
    elif scope_type == "categoria":
        scope_value = panel.get("filters", {}).get("categoria") or "categoria"
    elif scope_type == "funcionario":
        scope_value = panel.get("filters", {}).get("matricula") or "funcionario"
    else:
        scope_value = "geral"

    filename = (
        f"relatorio_consumo_{scope_type}_"
        f"{_sanitize_filename_component(str(scope_value))}_"
        f"{TimeService.now_local().strftime('%Y%m%d_%H%M%S')}.pdf"
    )
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)


@blueprint.get("/lojas")
@login_required
def lojas_lab():
    """Laboratório de Lojas (fornecedores): cruzamentos por NF/cupom e preços."""
    _require_admin()
    report = finance_service.get_supplier_lab_report(request.args.get("exercicio"))
    return render_template(
        "inventory/suppliers_lab.html",
        suppliers=report["suppliers"],
        comparacao_itens=report.get("comparacao_itens") or [],
        summary=report.get("summary") or {},
        exercise=report["exercise"],
        exercise_options=report.get("exercise_options") or [],
    )


@blueprint.get("/categorias")
@login_required
def category_admin():
    _require_admin()
    category_rows = _build_category_admin_rows()
    summary = {
        "total": len(category_rows),
        "ativas": sum(1 for row in category_rows if row["ativa"]),
        "sistema": sum(1 for row in category_rows if row["sistema"]),
        "customizadas": sum(1 for row in category_rows if not row["sistema"]),
    }
    return render_template(
        "inventory/categories.html",
        category_rows=category_rows,
        summary=summary,
    )


@blueprint.post("/categorias")
@login_required
def create_category_record():
    _require_admin()
    try:
        category_catalog_service.create_category(
            nome=request.form.get("nome"),
            descricao=request.form.get("descricao"),
            ordem=request.form.get("ordem"),
            ativa=bool(request.form.get("ativa")),
            actor=_current_actor_name(),
        )
        _reset_inventory_category_cache()
        flash("Categoria criada com sucesso.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    except Exception as exc:
        db.session.rollback()
        flash(f"Erro ao criar categoria: {exc}", "danger")
    return redirect(url_for("inventory.category_admin"))


@blueprint.post("/categorias/<int:category_id>")
@login_required
def update_category_record(category_id: int):
    _require_admin()
    try:
        category_catalog_service.update_category(
            category_id,
            nome=request.form.get("nome"),
            descricao=request.form.get("descricao"),
            ordem=request.form.get("ordem"),
            ativa=bool(request.form.get("ativa")),
            actor=_current_actor_name(),
        )
        _reset_inventory_category_cache()
        flash("Categoria atualizada com sucesso.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    except Exception as exc:
        db.session.rollback()
        flash(f"Erro ao atualizar categoria: {exc}", "danger")
    return redirect(url_for("inventory.category_admin"))


@blueprint.post("/categorias/<int:category_id>/excluir")
@login_required
def delete_category_record(category_id: int):
    _require_admin()
    try:
        category_catalog_service.delete_category(category_id)
        _reset_inventory_category_cache()
        flash("Categoria removida do catálogo.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    except Exception as exc:
        db.session.rollback()
        flash(f"Erro ao excluir categoria: {exc}", "danger")
    return redirect(url_for("inventory.category_admin"))


@blueprint.get("/categorias/relatorio-escopo")
@login_required
def download_scope_report():
    """Gera e baixa o Relatório de Escopo executivo (apenas admin)."""
    _require_admin()

    category_name = (request.args.get("categoria") or "").strip() or None
    redirect_target = request.referrer or url_for("inventory.list_items")

    try:
        from ..services.scope_report_service import ScopeReportService
        from ..utils.time_service import TimeService

        # Gerar relatório
        buffer = ScopeReportService.generate_executive_scope_report(category_name=category_name)

        # Timestamp para nome do arquivo
        timestamp = TimeService.now_local().strftime("%Y%m%d_%H%M%S")
        scope_name = _sanitize_filename_component(category_name or "geral")
        filename = f"relatorio_escopo_{scope_name}_{timestamp}.xlsx"

        response = send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-GALINT-Report-Scope"] = category_name or "Geral"
        return response
    except Exception as exc:
        flash(f"Erro ao gerar Relatório de Escopo: {exc}", "danger")
        return redirect(redirect_target)


@blueprint.get("/novo")
@login_required
def new_item_form():
    _require_admin_or_supervisor()
    codigo_prefill = request.args.get("codigo", "").strip()
    categoria_prefill = request.args.get("categoria", "").strip()
    form_data = None
    if codigo_prefill or categoria_prefill:
        form_data = {}
        if codigo_prefill:
            form_data["codigo"] = codigo_prefill
        if categoria_prefill:
            form_data["categoria"] = categoria_prefill
    
    # Se o código já existe, calcular saldo total para mostrar no form
    saldo_total_ean = None
    if codigo_prefill:
        try:
            saldo_total_ean = Item.get_saldo_total_by_codigo(codigo_prefill)
        except Exception:
            pass
    
    return render_template(
        "inventory/form.html",
        item=None,
        form_data=form_data,
        base_unit_options=BASE_ITEM_UNIT_OPTIONS,
        selected_base_unit=resolve_item_base_unit_label(form_data, fallback="Unidade") if form_data else "Unidade",
        saldo_desejado=0,
        saldo_total_ean=saldo_total_ean,
        liquid_types=LIQUID_PRODUCT_TYPES,
        preferred_supplier=None,
        category_options=_inventory_category_options(),
        all_suppliers=finance_service.list_suppliers(limit=300),
    )


@blueprint.get("/ajuda/unidades-dinamicas")
@login_required
def dynamic_units_help():
    return render_template("inventory/dynamic_units_help.html")


@blueprint.post("/novo")
@login_required
def create_item():
    _require_admin_or_supervisor()
    form = request.form
    saldo_raw = form.get("saldo_atual", "0").strip()
    try:
        saldo_desejado = int(saldo_raw or 0)
    except ValueError:
        saldo_desejado = -1
    tipo_novo = form.get("tipo_embalagem_novo") or None
    unidade_embalagem_novo = form.get("unidade_embalagem_novo")
    unidades_por_emb_raw = form.get("unidades_por_embalagem")

    litros_var = None
    grandeza_var = None
    unidades_var = None

    if tipo_novo in ["lata", "balde", "bombona"]:
        val = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        unidades_var = val
        if unidade_embalagem_novo == "litro":
            litros_var = val
        elif unidade_embalagem_novo == "kg":
            grandeza_var = val
    elif tipo_novo == "rolo":
        unidades_var = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
    elif tipo_novo in ["pacote", "saco"]:
        val = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        unidades_var = val
        if unidade_embalagem_novo == "kg":
            grandeza_var = val
    elif tipo_novo in ["caixa", "fardo"]:
        unidades_var = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
    elif tipo_novo == "litro":
        litros_var = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        unidades_var = litros_var

    _validate_packaging_type_value(tipo_novo, unidades_var)

    em_embalagens = None
    if tipo_novo in ["lata", "rolo", "pacote", "caixa", "fardo", "litro", "balde", "bombona", "saco"] and unidades_var and unidades_var > 0:
        em_embalagens = True
    
    payload = {
        "codigo": form.get("codigo", "").strip(),
        "descricao": form.get("descricao", "").strip(),
        "nota_fiscal": form.get("nota_fiscal", "").strip() or None,
        "localizacao": form.get("localizacao", "").strip() or None,
        "categoria": form.get("categoria", "Material Elétrico"),
        "marca": form.get("marca", "").strip() or None,
        "unidade": form.get("unidade", "").strip(),
        "numero_serie": form.get("numero_serie", "").strip() or None,
        "modelo": form.get("modelo", "").strip() or None,
        "data_entrada": form.get("data_entrada") or None,
        "data_fabricacao": form.get("data_fabricacao") or None,
        "data_validade": form.get("data_validade") or None,
        "lote": (form.get("lote") or "").strip() or None,
        "gerar_lote_automatico": bool(form.get("gerar_lote_automatico")),
        "tipo_embalagem": form.get("tipo_embalagem"),
        "grandeza_referencia": form.get("grandeza_referencia") or None,
        "litros_por_embalagem": form.get("litros_por_embalagem") or None,
        "tipo_embalagem_novo": tipo_novo,
        "unidades_por_embalagem": unidades_var,
        "voltagem": form.get("voltagem", "").strip() or None,
        "amperagem": form.get("amperagem", "").strip() or None,
        "local_instalacao": form.get("local_instalacao", "").strip() or None,
        # Financeiro
        "preco_compra_unitario": (form.get("preco_compra_unitario") or "").strip() or None,
        "preco_compra_unidade_preco": (form.get("preco_compra_unidade_preco") or "").strip().lower() or None,
        "preco_compra_fonte": (form.get("preco_compra_fonte") or "").strip() or None,
        "preco_compra_documento": (form.get("preco_compra_documento") or "").strip() or None,
        "preco_compra_chave_acesso": (form.get("preco_compra_chave_acesso") or "").strip() or None,
        "preco_compra_data_emissao": (form.get("preco_compra_data_emissao") or "").strip() or None,
        "preco_compra_data_recebimento": (form.get("preco_compra_data_recebimento") or "").strip() or None,
        "preco_reposicao_unitario": (form.get("preco_reposicao_unitario") or "").strip() or None,
        "preco_reposicao_unidade_preco": (form.get("preco_reposicao_unidade_preco") or "").strip().lower() or None,
        "preco_reposicao_fonte": (form.get("preco_reposicao_fonte") or "").strip() or None,
        "preco_reposicao_uf": (form.get("preco_reposicao_uf") or "").strip() or None,
        "preco_reposicao_query": (form.get("preco_reposicao_query") or "").strip() or None,
        "preco_reposicao_url": (form.get("preco_reposicao_url") or "").strip() or None,
        "foto_url": (form.get("foto_url") or "").strip() or None,
        "advanced_unit_settings": _parse_advanced_unit_settings(form.get("advanced_unit_settings_json")),
        "quantidade": saldo_desejado,  # Para registrar entrada quando item existe com lote diferente
        "equivalent_item_action": (form.get("equivalent_item_action") or "").strip() or None,
        "equivalent_item_source_code": (form.get("equivalent_item_source_code") or "").strip() or None,
        "equivalent_item_reuse_photo": form.get("equivalent_item_reuse_photo"),
        "equivalent_item_reuse_brand": form.get("equivalent_item_reuse_brand"),
        "equivalent_item_reuse_category": form.get("equivalent_item_reuse_category"),
        "equivalent_item_reuse_location": form.get("equivalent_item_reuse_location"),
    }
    finance_payload = _extract_finance_payload(form)
    payload.update({
        "finance_supplier_id": finance_payload.get("supplier_id"),
        "finance_origem_valor": finance_payload.get("origem_valor"),
        "finance_tipo_documento": finance_payload.get("tipo_documento"),
        "finance_comprovacao_status": finance_payload.get("comprovacao_status"),
        "finance_observacao": finance_payload.get("observacao"),
    })
    if _should_seed_nf_pre_registration(finance_payload):
        payload.update(
            {
                "pre_cadastro_pendente": True,
                "pre_cadastro_origem": "nf",
                "pre_cadastro_criado_em": datetime.utcnow(),
                "pre_cadastro_finalizado_em": None,
            }
        )
    if tipo_novo:
        payload["litros_por_embalagem"] = litros_var
        payload["grandeza_referencia"] = grandeza_var
    try:
        if not payload["codigo"] or not payload["descricao"]:
            raise ValueError("Código e descrição são obrigatórios")
        if saldo_desejado < 0:
            raise ValueError("Informe uma quantidade inicial válida")
        if saldo_desejado > 0:
            raise ValueError("A entrada inicial manual foi desativada. Cadastre o item com saldo zero e registre a entrada em Documentos Fiscais.")

        _validate_document_bridge_request(finance_payload)

        _validate_stock_entry_policy(
            codigo=payload["codigo"],
            quantidade=float(saldo_desejado if saldo_desejado > 0 else 0),
            finance_payload=finance_payload,
            allow_new_document_item=True,
        )
        
        if payload.get("preco_compra_unitario") is not None:
            payload["preco_compra_atualizado_em"] = datetime.utcnow()
            payload["preco_compra_atualizado_por"] = current_user.nome if hasattr(current_user, "nome") else current_user.id
        if payload.get("preco_reposicao_unitario") is not None:
            payload["preco_reposicao_atualizado_em"] = datetime.utcnow()
            payload["preco_reposicao_atualizado_por"] = current_user.nome if hasattr(current_user, "nome") else current_user.id

        # Processar upload de foto (se enviado)
        foto_file = request.files.get('foto')
        if foto_file and foto_file.filename:
            try:
                foto_path = ItemFotoService.upload_foto(foto_file, payload["codigo"])
                payload["foto_path"] = foto_path
            except ValueError as e:
                flash(f"Erro no upload da foto: {str(e)}", "warning")
        elif payload.get("foto_url"):
            try:
                foto_path = ItemFotoService.download_foto_from_url(str(payload["foto_url"]), payload["codigo"])
                payload["foto_path"] = foto_path
            except ValueError as e:
                flash(f"Erro ao baixar foto por link: {str(e)}", "warning")
        
        resultado = inventory_service.create_item(payload)
        
        # Verificar se foi atualização de item existente (lote diferente)
        foi_atualizacao = resultado.startswith("UPDATED:")
        codigo = resultado.replace("UPDATED:", "") if foi_atualizacao else resultado
        
        # Registrar entrada apenas se foi criação nova (não atualização)
        # Para atualizações, a entrada já foi registrada no service
        entrada_inicial = None

        history_recorded = False
        
        # Notificar criação de item aos administradores (notificação UNIFICADA)
        try:
            from ..services.notification_router import NotificationRouterService

            NotificationRouterService.route_item_created(codigo, entrada_inicial=entrada_inicial)
        except Exception:
            pass
        
        if foi_atualizacao:
            flash(f"Nova entrada registrada para item existente (lote atualizado).", "success")
        else:
            flash("Item cadastrado com sucesso.", "success")

        numero_documento = str(finance_payload.get("numero_documento") or "").strip()
        if numero_documento and _is_admin(current_user):
            flash(
                f"Item criado com saldo zero. Finalize a entrada pelo documento fiscal {numero_documento}.",
                "info",
            )
            return redirect(url_for("nf.nf_index", nota=numero_documento, codigo=codigo))
    except ValueError as exc:
        flash(str(exc), "danger")
        quantidade_context = saldo_desejado if saldo_desejado >= 0 else None
        if quantidade_context is not None:
            payload["saldo"] = quantidade_context
        saldo_total_ean = None
        if payload.get("codigo"):
            try:
                saldo_total_ean = Item.get_saldo_total_by_codigo(payload["codigo"])
            except Exception:
                saldo_total_ean = None
        return render_template(
            "inventory/form.html",
            item=None,
            form_data=payload,
            base_unit_options=BASE_ITEM_UNIT_OPTIONS,
            selected_base_unit=resolve_item_base_unit_label(payload, fallback="Unidade"),
            saldo_desejado=quantidade_context,
            saldo_total_ean=saldo_total_ean,
            liquid_types=LIQUID_PRODUCT_TYPES,
            preferred_supplier=finance_service.get_supplier(finance_payload.get("supplier_id")).to_dict() if finance_payload.get("supplier_id") else None,
            category_options=_inventory_category_options(selected_name=str(payload.get("categoria") or "")),
            all_suppliers=finance_service.list_suppliers(limit=300),
        ), 400
    return redirect(url_for("inventory.list_items"))


@blueprint.get("/<codigo>/editar")
@login_required
def edit_item_form(codigo: str):
    _require_admin_or_supervisor()
    item = inventory_service.get_item(codigo)
    if not item:
        flash("Item não encontrado.", "danger")
        return redirect(url_for("inventory.list_items"))

    if bool(item.get("pre_cadastro_pendente")):
        item = {**item, **_load_linked_document_context(item)}
    
    # Calcular saldo total de todos os lotes com o mesmo EAN
    saldo_total = Item.get_saldo_total_by_codigo(codigo)

    saldo_display = item.get("saldo", 0)
    if _uses_packaging_system(item):
        saldo_display = item.get("estoque_embalagens", saldo_display)
    
    return render_template(
        "inventory/form.html",
        item=item,
        form_data=None,
        base_unit_options=BASE_ITEM_UNIT_OPTIONS,
        selected_base_unit=resolve_item_base_unit_label(item, fallback="Unidade"),
        saldo_desejado=saldo_display,
        saldo_total_ean=saldo_total,
        liquid_types=LIQUID_PRODUCT_TYPES,
        preferred_supplier=finance_service.get_item_supplier_preference(codigo),
        category_options=_inventory_category_options(selected_name=str(item.get("categoria") or "")),
        all_suppliers=finance_service.list_suppliers(limit=300),
        finance_section_can_edit=_can_edit_finance_section(codigo),
    )


@blueprint.post("/<codigo>/financeiro/unlock")
@login_required
def unlock_finance_section(codigo: str):
    _require_admin_or_supervisor()
    item = inventory_service.get_item(codigo)
    if not item:
        return jsonify({"success": False, "message": "Item não encontrado."}), 404

    if _is_admin(current_user):
        _set_finance_unlock(codigo, True)
        return jsonify({"success": True, "message": "Seção financeira liberada para administrador."})

    payload = request.get_json(silent=True) or request.form or {}
    admin_matricula = str(payload.get("admin_matricula") or "").strip()
    admin_password = str(payload.get("admin_password") or payload.get("senha") or "").strip()

    if not admin_matricula or not admin_password:
        return jsonify({"success": False, "message": "Informe matrícula e senha do administrador."}), 400

    admin_user = Usuario.query.get(admin_matricula)
    if not admin_user or not _is_admin(admin_user) or not admin_user.check_password(admin_password):
        return jsonify({"success": False, "message": "Credenciais administrativas inválidas."}), 403

    _set_finance_unlock(codigo, True)
    return jsonify({
        "success": True,
        "message": f"Seção financeira liberada por {admin_user.nome}.",
    })


@blueprint.post("/<codigo>/editar")
@login_required
def update_item(codigo: str):
    _require_admin_or_supervisor()
    form = request.form
    prev_item = inventory_service.get_item(codigo)
    if not prev_item:
        flash("Item não encontrado.", "danger")
        return redirect(url_for("inventory.list_items"))

    saldo_raw = form.get("saldo_atual", "0").strip()
    saldo_unidades_soltas_raw = (form.get("saldo_unidades_soltas") or "").strip()
    # Por padrão, o saldo do formulário é inteiro (itens normais). Para itens com embalagem,
    # o saldo representa EMBALAGENS e pode ser float (mas o input do form usa step=1).
    try:
        saldo_desejado = float(saldo_raw or 0)
    except ValueError:
        saldo_desejado = -1
    finalize_pre_registration = (
        bool(prev_item.get("pre_cadastro_pendente"))
        and str(form.get("finalizar_pre_cadastro") or "").strip() in {"1", "true", "True"}
    )
    registrar_compra_edicao = bool(form.get("registrar_compra_edicao"))
    finance_section_edit_authorized = _can_edit_finance_section(codigo) and str(form.get("finance_section_edit_enabled") or "0").strip() in {"1", "true", "True"}

    # Lógica de processamento de Unidades Dinâmicas
    tipo_novo = form.get("tipo_embalagem_novo") or None
    unidade_embalagem_novo = form.get("unidade_embalagem_novo")
    unidades_por_emb_raw = form.get("unidades_por_embalagem")
    
    litros_var = None
    grandeza_var = None
    unidades_var = None
    
    if tipo_novo in ['lata', 'balde', 'bombona']:
        val = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        unidades_var = val
        if unidade_embalagem_novo == 'litro':
            litros_var = val
        elif unidade_embalagem_novo == 'kg':
            grandeza_var = val
    elif tipo_novo == 'rolo':
        val = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        unidades_var = val
    elif tipo_novo in ['pacote', 'saco']:
        val = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        unidades_var = val
        if unidade_embalagem_novo == 'kg':
            grandeza_var = val
    elif tipo_novo in ['caixa', 'fardo']:
        val = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        unidades_var = val
    elif tipo_novo == 'litro':
        val = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        litros_var = val
        unidades_var = val

    _validate_packaging_type_value(tipo_novo, unidades_var)
    
    # Se tipo_novo for None (Nenhum), limpa tudo
    
    payload = {
        "codigo": form.get("codigo", "").strip(),
        "descricao": form.get("descricao", "").strip(),
        "nota_fiscal": form.get("nota_fiscal", "").strip() or None,
        "localizacao": form.get("localizacao", "").strip() or None,
        "categoria": form.get("categoria", "Material Elétrico"),
        "marca": form.get("marca", "").strip() or None,
        "unidade": form.get("unidade", "").strip(),
        "numero_serie": form.get("numero_serie", "").strip() or None,
        "modelo": form.get("modelo", "").strip() or None,
        "data_entrada": form.get("data_entrada") or None,
        "data_fabricacao": form.get("data_fabricacao") or None,
        "data_validade": form.get("data_validade") or None,
        "lote": (form.get("lote") or "").strip() or None,
        "gerar_lote_automatico": bool(form.get("gerar_lote_automatico")),
        
        
        # Campos atualizados de Unidades Dinâmicas
        "tipo_embalagem_novo": tipo_novo,
        "litros_por_embalagem": litros_var,
        "grandeza_referencia": grandeza_var,
        "unidades_por_embalagem": unidades_var,
        
        # Histórico
        "ultima_edicao_em": datetime.now(),
        "ultima_edicao_por": current_user.nome if hasattr(current_user, 'nome') else current_user.id,
        # Campos de Equipamento
        "voltagem": form.get("voltagem", "").strip() or None,
        "amperagem": form.get("amperagem", "").strip() or None,
        "local_instalacao": form.get("local_instalacao", "").strip() or None,
        "advanced_unit_settings": _parse_advanced_unit_settings(form.get("advanced_unit_settings_json")),
        "preco_compra_unitario": (form.get("preco_compra_unitario") or "").strip() or prev_item.get("preco_compra_unitario"),
        "preco_compra_unidade_preco": (form.get("preco_compra_unidade_preco") or "").strip().lower() or prev_item.get("preco_compra_unidade_preco"),
        "preco_compra_fonte": (form.get("preco_compra_fonte") or "").strip() or prev_item.get("preco_compra_fonte"),
        "preco_compra_documento": (form.get("preco_compra_documento") or "").strip() or prev_item.get("preco_compra_documento"),
        "preco_compra_chave_acesso": (form.get("preco_compra_chave_acesso") or "").strip() or prev_item.get("preco_compra_chave_acesso"),
        "preco_compra_data_emissao": (form.get("preco_compra_data_emissao") or "").strip() or prev_item.get("preco_compra_data_emissao"),
        "preco_compra_data_recebimento": (form.get("preco_compra_data_recebimento") or "").strip() or prev_item.get("preco_compra_data_recebimento"),
        "preco_reposicao_unitario": prev_item.get("preco_reposicao_unitario"),
        "preco_reposicao_unidade_preco": prev_item.get("preco_reposicao_unidade_preco"),
        "preco_reposicao_fonte": prev_item.get("preco_reposicao_fonte"),
        "preco_reposicao_uf": prev_item.get("preco_reposicao_uf"),
        "preco_reposicao_query": prev_item.get("preco_reposicao_query"),
        "preco_reposicao_url": prev_item.get("preco_reposicao_url"),
        "preco_compra_atualizado_em": prev_item.get("preco_compra_atualizado_em"),
        "preco_compra_atualizado_por": prev_item.get("preco_compra_atualizado_por"),
        "preco_reposicao_atualizado_em": prev_item.get("preco_reposicao_atualizado_em"),
        "preco_reposicao_atualizado_por": prev_item.get("preco_reposicao_atualizado_por"),
        "finance_supplier_id": prev_item.get("finance_supplier_id"),
        "finance_origem_valor": prev_item.get("finance_origem_valor"),
        "finance_tipo_documento": prev_item.get("finance_tipo_documento"),
        "finance_comprovacao_status": prev_item.get("finance_comprovacao_status"),
        "finance_observacao": prev_item.get("finance_observacao"),
    }

    if finalize_pre_registration:
        payload.update(
            {
                "pre_cadastro_pendente": False,
                "pre_cadastro_finalizado_em": datetime.utcnow(),
            }
        )

    finance_payload = _extract_finance_payload(
        form,
        current_item=None if (registrar_compra_edicao or finance_section_edit_authorized) else prev_item,
    )
    if registrar_compra_edicao or finance_section_edit_authorized:
        payload.update({
            "preco_compra_unitario": (form.get("preco_compra_unitario") or "").strip() or None,
            "preco_compra_unidade_preco": (form.get("preco_compra_unidade_preco") or "").strip().lower() or None,
            "preco_compra_fonte": (form.get("preco_compra_fonte") or "").strip() or None,
            "preco_compra_documento": (form.get("preco_compra_documento") or "").strip() or None,
            "preco_compra_chave_acesso": (form.get("preco_compra_chave_acesso") or "").strip() or None,
            "preco_compra_data_emissao": (form.get("preco_compra_data_emissao") or "").strip() or None,
            "preco_compra_data_recebimento": (form.get("preco_compra_data_recebimento") or "").strip() or None,
            "preco_reposicao_unitario": (form.get("preco_reposicao_unitario") or "").strip() or None,
            "preco_reposicao_unidade_preco": (form.get("preco_reposicao_unidade_preco") or "").strip().lower() or None,
            "preco_reposicao_fonte": (form.get("preco_reposicao_fonte") or "").strip() or None,
            "preco_reposicao_uf": (form.get("preco_reposicao_uf") or "").strip() or None,
            "preco_reposicao_query": (form.get("preco_reposicao_query") or "").strip() or None,
            "preco_reposicao_url": (form.get("preco_reposicao_url") or "").strip() or None,
            "finance_supplier_id": finance_payload.get("supplier_id"),
            "finance_origem_valor": finance_payload.get("origem_valor"),
            "finance_tipo_documento": finance_payload.get("tipo_documento"),
            "finance_comprovacao_status": finance_payload.get("comprovacao_status"),
            "finance_observacao": finance_payload.get("observacao"),
        })
        payload["preco_compra_atualizado_em"] = datetime.utcnow()
        payload["preco_compra_atualizado_por"] = current_user.nome if hasattr(current_user, "nome") else current_user.id

    # Preservar campos antigos se não forem substituídos pelo novo sistema?
    # Neste caso, estamos assumindo que o formulário é a fonte da verdade para a edição.
    
    try:
        # buscar estado anterior para notificação
        prev_balance = None
        try:
            if prev_item:
                prev_balance = int(prev_item.get("saldo", 0))
        except Exception:
            prev_balance = None

        if saldo_desejado < 0:
            raise ValueError("Informe uma quantidade válida")

        if registrar_compra_edicao:
            raise ValueError("A incorporação de novas compras pela edição do item foi desativada. Use Documentos Fiscais.")

        current_packaged_balance = float(prev_item.get("estoque_embalagens") or 0.0)
        current_loose_balance = float(prev_item.get("estoque_unidades_soltas") or 0.0)
        current_total_balance = float(prev_item.get("saldo") or 0.0)
        previous_tipo_embalagem = prev_item.get("tipo_embalagem_novo") or None
        effective_tipo_embalagem = tipo_novo if tipo_novo is not None else previous_tipo_embalagem
        previous_uses_packaging = bool(previous_tipo_embalagem and prev_item.get("unidades_por_embalagem"))

        # A validação do saldo deve respeitar o modo de estoque ANTERIOR.
        # Ao definir litragem/embalagem pela primeira vez, o usuário está ajustando metadados,
        # não alterando o saldo operacional já bloqueado.
        if previous_uses_packaging:
            if abs(float(saldo_desejado) - current_packaged_balance) > 1e-6:
                raise ValueError("O saldo do item não pode mais ser alterado pela edição. Use Documentos Fiscais para entradas e rotinas operacionais para saídas/devoluções.")
            if saldo_unidades_soltas_raw:
                try:
                    saldo_unidades_soltas_informado = float(saldo_unidades_soltas_raw)
                except ValueError:
                    raise ValueError("Informe uma quantidade válida para unidades soltas")
                if abs(saldo_unidades_soltas_informado - current_loose_balance) > 1e-6:
                    raise ValueError("As unidades soltas não podem ser alteradas pela edição do item. Use Documentos Fiscais quando houver entrada de estoque.")
        elif abs(float(saldo_desejado) - current_total_balance) > 1e-6:
            raise ValueError("O saldo do item não pode mais ser alterado pela edição. Use Documentos Fiscais para entradas e rotinas operacionais para saídas/devoluções.")

        previous_internal_balance = float(prev_item.get("saldo") or 0.0)
        effective_unidades_por_embalagem = unidades_var
        if effective_unidades_por_embalagem in (None, ""):
            try:
                effective_unidades_por_embalagem = float(prev_item.get("unidades_por_embalagem") or 0.0)
            except (TypeError, ValueError):
                effective_unidades_por_embalagem = 0.0
        target_internal_balance = float(saldo_desejado)
        if effective_tipo_embalagem and float(effective_unidades_por_embalagem or 0.0) > 0:
            if saldo_unidades_soltas_raw == "":
                saldo_unidades_soltas_preview = float(prev_item.get("estoque_unidades_soltas") or 0.0)
            else:
                try:
                    saldo_unidades_soltas_preview = float(saldo_unidades_soltas_raw)
                except ValueError:
                    saldo_unidades_soltas_preview = -1
            if saldo_unidades_soltas_preview < 0:
                raise ValueError("Informe uma quantidade válida para unidades soltas")
            target_internal_balance = (float(saldo_desejado) * float(effective_unidades_por_embalagem)) + float(saldo_unidades_soltas_preview)

        purchase_delta = max(0.0, float(target_internal_balance) - previous_internal_balance)

        if finance_section_edit_authorized:
            comprovacao_status = str(finance_payload.get("comprovacao_status") or "sem_comprovacao").strip().lower()
            observacao_financeira = str(finance_payload.get("observacao") or "").strip()
            if comprovacao_status in {"sem_comprovacao", "parcial"} and not observacao_financeira:
                raise ValueError("A observação financeira é obrigatória ao salvar origem da compra sem comprovação completa.")

        # Processar upload de foto (se enviado)
        foto_file = request.files.get('foto')
        remover_foto = form.get('remover_foto')
        
        if remover_foto:
            # Remover foto existente
            if prev_item and prev_item.get('foto_path'):
                ItemFotoService.deletar_foto(prev_item['foto_path'])
            payload['foto_path'] = None
        elif foto_file and foto_file.filename:
            # Upload de nova foto
            try:
                # Deletar foto antiga se existir
                if prev_item and prev_item.get('foto_path'):
                    ItemFotoService.deletar_foto(prev_item['foto_path'])
                
                foto_path = ItemFotoService.upload_foto(foto_file, codigo)
                payload['foto_path'] = foto_path
            except ValueError as e:
                flash(f"Erro no upload da foto: {str(e)}", "warning")

        updated_codigo = inventory_service.update_item(codigo, payload)
        if abs(float(target_internal_balance) - float(previous_internal_balance)) > 1e-6:
            inventory_service.set_admin_absolute_balance(
                codigo=updated_codigo,
                novo_saldo=float(target_internal_balance),
                matricula=current_user.id,
                motivo="reclassificacao_embalagem",
                notify=False,
                audit_context={
                    "source": "inventory.update_item",
                    "previous_internal_balance": float(previous_internal_balance),
                    "target_internal_balance": float(target_internal_balance),
                    "tipo_embalagem_anterior": previous_tipo_embalagem,
                    "tipo_embalagem_novo": effective_tipo_embalagem,
                },
            )
        process_pending_result = None
        if finalize_pre_registration:
            process_pending_result = finance_service.process_pending_document_items_for_item(
                updated_codigo,
                usuario_matricula=current_user.id,
            )
            _clear_document_runtime_cache(process_pending_result.get("document_numbers"))

        history_recorded = False
        if finance_section_edit_authorized:
            _sync_finance_section_snapshot(
                codigo=updated_codigo,
                categoria=str(payload.get("categoria") or prev_item.get("categoria") or "Sem categoria"),
                preco_compra_unitario=payload.get("preco_compra_unitario"),
                usuario_id=current_user.id,
                finance_payload=finance_payload,
            )
        
        # Quando o saldo aumentou, adjust_item_balance já enviou o alerta operacional.
        # Mantemos notify_item_updated apenas para alterações cadastrais e ajustes sem entrada.
        should_notify_item_update = True
        try:
            item_pos_edicao = inventory_service.get_item(updated_codigo)
            saldo_atual_pos_edicao = int(float(item_pos_edicao.get("saldo") or 0)) if item_pos_edicao else None
            if prev_balance is not None and saldo_atual_pos_edicao is not None and saldo_atual_pos_edicao > prev_balance:
                should_notify_item_update = False
        except Exception:
            should_notify_item_update = True

        if should_notify_item_update:
            try:
                NotificationRouterService.route_item_updated(
                    updated_codigo,
                    prev=prev_item,
                    prev_balance=prev_balance,
                )
            except Exception:
                pass
        if process_pending_result:
            if process_pending_result.get("processed"):
                flash(
                    f"{process_pending_result['processed']} lançamento(s) documental(is) foram incorporados ao estoque após a finalização do pré-cadastro.",
                    "info",
                )
            elif not process_pending_result.get("errors") and not process_pending_result.get("skipped"):
                flash("O pré-cadastro foi finalizado, mas não havia lançamentos documentais pendentes para incorporar ao estoque.", "info")
            if process_pending_result.get("errors"):
                flash("O pré-cadastro foi finalizado, mas houve falhas ao incorporar parte dos lançamentos documentais ao estoque.", "warning")
        flash("Item atualizado com sucesso.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("inventory.edit_item_form", codigo=codigo))
    return redirect(url_for("inventory.list_items"))


@blueprint.get("/<codigo>/precos/reposicao/sugestoes")
@login_required
def sugestoes_preco_reposicao(codigo: str):
    item = Item.query.get(codigo)
    if not item:
        return {"success": False, "message": "Item nÃ£o encontrado"}, 404

    query = (request.args.get("q") or "").strip() or (item.descricao or "").strip()
    uf = _resolve_replacement_price_uf(request.args.get("uf"))

    try:
        data = price_suggestion_service.get_replacement_suggestions(query=query, uf=uf or None, limit=20)
    except Exception:
        current_app.logger.exception("Erro ao buscar sugestoes de preco de reposicao (codigo=%s)", codigo)
        return {"success": False, "message": "Erro interno ao buscar sugestoes"}, 500
    data["success"] = True
    return data


@blueprint.get("/categoria/<path:categoria>/precos/reposicao/lote")
@login_required
def sugestoes_preco_reposicao_lote(categoria: str):
    if not _is_admin(current_user):
        return {"success": False, "message": "Acesso negado"}, 403

    categoria_norm = (categoria or "").strip()
    if not categoria_norm:
        return {"success": False, "message": "Categoria invalida"}, 400

    try:
        item_limit = max(1, min(int(request.args.get("item_limit") or request.args.get("limit") or 10), 10))
    except (TypeError, ValueError):
        item_limit = 10

    try:
        suggestion_limit = max(1, min(int(request.args.get("suggestion_limit") or 10), 20))
    except (TypeError, ValueError):
        suggestion_limit = 10

    uf = _resolve_replacement_price_uf(request.args.get("uf"))

    items = (
        Item.query
        .filter(Item.categoria == categoria_norm)
        .order_by(Item.descricao.asc(), Item.codigo_item.asc())
        .limit(item_limit)
        .all()
    )

    requests_payload: list[dict[str, object]] = []
    item_map: dict[str, Item] = {}
    for item in items:
        query = _build_replacement_price_query(item)
        if not query:
            continue
        item_map[item.codigo_item] = item
        requests_payload.append({"item_id": item.codigo_item, "query": query})

    try:
        batch_data = price_suggestion_service.get_replacement_suggestions_batch(
            requests_payload=requests_payload,
            uf=uf or None,
            suggestion_limit=suggestion_limit,
            max_workers=min(4, max(len(requests_payload), 1)),
        )
    except Exception:
        current_app.logger.exception(
            "Erro ao buscar sugestoes em lote por categoria (categoria=%s)",
            categoria_norm,
        )
        return {"success": False, "message": "Erro interno ao buscar sugestões em lote"}, 500

    payload_items: list[dict[str, object]] = []
    for row in batch_data.get("items") or []:
        item_id = _safe_text(row.get("item_id")).strip()
        item = item_map.get(item_id)
        if not item:
            continue
        payload_items.append(
            {
                "item": _serialize_batch_price_item(item),
                "query": row.get("query"),
                "uf": row.get("uf"),
                "suggestions": row.get("suggestions") or [],
                "stats": row.get("stats") or {},
                "providers": row.get("providers") or [],
                "success": bool(row.get("success", True)),
                "error": row.get("error"),
            }
        )

    return {
        "success": True,
        "categoria": categoria_norm,
        "uf": batch_data.get("uf") or uf or None,
        "limit": item_limit,
        "suggestion_limit": suggestion_limit,
        "items": payload_items,
        "summary": batch_data.get("summary") or {
            "requested": len(requests_payload),
            "completed": len(payload_items),
            "failed": 0,
            "with_results": 0,
        },
    }


@blueprint.post("/<codigo>/precos/reposicao")
@login_required
def salvar_preco_reposicao(codigo: str):
    if not _is_admin(current_user):
        return {"success": False, "message": "Acesso negado"}, 403
    item = Item.query.get(codigo)
    if not item:
        return {"success": False, "message": "Item nÃ£o encontrado"}, 404

    payload = request.json or request.form or {}
    raw_price = payload.get("preco_reposicao_unitario")
    try:
        price = float(raw_price)
    except (TypeError, ValueError):
        return {"success": False, "message": "PreÃ§o invÃ¡lido"}, 400
    if price <= 0:
        return {"success": False, "message": "PreÃ§o invÃ¡lido"}, 400

    fonte = (payload.get("preco_reposicao_fonte") or "Mercado Livre").strip()
    uf = (payload.get("preco_reposicao_uf") or "").strip().upper() or None
    query = (payload.get("preco_reposicao_query") or "").strip() or None
    url = (payload.get("preco_reposicao_url") or "").strip() or None
    unidade_preco = (payload.get("preco_reposicao_unidade_preco") or "").strip().lower() or (item.preco_reposicao_unidade_preco or "").strip().lower() or infer_price_unit_for_item(item)

    preco_reposicao_base = price
    fator_preco_base = 1.0
    try:
        normalized = normalize_item_price(
            item,
            unit_price=price,
            price_unit=unidade_preco,
        )
        preco_reposicao_base = float(normalized.unit_price_base)
        unidade_preco = normalized.price_unit
        fator_preco_base = float(normalized.factor_to_base)
    except Exception:
        fallback_unidade_preco = infer_price_unit_for_item(item)
        if fallback_unidade_preco != unidade_preco:
            try:
                normalized = normalize_item_price(
                    item,
                    unit_price=price,
                    price_unit=fallback_unidade_preco,
                )
                preco_reposicao_base = float(normalized.unit_price_base)
                unidade_preco = normalized.price_unit
                fator_preco_base = float(normalized.factor_to_base)
            except Exception:
                preco_reposicao_base = price
        else:
            preco_reposicao_base = price

    item.preco_reposicao_unitario = price
    item.preco_reposicao_unitario_base = preco_reposicao_base
    item.preco_reposicao_unidade_preco = unidade_preco
    item.preco_reposicao_fator_base = fator_preco_base
    item.preco_reposicao_fonte = fonte
    item.preco_reposicao_uf = uf
    item.preco_reposicao_query = query
    item.preco_reposicao_url = url
    item.preco_reposicao_atualizado_em = datetime.utcnow()
    item.preco_reposicao_atualizado_por = current_user.nome if hasattr(current_user, "nome") else current_user.id
    item.ultima_edicao_em = datetime.utcnow()
    item.ultima_edicao_por = item.preco_reposicao_atualizado_por
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Erro ao salvar preco de reposicao (codigo=%s)", codigo)
        return {"success": False, "message": "Erro interno ao salvar preco de reposicao"}, 500

    return {
        "success": True,
        "item": {
            "codigo": item.codigo_item,
            "preco_reposicao_unitario": item.preco_reposicao_unitario,
            "preco_reposicao_unitario_base": item.preco_reposicao_unitario_base,
            "preco_reposicao_unidade_preco": item.preco_reposicao_unidade_preco,
            "preco_reposicao_fator_base": item.preco_reposicao_fator_base,
            "preco_reposicao_fonte": item.preco_reposicao_fonte,
            "preco_reposicao_uf": item.preco_reposicao_uf,
            "preco_reposicao_query": item.preco_reposicao_query,
            "preco_reposicao_url": item.preco_reposicao_url,
            "preco_reposicao_atualizado_em": item.preco_reposicao_atualizado_em.isoformat() if item.preco_reposicao_atualizado_em else None,
            "preco_reposicao_atualizado_por": item.preco_reposicao_atualizado_por,
        },
    }





@blueprint.post("/foto/url")
@login_required
def aplicar_foto_url_global():
    """Endpoint estavel para aplicar foto por URL sem depender do codigo na rota."""
    _require_admin()
    payload = request.form if request.form else (request.json or {})
    codigo = (payload.get("codigo") or "").strip()
    image_url = (payload.get("image_url") or "").strip()
    if not codigo:
        return {"success": False, "message": "Codigo do item nao informado"}, 400
    if not image_url:
        return {"success": False, "message": "URL da imagem nao informada"}, 400

    item = Item.query.get(codigo)
    if not item:
        return {"success": False, "message": "Item nao encontrado"}, 404

    try:
        if item.foto_path:
            ItemFotoService.deletar_foto(item.foto_path)

        foto_path = ItemFotoService.download_foto_from_url(image_url, codigo)
        item.foto_path = foto_path
        from ..extensions import db
        db.session.commit()
        return {"success": True, "message": "Foto atualizada", "foto_path": foto_path}
    except ValueError as exc:
        return {"success": False, "message": str(exc)}, 400
    except Exception:
        return {"success": False, "message": "Falha inesperada ao atualizar foto"}, 500


@blueprint.post("/foto/upload")
@login_required
def aplicar_foto_upload_global():
    """Endpoint estavel para upload rápido de foto sem depender do codigo na rota."""
    _require_admin()
    codigo = (request.form.get("codigo") or "").strip()
    foto_file = request.files.get("foto")
    if not codigo:
        return {"success": False, "message": "Codigo do item nao informado"}, 400
    if not foto_file or not getattr(foto_file, "filename", ""):
        return {"success": False, "message": "Selecione uma imagem para enviar"}, 400

    item = Item.query.get(codigo)
    if not item:
        return {"success": False, "message": "Item nao encontrado"}, 404

    try:
        if item.foto_path:
            ItemFotoService.deletar_foto(item.foto_path)

        foto_path = ItemFotoService.upload_foto(foto_file, codigo)
        item.foto_path = foto_path
        from ..extensions import db
        db.session.commit()
        return {"success": True, "message": "Foto atualizada", "foto_path": foto_path}
    except ValueError as exc:
        return {"success": False, "message": str(exc)}, 400
    except Exception:
        return {"success": False, "message": "Falha inesperada ao atualizar foto"}, 500


@blueprint.post("/<codigo>/foto/url")
@login_required
def atualizar_foto_por_url(codigo: str):
    _require_admin()
    item = Item.query.get(codigo)
    if not item:
        return {"success": False, "message": "Item nao encontrado"}, 404

    payload = request.form if request.form else (request.json or {})
    image_url = (payload.get("image_url") or "").strip()
    if not image_url:
        return {"success": False, "message": "URL da imagem nao informada"}, 400

    try:
        # remover foto anterior (se existir)
        if item.foto_path:
            ItemFotoService.deletar_foto(item.foto_path)

        foto_path = ItemFotoService.download_foto_from_url(image_url, codigo)
        item.foto_path = foto_path
        db.session.commit()
        return {"success": True, "message": "Foto atualizada", "foto_path": foto_path}
    except ValueError as exc:
        return {"success": False, "message": str(exc)}, 400
    except Exception:
        return {"success": False, "message": "Falha inesperada ao atualizar foto"}, 500
@blueprint.post("/<codigo>/excluir")
@login_required
def delete_item(codigo: str):
    _require_admin()
    try:
        inventory_service.delete_item(codigo)
        flash("Item excluído.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("inventory.list_items"))


@blueprint.post("/<codigo>/entrada")
@login_required
def registrar_entrada(codigo: str):
    _require_admin()
    quantidade = float(request.form.get("quantidade", "0") or 0)
    nota = request.form.get("nota_fiscal") or None
    
    # Capturar tipo de entrada para unidades dinâmicas
    tipo_entrada = request.form.get("tipo_entrada")  # "embalagem" ou "unidades"
    em_embalagens = None
    if tipo_entrada == "embalagem":
        em_embalagens = True
    elif tipo_entrada == "unidades":
        em_embalagens = False
    # Se tipo_entrada não foi enviado (item sem unidades dinâmicas), em_embalagens fica None
    
    try:
        if nota:
            finance_service.validate_document_backed_stock_entry(
                codigo_item=codigo,
                quantidade=quantidade,
                numero_documento=nota,
                tipo_documento="nf",
            )

        entrada = inventory_service.registrar_entrada(
            MovimentoPayload(codigo=codigo, quantidade=quantidade, matricula=current_user.id, nota_fiscal=nota, em_embalagens=em_embalagens)
        )

        if nota:
            finance_service.register_stock_document_entry(
                codigo_item=codigo,
                quantidade=float(quantidade),
                tipo_documento="nf",
                numero_documento=str(nota),
                entrada_id=getattr(entrada, "id_entrada", None),
                usuario_matricula=current_user.id,
                origem_valor="compra_nf",
            )
        flash("Entrada registrada.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("inventory.list_items"))


@blueprint.post("/<codigo>/saida")
@login_required
def registrar_saida(codigo: str):
    _require_admin()
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )
    quantidade = float(request.form.get("quantidade", "0") or 0)
    tipo_custodia = (request.form.get("tipo_custodia", "temporaria") or "").strip().lower()
    # Compat: instalações antigas usavam "diaria" para empréstimo temporário.
    if tipo_custodia in {"diaria", "diária", "daily", "d"}:
        tipo_custodia = "temporaria"
    if tipo_custodia in {"perm", "p"}:
        tipo_custodia = "permanente"
    if tipo_custodia not in {"temporaria", "permanente"}:
        tipo_custodia = "temporaria"
    matricula = request.form.get("matricula") or current_user.id
    
    # Capturar tipo de saída para unidades dinâmicas
    tipo_saida = request.form.get("tipo_saida")  # "embalagem" ou "unidades"
    em_embalagens = None
    if tipo_saida == "embalagem":
        em_embalagens = True
    elif tipo_saida == "unidades":
        em_embalagens = False
    # Se tipo_saida não foi enviado (item sem unidades dinâmicas), em_embalagens fica None
    operational_context = _collect_operational_context(request.form)
    
    try:
        saida_id = inventory_service.registrar_saida(
            MovimentoPayload(
                codigo=codigo, 
                quantidade=quantidade, 
                matricula=matricula,
                tipo_custodia=tipo_custodia,
                atividade_operacional=operational_context.get("atividade_operacional"),
                ordem_servico=operational_context.get("ordem_servico"),
                centro_custo=operational_context.get("centro_custo"),
                em_embalagens=em_embalagens
            )
        )
        flash("Saída registrada.", "success")
        if wants_json:
            return jsonify({"success": True, "saida_id": saida_id, "message": "Saída registrada."})
    except ValueError as exc:
        flash(str(exc), "danger")
        if wants_json:
            return jsonify({"success": False, "message": str(exc)}), 400
    return redirect(url_for("inventory.list_items"))


@blueprint.post("/<codigo>/saida-lote")
@login_required
def registrar_saida_lote(codigo: str):
    _require_admin()
    payload_json = request.get_json(silent=True) or {}
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
        or bool(payload_json)
    )

    matriculas_raw = payload_json.get("matriculas")
    if not isinstance(matriculas_raw, list):
        matriculas_raw = request.form.getlist("matricula")
    matriculas = [str(matricula).strip() for matricula in (matriculas_raw or []) if str(matricula).strip()]
    if not matriculas:
        return jsonify({"success": False, "message": "Selecione ao menos um funcionário."}), 400

    quantidade = float(payload_json.get("quantidade") or request.form.get("quantidade") or 1)
    if quantidade <= 0:
        return jsonify({"success": False, "message": "Quantidade inválida."}), 400

    tipo_custodia = (payload_json.get("tipo_custodia") or request.form.get("tipo_custodia") or "temporaria").strip().lower()
    if tipo_custodia in {"diaria", "diária", "daily", "d"}:
        tipo_custodia = "temporaria"
    if tipo_custodia in {"perm", "p"}:
        tipo_custodia = "permanente"
    if tipo_custodia not in {"temporaria", "permanente"}:
        tipo_custodia = "temporaria"

    tipo_saida = payload_json.get("tipo_saida") or request.form.get("tipo_saida")
    em_embalagens = None
    if tipo_saida == "embalagem":
        em_embalagens = True
    elif tipo_saida == "unidades":
        em_embalagens = False

    operational_context = _collect_operational_context(payload_json or request.form)

    saida_ids: list[int] = []
    errors: list[str] = []
    for matricula in matriculas:
        try:
            saida_id = inventory_service.registrar_saida(
                MovimentoPayload(
                    codigo=codigo,
                    quantidade=quantidade,
                    matricula=matricula,
                    tipo_custodia=tipo_custodia,
                    atividade_operacional=operational_context.get("atividade_operacional"),
                    ordem_servico=operational_context.get("ordem_servico"),
                    centro_custo=operational_context.get("centro_custo"),
                    em_embalagens=em_embalagens,
                ),
                skip_notification=True,
            )
            saida_ids.append(saida_id)
        except ValueError as exc:
            errors.append(f"{matricula}: {exc}")

    if saida_ids:
        try:
            if tipo_custodia == "permanente":
                TelegramService.notify_multiple_permanent_custody(saida_ids)
            else:
                for saida_id in saida_ids:
                    TelegramService.notify_withdrawal(saida_id, force_single=True)
        except Exception:
            pass

    success_count = len(saida_ids)
    failed_count = len(errors)
    if success_count == 0:
        return jsonify({
            "success": False,
            "message": "Nenhuma atribuição foi concluída.",
            "success_count": 0,
            "failed_count": failed_count,
            "errors": errors,
            "saida_ids": saida_ids,
        }), 400

    message = "Atribuição em lote concluída." if failed_count == 0 else "Atribuição em lote concluída parcialmente."
    if not wants_json:
        flash(message, "success" if failed_count == 0 else "warning")
        for error in errors[:5]:
            flash(error, "warning")
        return redirect(url_for("inventory.list_items"))

    return jsonify({
        "success": True,
        "message": message,
        "success_count": success_count,
        "failed_count": failed_count,
        "errors": errors,
        "saida_ids": saida_ids,
    })


@blueprint.post('/<codigo>/notify')
@login_required
def notify_item(codigo: str):
    _require_admin()
    try:
        from ..services.telegram_service import TelegramService

        res = TelegramService.notify_item_now(codigo)
        if res.get('success'):
            flash('Notificação enviada para administradores vinculados.', 'success')
        else:
            flash(f"Falha ao enviar notificação: {res.get('error')}", 'warning')
    except Exception as exc:
        flash(f'Erro ao notificar: {exc}', 'danger')
    return redirect(url_for('inventory.list_items'))


@blueprint.post('/categoria/<path:categoria>/excluir')
@login_required
def delete_category(categoria: str):
    _require_admin()
    try:
        # Buscar todos os itens da categoria
        itens = inventory_service.list_items()
        itens_categoria = [item for item in itens if item.get("categoria") == categoria]
        
        if not itens_categoria:
            flash(f"Nenhum item encontrado na categoria '{categoria}'.", "warning")
            return redirect(url_for('inventory.list_items'))
        
        # Excluir cada item da categoria
        deleted_count = 0
        for item in itens_categoria:
            try:
                inventory_service.delete_item(item["codigo"])
                deleted_count += 1
            except Exception:
                pass
        
        if deleted_count > 0:
            flash(f"Categoria '{categoria}' excluída com sucesso ({deleted_count} itens removidos).", "success")
        else:
            flash(f"Não foi possível excluir itens da categoria '{categoria}'.", "danger")
    except Exception as exc:
        flash(f"Erro ao excluir categoria: {exc}", "danger")
    return redirect(url_for('inventory.list_items'))


@blueprint.post('/categoria/<path:categoria>/excluir_inativos')
@login_required
def delete_inactive_items_by_category(categoria: str):
    """Exclui itens "inativos" (saldo 0) de uma categoria.

    Observação: aqui tratamos como inativo o item cujo saldo atual é <= 0.
    """
    _require_admin()
    try:
        itens = inventory_service.list_items()
        itens_categoria = [item for item in itens if item.get("categoria") == categoria]

        if not itens_categoria:
            flash(f"Nenhum item encontrado na categoria '{categoria}'.", "warning")
            return redirect(url_for('inventory.list_items', categoria=categoria))

        inativos = [item for item in itens_categoria if _safe_float(item.get("saldo")) <= 0]
        if not inativos:
            flash(f"Nenhum item inativo (saldo 0) encontrado na categoria '{categoria}'.", "info")
            return redirect(url_for('inventory.list_items', categoria=categoria))

        deleted_count = 0
        failed_count = 0
        for item in inativos:
            codigo = item.get("codigo")
            if not codigo:
                continue
            try:
                inventory_service.delete_item(codigo)
                deleted_count += 1
            except Exception:
                failed_count += 1

        if deleted_count:
            msg = f"Itens inativos excluídos na categoria '{categoria}': {deleted_count}."
            if failed_count:
                msg += f" Falharam: {failed_count}."
            flash(msg, "success")
        else:
            flash(f"Não foi possível excluir itens inativos na categoria '{categoria}'.", "danger")
    except Exception as exc:
        flash(f"Erro ao excluir itens inativos: {exc}", "danger")
    return redirect(url_for('inventory.list_items', categoria=categoria))


@blueprint.get('/categoria/<path:categoria>/relatorio')
@login_required
def category_report(categoria: str):
    """Gera relatório de itens de uma categoria em PDF."""
    requested_format = (request.args.get("format") or "pdf").strip().lower()
    if requested_format not in {"pdf", "xlsx"}:
        flash("Formato inválido. Use PDF.", "danger")
        return redirect(url_for("inventory.list_items", categoria=categoria))
    format_type = "pdf"

    itens = inventory_service.list_items()
    itens_categoria = [item for item in itens if item.get("categoria") == categoria]
    if not itens_categoria:
        flash(f"Nenhum item encontrado na categoria '{categoria}'.", "warning")
        return redirect(url_for("inventory.list_items", categoria=categoria))

    itens_categoria.sort(key=lambda x: _safe_text(x.get("descricao")).lower())

    timestamp = TimeService.now_local().strftime('%Y%m%d_%H%M%S')
    category_slug = _sanitize_filename_component(categoria)

    if format_type == "xlsx":
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
        except Exception:
            flash("Não foi possível gerar XLSX (dependência openpyxl).", "danger")
            return redirect(url_for("inventory.list_items", categoria=categoria))

        from ..utils.report_branding import get_company_header_lines

        wb = Workbook()
        ws = wb.active
        ws.title = "Categoria"

        ws.append(["RELATÓRIO DE ITENS - CATEGORIA"])
        for line in get_company_header_lines():
            ws.append([line])
        ws.append([f"Categoria: {categoria}"])
        ws.append([f"Total de itens: {len(itens_categoria)}"])
        ws.append([f"Gerado em: {TimeService.now_local().strftime('%d/%m/%Y %H:%M')}"])
        ws.append([])

        header_fill = PatternFill(start_color="1f2937", end_color="1f2937", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)

        headers = [
            "Código",
            "Descrição",
            "Marca",
            "Unidade",
            "Saldo",
            "Mín.",
            "Localização",
            "Última edição",
            "Editado por",
        ]
        header_row_index = ws.max_row + 1
        ws.append(headers)
        for cell in ws[header_row_index]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        for item in itens_categoria:
            saldo = item.get("saldo_display") or item.get("saldo")
            minimo = item.get("estoque_minimo")
            ultima_edicao_em = item.get("ultima_edicao_em")
            ws.append(
                [
                    _safe_text(item.get("codigo")),
                    _safe_text(item.get("descricao")),
                    _safe_text(item.get("marca")) or "N/D",
                    _safe_text(item.get("unidade")) or "N/D",
                    saldo,
                    minimo if minimo is not None else "",
                    _safe_text(item.get("localizacao")) or "",
                    _safe_text(ultima_edicao_em) or "",
                    _safe_text(item.get("ultima_edicao_por")) or "",
                ]
            )

        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["B"].width = 50
        ws.column_dimensions["C"].width = 22
        ws.column_dimensions["D"].width = 12
        ws.column_dimensions["E"].width = 10
        ws.column_dimensions["F"].width = 8
        ws.column_dimensions["G"].width = 25
        ws.column_dimensions["H"].width = 24
        ws.column_dimensions["I"].width = 22

        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        filename = f"relatorio_categoria_{category_slug}_{timestamp}.xlsx"
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # PDF
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception:
        flash("Não foi possível gerar PDF (dependência reportlab).", "danger")
        return redirect(url_for("inventory.list_items", categoria=categoria))

    from ..utils.report_branding import get_company_header_html

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.5 * cm,
        rightMargin=0.5 * cm,
        topMargin=0.5 * cm,
        bottomMargin=0.5 * cm,
        title="Relatório de Itens por Categoria",
        author="GALINT",
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.fontSize = 8
    body_style.leading = 9
    story = []

    title_style = styles["Title"]
    title_style.alignment = 1
    title_style.fontSize = 16
    subtitle_style = styles["Normal"]
    subtitle_style.alignment = 1

    story.append(Paragraph("RELATÓRIO DE ITENS - CATEGORIA", title_style))
    story.append(Paragraph(get_company_header_html(), subtitle_style))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph(f"Categoria: <b>{_safe_text(categoria)}</b>", styles["Normal"]))
    story.append(Paragraph(f"Total de itens: {len(itens_categoria)}", styles["Normal"]))
    story.append(Paragraph(f"Gerado em: {TimeService.now_local().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 0.4 * cm))

    header = ["Código", "Descrição", "Marca", "Unidade", "Saldo", "Mín.", "Localização"]
    data = [header]
    for item in itens_categoria:
        saldo = item.get("saldo_display") or item.get("saldo")
        data.append(
            [
                _safe_text(item.get("codigo")),
                Paragraph(_safe_text(item.get("descricao"))[:80], body_style),
                Paragraph((_safe_text(item.get("marca")) or "N/D")[:30], body_style),
                _safe_text(item.get("unidade")) or "N/D",
                _safe_text(saldo),
                _safe_text(item.get("estoque_minimo")),
                Paragraph((_safe_text(item.get("localizacao")) or "")[:60], body_style),
            ]
        )

    table = Table(
        data,
        colWidths=[3.2 * cm, 10.0 * cm, 4.2 * cm, 2.4 * cm, 2.0 * cm, 1.6 * cm, 6.0 * cm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)
    doc.build(story)

    buffer.seek(0)
    filename = f"relatorio_categoria_{category_slug}_{timestamp}.pdf"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf",
    )


@blueprint.post('/barcodes/gerar')
@login_required
def generate_all_barcodes():
    _require_admin()
    stats = inventory_service.ensure_barcodes_for_all()
    message = (
        f"Códigos de barras: {stats['generated']} gerados, "
        f"{stats['skipped']} já existiam, {stats['failed']} falharam."
    )
    category = "success" if stats["failed"] == 0 else "warning"
    flash(message, category)
    return redirect(url_for('inventory.list_items'))


@blueprint.get("/<codigo>/barcode.svg")
@login_required
def item_barcode_svg(codigo: str):
    _require_admin()
    item = Item.query.get(codigo)
    if not item:
        abort(404)

    payload = (item.codigo_item or "").strip()
    if not payload:
        abort(400)

    try:
        import barcode
        from barcode.writer import SVGWriter
    except Exception as exc:
        raise ValueError(
            "Biblioteca de código de barras não instalada. Instale 'python-barcode' (pip install python-barcode)."
        ) from exc

    code = barcode.get(
        "code128",
        payload,
        writer=SVGWriter(),
    )

    buffer = BytesIO()
    code.write(
        buffer,
        options={
            "write_text": False,
            "module_width": 0.4,
            "module_height": 24.0,
            "quiet_zone": 10.0,
            "background": "white",
            "foreground": "black",
        },
    )
    svg_bytes = buffer.getvalue()

    if not item.barcode_image_path:
        try:
            barcode_path = get_barcode_path(payload) or generate_barcode(payload, item.descricao)
            item.barcode_image_path = barcode_path
            from ..extensions import db
            db.session.commit()
        except Exception:
            pass

    resp = make_response(svg_bytes)
    resp.mimetype = "image/svg+xml"
    resp.headers["Content-Disposition"] = f'inline; filename="barcode_item_{payload}.svg"'
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@blueprint.get("/<codigo>/barcode.png")
@login_required
def item_barcode_png(codigo: str):
    _require_admin()
    item = Item.query.get(codigo)
    if not item:
        abort(404)

    payload = (item.codigo_item or "").strip()
    if not payload:
        abort(400)

    try:
        import barcode
        from barcode.writer import ImageWriter
    except Exception as exc:
        raise ValueError(
            "Biblioteca de código de barras não instalada. Instale 'python-barcode' (pip install python-barcode)."
        ) from exc

    code = barcode.get(
        "code128",
        payload,
        writer=ImageWriter(),
    )

    buffer = BytesIO()
    code.write(
        buffer,
        options={
            "write_text": False,
            "module_width": 0.4,
            "module_height": 28.0,
            "quiet_zone": 12.0,
            "background": "white",
            "foreground": "black",
        },
    )
    png_bytes = buffer.getvalue()

    if not item.barcode_image_path:
        try:
            barcode_path = get_barcode_path(payload) or generate_barcode(payload, item.descricao)
            item.barcode_image_path = barcode_path
            from ..extensions import db
            db.session.commit()
        except Exception:
            pass

    resp = make_response(png_bytes)
    resp.mimetype = "image/png"
    resp.headers["Content-Disposition"] = f'inline; filename="barcode_item_{payload}.png"'
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@blueprint.get("/api/<codigo>")
@login_required
def get_item_api(codigo: str):
    """API endpoint para buscar informações do item."""
    item = inventory_service.get_item(codigo)
    if not item:
        return jsonify({"success": False, "message": "Item não encontrado."}), 404

    return jsonify({"success": True, "item": item})


@blueprint.get("/api/<codigo>/history")
@login_required
def get_item_history_api(codigo: str):
    item = inventory_service.get_item(codigo)
    if not item:
        return jsonify({"success": False, "message": "Item não encontrado."}), 404

    history = inventory_service.list_item_movements(codigo, limit=20)
    return jsonify(
        {
            "success": True,
            "codigo": codigo,
            "history": [
                {
                    **registro,
                    "data": TimeService.isoformat_utc(registro.get("data")),
                }
                for registro in history
            ],
        }
    )


@blueprint.get("/api/nf-autofill")
@login_required
def nf_autofill_api():
    _require_admin_or_supervisor()
    numero = (request.args.get("numero") or "").strip()
    payload = _build_nf_autofill_payload(numero)
    if not payload:
        return jsonify({"found": False, "numero_documento": numero})
    return jsonify({"found": True, **payload})


@blueprint.get("/api/pre-cadastrados")
@login_required
def pre_registered_items_api():
    _require_admin_or_supervisor()
    numero = (request.args.get("numero") or "").strip()
    if numero:
        payload = _build_pre_registered_items_payload(numero)
        if not payload:
            return _json_no_store({
                "success": True,
                "mode": "single",
                "found": False,
                "numero_documento": numero,
                "documents": [],
                "items": [],
            })
        return _json_no_store({
            "success": True,
            "mode": "single",
            "found": True,
            "documents": [payload],
            **payload,
        })

    documents = _build_all_pre_registered_documents_payload()
    total_items = sum(len(document.get("items") or []) for document in documents)
    return _json_no_store({
        "success": True,
        "mode": "all",
        "found": bool(documents),
        "documents": documents,
        "total_documents": len(documents),
        "total_items": total_items,
    })


@blueprint.get("/api/equivalencias")
@login_required
def equivalent_items_api():
    _require_admin_or_supervisor()
    payload = {
        "codigo": (request.args.get("codigo") or "").strip() or None,
        "descricao": (request.args.get("descricao") or "").strip() or None,
        "marca": (request.args.get("marca") or "").strip() or None,
        "categoria": (request.args.get("categoria") or "").strip() or None,
        "unidade": (request.args.get("unidade") or "").strip() or None,
        "tipo_embalagem_novo": (request.args.get("tipo_embalagem_novo") or "").strip() or None,
        "unidades_por_embalagem": (request.args.get("unidades_por_embalagem") or "").strip() or None,
    }
    exclude_codigo = (request.args.get("exclude_codigo") or "").strip() or None
    candidates = inventory_service.find_equivalent_item_candidates(payload, exclude_codigo=exclude_codigo)

    enriched_candidates: list[dict[str, object]] = []
    for candidate in candidates:
        row = dict(candidate)
        codigo = str(row.get("codigo") or "").strip()
        if codigo:
            row["edit_url"] = url_for("inventory.edit_item_form", codigo=codigo)
        foto_path = str(row.get("foto_path") or "").strip()
        if foto_path:
            row["foto_url"] = url_for("static", filename=foto_path)
        enriched_candidates.append(row)

    return _json_no_store(
        {
            "success": True,
            "total": len(enriched_candidates),
            "candidates": enriched_candidates,
        }
    )
