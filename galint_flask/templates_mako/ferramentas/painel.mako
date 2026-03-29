<%inherit file="/base.mako"/>
<%!
    def fmt_dt(value):
        if not value:
            return "-"
        try:
            return value.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return str(value)
%>

<%block name="title">Painel de Ferramentas</%block>

<%block name="extra_css">
<style>
    .tools-panel-header {
        background: linear-gradient(120deg, #2563eb 0%, #3b82f6 100%);
        color: white;
        padding: 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 20px rgba(37, 99, 235, 0.4);
    }
    
    .tools-panel-header h2 {
        margin: 0;
        font-weight: 700;
        font-size: 1.75rem;
    }
    
    .tools-panel-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.95;
        font-size: 0.95rem;
    }
    
    .stats-row {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 1.5rem;
        margin-bottom: 2rem;
    }
    
    .stat-card {
        border-radius: 12px;
        padding: 1.5rem;
        color: white;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        transition: transform 0.3s ease;
    }
    
    .stat-card:hover {
        transform: translateY(-4px);
    }
    
    .stat-card.verde {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    }
    
    .stat-card.vermelho {
        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
    }
    
    .stat-card.amarelo {
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
    }
    
    .stat-number {
        font-size: 3rem;
        font-weight: 700;
        line-height: 1;
        margin-bottom: 0.5rem;
    }
    
    .stat-label {
        font-size: 1rem;
        font-weight: 600;
        opacity: 0.95;
    }
    
    .section-title {
        font-size: 1.25rem;
        font-weight: 700;
        color: #1f2937;
        margin: 2rem 0 1rem 0;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    .tool-card {
        background: #ffffff;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        border-left: 4px solid #3b82f6;
        transition: all 0.3s ease;
    }
    
    .tool-card:hover {
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
        transform: translateX(4px);
    }
    
    .tool-card.atrasada {
        border-left-color: #ef4444;
        background: #fef2f2;
    }
    
    .tool-card.reparo {
        border-left-color: #f59e0b;
        background: #fffbeb;
    }
    
    .tool-header {
        display: flex;
        justify-content: space-between;
        align-items: start;
        margin-bottom: 1rem;
    }
    
    .tool-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1f2937;
        margin: 0;
    }
    
    .tool-code {
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
        color: #6b7280;
        margin-top: 0.25rem;
    }
    
    .tool-info {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 0.75rem;
        margin-bottom: 1rem;
    }
    
    .info-item {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.9rem;
        color: #4b5563;
    }
    
    .info-icon {
        color: #3b82f6;
        font-size: 1.1rem;
    }
    
    .tool-actions {
        display: flex;
        gap: 0.5rem;
        flex-wrap: wrap;
    }
    
    .btn-action {
        border-radius: 6px;
        padding: 0.5rem 1rem;
        font-size: 0.9rem;
        font-weight: 600;
        border: none;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    
    .btn-devolver {
        background: #10b981;
        color: white;
    }
    
    .btn-devolver:hover {
        background: #059669;
        transform: scale(1.05);
    }
    
    .btn-reparo {
        background: #f59e0b;
        color: white;
    }
    
    .btn-reparo:hover {
        background: #d97706;
        transform: scale(1.05);
    }
    
    .badge-status {
        display: inline-block;
        padding: 0.35rem 0.75rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    
    .badge-em-uso {
        background: #d1fae5;
        color: #065f46;
    }
    
    .badge-atrasada {
        background: #fee2e2;
        color: #991b1b;
    }
    
    .badge-reparo {
        background: #fef3c7;
        color: #92400e;
    }
    
    .empty-state {
        text-align: center;
        padding: 3rem;
        color: #9ca3af;
    }
    
    .empty-state i {
        font-size: 4rem;
        margin-bottom: 1rem;
        opacity: 0.3;
    }
</style>
</%block>

<%block name="content">
<div class="container-fluid">
    <div class="tools-panel-header">
        <h2><i class="bi bi-speedometer2 me-2"></i>Painel de Ferramentas</h2>
        <p>Controle e rastreabilidade de ferramentas em uso</p>
    </div>
    
    <!-- Estatísticas -->
    <div class="stats-row">
        <div class="stat-card verde">
            <div class="stat-number">${stats['em_uso']}</div>
            <div class="stat-label"><i class="bi bi-tools me-2"></i>Em Uso Hoje</div>
        </div>
        <div class="stat-card vermelho">
            <div class="stat-number">${stats['atrasadas']}</div>
            <div class="stat-label"><i class="bi bi-exclamation-triangle me-2"></i>Atrasadas</div>
        </div>
        <div class="stat-card amarelo">
            <div class="stat-number">${stats['para_reparo']}</div>
            <div class="stat-label"><i class="bi bi-wrench me-2"></i>Para Reparo</div>
        </div>
    </div>
    
    <!-- Ferramentas Em Uso -->
    <div class="section-title">
        <i class="bi bi-tools"></i>
        <span>Ferramentas em Uso (Hoje)</span>
    </div>
    
    % if not em_uso:
        <div class="empty-state">
            <i class="bi bi-inbox"></i>
            <p>Nenhuma ferramenta em uso no momento</p>
        </div>
    % else:
        % for item in em_uso:
            <div class="tool-card">
                <div class="tool-header">
                    <div>
                        <h3 class="tool-title">${item['descricao']}</h3>
                        <div class="tool-code">📦 ${item['codigo_item']}</div>
                    </div>
                    <span class="badge-status badge-em-uso">EM USO</span>
                </div>
                
                <div class="tool-info">
                    <div class="info-item">
                        <i class="bi bi-person info-icon"></i>
                        <span><strong>${item['nome_usuario']}</strong> (...${item['matricula_ultimos5']})</span>
                    </div>
                    <div class="info-item">
                        <i class="bi bi-hash info-icon"></i>
                        <span>Quantidade: <strong>${item['quantidade']}</strong></span>
                    </div>
                    <div class="info-item">
                        <i class="bi bi-geo-alt info-icon"></i>
                        <span>${item['local_servico'] or 'Local não informado'}</span>
                    </div>
                    <div class="info-item">
                        <i class="bi bi-clock info-icon"></i>
                        <span>${fmt_dt(item['data_retirada'])}</span>
                    </div>
                </div>
                
                % if item.get('observacao'):
                    <div class="mb-2">
                        <small class="text-muted"><i class="bi bi-chat-left-text me-1"></i>${item['observacao']}</small>
                    </div>
                % endif
                
                <div class="tool-actions">
                    <form method="post" action="${url_for('ferramentas.devolver', retirada_id=item['id'])}" style="display: inline;">
                        <button type="submit" class="btn-action btn-devolver" onclick="return confirm('Confirmar devolução?')">
                            <i class="bi bi-check-circle me-1"></i>Devolver
                        </button>
                    </form>
                    <button type="button" class="btn-action btn-reparo" onclick="marcarReparo(${item['id']})">
                        <i class="bi bi-wrench me-1"></i>Marcar Para Reparo
                    </button>
                </div>
            </div>
        % endfor
    % endif
    
    <!-- Ferramentas Atrasadas -->
    % if atrasadas:
        <div class="section-title">
            <i class="bi bi-exclamation-triangle"></i>
            <span>Ferramentas Atrasadas</span>
        </div>
        
        % for item in atrasadas:
            <div class="tool-card atrasada">
                <div class="tool-header">
                    <div>
                        <h3 class="tool-title">${item['descricao']}</h3>
                        <div class="tool-code">📦 ${item['codigo_item']}</div>
                    </div>
                    <span class="badge-status badge-atrasada">ATRASADA</span>
                </div>
                
                <div class="tool-info">
                    <div class="info-item">
                        <i class="bi bi-person info-icon"></i>
                        <span><strong>${item['nome_usuario']}</strong> (...${item['matricula_ultimos5']})</span>
                    </div>
                    <div class="info-item">
                        <i class="bi bi-hash info-icon"></i>
                        <span>Quantidade: <strong>${item['quantidade']}</strong></span>
                    </div>
                    <div class="info-item">
                        <i class="bi bi-geo-alt info-icon"></i>
                        <span>${item['local_servico'] or 'Local não informado'}</span>
                    </div>
                    <div class="info-item">
                        <i class="bi bi-clock info-icon"></i>
                        <span>${fmt_dt(item['data_retirada'])} <strong class="text-danger">(${item['dias_em_uso']} dias)</strong></span>
                    </div>
                </div>
                
                <div class="tool-actions">
                    <form method="post" action="${url_for('ferramentas.devolver', retirada_id=item['id'])}" style="display: inline;">
                        <button type="submit" class="btn-action btn-devolver" onclick="return confirm('Confirmar devolução?')">
                            <i class="bi bi-check-circle me-1"></i>Devolver
                        </button>
                    </form>
                    <button type="button" class="btn-action btn-reparo" onclick="marcarReparo(${item['id']})">
                        <i class="bi bi-wrench me-1"></i>Marcar Para Reparo
                    </button>
                </div>
            </div>
        % endfor
    % endif
    
    <!-- Ferramentas Para Reparo -->
    % if para_reparo:
        <div class="section-title">
            <i class="bi bi-wrench"></i>
            <span>Ferramentas Para Reparo</span>
        </div>
        
        % for item in para_reparo:
            <div class="tool-card reparo">
                <div class="tool-header">
                    <div>
                        <h3 class="tool-title">${item['descricao']}</h3>
                        <div class="tool-code">📦 ${item['codigo_item']}</div>
                    </div>
                    <span class="badge-status badge-reparo">PARA REPARO</span>
                </div>
                
                <div class="tool-info">
                    <div class="info-item">
                        <i class="bi bi-person info-icon"></i>
                        <span><strong>${item['nome_usuario']}</strong> (...${item['matricula_ultimos5']})</span>
                    </div>
                    <div class="info-item">
                        <i class="bi bi-hash info-icon"></i>
                        <span>Quantidade: <strong>${item['quantidade']}</strong></span>
                    </div>
                    <div class="info-item">
                        <i class="bi bi-clock info-icon"></i>
                        <span>Retirada: ${fmt_dt(item['data_retirada'])}</span>
                    </div>
                </div>
                
                % if item.get('observacao_reparo'):
                    <div class="alert alert-warning mt-2 mb-0">
                        <i class="bi bi-wrench me-1"></i><strong>Motivo:</strong> ${item['observacao_reparo']}
                    </div>
                % endif
            </div>
        % endfor
    % endif
    
    <div class="mt-4 text-center">
        <a href="${url_for('ferramentas.retirar_page')}" class="btn btn-primary">
            <i class="bi bi-plus-circle me-1"></i>Nova Retirada
        </a>
    </div>
</div>
</%block>

<%block name="scripts">
$${parent.scripts()}
<script>
function marcarReparo(retiradaId) {
    const motivo = prompt('Informe o motivo do reparo:');
    if (!motivo || !motivo.trim()) {
        alert('Você precisa informar o motivo do reparo');
        return;
    }
    
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/ferramentas/marcar-reparo/' + retiradaId;
    
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'observacao';
    input.value = motivo;
    
    form.appendChild(input);
    document.body.appendChild(form);
    form.submit();
}
</script>
</%block>
