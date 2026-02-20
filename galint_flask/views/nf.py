"""Rotas para lançamento e acompanhamento de notas fiscais."""
from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

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
    )


@blueprint.post("/")
@login_required
def registrar_nf():
    _require_admin()
    codigo = request.form.get("codigo", "").strip()
    nota = request.form.get("nota_fiscal", "").strip()
    quantidade_raw = request.form.get("quantidade", "0")
    try:
        quantidade = int(quantidade_raw or 0)
    except ValueError:
        quantidade = 0
    try:
        inventory_service.registrar_nota_fiscal(
            MovimentoPayload(
                codigo=codigo,
                quantidade=quantidade,
                matricula=current_user.id,
                nota_fiscal=nota,
            )
        )
        flash("Nota fiscal registrada.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("nf.nf_index"))
