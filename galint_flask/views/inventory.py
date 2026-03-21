"""Inventory CRUD routes."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from io import BytesIO

from flask import Blueprint, abort, current_app, flash, jsonify, make_response, redirect, render_template, request, send_file, session, url_for
from flask_login import login_required, current_user

from ..extensions import db
from ..models import FinanceLedgerEntry, Item, Usuario
from ..services.config_service import ConfigService
from ..services.finance_service import finance_service
from ..services.inventory import MovimentoPayload, inventory_service
from ..services.item_foto_service import ItemFotoService
from ..services.price_suggestion_service import price_suggestion_service
from ..services.telegram_service import TelegramService
from ..utils.barcode_generator import generate_barcode, get_barcode_path
from ..utils.time_service import TimeService
from .movements import LIQUID_PRODUCT_TYPES

blueprint = Blueprint("inventory", __name__, url_prefix="/itens")


def _uses_packaging_system(item_data: dict | None) -> bool:
    if not item_data:
        return False
    tipo = (item_data.get("tipo_embalagem_novo") or "").strip().lower()
    if tipo not in {"lata", "rolo", "pacote", "caixa", "litro", "balde", "saco"}:
        return False
    try:
        unidades_por = float(item_data.get("unidades_por_embalagem") or 0)
    except (TypeError, ValueError):
        return False
    return unidades_por > 0


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


def _extract_finance_payload(form, *, current_item: dict | None = None) -> dict[str, object]:
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
        if not chave_acesso:
            chave_acesso = (current_item.get("preco_compra_chave_acesso") or None)
        if data_emissao is None:
            data_emissao = _parse_iso_date(current_item.get("preco_compra_data_emissao"))
        if data_recebimento is None:
            data_recebimento = _parse_iso_date(current_item.get("preco_compra_data_recebimento"))

    if not comprovacao:
        comprovacao = "comprovado" if tipo_documento in {"nf", "cupom"} else "sem_comprovacao"
    numero_nf = (form.get("nota_fiscal") or "").strip()
    numero_documento = (
        numero_nf
        or (form.get("preco_compra_documento") or "").strip()
        or (current_item.get("nota_fiscal") if current_item else "")
        or (current_item.get("preco_compra_documento") if current_item else "")
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
    tipo_documento = (str(finance_payload.get("tipo_documento") or "")).strip().lower() or "nf"
    if tipo_documento not in {"nf", "cupom"}:
        return

    numero_documento = (str(finance_payload.get("numero_documento") or "")).strip()
    chave_acesso = (str(finance_payload.get("chave_acesso") or "")).strip()
    data_emissao = finance_payload.get("data_emissao_documento")
    supplier_id = finance_payload.get("supplier_id")

    informed_bridge_data = bool(numero_documento or chave_acesso or data_emissao or supplier_id)
    if not informed_bridge_data:
        return

    if not numero_documento:
        raise ValueError("Informe o número da NF/cupom para abrir o documento fiscal automaticamente.")

    existing_document = finance_service.get_stock_document_by_number(numero_documento)
    if existing_document:
        return

    missing_fields: list[str] = []
    if not supplier_id:
        missing_fields.append("fornecedor")
    if tipo_documento == "nf" and not chave_acesso:
        missing_fields.append("chave de acesso")
    if not isinstance(data_emissao, date):
        missing_fields.append("data de emissão")

    if missing_fields:
        raise ValueError(
            "Para vincular automaticamente esse documento fiscal ao item, informe: "
            + ", ".join(missing_fields)
            + "."
        )


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
        saldo_total = sum(_safe_float(item.get("saldo")) for item in items)
        category_cards.append(
            {
                "categoria": category,
                "total": len(items),
                "saldo_total": saldo_total,
                "entries": items,
            }
        )
    return render_template(
        "inventory/list.html",
        itens=itens,
        can_manage=can_manage,
        can_edit_items=can_edit_items,
        can_create=can_create,
        category_cards=category_cards,
        selected_category=request.args.get("categoria", "").strip(),
        users_list=users_list,
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


@blueprint.get("/novo")
@login_required
def new_item_form():
    _require_admin_or_supervisor()
    codigo_prefill = request.args.get("codigo", "").strip()
    form_data = {"codigo": codigo_prefill} if codigo_prefill else None
    
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
        saldo_desejado=0,
        saldo_total_ean=saldo_total_ean,
        liquid_types=LIQUID_PRODUCT_TYPES,
        preferred_supplier=None,
        all_suppliers=finance_service.list_suppliers(limit=300),
    )


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

    if tipo_novo in ["lata", "balde"]:
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
    elif tipo_novo == "caixa":
        unidades_var = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
    elif tipo_novo == "litro":
        litros_var = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        unidades_var = litros_var

    em_embalagens = None
    if tipo_novo in ["lata", "rolo", "pacote", "caixa", "litro", "balde", "saco"] and unidades_var and unidades_var > 0:
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
        "preco_compra_fonte": (form.get("preco_compra_fonte") or "").strip() or None,
        "preco_compra_documento": (form.get("preco_compra_documento") or "").strip() or None,
        "preco_compra_chave_acesso": (form.get("preco_compra_chave_acesso") or "").strip() or None,
        "preco_compra_data_emissao": (form.get("preco_compra_data_emissao") or "").strip() or None,
        "preco_compra_data_recebimento": (form.get("preco_compra_data_recebimento") or "").strip() or None,
        "preco_reposicao_unitario": (form.get("preco_reposicao_unitario") or "").strip() or None,
        "preco_reposicao_fonte": (form.get("preco_reposicao_fonte") or "").strip() or None,
        "preco_reposicao_uf": (form.get("preco_reposicao_uf") or "").strip() or None,
        "preco_reposicao_query": (form.get("preco_reposicao_query") or "").strip() or None,
        "preco_reposicao_url": (form.get("preco_reposicao_url") or "").strip() or None,
        "foto_url": (form.get("foto_url") or "").strip() or None,
        "quantidade": saldo_desejado,  # Para registrar entrada quando item existe com lote diferente
    }
    finance_payload = _extract_finance_payload(form)
    payload.update({
        "finance_supplier_id": finance_payload.get("supplier_id"),
        "finance_origem_valor": finance_payload.get("origem_valor"),
        "finance_tipo_documento": finance_payload.get("tipo_documento"),
        "finance_comprovacao_status": finance_payload.get("comprovacao_status"),
        "finance_observacao": finance_payload.get("observacao"),
    })
    if tipo_novo:
        payload["litros_por_embalagem"] = litros_var
        payload["grandeza_referencia"] = grandeza_var
    try:
        if not payload["codigo"] or not payload["descricao"]:
            raise ValueError("Código e descrição são obrigatórios")
        if saldo_desejado < 0:
            raise ValueError("Informe uma quantidade inicial válida")

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
        if not foi_atualizacao and saldo_desejado > 0:
            # Registrar entrada com skip_notification=True pois enviaremos notificação unificada
            entrada_inicial = inventory_service.registrar_entrada(
                MovimentoPayload(
                    codigo=codigo,
                    quantidade=saldo_desejado,
                    matricula=current_user.id,
                    nota_fiscal=payload["nota_fiscal"],
                    em_embalagens=em_embalagens,
                ),
                skip_notification=True  # Não enviar notificação separada de entrada
            )

        history_recorded = _sync_item_financial_history(
            codigo=codigo,
            categoria=str(payload.get("categoria") or "Sem categoria"),
            quantidade=float(saldo_desejado if saldo_desejado > 0 else 0),
            preco_compra_unitario=payload.get("preco_compra_unitario"),
            data_lancamento=payload.get("data_entrada"),
            usuario_id=current_user.id,
            finance_payload=finance_payload,
            entrada_id=getattr(entrada_inicial, "id_entrada", None),
        )
        if saldo_desejado > 0 and not history_recorded and (
            finance_payload.get("supplier_id") or finance_payload.get("tipo_documento") or finance_payload.get("origem_valor")
        ):
            flash("Item salvo, mas o lançamento financeiro não foi registrado porque faltou valor de compra unitário.", "warning")
        
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
                f"Documento fiscal {numero_documento} atualizado automaticamente e aberto para conferência.",
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
            saldo_desejado=quantidade_context,
            saldo_total_ean=saldo_total_ean,
            liquid_types=LIQUID_PRODUCT_TYPES,
            preferred_supplier=finance_service.get_supplier(finance_payload.get("supplier_id")).to_dict() if finance_payload.get("supplier_id") else None,
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
    
    # Calcular saldo total de todos os lotes com o mesmo EAN
    saldo_total = Item.get_saldo_total_by_codigo(codigo)

    saldo_display = item.get("saldo", 0)
    if _uses_packaging_system(item):
        saldo_display = item.get("estoque_embalagens", saldo_display)
    
    return render_template(
        "inventory/form.html",
        item=item,
        form_data=None,
        saldo_desejado=saldo_display,
        saldo_total_ean=saldo_total,
        liquid_types=LIQUID_PRODUCT_TYPES,
        preferred_supplier=finance_service.get_item_supplier_preference(codigo),
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
    registrar_compra_edicao = bool(form.get("registrar_compra_edicao"))
    finance_section_edit_authorized = _can_edit_finance_section(codigo) and str(form.get("finance_section_edit_enabled") or "0").strip() in {"1", "true", "True"}

    # Lógica de processamento de Unidades Dinâmicas
    tipo_novo = form.get("tipo_embalagem_novo") or None
    unidade_embalagem_novo = form.get("unidade_embalagem_novo")
    unidades_por_emb_raw = form.get("unidades_por_embalagem")
    
    litros_var = None
    grandeza_var = None
    unidades_var = None
    
    if tipo_novo in ['lata', 'balde']:
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
    elif tipo_novo == 'caixa':
        val = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        unidades_var = val
    elif tipo_novo == 'litro':
        val = float(unidades_por_emb_raw) if unidades_por_emb_raw and unidades_por_emb_raw.strip() else None
        litros_var = val
        unidades_var = val
    
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
        "preco_compra_unitario": (form.get("preco_compra_unitario") or "").strip() or prev_item.get("preco_compra_unitario"),
        "preco_compra_fonte": (form.get("preco_compra_fonte") or "").strip() or prev_item.get("preco_compra_fonte"),
        "preco_compra_documento": (form.get("preco_compra_documento") or "").strip() or prev_item.get("preco_compra_documento"),
        "preco_compra_chave_acesso": (form.get("preco_compra_chave_acesso") or "").strip() or prev_item.get("preco_compra_chave_acesso"),
        "preco_compra_data_emissao": (form.get("preco_compra_data_emissao") or "").strip() or prev_item.get("preco_compra_data_emissao"),
        "preco_compra_data_recebimento": (form.get("preco_compra_data_recebimento") or "").strip() or prev_item.get("preco_compra_data_recebimento"),
        "preco_reposicao_unitario": prev_item.get("preco_reposicao_unitario"),
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

    finance_payload = _extract_finance_payload(
        form,
        current_item=None if (registrar_compra_edicao or finance_section_edit_authorized) else prev_item,
    )
    if registrar_compra_edicao or finance_section_edit_authorized:
        payload.update({
            "preco_compra_unitario": (form.get("preco_compra_unitario") or "").strip() or None,
            "preco_compra_fonte": (form.get("preco_compra_fonte") or "").strip() or None,
            "preco_compra_documento": (form.get("preco_compra_documento") or "").strip() or None,
            "preco_compra_chave_acesso": (form.get("preco_compra_chave_acesso") or "").strip() or None,
            "preco_compra_data_emissao": (form.get("preco_compra_data_emissao") or "").strip() or None,
            "preco_compra_data_recebimento": (form.get("preco_compra_data_recebimento") or "").strip() or None,
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

        previous_internal_balance = float(prev_item.get("saldo") or 0.0)
        effective_tipo_embalagem = tipo_novo if tipo_novo is not None else (prev_item.get("tipo_embalagem_novo") or None)
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

        if registrar_compra_edicao:
            _validate_document_bridge_request(finance_payload)
            if purchase_delta <= 0:
                raise ValueError("Para registrar nova compra pela edição do item, aumente o saldo do estoque.")
        elif finance_section_edit_authorized:
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

        if saldo_desejado >= 0:
            from ..services.embalagem_service import EmbalagemService

            item_atualizado = Item.query.get(updated_codigo)
            if item_atualizado and EmbalagemService.tem_embalagem(item_atualizado):
                saldo_embalagens_anterior = float(item_atualizado.estoque_embalagens or 0.0)
                saldo_soltas_anterior = float(item_atualizado.estoque_unidades_soltas or 0.0)
                saldo_embalagens = float(saldo_desejado)

                # Unidades soltas são a parte "aberta" na grandeza interna:
                # - lata/balde com litros: litros
                # - lata/balde com kg: kg
                # - rolo: metros
                # - caixa/pacote: unidades
                # Se o campo não veio no form, preserva o que já existe.
                if saldo_unidades_soltas_raw == "":
                    saldo_unidades_soltas = float(item_atualizado.estoque_unidades_soltas or 0.0)
                else:
                    try:
                        saldo_unidades_soltas = float(saldo_unidades_soltas_raw)
                    except ValueError:
                        saldo_unidades_soltas = -1

                if saldo_unidades_soltas < 0:
                    raise ValueError("Informe uma quantidade válida para unidades soltas")

                unidades_por_embalagem = float(item_atualizado.unidades_por_embalagem or 1)
                novo_saldo_unidades = (saldo_embalagens * unidades_por_embalagem) + float(saldo_unidades_soltas)

                # Para itens com embalagem, o saldo do formulário representa embalagens.
                item_atualizado.estoque_embalagens = saldo_embalagens
                item_atualizado.estoque_unidades_soltas = float(saldo_unidades_soltas)

                descricao_evento = (
                    f"Ajuste manual via edição do item (saldo em embalagens): de {saldo_embalagens_anterior:g} para {saldo_embalagens:g}"
                )
                if abs(saldo_soltas_anterior - float(saldo_unidades_soltas)) > 1e-9:
                    descricao_evento += (
                        f" | soltas: de {saldo_soltas_anterior:g} para {float(saldo_unidades_soltas):g}"
                    )

                inventory_service.adjust_item_balance(
                    codigo=updated_codigo,
                    novo_saldo=novo_saldo_unidades,
                    matricula=current_user.id,
                    nota_fiscal=payload.get("nota_fiscal"),
                    descricao=descricao_evento,
                )
            else:
                # Itens sem embalagem: saldo do form representa o saldo total na própria unidade.
                inventory_service.adjust_item_balance(
                    codigo=updated_codigo,
                    novo_saldo=float(saldo_desejado),
                    matricula=current_user.id,
                    nota_fiscal=payload.get("nota_fiscal"),
                    descricao="Ajuste manual via edição do item",
                )

        history_recorded = False
        if registrar_compra_edicao and purchase_delta > 0:
            history_recorded = _sync_item_financial_history(
                codigo=updated_codigo,
                categoria=str(payload.get("categoria") or prev_item.get("categoria") or "Sem categoria"),
                quantidade=float(purchase_delta),
                preco_compra_unitario=payload.get("preco_compra_unitario"),
                data_lancamento=payload.get("data_entrada"),
                usuario_id=current_user.id,
                finance_payload=finance_payload,
                entrada_id=None,
            )
            if not history_recorded and (
                finance_payload.get("supplier_id") or finance_payload.get("tipo_documento") or finance_payload.get("origem_valor")
            ):
                flash("Entrada registrada, mas o lançamento financeiro não foi gravado porque faltou valor de compra unitário.", "warning")
        elif finance_section_edit_authorized:
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
                TelegramService.notify_item_updated(updated_codigo, prev=prev_item, prev_balance=prev_balance)
            except Exception:
                pass
        if registrar_compra_edicao and purchase_delta > 0:
            flash("Item atualizado e nova compra vinculada ao documento fiscal.", "success")
            numero_documento = str(finance_payload.get("numero_documento") or "").strip()
            if numero_documento and _is_admin(current_user):
                flash(
                    f"Documento fiscal {numero_documento} atualizado automaticamente e aberto para conferência.",
                    "info",
                )
                return redirect(url_for("nf.nf_index", nota=numero_documento, codigo=updated_codigo))
        else:
            flash("Item atualizado com sucesso.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("inventory.edit_item_form", codigo=codigo))
    return redirect(url_for("inventory.list_items"))


@blueprint.get("/<codigo>/precos/reposicao/sugestoes")
@login_required
def sugestoes_preco_reposicao(codigo: str):
    if not _is_admin(current_user):
        return {"success": False, "message": "Acesso negado"}, 403
    item = Item.query.get(codigo)
    if not item:
        return {"success": False, "message": "Item nÃ£o encontrado"}, 404

    query = (request.args.get("q") or "").strip() or (item.descricao or "").strip()
    uf = (request.args.get("uf") or "").strip().upper()
    if not uf:
        try:
            uf = (ConfigService.get_empresa_config().endereco_estado or "").strip().upper()
        except Exception:
            uf = ""

    try:
        data = price_suggestion_service.get_replacement_suggestions(query=query, uf=uf or None, limit=20)
    except Exception:
        current_app.logger.exception("Erro ao buscar sugestoes de preco de reposicao (codigo=%s)", codigo)
        return {"success": False, "message": "Erro interno ao buscar sugestoes"}, 500
    data["success"] = True
    return data


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

    item.preco_reposicao_unitario = price
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
    
    try:
        saida_id = inventory_service.registrar_saida(
            MovimentoPayload(
                codigo=codigo, 
                quantidade=quantidade, 
                matricula=matricula,
                tipo_custodia=tipo_custodia,
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


@blueprint.post('/categoria/<categoria>/excluir')
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


@blueprint.post('/categoria/<categoria>/excluir_inativos')
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


@blueprint.get('/categoria/<categoria>/relatorio')
@login_required
def category_report(categoria: str):
    """Gera relatório de itens de uma categoria em PDF ou XLSX."""
    format_type = (request.args.get("format") or "pdf").strip().lower()
    if format_type not in {"pdf", "xlsx"}:
        flash("Formato inválido. Use PDF ou XLSX.", "danger")
        return redirect(url_for("inventory.list_items", categoria=categoria))

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
            saldo = _safe_float(item.get("saldo"))
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
        flash("Não foi possível gerar PDF (dependência reportlab). Gere em XLSX.", "danger")
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
        data.append(
            [
                _safe_text(item.get("codigo")),
                Paragraph(_safe_text(item.get("descricao"))[:80], body_style),
                Paragraph((_safe_text(item.get("marca")) or "N/D")[:30], body_style),
                _safe_text(item.get("unidade")) or "N/D",
                _safe_text(item.get("saldo")),
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
    from flask import jsonify
    item = Item.query.get(codigo)
    if not item:
        return jsonify({"error": "Item não encontrado"}), 404
    
    return jsonify({
        "codigo": item.codigo,
        "descricao": item.descricao,
        "unidade": item.unidade,
        "tipo_embalagem_novo": item.tipo_embalagem_novo,
        "unidades_por_embalagem": item.unidades_por_embalagem,
        "saldo": item.saldo,
    })


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
