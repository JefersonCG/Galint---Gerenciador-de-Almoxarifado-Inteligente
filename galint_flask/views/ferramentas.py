"""Rotas para gerenciamento de ferramentas."""
from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..mako_renderer import render_mako_template
from ..services.ferramentas import ferramentas_service
from ..services.inventory import inventory_service
from ..services.users import user_service

blueprint = Blueprint("ferramentas", __name__, url_prefix="/ferramentas")


def _require_admin() -> None:
    if not bool(getattr(current_user, "is_admin", False)):
        from flask import abort
        abort(403)


@blueprint.get("/retirar")
@login_required
def retirar_page():
    """Página de retirada de ferramentas (formulário apenas)."""
    _require_admin()
    
    return render_mako_template(
        'ferramentas/retirar.mako',
        usuarios=user_service.list_users(),
    )


@blueprint.post("/retirar")
@login_required
def retirar():
    """Processa retirada de ferramenta."""
    _require_admin()
    
    codigo = (request.form.get("codigo") or "").strip()
    matricula = (request.form.get("matricula") or "").strip()
    quantidade_str = (request.form.get("quantidade") or "1").strip()
    local_servico = (request.form.get("local_servico") or "").strip() or None
    observacao = (request.form.get("observacao") or "").strip() or None
    
    try:
        quantidade = int(quantidade_str)
        if quantidade < 1:
            raise ValueError("Quantidade deve ser maior que zero")
    except ValueError:
        flash("Quantidade inválida", "danger")
        return redirect(url_for("ferramentas.retirar_page"))
    
    if not codigo:
        flash("Informe o código da ferramenta", "danger")
        return redirect(url_for("ferramentas.retirar_page"))
    
    if not matricula:
        flash("Informe a matrícula do funcionário", "danger")
        return redirect(url_for("ferramentas.retirar_page"))
    
    try:
        retirada_id = ferramentas_service.retirar_ferramenta(
            codigo_item=codigo,
            matricula=matricula,
            quantidade=quantidade,
            local_servico=local_servico,
            observacao=observacao,
        )
        flash(f"Ferramenta retirada com sucesso! ID: {retirada_id}", "success")
        return redirect(url_for("ferramentas.retirar_page"))
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("ferramentas.retirar_page"))


# Rota do painel separada removida - agora está integrado na página de retirada
# @blueprint.get("/painel") foi descontinuado

@blueprint.post("/devolver/<int:retirada_id>")
@login_required
def devolver(retirada_id: int):
    """Registra devolução de ferramenta."""
    _require_admin()
    
    observacao = (request.form.get("observacao") or "").strip() or None
    
    try:
        ferramentas_service.devolver_ferramenta(retirada_id, observacao)
        flash("Ferramenta devolvida com sucesso!", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    
    return redirect(url_for("ferramentas.retirar_page"))


@blueprint.post("/marcar-reparo/<int:retirada_id>")
@login_required
def marcar_reparo(retirada_id: int):
    """Marca ferramenta para reparo."""
    _require_admin()
    
    observacao = (request.form.get("observacao") or "").strip()
    
    if not observacao:
        flash("Informe o motivo do reparo", "danger")
        return redirect(url_for("ferramentas.retirar_page"))
    
    try:
        ferramentas_service.marcar_para_reparo(retirada_id, observacao)
        flash("Ferramenta marcada para reparo", "warning")
    except ValueError as exc:
        flash(str(exc), "danger")
    
    return redirect(url_for("ferramentas.retirar_page"))


@blueprint.get("/item-info/<codigo>")
@login_required
def item_info(codigo: str):
    """API: Informações de uma ferramenta."""
    _require_admin()
    codigo = (codigo or "").strip()
    if not codigo:
        return jsonify({"found": False}), 400
    
    item = inventory_service.get_item(codigo)
    if not item:
        return jsonify({"found": False}), 404
    
    return jsonify({
        "found": True,
        "codigo": codigo,
        "descricao": item.get("descricao"),
        "categoria": item.get("categoria"),
        "unidade": item.get("unidade"),
        "saldo": item.get("saldo"),
    })


@blueprint.get("/buscar-item")
@login_required
def buscar_item():
    """API: Busca itens por código ou nome (parcial)."""
    _require_admin()
    query = (request.args.get("q") or "").strip()
    
    if not query or len(query) < 2:
        return jsonify({"items": []})
    
    resultados = inventory_service.search_items_for_autocomplete(query, limit=20)
    return jsonify({"items": resultados})
