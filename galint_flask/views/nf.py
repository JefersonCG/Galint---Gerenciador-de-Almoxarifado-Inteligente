"""Rotas para lançamento e acompanhamento de notas fiscais."""
from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..services.finance_service import finance_service
from ..services.inventory import MovimentoPayload, inventory_service

blueprint = Blueprint("nf", __name__, url_prefix="/nf")


@blueprint.before_request
def _abort_if_feature_disabled() -> None:
    if not current_app.config.get("FEATURE_NOTAS_ENABLED", True):
        abort(404)


def _require_admin() -> None:
    if not bool(getattr(current_user, "is_admin", False)):
        abort(403)


@blueprint.get("/")
@login_required
def nf_index():
    nota_busca = (request.args.get("nota") or "").strip()
    nota_detalhes = inventory_service.get_nota_fiscal(nota_busca) if nota_busca else None
    itens = inventory_service.list_items()
    notas = inventory_service.list_notas_fiscais()
    can_manage = bool(getattr(current_user, "is_admin", False))
    return render_template(
        "nf/index.html",
        itens=itens,
        notas=notas,
        nota_busca=nota_busca,
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
    origem_valor = (request.form.get("finance_origem_valor") or "compra_nf").strip() or "compra_nf"
    tipo_documento = (request.form.get("finance_tipo_documento") or "nf").strip() or "nf"
    comprovacao_status = (request.form.get("finance_comprovacao_status") or "comprovado").strip() or "comprovado"
    preco_unitario_raw = (request.form.get("preco_unitario") or "").strip()
    observacao = (request.form.get("finance_observacao") or "").strip() or None
    quantidade_raw = request.form.get("quantidade", "0")
    try:
        quantidade = int(quantidade_raw or 0)
    except ValueError:
        quantidade = 0
    try:
        entrada = inventory_service.registrar_entrada(
            MovimentoPayload(
                codigo=codigo,
                quantidade=quantidade,
                matricula=current_user.id,
                nota_fiscal=nota,
            )
        )
        preco_unitario = float(preco_unitario_raw) if preco_unitario_raw else None
        item = inventory_service.get_item(codigo) or {}
        if supplier_id:
            finance_service.set_item_supplier_preference(
                codigo,
                supplier_id,
                origem=origem_valor,
                atualizado_por=current_user.id,
            )
        if preco_unitario is not None:
            finance_service.register_financial_entry(
                codigo_item=codigo,
                categoria_nome=str(item.get("categoria") or "Sem categoria"),
                quantidade=float(quantidade),
                valor_unitario=preco_unitario,
                fornecedor_id=supplier_id,
                entrada_id=getattr(entrada, "id_entrada", None),
                usuario_matricula=current_user.id,
                origem_valor=origem_valor,
                tipo_documento=tipo_documento,
                numero_documento=nota,
                comprovacao_status=comprovacao_status,
                observacao=observacao,
            )
        else:
            flash("Entrada registrada sem lançamento financeiro, porque o valor unitário não foi informado.", "warning")
        flash("Nota fiscal registrada.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("nf.nf_index"))
