"""Grupos de itens (produto genérico), página "Grupos de itens" do menu Estoque (24/11/2026).

Só administrador. Monta os grupos que a retirada vai usar como um produto só (sai o mais antigo
primeiro). Regras em services/item_grupo_service.py.
"""
from __future__ import annotations

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import ItemGrupo
from ..services import item_grupo_service as service

blueprint = Blueprint("item_grupos", __name__, url_prefix="/itens/grupos")


def _require_admin() -> None:
    if not bool(getattr(current_user, "is_admin", False)):
        abort(403)


def _get_group(grupo_id: int) -> ItemGrupo:
    grupo = db.session.get(ItemGrupo, grupo_id)
    if grupo is None:
        abort(404)
    return grupo


def _back():
    return redirect(url_for("item_grupos.index") + (f"#{request.form.get('ancora')}" if request.form.get("ancora") else ""))


@blueprint.get("/")
@login_required
def index():
    _require_admin()
    return render_template("inventory/grupos.html", grupos=service.list_groups(), sugestoes=service.suggestions())


@blueprint.get("/buscar")
@login_required
def buscar():
    _require_admin()
    return jsonify(service.search_items(str(request.args.get("q") or "")))


@blueprint.post("/criar")
@login_required
def criar():
    _require_admin()
    try:
        grupo = service.create_group(request.form.get("nome"), request.form.getlist("codigos"), usuario=getattr(current_user, "nome", None))
    except ValueError as exc:
        flash(str(exc), "danger")
        return _back()
    flash(f"Grupo {grupo.nome} criado com {len(grupo.membros)} itens.", "success")
    return redirect(url_for("item_grupos.index") + f"#grupo-{grupo.id}")


@blueprint.post("/<int:grupo_id>/adicionar")
@login_required
def adicionar(grupo_id: int):
    _require_admin()
    grupo = _get_group(grupo_id)
    try:
        added = service.add_members(grupo, request.form.getlist("codigos"))
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("item_grupos.index") + f"#grupo-{grupo.id}")
    flash(f"{added} item(ns) adicionado(s) ao grupo {grupo.nome}.", "success")
    return redirect(url_for("item_grupos.index") + f"#grupo-{grupo.id}")


@blueprint.post("/<int:grupo_id>/remover")
@login_required
def remover(grupo_id: int):
    _require_admin()
    grupo = _get_group(grupo_id)
    service.remove_member(grupo, str(request.form.get("codigo") or ""))
    return redirect(url_for("item_grupos.index") + f"#grupo-{grupo.id}")


@blueprint.post("/<int:grupo_id>/renomear")
@login_required
def renomear(grupo_id: int):
    _require_admin()
    grupo = _get_group(grupo_id)
    try:
        service.rename_group(grupo, request.form.get("nome"))
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("item_grupos.index") + f"#grupo-{grupo.id}")


@blueprint.post("/<int:grupo_id>/excluir")
@login_required
def excluir(grupo_id: int):
    _require_admin()
    grupo = _get_group(grupo_id)
    nome = grupo.nome
    service.delete_group(grupo)
    flash(f"Grupo {nome} desfeito (os itens continuam cadastrados).", "info")
    return redirect(url_for("item_grupos.index"))
