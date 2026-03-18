"""Rotas para lançamento e acompanhamento de notas fiscais."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem, Entrada, FinanceLedgerEntry, TelegramOutbox
from ..services.finance_service import finance_service
from ..services.inventory import inventory_service

blueprint = Blueprint("nf", __name__, url_prefix="/nf")


def _purge_linked_entry(entrada_id: int | None) -> None:
    if entrada_id is None:
        return
    FinanceLedgerEntry.query.filter_by(entrada_id=entrada_id).delete(synchronize_session=False)
    TelegramOutbox.query.filter_by(entrada_id=entrada_id).delete(synchronize_session=False)
    linked_entry = db.session.get(Entrada, entrada_id)
    if linked_entry is not None:
        db.session.delete(linked_entry)


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
    novo_codigo = request.form.get("novo_codigo", "").strip()
    nova_descricao = request.form.get("nova_descricao", "").strip()
    nova_categoria = request.form.get("nova_categoria", "").strip() or "Material Elétrico"
    nova_unidade = request.form.get("nova_unidade", "").strip() or "Unidade"
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
        if not codigo and novo_codigo:
            codigo = novo_codigo

        item_existente = inventory_service.get_item(codigo) if codigo else None
        if not item_existente:
            if not codigo:
                raise ValueError("Selecione um item existente ou informe o código do novo item")
            if not nova_descricao:
                raise ValueError("Informe a descrição para cadastrar o novo item da nota")
            inventory_service.create_item(
                {
                    "codigo": codigo,
                    "descricao": nova_descricao,
                    "categoria": nova_categoria,
                    "unidade": nova_unidade,
                    "nota_fiscal": nota or None,
                    "marca": None,
                    "localizacao": None,
                    "quantidade": 0,
                }
            )

        if quantidade <= 0:
            raise ValueError("Informe uma quantidade válida")
        if not nota:
            raise ValueError("Informe o número do documento")

        preco_unitario = float(preco_unitario_raw) if preco_unitario_raw else None
        item = inventory_service.get_item(codigo) or {}

        document_result = finance_service.register_stock_document_entry(
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
            document_only=True,
        )
        document_item = document_result.get("document_item")
        linked_entry_id = getattr(document_item, "entrada_id", None)
        if linked_entry_id is not None:
            document_item.entrada_id = None
            _purge_linked_entry(linked_entry_id)
            db.session.commit()
        flash("Nota fiscal registrada apenas como documento. Estoque e financeiro não foram incorporados ao sistema.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("nf.nf_index"))


@blueprint.post("/<int:documento_id>/itens/<int:documento_item_id>/excluir")
@login_required
def excluir_item_documento(documento_id: int, documento_item_id: int):
    _require_admin()
    documento = db.session.get(DocumentoEntradaEstoque, documento_id)
    item_row = db.session.get(DocumentoEntradaEstoqueItem, documento_item_id)

    if documento is None or item_row is None or item_row.documento_id != documento.id_documento:
        flash("Item do documento fiscal não encontrado.", "danger")
        return redirect(url_for("nf.nf_index"))

    numero_documento = documento.numero_documento
    codigo_item = item_row.codigo_item

    _purge_linked_entry(item_row.entrada_id)
    db.session.delete(item_row)
    db.session.flush()

    has_items = (
        DocumentoEntradaEstoqueItem.query
        .filter_by(documento_id=documento.id_documento)
        .first()
        is not None
    )
    if not has_items:
        db.session.delete(documento)

    db.session.commit()
    flash(f"Item {codigo_item} removido do documento fiscal {numero_documento}.", "success")
    return redirect(url_for("nf.nf_index", nota=numero_documento))
