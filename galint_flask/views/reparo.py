"""Rotas para gerenciamento de equipamentos em reparo."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required, current_user

from ..models import Item
from ..services.reparo_service import reparo_service
from ..extensions import db

blueprint = Blueprint("reparo", __name__, url_prefix="/reparos")


def _is_admin(user) -> bool:
    """Verifica se o usuário é administrador."""
    if not user:
        return False
    value = getattr(user, "is_admin", False)
    if isinstance(value, str):
        return value.strip() in ("1", "true", "True", "TRUE")
    return bool(value)


def _is_supervisor(user) -> bool:
    """Verifica se o usuário é supervisor."""
    if not user:
        return False
    setor = (getattr(user, "setor", "") or "").strip().lower()
    cargo = (getattr(user, "cargo", "") or "").strip().lower()
    return "supervisor" in setor or "supervisor" in cargo


def _require_admin_or_supervisor() -> None:
    """Requer que o usuário seja admin ou supervisor."""
    if not (_is_admin(current_user) or _is_supervisor(current_user)):
        abort(403)


@blueprint.route("/", methods=["GET"])
@login_required
def listar_reparos():
    """Página principal de listagem de reparos."""
    # Filtros da URL
    status_filtro = request.args.get("status")
    busca = request.args.get("busca", "").strip()
    apenas_abertos = request.args.get("abertos") == "1"
    
    # Buscar reparos
    if busca:
        reparos = reparo_service.buscar_reparos(busca, limit=100)
    else:
        reparos = reparo_service.listar_reparos(
            status=status_filtro,
            apenas_abertos=apenas_abertos,
            limit=100
        )
    
    # Estatísticas
    stats = reparo_service.get_estatisticas()
    
    return render_template(
        "reparo/list.html",
        reparos=reparos,
        stats=stats,
        status_filtro=status_filtro,
        busca=busca,
        apenas_abertos=apenas_abertos,
    )


@blueprint.route("/novo", methods=["POST"])
@login_required
def enviar_para_reparo():
    """Endpoint para enviar um equipamento para reparo."""
    try:
        codigo_item = request.form.get("codigo_item", "").strip()
        problema = request.form.get("problema_descrito", "").strip()
        fornecedor = request.form.get("fornecedor_oficina", "").strip() or None
        observacoes = request.form.get("observacoes", "").strip() or None
        
        # Custo estimado e prazo (opcionais)
        custo_estimado = None
        custo_str = request.form.get("custo_estimado", "").strip()
        if custo_str:
            try:
                custo_estimado = float(custo_str.replace(",", "."))
            except ValueError:
                pass
        
        prazo_previsto = None
        prazo_str = request.form.get("prazo_previsto", "").strip()
        if prazo_str:
            try:
                prazo_previsto = datetime.strptime(prazo_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        
        if not codigo_item or not problema:
            flash("Código do item e problema são obrigatórios", "error")
            return redirect(url_for("reparo.listar_reparos"))
        
        # Criar reparo
        reparo_service.enviar_para_reparo(
            codigo_item=codigo_item,
            matricula_responsavel=current_user.id,
            problema_descrito=problema,
            fornecedor_oficina=fornecedor,
            custo_estimado=custo_estimado,
            prazo_previsto=prazo_previsto,
            observacoes=observacoes,
        )
        
        flash(f"Equipamento {codigo_item} enviado para reparo com sucesso", "success")
        return redirect(url_for("reparo.listar_reparos"))
        
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("reparo.listar_reparos"))
    except Exception as e:
        flash(f"Erro ao enviar para reparo: {str(e)}", "error")
        return redirect(url_for("reparo.listar_reparos"))


@blueprint.route("/<int:reparo_id>", methods=["GET"])
@login_required
def detalhes_reparo(reparo_id: int):
    """Página de detalhes de um reparo."""
    reparo = reparo_service.get_reparo_by_id(reparo_id)
    
    if not reparo:
        flash("Reparo não encontrado", "error")
        return redirect(url_for("reparo.listar_reparos"))
    
    return render_template("reparo/detalhes.html", reparo=reparo)


@blueprint.route("/<int:reparo_id>/atualizar", methods=["POST"])
@login_required
def atualizar_reparo(reparo_id: int):
    """Atualiza o status de um reparo."""
    _require_admin_or_supervisor()
    
    try:
        novo_status = request.form.get("status", "").strip()
        solucao = request.form.get("solucao_aplicada", "").strip() or None
        observacoes_novas = request.form.get("observacoes", "").strip() or None
        
        # Custo real
        custo_real = None
        custo_str = request.form.get("custo_real", "").strip()
        if custo_str:
            try:
                custo_real = float(custo_str.replace(",", "."))
            except ValueError:
                pass
        
        if not novo_status:
            flash("Status é obrigatório", "error")
            return redirect(url_for("reparo.detalhes_reparo", reparo_id=reparo_id))
        
        # Atualizar
        reparo = reparo_service.atualizar_status(
            reparo_id=reparo_id,
            novo_status=novo_status,
            matricula_atualizador=current_user.id,
            solucao_aplicada=solucao,
            custo_real=custo_real,
            observacoes=observacoes_novas,
        )
        
        flash(f"Reparo atualizado para '{reparo.status_display}'", "success")
        return redirect(url_for("reparo.detalhes_reparo", reparo_id=reparo_id))
        
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("reparo.detalhes_reparo", reparo_id=reparo_id))
    except Exception as e:
        flash(f"Erro ao atualizar reparo: {str(e)}", "error")
        return redirect(url_for("reparo.detalhes_reparo", reparo_id=reparo_id))


@blueprint.route("/<int:reparo_id>/finalizar", methods=["POST"])
@login_required
def finalizar_reparo(reparo_id: int):
    """Finaliza um reparo (concluído ou sem conserto)."""
    _require_admin_or_supervisor()
    
    try:
        status_final = request.form.get("status_final", "").strip()
        solucao = request.form.get("solucao_aplicada", "").strip() or None
        
        # Custo real
        custo_real = None
        custo_str = request.form.get("custo_real", "").strip()
        if custo_str:
            try:
                custo_real = float(custo_str.replace(",", "."))
            except ValueError:
                pass
        
        if status_final not in ["concluido", "sem_conserto"]:
            flash("Status final deve ser 'concluido' ou 'sem_conserto'", "error")
            return redirect(url_for("reparo.detalhes_reparo", reparo_id=reparo_id))
        
        # Finalizar
        reparo = reparo_service.finalizar_reparo(
            reparo_id=reparo_id,
            matricula_atualizador=current_user.id,
            status_final=status_final,
            solucao_aplicada=solucao,
            custo_real=custo_real,
        )
        
        flash(f"Reparo finalizado: {reparo.status_display}", "success")
        return redirect(url_for("reparo.listar_reparos"))
        
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("reparo.detalhes_reparo", reparo_id=reparo_id))
    except Exception as e:
        flash(f"Erro ao finalizar reparo: {str(e)}", "error")
        return redirect(url_for("reparo.detalhes_reparo", reparo_id=reparo_id))


@blueprint.route("/api/itens/autocomplete", methods=["GET"])
@login_required
def autocomplete_itens():
    """API para autocomplete de itens (apenas Ferramentas, EPI, Material de EP)."""
    termo = request.args.get("q", "").strip()
    
    if not termo or len(termo) < 2:
        return jsonify([])
    
    # Buscar itens com categoria apropriada
    itens = (
        db.session.query(Item)
        .filter(
            db.or_(
                Item.codigo_item.ilike(f"%{termo}%"),
                Item.descricao.ilike(f"%{termo}%")
            )
        )
        .filter(
            db.or_(
                Item.categoria.ilike("%ferramenta%"),
                Item.categoria.ilike("%epi%"),
                db.and_(
                    Item.categoria.ilike("%material%"),
                    Item.categoria.ilike("%ep%")
                )
            )
        )
        .limit(20)
        .all()
    )
    
    resultado = [
        {
            "codigo": item.codigo_item,
            "descricao": item.descricao,
            "categoria": item.categoria,
            "label": f"{item.codigo_item} - {item.descricao}",
        }
        for item in itens
    ]
    
    return jsonify(resultado)


@blueprint.route("/api/stats", methods=["GET"])
@login_required
def api_estatisticas():
    """API para obter estatísticas de reparos."""
    stats = reparo_service.get_estatisticas()
    return jsonify(stats)
