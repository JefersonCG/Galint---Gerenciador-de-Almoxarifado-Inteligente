# -*- coding: utf-8 -*-
"""
Views para Gestão de Patrimônio
================================
Rotas e endpoints para gerenciar códigos patrimoniais de ferramentas.
"""

from flask import Blueprint, jsonify, render_template, request, flash, redirect, url_for
from flask_login import login_required

from ..extensions import db
from ..models import Item, PatrimonioFerramenta
from ..services.patrimonio_service import PatrimonioService

bp = Blueprint('patrimonio', __name__, url_prefix='/patrimonio')


@bp.route('/item/<codigo_item>')
@login_required
def listar_codigos(codigo_item):
    """Lista todos os códigos patrimoniais de um item."""
    item = db.session.get(Item, codigo_item)
    if not item:
        flash('Item não encontrado', 'error')
        return redirect(url_for('inventory.index'))
    
    # Busca todos os códigos patrimoniais
    codigos = PatrimonioService.listar_todos(codigo_item)
    
    # Estatísticas
    stats = PatrimonioService.estatisticas_item(codigo_item)
    
    return render_template(
        'patrimonio/listar.html',
        item=item,
        codigos=codigos,
        stats=stats
    )


@bp.route('/adicionar-lote', methods=['POST'])
@login_required
def adicionar_lote():
    """Adiciona múltiplos códigos patrimoniais em lote."""
    data = request.get_json() if request.is_json else request.form
    
    codigo_item = data.get('codigo_item')
    prefixo = data.get('prefixo', 'PAT')
    quantidade = int(data.get('quantidade', 1))
    numero_inicial = int(data.get('numero_inicial', 1))
    observacao = data.get('observacao')
    
    result = PatrimonioService.adicionar_codigos_lote(
        codigo_item=codigo_item,
        prefixo=prefixo,
        quantidade=quantidade,
        numero_inicial=numero_inicial,
        observacao=observacao
    )
    
    if request.is_json:
        return jsonify(result)
    
    if result['success']:
        flash(f"{result['quantidade_criada']} códigos patrimoniais criados com sucesso!", 'success')
        if result['codigos_duplicados']:
            flash(f"{len(result['codigos_duplicados'])} códigos já existiam e foram ignorados", 'warning')
    else:
        flash(f"Erro ao criar códigos: {result['error']}", 'error')
    
    return redirect(url_for('patrimonio.listar_codigos', codigo_item=codigo_item))


@bp.route('/disponiveis/<codigo_item>')
@login_required
def listar_disponiveis(codigo_item):
    """API: Lista códigos patrimoniais disponíveis."""
    codigos = PatrimonioService.listar_disponiveis(codigo_item)
    return jsonify({
        'success': True,
        'codigos': codigos,
        'total': len(codigos)
    })


@bp.route('/atribuir', methods=['POST'])
@login_required
def atribuir():
    """Atribui código patrimonial a usuário."""
    data = request.get_json()
    
    codigo_patrimonial = data.get('codigo_patrimonial')
    matricula = data.get('matricula')
    
    result = PatrimonioService.atribuir_a_usuario(codigo_patrimonial, matricula)
    
    return jsonify(result)


@bp.route('/devolver', methods=['POST'])
@login_required
def devolver():
    """Devolve código patrimonial (libera para reuso)."""
    data = request.get_json()
    
    codigo_patrimonial = data.get('codigo_patrimonial')
    
    result = PatrimonioService.devolver(codigo_patrimonial)
    
    return jsonify(result)


@bp.route('/historico/<codigo_patrimonial>')
@login_required
def historico(codigo_patrimonial):
    """Mostra histórico completo de uso de um código patrimonial."""
    patrimonio = PatrimonioService.buscar_por_codigo(codigo_patrimonial)
    
    if not patrimonio:
        flash(f'Código patrimonial {codigo_patrimonial} não encontrado', 'error')
        return redirect(url_for('inventory.index'))
    
    historico = PatrimonioService.historico_uso(codigo_patrimonial)
    
    return render_template(
        'patrimonio/historico.html',
        patrimonio=patrimonio,
        historico=historico
    )


@bp.route('/alterar-status', methods=['POST'])
@login_required
def alterar_status():
    """Altera status de um código patrimonial."""
    data = request.get_json()
    
    codigo_patrimonial = data.get('codigo_patrimonial')
    novo_status = data.get('status')
    observacao = data.get('observacao')
    
    result = PatrimonioService.alterar_status(
        codigo_patrimonial=codigo_patrimonial,
        novo_status=novo_status,
        observacao=observacao
    )
    
    return jsonify(result)


@bp.route('/deletar/<codigo_patrimonial>', methods=['DELETE', 'POST'])
@login_required
def deletar(codigo_patrimonial):
    """Remove um código patrimonial."""
    result = PatrimonioService.deletar_codigo(codigo_patrimonial)
    
    if request.is_json:
        return jsonify(result)
    
    if result['success']:
        flash(f"Código {codigo_patrimonial} removido com sucesso!", 'success')
    else:
        flash(f"Erro ao remover código: {result['error']}", 'error')
    
    # Redirect para a página anterior ou index
    return redirect(request.referrer or url_for('inventory.index'))


@bp.route('/buscar/<codigo_patrimonial>')
@login_required
def buscar(codigo_patrimonial):
    """API: Busca informações de um código patrimonial."""
    patrimonio = PatrimonioService.buscar_por_codigo(codigo_patrimonial)
    
    if patrimonio:
        return jsonify({
            'success': True,
            'patrimonio': patrimonio
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Código patrimonial não encontrado'
        }), 404


@bp.route('/estatisticas/<codigo_item>')
@login_required
def estatisticas(codigo_item):
    """API: Retorna estatísticas de códigos patrimoniais de um item."""
    stats = PatrimonioService.estatisticas_item(codigo_item)
    
    return jsonify({
        'success': True,
        'estatisticas': stats
    })
