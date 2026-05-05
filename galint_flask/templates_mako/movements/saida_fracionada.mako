<%inherit file="/base.mako"/>

<%block name="title">Registro de Saída Fracionada</%block>

<%block name="extra_css">
<style>
    @import url('${url_for("static", filename="css/express-return-modal.css")}?v=20260414b');

    .saida-container {
        max-width: 900px;
        margin: 0 auto;
    }

    .saida-shell {
        background: linear-gradient(180deg, #eef2f7 0%, #f8fafc 100%);
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 30px;
        padding: 1.85rem;
        box-shadow: 0 24px 54px rgba(15, 23, 42, 0.1);
    }
    
    .page-header {
        position: relative;
        overflow: hidden;
        background: linear-gradient(135deg, #020617 0%, #172554 45%, #2563eb 100%);
        color: white;
        padding: 2rem;
        border-radius: 24px;
        margin-bottom: 2rem;
        box-shadow: 0 28px 64px rgba(15, 23, 42, 0.2);
    }

    .page-header::before {
        content: "";
        position: absolute;
        inset: 0;
        background: radial-gradient(circle at 16% 18%, rgba(56, 189, 248, 0.22), transparent 28%), radial-gradient(circle at 84% 18%, rgba(96, 165, 250, 0.18), transparent 22%);
        pointer-events: none;
    }

    .page-header > * {
        position: relative;
        z-index: 1;
    }
    
    .page-header h2 {
        margin: 0;
        font-weight: 700;
        font-size: 1.75rem;
    }
    
    .page-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.95;
        font-size: 0.95rem;
    }

    .page-header-actions {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-top: 1rem;
        flex-wrap: wrap;
    }

    .btn-mirror-screen {
        display: inline-flex;
        align-items: center;
        gap: 0.78rem;
        border-radius: 999px;
        padding: 0.45rem 1.05rem 0.45rem 0.5rem;
        border: none;
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.18), rgba(191, 219, 254, 0.08));
        color: #f8fbff;
        font-weight: 800;
        letter-spacing: 0.01em;
        text-decoration: none;
        box-shadow: 0 18px 36px rgba(15, 23, 42, 0.22);
        backdrop-filter: blur(14px);
        transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
    }

    .btn-mirror-screen:hover {
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.24), rgba(147, 197, 253, 0.14));
        color: #ffffff;
        transform: translateY(-1px);
        box-shadow: 0 22px 42px rgba(15, 23, 42, 0.24);
    }

    .btn-mirror-screen:focus-visible {
        outline: none;
        box-shadow: 0 0 0 3px rgba(125, 211, 252, 0.24), 0 22px 42px rgba(15, 23, 42, 0.24);
    }

    .btn-mirror-screen-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 2.2rem;
        height: 2.2rem;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.14);
        color: #ffffff;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.18);
        flex: 0 0 auto;
    }

    .btn-mirror-screen-icon img {
        width: 1.3rem;
        height: 1.3rem;
        object-fit: contain;
        display: block;
    }

    .btn-mirror-screen-label {
        display: inline-flex;
        align-items: center;
        line-height: 1;
    }
    
    .input-card {
        background: linear-gradient(145deg, #0f172a 0%, #1e293b 100%);
        border-radius: 24px;
        padding: 1.5rem;
        box-shadow: 0 22px 48px rgba(15, 23, 42, 0.16);
        margin-bottom: 1.5rem;
        border: 1px solid rgba(148, 163, 184, 0.18);
    }
    
    .input-card .form-label {
        font-weight: 600;
        color: #e2e8f0;
        margin-bottom: 0.5rem;
        font-size: 0.9rem;
    }
    
    .input-card .form-control,
    .input-card .form-select {
        border-radius: 8px;
        border: 1px solid rgba(148, 163, 184, 0.22);
        background: rgba(15, 23, 42, 0.82);
        color: #f8fafc;
        padding: 0.75rem 1rem;
        transition: all 0.3s ease;
        font-size: 1rem;
    }

    .input-card .form-control::placeholder {
        color: #94a3b8;
    }
    
    .input-card .form-control:focus,
    .input-card .form-select:focus {
        border-color: #3b82f6;
        box-shadow: 0 0 0 0.2rem rgba(37, 99, 235, 0.15);
        background: rgba(15, 23, 42, 0.92);
    }
    
    .btn-register {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        border: none;
        border-radius: 8px;
        padding: 1rem 2rem;
        font-weight: 700;
        color: white;
        font-size: 1.1rem;
        transition: all 0.3s ease;
        box-shadow: 0 4px 12px rgba(17, 153, 142, 0.3);
    }
    
    .btn-register:hover:not(:disabled) {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(17, 153, 142, 0.4);
    }
    
    .btn-register:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .info-strip {
        background: linear-gradient(145deg, rgba(15, 23, 42, 0.94) 0%, rgba(30, 41, 59, 0.92) 100%);
        border: 1px solid rgba(56, 189, 248, 0.28);
        color: #dbeafe;
        border-radius: 18px;
        padding: 1rem;
        box-shadow: 0 16px 34px rgba(15, 23, 42, 0.14);
        margin-bottom: 1.5rem;
    }

    .info-strip strong {
        color: #ffffff;
    }

    .info-strip i {
        color: #7dd3fc;
    }
    
    .autocomplete-dropdown {
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        max-height: 300px;
        overflow-y: auto;
        background: white;
        border: 2px solid #3b82f6;
        border-top: none;
        border-radius: 0 0 8px 8px;
        z-index: 1000;
        display: none;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }
    
    .autocomplete-dropdown.show {
        display: block;
    }
    
    .autocomplete-item {
        padding: 0.75rem 1rem;
        cursor: pointer;
        border-bottom: 1px solid #f0f0f0;
        transition: background 0.15s ease;
    }
    
    .autocomplete-item:last-child {
        border-bottom: none;
    }
    
    .autocomplete-item:hover,
    .autocomplete-item.active {
        background: #e7f3ff;
    }
    
    .autocomplete-item-title {
        font-weight: 600;
        color: #212529;
        margin-bottom: 0.25rem;
    }
    
    .autocomplete-item-details {
        font-size: 0.85rem;
        color: #6c757d;
    }
    
    .autocomplete-item-code {
        color: #0d6efd;
        font-family: monospace;
    }

    .modal-item-layout {
        display: grid;
        grid-template-columns: 96px 1fr;
        gap: 1rem;
        align-items: start;
    }

    .modal-item-photo {
        width: 96px;
        height: 96px;
        border-radius: 12px;
        object-fit: cover;
        border: 1px solid #dbe4f0;
        background: #f8fafc;
        display: none;
    }

    .modal-item-photo.show {
        display: block;
    }

    .modal-item-photo-empty {
        width: 96px;
        height: 96px;
        border-radius: 12px;
        border: 1px dashed #cbd5e1;
        background: #f8fafc;
        color: #64748b;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.5rem;
    }

    .modal-item-photo-empty.hide {
        display: none;
    }

    .modal-kpi-line {
        margin: 0.2rem 0;
        color: #334155;
    }

    .modal-kpi-line strong {
        color: #0f172a;
    }

    .modal-live-summary {
        background: #f8fafc;
        border: 1px solid #dbe4f0;
        border-radius: 10px;
        padding: 0.85rem 1rem;
        margin-top: 0.75rem;
    }

    .modal-live-summary.invalid {
        background: #fef2f2;
        border-color: #fecaca;
    }

    .modal-live-summary .summary-line {
        margin: 0.15rem 0;
        color: #334155;
        font-size: 0.95rem;
    }

    .modal-live-summary.invalid .summary-line,
    .modal-live-summary.invalid .summary-warning {
        color: #b91c1c;
    }

    .summary-warning {
        margin-top: 0.45rem;
        font-size: 0.9rem;
        display: none;
    }

    .summary-warning.show {
        display: block;
    }

    .operation-preview {
        display: grid;
        grid-template-columns: 220px 1fr;
        gap: 1.25rem;
        background: linear-gradient(145deg, #0f172a 0%, #1e293b 100%);
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 24px;
        padding: 1.25rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 22px 48px rgba(15, 23, 42, 0.16);
    }

    .operation-preview.is-empty {
        grid-template-columns: 1fr;
    }

    .operation-preview-media {
        min-height: 220px;
        border-radius: 20px;
        overflow: hidden;
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.96) 0%, rgba(15, 23, 42, 0.96) 100%);
        border: 1px solid rgba(148, 163, 184, 0.2);
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .operation-preview-media img {
        width: 100%;
        height: 220px;
        object-fit: contain;
        background: rgba(255, 255, 255, 0.04);
    }

    .operation-preview-placeholder {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        color: #cbd5e1;
        text-align: center;
        padding: 1.25rem;
    }

    .operation-preview-placeholder i {
        font-size: 3.25rem;
        color: #60a5fa;
    }

    .operation-preview-body {
        color: #e2e8f0;
        display: flex;
        flex-direction: column;
        gap: 0.85rem;
    }

    .operation-preview-eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        width: fit-content;
        padding: 0.4rem 0.7rem;
        border-radius: 999px;
        background: rgba(59, 130, 246, 0.16);
        border: 1px solid rgba(59, 130, 246, 0.24);
        color: #bfdbfe;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .operation-preview-title {
        margin: 0;
        color: #f8fafc;
        font-size: 1.35rem;
        font-weight: 800;
        letter-spacing: -0.02em;
    }

    .operation-preview-subtitle {
        color: #93c5fd;
        font-size: 0.92rem;
    }

    .operation-preview-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.75rem;
    }

    .operation-preview-stat {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 14px;
        padding: 0.8rem 0.9rem;
    }

    .operation-preview-stat-label {
        display: block;
        color: #94a3b8;
        font-size: 0.78rem;
        margin-bottom: 0.25rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }

    .operation-preview-stat-value {
        color: #f8fafc;
        font-size: 1rem;
        font-weight: 700;
        line-height: 1.35;
    }

    .operation-preview-note {
        color: #cbd5e1;
        font-size: 0.88rem;
    }

    @media (max-width: 991.98px) {
        .operation-preview {
            grid-template-columns: 1fr;
        }

        .operation-preview-grid {
            grid-template-columns: 1fr;
        }
    }
</style>
</%block>

<%block name="page_header">
    <h2><i class="bi bi-droplet-half me-2"></i>Registro de Saída Fracionada</h2>
    <p>Insira a quantidade pesada com o novo container dark, mantendo o fluxo específico para itens líquidos e fracionados.</p>
    <div class="page-header-actions">
        <a class="btn-mirror-screen" data-mirror-screen="1" href="${url_for('movements.painel_espelho_page')}" target="_blank" rel="noopener">
            <span class="btn-mirror-screen-icon"><img src="${url_for('static', filename='img/galint-icon.png')}" alt="GALINT"></span>
            <span class="btn-mirror-screen-label">Painel de Visualização</span>
        </a>
        <button class="btn-mirror-screen btn-express-return" type="button" id="btn-open-express-return">
            <span class="btn-mirror-screen-icon"><i class="bi bi-arrow-return-left"></i></span>
            <span class="btn-mirror-screen-label">Devolução Expressa</span>
        </button>
    </div>
</%block>

<%block name="content">
<div class="saida-container">
    <div class="saida-shell">

    <div class="info-strip" role="alert">
        <i class="bi bi-info-circle me-2"></i>
        <strong>Dica:</strong> Use esta tela quando a retirada depender da pesagem real, em kg ou litro.
    </div>

    <div class="input-card">
        <div class="row g-3">
            <div class="col-md-6 position-relative">
                <label class="form-label"><i class="bi bi-person-badge me-1"></i>Crachá/Matrícula</label>
                <input class="form-control" id="input-usuario" placeholder="Leia ou digite o crachá ou nome" autocomplete="off" required>
                <div id="autocomplete-dropdown-usuario" class="autocomplete-dropdown"></div>
            </div>
            <div class="col-md-6">
                <label class="form-label"><i class="bi bi-geo-alt me-1"></i>Local do Serviço / Finalidade</label>
                <input class="form-control" id="input-local" placeholder="Ex: Pintura do bloco 5" autocomplete="off">
            </div>
        </div>

        <div class="row g-3 mt-1">
            <div class="col-md-4">
                <label class="form-label"><i class="bi bi-diagram-3 me-1"></i>Atividade operacional</label>
                <select class="form-select" id="input-atividade-operacional">
                    <option value="">Selecionar atividade</option>
                    % for option in operational_activity_options:
                    <option value="${option.get('key')}">${option.get('label')}</option>
                    % endfor
                </select>
            </div>
            <div class="col-md-4">
                <label class="form-label"><i class="bi bi-file-earmark-text me-1"></i>OS / referência</label>
                <input class="form-control" id="input-ordem-servico" placeholder="Ex: OS-2487" autocomplete="off">
            </div>
            <div class="col-md-4">
                <label class="form-label"><i class="bi bi-building me-1"></i>Centro de custo</label>
                <input class="form-control" id="input-centro-custo" placeholder="Ex: MANUTENCAO BLOCO 5" autocomplete="off">
            </div>
        </div>
        
        <hr class="my-3">
        
        <div class="row g-3">
            <div class="col-md-8 position-relative">
                <label class="form-label"><i class="bi bi-upc-scan me-1"></i>Código do Item</label>
                <input class="form-control" id="input-codigo" placeholder="Leia ou digite o código do item" autocomplete="off" required>
                <div id="autocomplete-dropdown-codigo" class="autocomplete-dropdown"></div>
            </div>
            <div class="col-md-4 d-flex align-items-end">
                <button class="btn btn-register w-100" type="button" id="btn-registrar" disabled>
                    <i class="bi bi-check-circle me-2"></i>Registrar Saída
                </button>
            </div>
        </div>
    </div>

    <div class="operation-preview is-empty" id="current-item-preview">
        <div class="operation-preview-body">
            <span class="operation-preview-eyebrow"><i class="bi bi-display"></i> Painel operacional</span>
            <div class="operation-preview-placeholder">
                <i class="bi bi-droplet-half"></i>
                <div>
                    <strong>Nenhum item fracionado em foco</strong>
                    <div class="operation-preview-note">Selecione um item para exibir foto, saldo total e contexto da retirada fracionada.</div>
                </div>
            </div>
        </div>
    </div>
    </div>
</div>

<!-- Modal de Quantidade Manual -->
<div class="modal fade" id="modalQuantidade" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
            <div class="modal-header" style="background: linear-gradient(120deg, #2563eb 0%, #3b82f6 100%); color: white;">
                <h5 class="modal-title"><i class="bi bi-calculator me-2"></i>Quantidade Retirada</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <div class="modal-item-layout mb-3">
                    <div>
                        <img id="modal-item-photo" class="modal-item-photo" alt="Foto do item">
                        <div id="modal-item-photo-empty" class="modal-item-photo-empty">
                            <i class="bi bi-image"></i>
                        </div>
                    </div>
                    <div>
                        <p class="mb-2">Item: <strong id="modal-item-desc"></strong></p>
                        <p class="modal-kpi-line">Unidade: <strong id="modal-item-unidade"></strong> <span class="text-muted">|</span> Saldo total: <strong id="modal-saldo-total"></strong></p>
                        <p class="modal-kpi-line mb-0">Capacidade por embalagem: <strong id="modal-capacidade-embalagem">-</strong></p>
                    </div>
                </div>
                
                <!-- Opção de escolher entre KG ou LITRO -->
                <div class="mb-3">
                    <label class="form-label fw-bold">Escolha a unidade:</label>
                    <div class="btn-group w-100" role="group">
                        <input type="radio" class="btn-check" name="unidade-tipo" id="unidade-kg" value="kg" checked>
                        <label class="btn btn-outline-primary" for="unidade-kg" id="label-unidade-kg">
                            <i class="bi bi-box me-1"></i>KG
                        </label>
                        <input type="radio" class="btn-check" name="unidade-tipo" id="unidade-litro" value="litro">
                        <label class="btn btn-outline-primary" for="unidade-litro" id="label-unidade-litro">
                            <i class="bi bi-droplet me-1"></i>LITRO
                        </label>
                        <input type="radio" class="btn-check" name="unidade-tipo" id="unidade-metro" value="metro">
                        <label class="btn btn-outline-primary" for="unidade-metro" id="label-unidade-metro" style="display: none;">
                            <i class="bi bi-rulers me-1"></i>METRO
                        </label>
                        <input type="radio" class="btn-check" name="unidade-tipo" id="unidade-centimetro" value="cm">
                        <label class="btn btn-outline-primary" for="unidade-centimetro" id="label-unidade-centimetro" style="display: none;">
                            <i class="bi bi-rulers me-1"></i>CM
                        </label>
                    </div>
                </div>
                
                <div class="mb-3">
                    <label class="form-label fw-bold">Digite a quantidade retirada:</label>
                    <div class="input-group input-group-lg">
                        <input type="number" class="form-control" id="modal-quantidade-input" 
                               min="0.001" step="0.001" placeholder="Ex: 0.400" autofocus>
                        <span class="input-group-text" id="modal-quantidade-unidade">kg</span>
                    </div>
                    <small class="text-muted">Informe o valor pesado na balança <span id="hint-unidade">ou LITRO</span></small>
                    <div id="modal-live-summary" class="modal-live-summary">
                        <div class="summary-line">Saldo após retirada: <strong id="modal-saldo-restante">-</strong></div>
                        <div class="summary-line">Restante estimado: <strong id="modal-restante-embalagens">-</strong></div>
                        <div id="modal-summary-warning" class="summary-warning">Retirada maior que o saldo disponível.</div>
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                <button type="button" class="btn btn-primary" id="btn-confirmar-quantidade">Confirmar</button>
            </div>
        </div>
    </div>
</div>

<div class="modal fade" id="modalDevolucaoExpressa" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered modal-lg express-return-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title"><i class="bi bi-arrow-return-left me-2"></i>Devolução Expressa</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Fechar"></button>
            </div>
            <div class="modal-body">
                <div class="express-return-window-note">A devolução expressa mostra só retiradas fracionadas do dia e some automaticamente às 17:00.</div>
                <div class="alert alert-secondary express-return-status" data-express-return-role="status" role="status">Abra o painel para carregar os colaboradores com devolução pendente.</div>
                <section class="express-return-section">
                    <div class="express-return-section-title"><i class="bi bi-people"></i>Colaboradores com saídas fracionadas pendentes</div>
                    <div class="express-return-collaborators" data-express-return-role="collaborators">
                        <div class="express-return-empty">Abra o painel para carregar os colaboradores.</div>
                    </div>
                </section>
                <section class="express-return-section">
                    <div class="express-return-section-title"><i class="bi bi-droplet-half"></i>Itens do colaborador selecionado</div>
                    <div class="express-return-list" data-express-return-role="items">
                        <div class="express-return-empty">Selecione um colaborador acima.</div>
                    </div>
                </section>
                <div class="express-return-detail is-empty" data-express-return-role="detail">
                    <strong>Nenhum item selecionado.</strong>
                    <div class="express-return-hint">Escolha um item da lista abaixo para liberar a devolução.</div>
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Fechar</button>
                <button type="button" class="btn btn-register" data-express-return-role="submit" disabled>Fazer devolução</button>
            </div>
        </div>
    </div>
</div>

<form method="post" action="${url_for('movements.registrar_saida')}" id="hidden-form" style="display: none;">
    <input type="hidden" name="usuario" id="hidden-usuario">
    <input type="hidden" name="local_servico" id="hidden-local">
    <input type="hidden" name="atividade_operacional" id="hidden-atividade-operacional">
    <input type="hidden" name="ordem_servico" id="hidden-ordem-servico">
    <input type="hidden" name="centro_custo" id="hidden-centro-custo">
    <input type="hidden" name="codigo" id="hidden-codigo">
    <input type="hidden" name="quantidade" id="hidden-quantidade">
</form>

</%block>

<%block name="scripts">
${parent.scripts()}
<script src="${url_for('static', filename='js/mirror-screen-launcher.js')}"></script>
<script src="${url_for('static', filename='js/express-return-modal.js')}?v=20260414b"></script>
<script>
(function() {
    let pendingItem = null;
    const CAN_MANAGE = ${'true' if can_manage else 'false'};
    const usuariosAutocompleteData = ${tojson(usuarios)|n};
    const itemSearchUrl = '${url_for("movements.buscar_item")}';

    function normalizeAutocompleteText(value) {
        return String(value || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .trim();
    }

    async function fetchItemSuggestions(query) {
        const response = await window.galintFetchWithAuth(itemSearchUrl + '?q=' + encodeURIComponent(query), {
            headers: { 'Accept': 'application/json' }
        }, 'Sua sessão expirou durante a busca de itens. Faça login novamente.');
        if (!response.ok) {
            throw new Error('Falha ao buscar itens');
        }
        const data = await response.json();
        return (data.items || data.itens || []).slice(0, 20);
    }
    
    const inputUsuario = document.getElementById('input-usuario');
    const inputLocal = document.getElementById('input-local');
    const inputAtividadeOperacional = document.getElementById('input-atividade-operacional');
    const inputOrdemServico = document.getElementById('input-ordem-servico');
    const inputCentroCusto = document.getElementById('input-centro-custo');
    const inputCodigo = document.getElementById('input-codigo');
    const btnRegistrar = document.getElementById('btn-registrar');
    
    // Modal
    const modalQuantidade = new bootstrap.Modal(document.getElementById('modalQuantidade'));
    const modalItemDesc = document.getElementById('modal-item-desc');
    const modalItemUnidade = document.getElementById('modal-item-unidade');
    const modalSaldoTotal = document.getElementById('modal-saldo-total');
    const modalCapacidadeEmbalagem = document.getElementById('modal-capacidade-embalagem');
    const modalQuantidadeInput = document.getElementById('modal-quantidade-input');
    const modalQuantidadeUnidade = document.getElementById('modal-quantidade-unidade');
    const btnConfirmarQuantidade = document.getElementById('btn-confirmar-quantidade');
    const modalItemPhoto = document.getElementById('modal-item-photo');
    const modalItemPhotoEmpty = document.getElementById('modal-item-photo-empty');
    const modalLiveSummary = document.getElementById('modal-live-summary');
    const modalSaldoRestante = document.getElementById('modal-saldo-restante');
    const modalRestanteEmbalagens = document.getElementById('modal-restante-embalagens');
    const modalSummaryWarning = document.getElementById('modal-summary-warning');
    const currentItemPreview = document.getElementById('current-item-preview');
    const mirrorChannelName = 'galint-operation-mirror-v1';
    const mirrorStorageKey = 'galint.operationMirrorState.v1';
    const mirrorChannel = typeof window.BroadcastChannel !== 'undefined' ? new BroadcastChannel(mirrorChannelName) : null;
    let itemPreviewRequestId = 0;
    
    // Radio buttons de unidade
    const radioKg = document.getElementById('unidade-kg');
    const radioLitro = document.getElementById('unidade-litro');
    const radioMetro = document.getElementById('unidade-metro');
    const radioCentimetro = document.getElementById('unidade-centimetro');
    const labelUnidadeKg = document.getElementById('label-unidade-kg');
    const labelUnidadeLitro = document.getElementById('label-unidade-litro');
    const labelUnidadeMetro = document.getElementById('label-unidade-metro');
    const labelUnidadeCentimetro = document.getElementById('label-unidade-centimetro');
    const hintUnidade = document.getElementById('hint-unidade');

    function normalizeFractionUnitCode(unitCode) {
        const normalized = String(unitCode || '').trim().toLowerCase();
        if (normalized === 'quilo') return 'kg';
        return normalized;
    }

    function getSelectedUnitBadge(unitCode) {
        const normalized = normalizeFractionUnitCode(unitCode);
        if (normalized === 'litro') return 'L';
        if (normalized === 'kg') return 'kg';
        if (normalized === 'metro') return 'm';
        if (normalized === 'cm') return 'cm';
        return 'un';
    }

    function getPendingItemUnitFactors(item) {
        const source = item && (item.fracaoFatoresBase || item.fracao_fatores_base);
        if (!source || typeof source !== 'object') {
            return {};
        }

        const factors = {};
        Object.keys(source).forEach(function(key) {
            const normalizedKey = normalizeFractionUnitCode(key);
            const value = Number(source[key]);
            if (normalizedKey && Number.isFinite(value) && value > 0) {
                factors[normalizedKey] = value;
            }
        });
        return factors;
    }

    function configureFractionUnitOptions(defaultUnit, item) {
        const normalizedDefault = normalizeFractionUnitCode(defaultUnit);
        const factors = getPendingItemUnitFactors(item);
        const hasAnyFactors = Object.keys(factors).length > 0;
        const linearMode = normalizedDefault === 'metro';

        labelUnidadeKg.style.display = linearMode ? 'none' : '';
        labelUnidadeLitro.style.display = linearMode ? 'none' : '';
        labelUnidadeMetro.style.display = linearMode ? '' : 'none';
        labelUnidadeCentimetro.style.display = linearMode ? '' : 'none';

        if (linearMode) {
            const hasMetro = !hasAnyFactors || !!factors.metro;
            const hasCentimetro = !hasAnyFactors || !!factors.cm;
            labelUnidadeMetro.style.display = hasMetro ? '' : 'none';
            labelUnidadeCentimetro.style.display = hasCentimetro ? '' : 'none';
            radioKg.disabled = true;
            radioLitro.disabled = true;
            radioMetro.disabled = !hasMetro;
            radioCentimetro.disabled = !hasCentimetro;
            radioMetro.checked = hasMetro;
            radioCentimetro.checked = !hasMetro && hasCentimetro;
            radioKg.checked = false;
            radioLitro.checked = false;
            return;
        }

        const hasKg = !hasAnyFactors || !!factors.kg;
        const hasLitro = !hasAnyFactors || !!factors.litro;
        labelUnidadeKg.style.display = hasKg ? '' : 'none';
        labelUnidadeLitro.style.display = hasLitro ? '' : 'none';
        radioKg.disabled = !hasKg;
        radioLitro.disabled = !hasLitro;
        radioMetro.disabled = true;
        radioCentimetro.disabled = true;
        const preferLitro = normalizedDefault === 'litro' && hasLitro;
        const preferKg = normalizedDefault !== 'litro' && hasKg;
        radioKg.checked = preferKg || (!preferLitro && hasKg);
        radioLitro.checked = preferLitro || (!radioKg.checked && hasLitro);
        radioMetro.checked = false;
        radioCentimetro.checked = false;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    function publishMirrorState(payload) {
        const launcher = window.GalintMirrorScreenLauncher;
        if (launcher && typeof launcher.publishMirrorState === 'function') {
            launcher.publishMirrorState(payload, {
                storageKey: mirrorStorageKey,
                channel: mirrorChannel,
            });
            return;
        }
        try {
            window.localStorage.setItem(mirrorStorageKey, JSON.stringify(payload));
        } catch (error) {
            console.error('Erro ao persistir estado do painel espelho:', error);
        }
        if (mirrorChannel) {
            try {
                mirrorChannel.postMessage(payload);
            } catch (error) {
                console.error('Erro ao publicar estado do painel espelho:', error);
            }
        }
    }

    function getOperationalContext() {
        const atividadeKey = inputAtividadeOperacional ? String(inputAtividadeOperacional.value || '').trim() : '';
        const atividadeLabel = atividadeKey && inputAtividadeOperacional
            ? String(inputAtividadeOperacional.options[inputAtividadeOperacional.selectedIndex]?.text || '').trim()
            : '';
        return {
            atividade_operacional: atividadeKey,
            atividade_label: atividadeLabel,
            ordem_servico: String(inputOrdemServico && inputOrdemServico.value ? inputOrdemServico.value : '').trim(),
            centro_custo: String(inputCentroCusto && inputCentroCusto.value ? inputCentroCusto.value : '').trim(),
        };
    }

    function getSelectedUnitCode() {
        const unidadeSelecionada = document.querySelector('input[name="unidade-tipo"]:checked');
        return unidadeSelecionada ? normalizeFractionUnitCode(unidadeSelecionada.value) : '';
    }

    function getPendingItemOperationalFactor(item) {
        const value = Number(item && item.unitFactorBase);
        return Number.isFinite(value) && value > 0 ? value : 1;
    }

    function getSelectedUnitFactorBase(item, unitCode) {
        const factors = getPendingItemUnitFactors(item);
        const normalized = normalizeFractionUnitCode(unitCode);
        const explicitFactor = Number(factors[normalized]);
        if (Number.isFinite(explicitFactor) && explicitFactor > 0) {
            return explicitFactor;
        }
        if (normalized === 'cm') {
            return getPendingItemOperationalFactor(item) / 100;
        }
        return getPendingItemOperationalFactor(item);
    }

    function convertSelectedQuantityToCanonicalBase(item, quantity, unitCode) {
        const rawQuantity = Number(quantity || 0);
        if (!Number.isFinite(rawQuantity) || rawQuantity <= 0) {
            return 0;
        }
        return rawQuantity * getSelectedUnitFactorBase(item, unitCode);
    }

    function convertSelectedQuantityToOperationalUnit(item, quantity, unitCode) {
        const canonicalBase = convertSelectedQuantityToCanonicalBase(item, quantity, unitCode);
        const operationalFactor = getPendingItemOperationalFactor(item);
        if (!(canonicalBase > 0) || !(operationalFactor > 0)) {
            return canonicalBase;
        }
        return canonicalBase / operationalFactor;
    }

    function formatCurrencyBR(value) {
        const numericValue = Number(value || 0);
        if (!Number.isFinite(numericValue)) {
            return '';
        }
        return numericValue.toLocaleString('pt-BR', {
            style: 'currency',
            currency: 'BRL'
        });
    }

    function getPendingItemFinancialReference(item) {
        const reference = item && (item.valorReferencia || item.valor_referencia);
        if (!reference || typeof reference !== 'object') {
            return {
                hasValue: false,
                unitPriceBase: 0,
                unitPriceDisplay: '',
                unitPriceDisplayFull: '',
                sourceLabel: ''
            };
        }

        const unitPriceBase = Number(reference.valor_unitario_base || 0);
        return {
            hasValue: Number.isFinite(unitPriceBase) && unitPriceBase > 0,
            unitPriceBase: Number.isFinite(unitPriceBase) && unitPriceBase > 0 ? unitPriceBase : 0,
            unitPriceDisplay: String(reference.valor_unitario_display || '').trim(),
            unitPriceDisplayFull: String(reference.valor_unitario_display_full || '').trim(),
            sourceLabel: String(reference.origem_label || '').trim(),
        };
    }

    function buildPendingItemConversionDisplay(item, quantity, unitCode) {
        const rawQuantity = Number(quantity || 0);
        if (!Number.isFinite(rawQuantity) || rawQuantity <= 0 || !item) {
            return '';
        }

        const normalizedUnit = normalizeFractionUnitCode(unitCode);
        const operationalQuantity = convertSelectedQuantityToOperationalUnit(item, rawQuantity, normalizedUnit);
        const baseDisplay = formatDecimal(operationalQuantity) + ' ' + String(item.displayUnit || getSelectedUnitBadge(normalizedUnit) || 'un');
        const packageCapacity = Number(item.packageCapacity || 0);
        if (packageCapacity > 0 && operationalQuantity > 0) {
            const packageQuantity = operationalQuantity / packageCapacity;
            if (Number.isFinite(packageQuantity) && packageQuantity > 0 && Math.abs(packageQuantity - Math.round(packageQuantity)) > 0.000001) {
                return baseDisplay + ' = ' + formatDecimal(packageQuantity) + ' ' + pluralizePackage(packageQuantity, String(item.packageName || 'embalagem'), String(item.packagePlural || 'embalagens'));
            }
        }

        const originalDisplay = formatDecimal(rawQuantity) + ' ' + getSelectedUnitBadge(normalizedUnit);
        return originalDisplay !== baseDisplay ? (originalDisplay + ' = ' + baseDisplay) : '';
    }

    function buildPendingItemFinancialSummary(item, quantity, unitCode) {
        if (!item) {
            return null;
        }

        const rawQuantity = Number(quantity || 0);
        if (!Number.isFinite(rawQuantity) || rawQuantity <= 0) {
            return null;
        }

        const reference = getPendingItemFinancialReference(item);
        const quantityBase = convertSelectedQuantityToCanonicalBase(item, rawQuantity, unitCode);
        const conversionDisplay = buildPendingItemConversionDisplay(item, rawQuantity, unitCode);
        if (!reference.hasValue || !(quantityBase > 0)) {
            return conversionDisplay
                ? {
                    totalDisplay: '',
                    detailDisplay: conversionDisplay,
                    sourceLabel: '',
                }
                : null;
        }

        const totalValue = reference.unitPriceBase * quantityBase;
        if (!(totalValue > 0)) {
            return conversionDisplay
                ? {
                    totalDisplay: '',
                    detailDisplay: conversionDisplay,
                    sourceLabel: '',
                }
                : null;
        }

        return {
            totalDisplay: formatCurrencyBR(totalValue),
            detailDisplay: conversionDisplay || reference.unitPriceDisplay || '',
            sourceLabel: reference.sourceLabel,
        };
    }

    function buildPendingItemFromInfo(codigo, data, baseItem) {
        const currentItem = baseItem || {};
        return {
            ...currentItem,
            codigo: data.codigo || codigo,
            descricao: data.descricao || codigo,
            categoria: data.categoria || currentItem.categoria || '',
            marca: data.marca || currentItem.marca || '',
            unidade: data.nome_embalagem || data.unidade || currentItem.unidade || 'un',
            usuario: String(currentItem.usuario || inputUsuario.value || '').trim(),
            local: String(currentItem.local || inputLocal.value || '').trim(),
            defaultFractionUnit: normalizeFractionUnitCode(data.fracao_unidade_padrao || currentItem.defaultFractionUnit || ''),
            totalBase: Number(data.saldo_total_fracionado ?? data.saldo ?? currentItem.totalBase ?? 0),
            saldo: data.saldo,
            saldo_display: data.saldo_display || currentItem.saldo_display || '',
            displayUnit: String(data.unidade_exibicao_total || currentItem.displayUnit || 'L'),
            packageCapacity: Number(data.capacidade_embalagem || currentItem.packageCapacity || 0),
            packageName: String(data.nome_embalagem || currentItem.packageName || 'embalagem'),
            packagePlural: String(data.nome_embalagem_plural || currentItem.packagePlural || 'embalagens'),
            fotoUrl: data.foto_url || currentItem.fotoUrl || currentItem.foto_url || null,
            foto_url: data.foto_url || currentItem.fotoUrl || currentItem.foto_url || null,
            valorReferencia: data.valor_referencia || currentItem.valorReferencia || currentItem.valor_referencia || null,
            valor_referencia: data.valor_referencia || currentItem.valorReferencia || currentItem.valor_referencia || null,
            unitFactorBase: Number(data.devolucao_unidade_fator_base || currentItem.unitFactorBase || 1),
            fracaoFatoresBase: data.fracao_fatores_base || currentItem.fracaoFatoresBase || currentItem.fracao_fatores_base || {},
            fracao_fatores_base: data.fracao_fatores_base || currentItem.fracaoFatoresBase || currentItem.fracao_fatores_base || {},
            _fractionalInfoLoaded: true,
        };
    }

    async function fetchFractionalItemInfo(codigo) {
        const rawCodigo = String(codigo || '').trim();
        if (!rawCodigo) {
            throw new Error('Informe o código do item');
        }

        const params = new URLSearchParams();
        const identificador = String(inputUsuario.dataset.matricula || inputUsuario.value || '').trim();
        if (identificador) {
            params.set('usuario', identificador);
        }

        const response = await window.galintFetchWithAuth(
            '/movimentos/item-info/' + encodeURIComponent(rawCodigo) + (params.toString() ? ('?' + params.toString()) : ''),
            undefined,
            'Sua sessão expirou ao consultar o item. Faça login novamente.'
        );
        const data = await response.json();
        if (!response.ok || !data || !data.found || !data.descricao) {
            throw new Error('Item não encontrado');
        }
        return data;
    }

    async function hydratePendingItemPreview(codigo, options) {
        const extraOptions = options || {};
        const rawCodigo = String(codigo || '').trim();
        if (!rawCodigo) {
            return null;
        }

        const requestId = ++itemPreviewRequestId;
        try {
            const data = await fetchFractionalItemInfo(rawCodigo);
            if (requestId !== itemPreviewRequestId || String(inputCodigo.value || '').trim() !== rawCodigo) {
                return null;
            }
            pendingItem = buildPendingItemFromInfo(rawCodigo, data, extraOptions.baseItem || pendingItem || {});
            renderCurrentPreview(pendingItem, extraOptions.status || 'preview');
            return pendingItem;
        } catch (error) {
            if (!extraOptions.silent && !(error && error.isAuthRedirect)) {
                throw error;
            }
            return null;
        }
    }

    function buildMirrorPayload(status, item, extra) {
        const actor = String((item && item.usuario) || inputUsuario.value || '').trim();
        const local = String((item && item.local) || inputLocal.value || '').trim();
        const operationalContext = getOperationalContext();
        const unidade = getSelectedUnitCode();
        const quantidadeAtual = extra && extra.quantidade != null ? extra.quantidade : parseFloat(modalQuantidadeInput.value || '0');
        const quantidadeDisplay = quantidadeAtual && quantidadeAtual > 0
            ? formatDecimal(quantidadeAtual) + ' ' + getSelectedUnitBadge(unidade)
            : '--';
        const financialSummary = item ? buildPendingItemFinancialSummary(item, quantidadeAtual, unidade) : null;
        const payload = {
            kind: 'fracionada',
            kind_label: 'Saida fracionada',
            status: status,
            generated_at: new Date().toISOString(),
            source_label: 'saida fracionada',
            batch_label: 'retirada pesada em balanca',
            actor: {
                nome: actor,
            },
            context: {
                local_servico: local,
                atividade_operacional: operationalContext.atividade_label || operationalContext.atividade_operacional,
                ordem_servico: operationalContext.ordem_servico,
                centro_custo: operationalContext.centro_custo,
            },
        };

        if (item) {
            payload.item = {
                codigo: item.codigo || '',
                descricao: item.descricao || item.codigo || '',
                categoria: item.categoria || '',
                marca: item.marca || '',
                foto_url: item.fotoUrl || item.foto_url || '',
                saldo: item.totalBase,
                saldo_display: String(item.saldo_display || '').trim() || (formatDecimal(item.totalBase || 0) + ' ' + String(item.displayUnit || 'L')),
                financial: financialSummary ? {
                    valor_total_display: financialSummary.totalDisplay || '',
                    valor_detalhe_display: financialSummary.detailDisplay || '',
                    valor_origem_label: financialSummary.sourceLabel || '',
                } : null,
            };
            payload.movement = {
                quantidade: quantidadeAtual || null,
                quantidade_display: quantidadeDisplay,
                valor_total_display: financialSummary?.totalDisplay || '',
                valor_detalhe_display: financialSummary?.detailDisplay || '',
            };
        }

        return payload;
    }

    function renderCurrentPreview(item, status, publishState, extra) {
        const previewStatus = status || (item ? 'preview' : 'idle');
        const shouldPublish = publishState !== false;
        if (!currentItemPreview) return;
        if (!item) {
            currentItemPreview.className = 'operation-preview is-empty';
            currentItemPreview.innerHTML = '' +
                '<div class="operation-preview-body">' +
                    '<span class="operation-preview-eyebrow"><i class="bi bi-display"></i> Painel operacional</span>' +
                    '<div class="operation-preview-placeholder">' +
                        '<i class="bi bi-droplet-half"></i>' +
                        '<div><strong>Nenhum item fracionado em foco</strong><div class="operation-preview-note">Selecione um item para exibir foto, saldo total e contexto da retirada fracionada.</div></div>' +
                    '</div>' +
                '</div>';
            if (shouldPublish) {
                publishMirrorState(buildMirrorPayload(previewStatus, null, extra));
            }
            return;
        }

        const unidade = getSelectedUnitCode();
        const operationalContext = getOperationalContext();
        const quantidadeAtual = extra && extra.quantidade != null ? extra.quantidade : parseFloat(modalQuantidadeInput.value || '0');
        const quantidadeDisplay = quantidadeAtual && quantidadeAtual > 0
            ? formatDecimal(quantidadeAtual) + ' ' + getSelectedUnitBadge(unidade)
            : 'Aguardando pesagem';
        const saldoDisplay = String(item.saldo_display || '').trim() || (formatDecimal(item.totalBase || 0) + ' ' + String(item.displayUnit || 'L'));
        const financialSummary = buildPendingItemFinancialSummary(item, quantidadeAtual, unidade);
        const usuarioDisplay = String(item.usuario || inputUsuario.value || '').trim() || 'Nao informado';
        const localDisplay = String(item.local || inputLocal.value || '').trim() || 'Nao informado';
        const eyebrowLabel = previewStatus === 'completed'
            ? '<i class="bi bi-check2-circle"></i> Ultima retirada registrada'
            : '<i class="bi bi-droplet-half"></i> Retirada pesada';
        const financialStatHtml = financialSummary && financialSummary.totalDisplay
            ? '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Valor estimado</span><span class="operation-preview-stat-value">' + escapeHtml(financialSummary.totalDisplay) + '</span></div>'
            : '';
        const previewNoteParts = [
            previewStatus === 'completed'
                ? 'Ultima retirada registrada. Confira a pesagem antes de iniciar a proxima operacao.'
                : 'Use a balanca para informar o valor real retirado na unidade operacional exibida.'
        ];
        if (financialSummary && financialSummary.detailDisplay) {
            previewNoteParts.push((financialSummary.totalDisplay ? 'Conversao: ' : 'Equivalencia: ') + financialSummary.detailDisplay + '.');
        }
        if (financialSummary && financialSummary.sourceLabel && financialSummary.totalDisplay) {
            previewNoteParts.push('Referencia de preco: ' + financialSummary.sourceLabel + '.');
        }
        const previewNote = previewNoteParts.join(' ').trim();
        const fotoHtml = item.fotoUrl || item.foto_url
            ? '<img src="' + escapeHtml(item.fotoUrl || item.foto_url) + '" alt="' + escapeHtml(item.descricao || item.codigo || 'Item fracionado') + '">'
            : '<div class="operation-preview-placeholder"><i class="bi bi-image"></i><div>Sem foto do item</div></div>';

        currentItemPreview.className = 'operation-preview';
        currentItemPreview.innerHTML = '' +
            '<div class="operation-preview-media">' + fotoHtml + '</div>' +
            '<div class="operation-preview-body">' +
                '<span class="operation-preview-eyebrow">' + eyebrowLabel + '</span>' +
                '<div>' +
                    '<h3 class="operation-preview-title">' + escapeHtml(item.descricao || item.codigo || 'Item') + '</h3>' +
                    '<div class="operation-preview-subtitle">Codigo ' + escapeHtml(item.codigo || '—') + (item.categoria ? ' • ' + escapeHtml(item.categoria) : '') + (item.marca ? ' • ' + escapeHtml(item.marca) : '') + '</div>' +
                '</div>' +
                '<div class="operation-preview-grid">' +
                    '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Quantidade</span><span class="operation-preview-stat-value">' + escapeHtml(quantidadeDisplay) + '</span></div>' +
                    '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Saldo total</span><span class="operation-preview-stat-value">' + escapeHtml(saldoDisplay) + '</span></div>' +
                    financialStatHtml +
                    '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Colaborador</span><span class="operation-preview-stat-value">' + escapeHtml(usuarioDisplay) + '</span></div>' +
                    '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Local</span><span class="operation-preview-stat-value">' + escapeHtml(localDisplay) + '</span></div>' +
                    '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Atividade</span><span class="operation-preview-stat-value">' + escapeHtml(operationalContext.atividade_label || 'Nao informada') + '</span></div>' +
                    '<div class="operation-preview-stat"><span class="operation-preview-stat-label">OS / Centro de custo</span><span class="operation-preview-stat-value">' + escapeHtml([operationalContext.ordem_servico, operationalContext.centro_custo].filter(Boolean).join(' • ') || 'Nao informado') + '</span></div>' +
                '</div>' +
                '<div class="operation-preview-note">' + escapeHtml(previewNote) + '</div>' +
            '</div>';
        if (shouldPublish) {
            publishMirrorState(buildMirrorPayload(previewStatus, item, extra));
        }
    }
    
    // Atualizar display da unidade selecionada
    function atualizarUnidadeModal() {
        const unidadeSelecionada = document.querySelector('input[name="unidade-tipo"]:checked').value;
        modalQuantidadeUnidade.textContent = getSelectedUnitBadge(unidadeSelecionada);
        if (unidadeSelecionada === 'kg') {
            hintUnidade.textContent = 'ou LITRO';
        } else if (unidadeSelecionada === 'litro') {
            hintUnidade.textContent = 'ou KG';
        } else if (unidadeSelecionada === 'metro') {
            hintUnidade.textContent = 'ou CM';
        } else {
            hintUnidade.textContent = 'ou METRO';
        }
        atualizarResumoRetirada();
        if (pendingItem) {
            renderCurrentPreview(pendingItem, 'preview');
        }
    }

    function formatDecimal(value) {
        const number = Number(value || 0);
        if (!Number.isFinite(number)) return '0';
        return number.toLocaleString('pt-BR', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 3
        });
    }

    function pluralizePackage(count, singular, plural) {
        return Math.abs(Number(count || 0) - 1) < 0.000001 ? singular : plural;
    }

    function buildRestanteEmbalagens(item, remainingBase) {
        const capacidade = Number(item.packageCapacity || 0);
        const singular = String(item.packageName || 'embalagem');
        const plural = String(item.packagePlural || 'embalagens');
        const unidade = String(item.displayUnit || 'L');

        if (!(capacidade > 0)) {
            return formatDecimal(Math.max(0, remainingBase)) + ' ' + unidade;
        }

        const embalagensInteiras = Math.floor(Math.max(0, remainingBase) / capacidade + 0.0000001);
        const sobra = Math.max(0, remainingBase - (embalagensInteiras * capacidade));

        if (embalagensInteiras <= 0 && sobra <= 0.000001) {
            return 'Sem saldo restante';
        }
        if (embalagensInteiras > 0 && sobra > 0.000001) {
            const looseSuffix = Math.abs(sobra - 1) < 0.000001 ? 'solto' : 'soltos';
            return formatDecimal(embalagensInteiras) + ' ' + pluralizePackage(embalagensInteiras, singular, plural) + ' + ' + formatDecimal(sobra) + ' ' + unidade + ' ' + looseSuffix;
        }
        if (embalagensInteiras > 0) {
            return formatDecimal(embalagensInteiras) + ' ' + pluralizePackage(embalagensInteiras, singular, plural);
        }
        const looseSuffix = Math.abs(sobra - 1) < 0.000001 ? 'solto' : 'soltos';
        return formatDecimal(sobra) + ' ' + unidade + ' ' + looseSuffix;
    }

    function atualizarResumoRetirada() {
        if (!pendingItem) {
            modalSaldoRestante.textContent = '-';
            modalRestanteEmbalagens.textContent = '-';
            modalLiveSummary.classList.remove('invalid');
            modalSummaryWarning.classList.remove('show');
            btnConfirmarQuantidade.disabled = false;
            return;
        }

        const retirado = parseFloat(modalQuantidadeInput.value || '0');
        const saldoTotal = Number(pendingItem.totalBase || 0);
    const remainingBase = saldoTotal - convertSelectedQuantityToOperationalUnit(pendingItem, retirado, getSelectedUnitCode());
        const displayUnit = String(pendingItem.displayUnit || 'L');
        const isInvalid = remainingBase < -0.000001;

        modalSaldoRestante.textContent = formatDecimal(Math.max(0, remainingBase)) + ' ' + displayUnit;
        modalRestanteEmbalagens.textContent = buildRestanteEmbalagens(pendingItem, remainingBase);
        modalLiveSummary.classList.toggle('invalid', isInvalid);
        modalSummaryWarning.classList.toggle('show', isInvalid);
        renderCurrentPreview(pendingItem, 'preview', true, { quantidade: Number.isFinite(retirado) ? retirado : 0 });

        if (isInvalid) {
            btnConfirmarQuantidade.disabled = true;
        } else if (CAN_MANAGE) {
            btnConfirmarQuantidade.disabled = false;
        }
    }

    function mostrarPlaceholderFoto() {
        modalItemPhoto.removeAttribute('src');
        modalItemPhoto.classList.remove('show');
        modalItemPhotoEmpty.classList.remove('hide');
    }

    function exibirFotoItem(url) {
        if (!url) {
            mostrarPlaceholderFoto();
            return;
        }

        modalItemPhoto.onload = function() {
            modalItemPhoto.classList.add('show');
            modalItemPhotoEmpty.classList.add('hide');
        };

        modalItemPhoto.onerror = function() {
            mostrarPlaceholderFoto();
        };

        modalItemPhoto.src = url + (url.includes('?') ? '&' : '?') + 'v=' + Date.now();
    }
    
    radioKg.addEventListener('change', atualizarUnidadeModal);
    radioLitro.addEventListener('change', atualizarUnidadeModal);
    radioMetro.addEventListener('change', atualizarUnidadeModal);
    radioCentimetro.addEventListener('change', atualizarUnidadeModal);
    
    const dropdownUsuario = document.getElementById('autocomplete-dropdown-usuario');
    const dropdownCodigo = document.getElementById('autocomplete-dropdown-codigo');
    let debounceTimerUsuario = null;
    let debounceTimerCodigo = null;
    let itemSearchRequestId = 0;
    let currentFuncionarios = [];
    let currentItens = [];
    
    // Autocomplete de usuário
    inputUsuario.addEventListener('input', function() {
        const query = this.value.trim();
        clearTimeout(debounceTimerUsuario);
        
        if (query.length < 1) {
            dropdownUsuario.classList.remove('show');
            return;
        }
        
        debounceTimerUsuario = setTimeout(() => {
            const normalizedQuery = normalizeAutocompleteText(query);
            currentFuncionarios = usuariosAutocompleteData.filter(func => {
                const nome = normalizeAutocompleteText(func.nome);
                const matricula = normalizeAutocompleteText(func.matricula);
                return nome.includes(normalizedQuery) || matricula.includes(normalizedQuery);
            }).slice(0, 20);

            showAutocompleteUsuario(currentFuncionarios);
        }, 150);
    });
    
    function showAutocompleteUsuario(funcionarios) {
        if (funcionarios.length === 0) {
            dropdownUsuario.classList.remove('show');
            return;
        }
        
        dropdownUsuario.innerHTML = funcionarios.map((func, index) => {
            return '<div class=\"autocomplete-item\" data-index=\"' + index + '\">' +
                '<div class=\"autocomplete-item-title\">' + func.nome + '</div>' +
                '<div class=\"autocomplete-item-details\">Matrícula: ' + func.matricula +
                (func.setor ? ' | Setor: ' + func.setor : '') +
                (func.cargo ? ' | Cargo: ' + func.cargo : '') + '</div>' +
                '</div>';
        }).join('');
        
        dropdownUsuario.classList.add('show');
        
        dropdownUsuario.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('click', function() {
                const index = parseInt(this.getAttribute('data-index'));
                selectUsuario(currentFuncionarios[index]);
            });
        });
    }
    
    function selectUsuario(func) {
        inputUsuario.value = func.nome + ' — ' + func.matricula;
        inputUsuario.dataset.matricula = func.matricula;
        dropdownUsuario.classList.remove('show');
        if (pendingItem) {
            pendingItem.usuario = String(inputUsuario.value || '').trim();
            renderCurrentPreview(pendingItem, 'preview');
        }
        if (!inputLocal.value) {
            inputLocal.focus();
        } else {
            inputCodigo.focus();
        }
        updateButtonState();
    }
    
    // Keyboard navigation para usuário
    inputUsuario.addEventListener('keydown', function(e) {
        const items = dropdownUsuario.querySelectorAll('.autocomplete-item');
        const activeItem = dropdownUsuario.querySelector('.autocomplete-item.active');
        let currentIndex = -1;
        
        if (activeItem) {
            currentIndex = Array.from(items).indexOf(activeItem);
        }
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (currentIndex < items.length - 1) {
                setActiveItem(items, currentIndex + 1);
            }
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (currentIndex > 0) {
                setActiveItem(items, currentIndex - 1);
            }
        } else if (e.key === 'Enter' && activeItem) {
            e.preventDefault();
            const index = parseInt(activeItem.getAttribute('data-index'));
            selectUsuario(currentFuncionarios[index]);
        } else if (e.key === 'Escape') {
            dropdownUsuario.classList.remove('show');
        }
    });
    
    // Autocomplete de código
    inputCodigo.addEventListener('input', function() {
        const query = this.value.trim();
        clearTimeout(debounceTimerCodigo);
        
        if (query.length < 1) {
            dropdownCodigo.classList.remove('show');
            if (!pendingItem) {
                renderCurrentPreview(null, 'idle');
            }
            return;
        }
        
        debounceTimerCodigo = setTimeout(async () => {
            const requestId = ++itemSearchRequestId;
            try {
                currentItens = await fetchItemSuggestions(query);
                if (requestId !== itemSearchRequestId) {
                    return;
                }
                showAutocompleteCodigo(currentItens);
            } catch (error) {
                if (error && error.isAuthRedirect) {
                    return;
                }
                console.error('Erro ao buscar itens:', error);
                if (requestId === itemSearchRequestId) {
                    currentItens = [];
                    dropdownCodigo.classList.remove('show');
                }
            }
        }, 150);
    });
    
    function formatarSaldoItem(item) {
        try {
            if (!item || item.saldo === undefined || item.saldo === null) return '';
            
            const saldo = parseFloat(item.saldo) || 0;
            const tipoEmbalagem = String(item.tipo_embalagem_novo || '').trim().toLowerCase();
            const unidadesPorEmb = parseFloat(item.unidades_por_embalagem) || 0;
            const grandezaRef = parseFloat(item.grandeza_referencia) || 0;
            const litrosPorEmb = parseFloat(item.litros_por_embalagem) || 0;
            
            // Se tem embalagem com unidades_por_embalagem
            if (tipoEmbalagem && unidadesPorEmb > 0) {
                const qtdEmbalagens = Math.floor(saldo / unidadesPorEmb);
                const unidadesSoltas = saldo - (qtdEmbalagens * unidadesPorEmb);
                const plural = (qtdEmbalagens !== 1 ? 's' : '');

                let unidadeSolta = 'un';
                if (litrosPorEmb > 0) {
                    unidadeSolta = 'L';
                } else if (grandezaRef > 0 && (tipoEmbalagem === 'balde' || tipoEmbalagem === 'bombona' || tipoEmbalagem === 'lata')) {
                    unidadeSolta = 'kg';
                } else if (tipoEmbalagem === 'rolo') {
                    unidadeSolta = 'm';
                }

                if (qtdEmbalagens > 0) {
                    if (unidadesSoltas > 0.000001) {
                        const soltaTxt = (unidadeSolta === 'un') ? Math.round(unidadesSoltas) : unidadesSoltas.toFixed(2);
                        const looseSuffix = Math.abs(unidadesSoltas - 1) <= 0.000001 ? 'solto' : 'soltos';
                        return qtdEmbalagens + ' ' + tipoEmbalagem + plural + ' + ' + soltaTxt + ' ' + unidadeSolta + ' ' + looseSuffix;
                    }
                    return qtdEmbalagens + ' ' + tipoEmbalagem + plural;
                }

                const totalTxt = (unidadeSolta === 'un') ? Math.round(saldo) : saldo.toFixed(2);
                const looseSuffix = Math.abs(saldo - 1) <= 0.000001 ? 'solto' : 'soltos';
                return totalTxt + ' ' + unidadeSolta + ' ' + looseSuffix;
            }
            
            // Fallback: mostra saldo com unidade genérica
            return Math.round(saldo) + ' un';
        } catch (e) {
            console.error('Erro ao formatar saldo:', e);
            return item.saldo_display ? String(item.saldo_display) : (item.saldo ? String(item.saldo) : '');
        }
    }
    
    function showAutocompleteCodigo(itens) {
        if (itens.length === 0) {
            dropdownCodigo.classList.remove('show');
            return;
        }
        
        dropdownCodigo.innerHTML = itens.map((item, index) => {
            const saldoFormatado = formatarSaldoItem(item);
            return '<div class=\"autocomplete-item\" data-index=\"' + index + '\">' +
                '<div class=\"autocomplete-item-title\">' + (item.descricao || item.codigo) + '</div>' +
                '<div class=\"autocomplete-item-details\">' +
                '<span class=\"autocomplete-item-code\">Código: ' + item.codigo + '</span>' +
                (saldoFormatado ? ' | Saldo: ' + saldoFormatado : '') +
                (item.categoria ? ' | Categoria: ' + item.categoria : '') +
                (item.marca ? ' | Marca: ' + item.marca : '') + '</div>' +
                '</div>';
        }).join('');
        
        dropdownCodigo.classList.add('show');
        
        dropdownCodigo.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('click', function() {
                const index = parseInt(this.getAttribute('data-index'));
                selectCodigo(currentItens[index]);
            });
        });
    }
    
    function selectCodigo(item) {
        inputCodigo.value = item.codigo;
        inputCodigo.dataset.descricao = item.descricao;
        inputCodigo.dataset.unidade = item.unidade;
        dropdownCodigo.classList.remove('show');
        pendingItem = {
            ...pendingItem,
            codigo: item.codigo,
            descricao: item.descricao || item.codigo,
            categoria: item.categoria,
            marca: item.marca,
            saldo: item.saldo,
            saldo_display: item.saldo_display,
            usuario: String(inputUsuario.value || '').trim(),
            local: String(inputLocal.value || '').trim(),
            foto_url: item.foto_url,
            fotoUrl: item.foto_url,
        };
        renderCurrentPreview(pendingItem, 'preview');
        hydratePendingItemPreview(item.codigo, { baseItem: pendingItem, silent: true });
        updateButtonState();
    }
    
    // Keyboard navigation para código
    inputCodigo.addEventListener('keydown', function(e) {
        const items = dropdownCodigo.querySelectorAll('.autocomplete-item');
        const activeItem = dropdownCodigo.querySelector('.autocomplete-item.active');
        let currentIndex = -1;
        
        if (activeItem) {
            currentIndex = Array.from(items).indexOf(activeItem);
        }
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (currentIndex < items.length - 1) {
                setActiveItem(items, currentIndex + 1);
            }
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (currentIndex > 0) {
                setActiveItem(items, currentIndex - 1);
            }
        } else if (e.key === 'Enter' && activeItem) {
            e.preventDefault();
            const index = parseInt(activeItem.getAttribute('data-index'));
            selectCodigo(currentItens[index]);
        } else if (e.key === 'Escape') {
            dropdownCodigo.classList.remove('show');
        }
    });
    
    function setActiveItem(items, index) {
        items.forEach(item => item.classList.remove('active'));
        if (items[index]) {
            items[index].classList.add('active');
            items[index].scrollIntoView({ block: 'nearest' });
        }
    }
    
    // Fechar dropdowns ao clicar fora
    document.addEventListener('click', function(e) {
        if (e.target !== inputUsuario && !dropdownUsuario.contains(e.target)) {
            dropdownUsuario.classList.remove('show');
        }
        if (e.target !== inputCodigo && !dropdownCodigo.contains(e.target)) {
            dropdownCodigo.classList.remove('show');
        }
    });
    
    function updateButtonState() {
        if (!CAN_MANAGE) {
            btnRegistrar.disabled = true;
            return;
        }
        const hasUsuario = inputUsuario.value.trim() && inputUsuario.dataset.matricula;
        const hasCodigo = inputCodigo.value.trim();
        btnRegistrar.disabled = !(hasUsuario && hasCodigo);
    }
    
    inputUsuario.addEventListener('input', updateButtonState);
    inputCodigo.addEventListener('input', updateButtonState);
    
    btnRegistrar.addEventListener('click', async function() {
        if (!CAN_MANAGE) {
            alert('Seu usuário não tem permissão para registrar saídas. Solicite acesso de administrador.');
            return;
        }
        const usuario = inputUsuario.value.trim();
        const local = inputLocal.value.trim();
        const codigo = inputCodigo.value.trim();
        
        if (!usuario) {
            alert('Informe o crachá/matrícula');
            inputUsuario.focus();
            return;
        }
        
        if (!codigo) {
            alert('Informe o código do item');
            inputCodigo.focus();
            return;
        }
        
        // Buscar informações do item
        btnRegistrar.disabled = true;
        btnRegistrar.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Buscando...';
        
        try {
            const data = await fetchFractionalItemInfo(codigo);
            if (!data.permite_saida_fracionada) {
                alert('Este item não requer saída fracionada. Use a tela de "Registro de Saída" normal.');
                inputCodigo.value = '';
                inputCodigo.focus();
                return;
            }

            pendingItem = buildPendingItemFromInfo(codigo, data, {
                ...pendingItem,
                codigo: codigo,
                usuario: usuario,
                local: local,
            });
            renderCurrentPreview(pendingItem, 'preview');
            mostrarModalQuantidade(pendingItem);
        } catch (error) {
            if (error && error.isAuthRedirect) {
                return;
            }
            alert(error.message || 'Erro ao buscar item');
        } finally {
            btnRegistrar.disabled = false;
            btnRegistrar.innerHTML = '<i class="bi bi-check-circle me-2"></i>Registrar Saída';
        }
    });
    
    function mostrarModalQuantidade(item) {
        modalItemDesc.textContent = item.descricao;
        modalItemUnidade.textContent = item.unidade;
        modalQuantidadeInput.value = '';
        modalSaldoTotal.textContent = formatDecimal(item.totalBase) + ' ' + item.displayUnit;
        modalCapacidadeEmbalagem.textContent = item.packageCapacity > 0
            ? formatDecimal(item.packageCapacity) + ' ' + item.displayUnit + ' por ' + item.packageName
            : '-';

        exibirFotoItem(item.fotoUrl);
        
        const defaultUnit = normalizeFractionUnitCode(item.defaultFractionUnit || '');
        configureFractionUnitOptions(defaultUnit, item);
        atualizarUnidadeModal();
        atualizarResumoRetirada();
        
        modalQuantidade.show();
        
        // Foco no input quando modal abre
        document.getElementById('modalQuantidade').addEventListener('shown.bs.modal', function() {
            modalQuantidadeInput.focus();
        }, { once: true });
    }
    
    btnConfirmarQuantidade.addEventListener('click', async function() {
        if (!CAN_MANAGE) {
            alert('Seu usuário não tem permissão para registrar saídas. Solicite acesso de administrador.');
            return;
        }
        const quantidade = parseFloat(modalQuantidadeInput.value);
        
        if (!quantidade || quantidade <= 0) {
            alert('Informe uma quantidade válida maior que zero');
            modalQuantidadeInput.focus();
            return;
        }

        if (pendingItem && quantidade > Number(pendingItem.totalBase || 0)) {
            alert('A retirada informada excede o saldo disponível do item.');
            modalQuantidadeInput.focus();
            return;
        }
        
        // Capturar unidade selecionada
        const unidadeSelecionada = document.querySelector('input[name="unidade-tipo"]:checked').value;
        
        // Desabilitar botão durante processamento
        btnConfirmarQuantidade.disabled = true;
        btnConfirmarQuantidade.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processando...';
        
        try {
            // Enviar via AJAX usando FormData
            const formData = new FormData();
            formData.append('usuario', pendingItem.usuario);
            formData.append('local_servico', pendingItem.local);
            formData.append('codigo', pendingItem.codigo);
            formData.append('quantidade', quantidade);
            formData.append('unidade_fracionada', unidadeSelecionada); // Adicionar unidade
            const operationalContext = getOperationalContext();
            if (operationalContext.atividade_operacional) {
                formData.append('atividade_operacional', operationalContext.atividade_operacional);
            }
            if (operationalContext.ordem_servico) {
                formData.append('ordem_servico', operationalContext.ordem_servico);
            }
            if (operationalContext.centro_custo) {
                formData.append('centro_custo', operationalContext.centro_custo);
            }
            // Atenção: não usar template string com ${...} aqui, pois o Mako interpreta e quebra a página.
            formData.append('observacao', 'Retirada fracionada: ' + quantidade + ' ' + String(unidadeSelecionada || '').toUpperCase());
            
            const response = await window.galintFetchWithAuth('${url_for("movements.registrar_saida")}', {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: formData
            }, 'Sua sessão expirou antes de concluir a saída fracionada. Faça login novamente.');
            
            if (response.ok) {
                const data = await response.json();
                const completedSnapshot = pendingItem ? {
                    ...pendingItem,
                    usuario: String(pendingItem.usuario || inputUsuario.value || '').trim(),
                    local: String(pendingItem.local || inputLocal.value || '').trim(),
                } : null;
                
                // Sucesso - fechar modal e limpar campos
                modalQuantidade.hide();
                
                // Mostrar mensagem de sucesso
                alert(data.message || 'Saída registrada com sucesso!');
                if (completedSnapshot) {
                    publishMirrorState(buildMirrorPayload('completed', completedSnapshot, { quantidade: quantidade }));
                    renderCurrentPreview(completedSnapshot, 'completed', false, { quantidade: quantidade });
                }
                
                // Limpar campos para nova entrada
                inputUsuario.value = '';
                inputUsuario.dataset.matricula = '';
                inputLocal.value = '';
                if (inputAtividadeOperacional) {
                    inputAtividadeOperacional.value = '';
                }
                if (inputOrdemServico) {
                    inputOrdemServico.value = '';
                }
                if (inputCentroCusto) {
                    inputCentroCusto.value = '';
                }
                inputCodigo.value = '';
                btnRegistrar.disabled = true;
                pendingItem = null;
                
                // Focar no campo de usuário para próxima entrada
                inputUsuario.focus();
            } else {
                // Tentar parsear erro como JSON
                try {
                    const errorData = await response.json();
                    alert('Erro: ' + (errorData.error || 'Erro ao registrar saída'));
                } catch {
                    // Se não for JSON, tentar extrair do HTML
                    const text = await response.text();
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(text, 'text/html');
                    const alertElement = doc.querySelector('.alert-danger');
                    const errorMsg = alertElement ? alertElement.textContent.trim() : 'Erro ao registrar saída';
                    alert('Erro: ' + errorMsg);
                }
            }
        } catch (error) {
            if (error && error.isAuthRedirect) {
                return;
            }
            alert('Erro de conexão: ' + error.message);
        } finally {
            btnConfirmarQuantidade.disabled = false;
            btnConfirmarQuantidade.innerHTML = 'Confirmar';
        }
    });
    
    // Enter no modal confirma
    modalQuantidadeInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            btnConfirmarQuantidade.click();
        }
    });

    modalQuantidadeInput.addEventListener('input', atualizarResumoRetirada);

    inputUsuario.addEventListener('blur', function() {
        if (pendingItem) {
            pendingItem.usuario = String(inputUsuario.value || '').trim();
            renderCurrentPreview(pendingItem, 'preview');
        }
    });

    inputLocal.addEventListener('input', function() {
        if (pendingItem) {
            pendingItem.local = String(inputLocal.value || '').trim();
            renderCurrentPreview(pendingItem, 'preview');
        }
    });

    [inputAtividadeOperacional, inputOrdemServico, inputCentroCusto].forEach(function(field) {
        if (!field) return;
        field.addEventListener('input', function() {
            if (pendingItem) {
                renderCurrentPreview(pendingItem, 'preview');
            }
        });
        field.addEventListener('change', function() {
            if (pendingItem) {
                renderCurrentPreview(pendingItem, 'preview');
            }
        });
    });

    inputCodigo.addEventListener('blur', async function() {
        const codigo = String(inputCodigo.value || '').trim();
        if (!codigo) return;
        try {
            const response = await window.galintFetchWithAuth(
                '/movimentos/item-info/' + encodeURIComponent(codigo),
                undefined,
                'Sua sessão expirou ao carregar o preview do item. Faça login novamente.'
            );
            const data = await response.json();
            if (!response.ok || !data || !data.found) return;
            pendingItem = {
                ...pendingItem,
                codigo: data.codigo || codigo,
                descricao: data.descricao || codigo,
                categoria: data.categoria,
                marca: data.marca,
                totalBase: Number(data.saldo_total_fracionado || data.saldo || 0),
                displayUnit: String(data.unidade_exibicao_total || 'L'),
                packageCapacity: Number(data.capacidade_embalagem || 0),
                packageName: String(data.nome_embalagem || 'embalagem'),
                packagePlural: String(data.nome_embalagem_plural || 'embalagens'),
                fotoUrl: data.foto_url || null,
                local: String(inputLocal.value || '').trim(),
            };
            renderCurrentPreview(pendingItem, 'preview');
        } catch (error) {
            if (error && error.isAuthRedirect) {
                return;
            }
            console.error('Erro ao carregar preview fracionado:', error);
        }
    });

    renderCurrentPreview(null, 'idle');
    
    if (window.GalintExpressReturnModal) {
        window.GalintExpressReturnModal.init({
            openButtonId: 'btn-open-express-return',
            modalId: 'modalDevolucaoExpressa',
            authMessageLoad: 'Sua sessão expirou durante a carga da devolução expressa. Faça login novamente.',
            authMessageSubmit: 'Sua sessão expirou antes de concluir a devolução expressa. Faça login novamente.',
            getInitialCollaboratorIdentifier: function() {
                if (inputUsuario.dataset && inputUsuario.dataset.matricula) {
                    return String(inputUsuario.dataset.matricula || '').trim();
                }
                var rawIdentifier = String(inputUsuario.value || '').trim();
                if (!rawIdentifier) {
                    return '';
                }
                if (rawIdentifier.indexOf('—') > -1) {
                    return rawIdentifier.split('—').pop().trim();
                }
                return rawIdentifier;
            },
            buildCollaboratorsUrl: function() {
                return window.GalintExpressReturnModal.buildUrl('${url_for("movements.devolucao_expressa_collaborators_payload")}', {
                    scope: 'fracionada'
                });
            },
            buildItemsUrl: function(collaborator) {
                return window.GalintExpressReturnModal.buildUrl('${url_for("movements.devolucao_expressa_payload")}', {
                    scope: 'fracionada',
                    usuario: collaborator && collaborator.matricula ? collaborator.matricula : ''
                });
            },
            renderItemButtonContent: function(item) {
                var localTexto = String(item.local_servico || '').trim();
                var atividadeTexto = String(item.atividade_operacional || '').trim();
                return '' +
                    '<div class="express-return-item-title">' + escapeHtml(item.descricao || item.codigo || 'Item') + '</div>' +
                    '<div class="express-return-item-meta">' +
                        '<span class="express-return-item-code">Código: ' + escapeHtml(item.codigo || '') + '</span>' +
                        '<span>Retirado hoje: ' + escapeHtml(item.retirado_hoje_display || '-') + '</span>' +
                        '<span>Pendente: ' + escapeHtml(item.pendente_hoje_display || '-') + '</span>' +
                    '</div>' +
                    '<div class="express-return-item-meta">' +
                        '<span>Última saída: ' + escapeHtml(item.ultima_saida_label || 'N/D') + '</span>' +
                        (localTexto ? '<span>Local: ' + escapeHtml(localTexto) + '</span>' : '') +
                        (atividadeTexto ? '<span>Atividade: ' + escapeHtml(atividadeTexto) + '</span>' : '') +
                    '</div>';
            },
            renderDetail: function(context) {
                var item = context.item;
                var unitOptions = Array.isArray(item.devolucao_unidades_opcoes) ? item.devolucao_unidades_opcoes : [];
                var selectedUnitOption = unitOptions.find(function(option) {
                    return String(option && option.unit_code || '') === String(item.devolucao_unidade_codigo || '');
                }) || unitOptions[0] || {};
                var quantityStep = String(selectedUnitOption.input_step || '0.001');
                var quantityMin = String(selectedUnitOption.input_min || quantityStep);
                return '' +
                    '<div class="express-return-detail-title">' + escapeHtml(item.descricao || item.codigo || 'Item') + '</div>' +
                    '<div class="express-return-detail-subtitle">Código ' + escapeHtml(item.codigo || '') + (item.categoria ? ' • ' + escapeHtml(item.categoria) : '') + (item.marca ? ' • ' + escapeHtml(item.marca) : '') + '</div>' +
                    '<div class="express-return-kpis">' +
                        '<div class="express-return-kpi"><span class="express-return-kpi-label">Retirado hoje</span><span class="express-return-kpi-value">' + escapeHtml(item.retirado_hoje_display || '-') + '</span></div>' +
                        '<div class="express-return-kpi"><span class="express-return-kpi-label">Pendente agora</span><span class="express-return-kpi-value">' + escapeHtml(item.pendente_hoje_display || '-') + '</span></div>' +
                    '</div>' +
                    '<div class="row g-3">' +
                        '<div class="col-md-6">' +
                            '<label class="form-label" for="express-return-quantity">Quantidade a devolver</label>' +
                            '<input class="form-control" type="number" id="express-return-quantity" min="' + escapeHtml(quantityMin) + '" step="' + escapeHtml(quantityStep) + '" value="' + escapeHtml(String(item.pendente_hoje || '')) + '">' +
                        '</div>' +
                        '<div class="col-md-6">' +
                            '<label class="form-label" for="express-return-unit">Unidade</label>' +
                            '<input class="form-control" id="express-return-unit" readonly value="' + escapeHtml(item.devolucao_unidade_exibicao || item.devolucao_unidade_codigo || '') + '">' +
                        '</div>' +
                        '<div class="col-12">' +
                            '<label class="form-label" for="express-return-observation">Observação</label>' +
                            '<input class="form-control" id="express-return-observation" value="Devolução expressa via tela fracionada" maxlength="200">' +
                            '<div class="express-return-hint">Se não alterar a quantidade, a devolução vai usar automaticamente todo o pendente mostrado acima.</div>' +
                        '</div>' +
                    '</div>';
            },
            buildSubmitRequest: function(context) {
                var quantityField = context.modalEl.querySelector('#express-return-quantity');
                var observationField = context.modalEl.querySelector('#express-return-observation');
                var quantidade = quantityField ? Number(quantityField.value || 0) : 0;
                var observacao = observationField ? String(observationField.value || '').trim() : '';
                if (!Number.isFinite(quantidade) || quantidade <= 0) {
                    throw new Error('Informe uma quantidade válida para registrar a devolução expressa.');
                }
                return {
                    url: '${url_for("movements.registrar_devolucao_expressa")}',
                    options: {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Accept': 'application/json'
                        },
                        body: JSON.stringify({
                            usuario: context.collaborator && context.collaborator.matricula ? context.collaborator.matricula : '',
                            codigo: context.item && context.item.codigo ? context.item.codigo : '',
                            quantidade: quantidade,
                            from_unit: context.item && context.item.devolucao_unidade_codigo ? context.item.devolucao_unidade_codigo : '',
                            observacao: observacao || 'Devolução expressa via tela fracionada'
                        })
                    }
                };
            },
            messages: {
                initialStatus: 'Abra o painel para carregar os colaboradores com devolução pendente.',
                loadingCollaborators: 'Carregando colaboradores com saídas fracionadas pendentes...',
                loadingItems: 'Carregando itens do colaborador...',
                selectCollaborator: 'Escolha o colaborador para carregar os itens fracionados pendentes.',
                selectCollaboratorFirst: 'Selecione um colaborador acima.',
                selectItem: 'Escolha o item para concluir a devolução expressa.',
                readyToSubmit: 'Revise os dados e confirme a devolução.',
                noCollaborators: 'Nenhum colaborador com saída fracionada pendente foi encontrado hoje.',
                noItems: 'Nenhum item fracionado elegível foi encontrado para este colaborador.',
                emptyDetailTitle: 'Nenhum item selecionado.',
                emptyDetailHint: 'Escolha um item da lista abaixo para liberar a devolução.',
                submitButton: 'Fazer devolução',
                submitBusy: 'Devolvendo...',
                submitSuccess: 'Devolução expressa registrada com sucesso.',
                submitError: 'Falha ao registrar a devolução expressa.'
            }
        });
    }

    // Foco inicial
    inputUsuario.focus();
})();
</script>
</%block>
