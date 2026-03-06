"""Views para gerenciamento de atualizações."""
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
from flask_login import login_required, current_user

from ..services.update_service import UpdateService
from ..paths import get_version, is_frozen


blueprint = Blueprint(
    'updates',
    __name__,
    url_prefix='/atualizacoes'
)


@blueprint.get('/')
@login_required
def index():
    """Página de atualizações."""
    if not getattr(current_user, "is_admin", False):
        flash('Acesso negado. Apenas administradores podem gerenciar atualizações.', 'error')
        return redirect(url_for('painel.index'))
    
    current_version = get_version()
    is_executable = is_frozen()
    settings = UpdateService.get_auto_update_settings()
    history = UpdateService.get_update_history()
    pending = UpdateService.get_pending_update()
    
    return render_template(
        'updates/index.html',
        current_version=current_version,
        is_executable=is_executable,
        settings=settings,
        history=history,
        pending=pending
    )


@blueprint.post('/check')
@login_required
def check():
    """Verifica se há atualizações disponíveis."""
    if not getattr(current_user, "is_admin", False):
        return jsonify({'error': 'Acesso negado'}), 403
    
    if not is_frozen():
        return jsonify({
            'error': 'Atualizações automáticas só funcionam no executável. Você está em modo desenvolvimento.'
        }), 400
    
    update_info = UpdateService.check_for_updates()
    UpdateService.mark_check_done()
    
    if not update_info:
        return jsonify({
            'available': False,
            'message': 'Você já está na versão mais recente!',
            'current_version': get_version()
        })
    
    return jsonify({
        'available': True,
        'update_info': update_info
    })


@blueprint.post('/download')
@login_required
def download():
    """Baixa a atualização."""
    if not getattr(current_user, "is_admin", False):
        return jsonify({'error': 'Acesso negado'}), 403
    
    if not is_frozen():
        return jsonify({'error': 'Apenas no executável'}), 400
    
    data = request.get_json()
    download_url = data.get('download_url')
    sha256 = data.get('sha256')
    
    if not download_url:
        return jsonify({'error': 'URL de download não fornecida'}), 400
    
    # Download em background (simplificado, pode melhorar com threading)
    update_file = UpdateService.download_update(download_url, sha256)
    
    if not update_file:
        return jsonify({'error': 'Falha ao baixar atualização'}), 500
    
    return jsonify({
        'success': True,
        'update_file': str(update_file),
        'message': 'Download concluído!'
    })


@blueprint.post('/install')
@login_required
def install():
    """Instala a atualização baixada."""
    if not getattr(current_user, "is_admin", False):
        return jsonify({'error': 'Acesso negado'}), 403
    
    if not is_frozen():
        return jsonify({'error': 'Apenas no executável'}), 400
    
    data = request.get_json()
    update_file_path = data.get('update_file')
    
    if not update_file_path:
        return jsonify({'error': 'Arquivo de atualização não fornecido'}), 400
    
    from pathlib import Path
    update_file = Path(update_file_path)
    
    if not update_file.exists():
        return jsonify({'error': 'Arquivo de atualização não encontrado'}), 404
    
    # Agenda instalação
    success = UpdateService.install_update(update_file)
    
    if not success:
        return jsonify({'error': 'Falha ao agendar instalação'}), 500
    
    return jsonify({
        'success': True,
        'message': 'Instalação agendada! O sistema será reiniciado em instantes...',
        'action': 'restart_required'
    })


@blueprint.post('/settings')
@login_required
def update_settings():
    """Atualiza configurações de auto-update."""
    if not getattr(current_user, "is_admin", False):
        return jsonify({'error': 'Acesso negado'}), 403
    
    data = request.get_json()
    
    settings = UpdateService.get_auto_update_settings()
    
    # Atualizar apenas campos permitidos
    if 'enabled' in data:
        settings['enabled'] = bool(data['enabled'])
    
    if 'check_interval_hours' in data:
        try:
            hours = int(data['check_interval_hours'])
            if hours < 1:
                return jsonify({'error': 'Intervalo deve ser pelo menos 1 hora'}), 400
            settings['check_interval_hours'] = hours
        except ValueError:
            return jsonify({'error': 'Intervalo inválido'}), 400
    
    if 'auto_install' in data:
        settings['auto_install'] = bool(data['auto_install'])
    
    UpdateService.save_auto_update_settings(settings)
    
    flash('Configurações de atualização salvas com sucesso!', 'success')
    
    return jsonify({
        'success': True,
        'settings': settings
    })


@blueprint.get('/history')
@login_required
def history():
    """Retorna histórico de atualizações."""
    if not getattr(current_user, "is_admin", False):
        return jsonify({'error': 'Acesso negado'}), 403
    
    history = UpdateService.get_update_history()
    
    return jsonify({
        'history': history
    })
