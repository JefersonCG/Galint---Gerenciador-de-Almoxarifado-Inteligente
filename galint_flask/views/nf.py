"""Rotas para lançamento e acompanhamento de notas fiscais."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..services.finance_service import finance_service
from ..services.inventory import inventory_service

blueprint = Blueprint("nf", __name__, url_prefix="/nf")


@blueprint.before_request
def _abort_if_feature_disabled() -> None:
    if not current_app.config.get("FEATURE_NOTAS_ENABLED", True):
        abort(404)


def _require_admin() -> None:
    if not bool(getattr(current_user, "is_admin", False)):
        abort(403)


@blueprint.get("/api/documentos/autocomplete")
@login_required
def autocomplete_documentos():
    _require_admin()
    term = (request.args.get("q") or "").strip()
    if len(term) < 2:
        return jsonify({"success": True, "results": []})
    return jsonify({"success": True, "results": finance_service.search_stock_documents(term, limit=8)})


@blueprint.get("/")
@login_required
def nf_index():
    nota_busca = (request.args.get("nota") or "").strip()
    codigo_prefill = (request.args.get("codigo") or "").strip()
    nota_detalhes = inventory_service.get_nota_fiscal(nota_busca) if nota_busca else None
    itens = inventory_service.list_items()
    selected_item = next((item for item in itens if str(item.get("codigo") or "") == codigo_prefill), None) if codigo_prefill else None
    notas = inventory_service.list_notas_fiscais()
    can_manage = bool(getattr(current_user, "is_admin", False))
    return render_template(
        "nf/index.html",
        itens=itens,
        selected_item=selected_item,
        notas=notas,
        nota_busca=nota_busca,
        codigo_prefill=codigo_prefill,
        nota_detalhes=nota_detalhes,
        can_manage=can_manage,
        preferred_suppliers=finance_service.list_suppliers(limit=100),
    )


@blueprint.post("/")
@login_required
def registrar_nf():
    _require_admin()
    codigo = request.form.get("codigo", "").strip()
    nota = request.form.get("nota_fiscal", "").strip()
    supplier_raw = (request.form.get("finance_supplier_id") or "").strip()
    supplier_id = int(supplier_raw) if supplier_raw.isdigit() else None
    supplier_name = (request.form.get("supplier_name") or request.form.get("finance_supplier_search") or "").strip() or None
    supplier_cnpj = (request.form.get("supplier_cnpj") or "").strip() or None
    origem_valor = (request.form.get("finance_origem_valor") or "compra_nf").strip() or "compra_nf"
    tipo_documento = (request.form.get("finance_tipo_documento") or "nf").strip() or "nf"
    comprovacao_status = (request.form.get("finance_comprovacao_status") or "comprovado").strip() or "comprovado"
    preco_unitario_raw = (request.form.get("preco_unitario") or "").strip()
    observacao = (request.form.get("finance_observacao") or "").strip() or None
    data_emissao_raw = (request.form.get("data_emissao") or "").strip()
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

    try:
        if not codigo:
            raise ValueError("Selecione o item da entrada")
        if quantidade <= 0:
            raise ValueError("Informe uma quantidade válida")
        if not nota:
            raise ValueError("Informe o número do documento")

        preco_unitario = float(preco_unitario_raw) if preco_unitario_raw else None
        item = inventory_service.get_item(codigo) or {}

        finance_service.register_stock_document_entry(
            codigo_item=codigo,
            quantidade=float(quantidade),
            tipo_documento=tipo_documento,
            numero_documento=nota,
            data_emissao=data_emissao,
            data_recebimento=data_recebimento,
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
        )
        flash("Nota fiscal registrada apenas como documento. Estoque e financeiro não foram incorporados ao sistema.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("nf.nf_index"))
