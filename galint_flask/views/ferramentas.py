"""Rotas para gerenciamento de ferramentas."""
from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..mako_renderer import render_mako_template
from ..services.ferramentas import ferramentas_service
from ..services.inventory import inventory_service
from ..services.users import user_service
from ..models import RetiradaFerramenta
from ..extensions import db

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
        itens=inventory_service.list_items(),
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


@blueprint.post("/retirar-multipla")
def retirar_multipla():
    """Processa retirada de múltiplas ferramentas (JSON).

    Espera payload:
    {
      "matricula": "...",
      "local_servico": "..." | null,
      "observacao": "..." | null,
      "itens": [{"codigo": "...", "quantidade": 1}, ...]
    }

    Retorna resultados por item (sucesso parcial).
    """
    # Endpoint chamado via fetch; para evitar HTML de redirect do Flask-Login (login_required),
    # retornamos sempre JSON em casos de não autenticado/não autorizado.
    if not bool(getattr(current_user, "is_authenticated", False)):
        return jsonify({"success": False, "message": "Sessão expirada. Faça login novamente."}), 401

    if not bool(getattr(current_user, "is_admin", False)):
        return jsonify({"success": False, "message": "Acesso negado."}), 403

    payload = request.get_json(silent=True) or {}
    matricula = (payload.get("matricula") or "").strip()
    local_servico = (payload.get("local_servico") or "").strip() or None
    observacao = (payload.get("observacao") or "").strip() or None
    itens = payload.get("itens") or []

    if not matricula:
        return jsonify({"success": False, "message": "Informe a matrícula do funcionário"}), 400

    if not isinstance(itens, list) or len(itens) == 0:
        return jsonify({"success": False, "message": "Adicione pelo menos uma ferramenta"}), 400

    resultados: list[dict[str, object]] = []
    retirada_ids_ok: list[int] = []

    for idx, item in enumerate(itens):
        codigo = ((item or {}).get("codigo") or "").strip()
        quantidade_raw = (item or {}).get("quantidade")

        if not codigo:
            resultados.append({
                "index": idx,
                "codigo": codigo,
                "success": False,
                "message": "Código inválido",
            })
            continue

        try:
            quantidade = int(quantidade_raw) if quantidade_raw is not None else 1
            if quantidade < 1:
                raise ValueError
        except Exception:
            resultados.append({
                "index": idx,
                "codigo": codigo,
                "success": False,
                "message": "Quantidade inválida",
            })
            continue

        try:
            retirada_id = ferramentas_service.retirar_ferramenta(
                codigo_item=codigo,
                matricula=matricula,
                quantidade=quantidade,
                local_servico=local_servico,
                observacao=observacao,
                notify_telegram=False,
            )
            retirada_ids_ok.append(int(retirada_id))
            resultados.append({
                "index": idx,
                "codigo": codigo,
                "success": True,
                "retirada_id": retirada_id,
                "message": "Retirada registrada",
            })
        except ValueError as exc:
            resultados.append({
                "index": idx,
                "codigo": codigo,
                "success": False,
                "message": str(exc),
            })

    total_ok = sum(1 for r in resultados if r.get("success"))
    total = len(resultados)
    success = (total_ok == total)

    if success:
        message = f"Retirada registrada para {total_ok} ferramenta(s)."
    else:
        message = f"Retirada parcial: {total_ok}/{total} registrada(s)."

    # Notificação consolidada (uma mensagem para o lote)
    if retirada_ids_ok:
        try:
            retiradas_ok = (
                db.session.query(RetiradaFerramenta)
                .filter(RetiradaFerramenta.id.in_(retirada_ids_ok))
                .order_by(RetiradaFerramenta.id.asc())
                .all()
            )
            ferramentas_service._notificar_retirada_multipla_telegram(retiradas_ok)  # type: ignore[attr-defined]
        except Exception:
            pass

    return jsonify({
        "success": success,
        "message": message,
        "resultados": resultados,
    })


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


@blueprint.post("/devolver/<int:retirada_id>/api")
@login_required
def devolver_api(retirada_id: int):
    """Registra devolução de ferramenta via API (JSON)."""
    _require_admin()

    observacao = (request.form.get("observacao") or "").strip() or None

    try:
        ferramentas_service.devolver_ferramenta(retirada_id, observacao)
        return jsonify({"success": True, "message": "Ferramenta devolvida com sucesso"})
    except ValueError as exc:
        message = str(exc)
        if message.strip().lower() == "ferramenta já foi devolvida":
            return jsonify({"success": True, "message": message})
        return jsonify({"success": False, "message": message}), 400


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
    
    if not query or len(query) < 1:
        return jsonify({"items": [], "itens": []})
    
    resultados = inventory_service.search_items_for_autocomplete(query, limit=20)
    return jsonify({"items": resultados, "itens": resultados})


@blueprint.get("/buscar-funcionario")
@login_required
def buscar_funcionario():
    """API: Busca funcionários por nome ou matrícula (parcial)."""
    _require_admin()
    query = (request.args.get("q") or "").strip()
    
    if not query or len(query) < 1:
        return jsonify({"funcionarios": []})
    
    # Buscar funcionários que correspondam ao query (nome ou matrícula)
    from ..models import Usuario as UsuarioModel
    
    query_lower = query.lower()
    funcionarios_list = (
        db.session.query(UsuarioModel)
        .filter(
            or_(
                UsuarioModel.nome.ilike(f"%{query}%"),
                UsuarioModel.matricula.ilike(f"%{query}%")
            )
        )
        .order_by(UsuarioModel.nome)
        .limit(20)
        .all()
    )
    
    resultados = [
        {
            "matricula": f.matricula,
            "nome": f.nome,
            "setor": f.setor or "N/D",
            "cargo": f.cargo or "N/D",
        }
        for f in funcionarios_list
    ]
    
    return jsonify({"funcionarios": resultados})
