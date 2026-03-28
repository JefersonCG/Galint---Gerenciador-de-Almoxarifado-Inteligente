<%inherit file="/base.mako"/>

<%block name="title">Registro de Saída Fracionada</%block>

<%block name="extra_css">
<style>
    .saida-container {
        max-width: 1080px;
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

    .saida-command-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 1rem;
        margin-bottom: 1.35rem;
    }

    .saida-command-card {
        border-radius: 1.15rem;
        border: 1px solid rgba(148, 163, 184, 0.16);
        background: linear-gradient(180deg, rgba(8, 17, 31, 0.98), rgba(15, 27, 45, 0.96));
        padding: 1rem;
        color: #e2e8f0;
        box-shadow: 0 18px 42px rgba(15, 23, 42, 0.18);
    }

    .saida-command-label {
        display: block;
        margin-bottom: 0.45rem;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: rgba(226, 232, 240, 0.68);
    }

    .saida-command-value {
        font-size: 1.2rem;
        font-weight: 700;
        color: #ffffff;
    }

    .saida-command-copy {
        margin: 0.4rem 0 0;
        font-size: 0.84rem;
        color: rgba(226, 232, 240, 0.78);
        line-height: 1.55;
    }

    .workflow-panel {
        border-radius: 1.15rem;
        border: 1px solid rgba(148, 163, 184, 0.16);
        background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(241,245,249,0.96));
        padding: 1.2rem 1.25rem;
        box-shadow: 0 18px 42px rgba(15, 23, 42, 0.08);
        margin-bottom: 1.35rem;
    }

    .workflow-kicker {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.3rem 0.68rem;
        border-radius: 999px;
        border: 1px solid rgba(37, 99, 235, 0.12);
        background: rgba(37, 99, 235, 0.08);
        color: #2563eb;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
    }

    .workflow-title {
        margin: 0.7rem 0 0;
        font-size: 1.05rem;
        font-weight: 800;
        color: #0f172a;
    }

    .workflow-copy {
        margin: 0.4rem 0 0;
        color: #475569;
        font-size: 0.9rem;
        line-height: 1.6;
    }

    .workflow-list {
        margin: 0.85rem 0 0;
        padding-left: 1.05rem;
        color: #334155;
    }

    .workflow-list li + li {
        margin-top: 0.35rem;
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
    
    .input-card .form-control {
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
    
    .input-card .form-control:focus {
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

    .fracionada-modal-shell {
        border-radius: 1.2rem;
        overflow: hidden;
        border: 1px solid rgba(148, 163, 184, 0.16);
        box-shadow: 0 24px 58px rgba(15, 23, 42, 0.28);
        background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(241,245,249,0.96));
    }

    .fracionada-modal-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1rem;
        padding: 1.1rem 1.25rem;
        border-bottom: 1px solid rgba(148, 163, 184, 0.16);
        background: linear-gradient(135deg, rgba(8,17,31,0.98), rgba(15,27,45,0.95) 46%, rgba(37,99,235,0.72) 100%);
        color: #e2e8f0;
    }

    .fracionada-modal-kicker {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.3rem 0.65rem;
        border-radius: 999px;
        border: 1px solid rgba(255,255,255,0.14);
        background: rgba(255,255,255,0.08);
        color: #e2e8f0;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
    }

    .fracionada-modal-title {
        margin: 0.65rem 0 0;
        font-size: 1.08rem;
        font-weight: 700;
    }

    .fracionada-modal-copy {
        margin: 0.35rem 0 0;
        font-size: 0.86rem;
        line-height: 1.55;
        color: rgba(226, 232, 240, 0.82);
    }

    .fracionada-modal-body {
        padding: 1.15rem 1.25rem 1.25rem;
    }

    .fracionada-modal-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.75rem;
        padding: 1rem 1.25rem 1.15rem;
        border-top: 1px solid rgba(148,163,184,0.16);
    }

    @media (max-width: 767px) {
        .saida-shell {
            padding: 1rem;
            border-radius: 22px;
        }

        .page-header {
            padding: 1.35rem 1rem;
            border-radius: 20px;
        }
    }
</style>
</%block>

<%block name="content">
<div class="saida-container">
    <div class="saida-shell">
    <div class="page-header">
        <h2><i class="bi bi-droplet-half me-2"></i>Registro de Saída Fracionada</h2>
        <p>Insira a quantidade pesada com o novo container dark, mantendo o fluxo específico para itens líquidos e fracionados.</p>
    </div>

    <div class="saida-command-grid">
        <div class="saida-command-card">
            <span class="saida-command-label">Tipo</span>
            <div class="saida-command-value">Retirada por pesagem</div>
            <p class="saida-command-copy">Use esta rotina quando a quantidade real depender do valor pesado ou medido no momento da saída.</p>
        </div>
        <div class="saida-command-card">
            <span class="saida-command-label">Unidade</span>
            <div class="saida-command-value">Kg ou litro</div>
            <p class="saida-command-copy">O fluxo já prepara o operador para escolher a unidade correta dentro do modal de confirmação.</p>
        </div>
        <div class="saida-command-card">
            <span class="saida-command-label">Conferência</span>
            <div class="saida-command-value">Saldo em tempo real</div>
            <p class="saida-command-copy">A confirmação mostra saldo restante e leitura estimada da embalagem antes de gravar a baixa.</p>
        </div>
    </div>

    <div class="workflow-panel">
        <span class="workflow-kicker"><i class="bi bi-bezier2"></i> Fluxo guiado</span>
        <h3 class="workflow-title">Operação em três passos</h3>
        <p class="workflow-copy">Primeiro identifique colaborador e local de uso. Depois localize o item. Por fim, confirme no modal a quantidade real retirada e a unidade de medição.</p>
        <ul class="workflow-list">
            <li>Produtos com volume ou massa variável devem sair por esta tela, não pela saída comum.</li>
            <li>O modal final serve como barreira de conferência antes de descontar o saldo.</li>
            <li>O local do serviço permanece registrado para rastreabilidade operacional.</li>
        </ul>
    </div>

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
    </div>
</div>

<!-- Modal de Quantidade Manual -->
<div class="modal fade" id="modalQuantidade" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content fracionada-modal-shell">
            <div class="modal-header fracionada-modal-header">
                <div>
                    <span class="fracionada-modal-kicker"><i class="bi bi-calculator"></i> Conferência final</span>
                    <h5 class="modal-title fracionada-modal-title"><i class="bi bi-calculator me-2"></i>Quantidade Retirada</h5>
                    <p class="fracionada-modal-copy">Confirme a unidade correta, revise o saldo projetado e só então grave a saída fracionada do item.</p>
                </div>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body fracionada-modal-body">
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
                        <label class="btn btn-outline-primary" for="unidade-kg">
                            <i class="bi bi-box me-1"></i>KG
                        </label>
                        <input type="radio" class="btn-check" name="unidade-tipo" id="unidade-litro" value="litro">
                        <label class="btn btn-outline-primary" for="unidade-litro">
                            <i class="bi bi-droplet me-1"></i>LITRO
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
            <div class="modal-footer fracionada-modal-footer">
                <button type="button" class="galint-btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                <button type="button" class="galint-btn-primary" id="btn-confirmar-quantidade">Confirmar</button>
            </div>
        </div>
    </div>
</div>

<form method="post" action="${url_for('movements.registrar_saida')}" id="hidden-form" style="display: none;">
    <input type="hidden" name="usuario" id="hidden-usuario">
    <input type="hidden" name="local_servico" id="hidden-local">
    <input type="hidden" name="codigo" id="hidden-codigo">
    <input type="hidden" name="quantidade" id="hidden-quantidade">
</form>

</%block>

<%block name="scripts">
${parent.scripts()}
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
        const response = await fetch(itemSearchUrl + '?q=' + encodeURIComponent(query), {
            headers: { 'Accept': 'application/json' }
        });
        if (!response.ok) {
            throw new Error('Falha ao buscar itens');
        }
        const data = await response.json();
        return (data.items || data.itens || []).slice(0, 20);
    }
    
    const inputUsuario = document.getElementById('input-usuario');
    const inputLocal = document.getElementById('input-local');
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
    
    // Radio buttons de unidade
    const radioKg = document.getElementById('unidade-kg');
    const radioLitro = document.getElementById('unidade-litro');
    const hintUnidade = document.getElementById('hint-unidade');
    
    // Atualizar display da unidade selecionada
    function atualizarUnidadeModal() {
        const unidadeSelecionada = document.querySelector('input[name="unidade-tipo"]:checked').value;
        modalQuantidadeUnidade.textContent = unidadeSelecionada === 'kg' ? 'kg' : 'L';
        hintUnidade.textContent = unidadeSelecionada === 'kg' ? 'ou LITRO' : 'ou KG';
        atualizarResumoRetirada();
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
            return formatDecimal(embalagensInteiras) + ' ' + pluralizePackage(embalagensInteiras, singular, plural) + ' + ' + formatDecimal(sobra) + ' ' + unidade;
        }
        if (embalagensInteiras > 0) {
            return formatDecimal(embalagensInteiras) + ' ' + pluralizePackage(embalagensInteiras, singular, plural);
        }
        return formatDecimal(sobra) + ' ' + unidade;
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
        const remainingBase = saldoTotal - (Number.isFinite(retirado) ? retirado : 0);
        const displayUnit = String(pendingItem.displayUnit || 'L');
        const isInvalid = remainingBase < -0.000001;

        modalSaldoRestante.textContent = formatDecimal(Math.max(0, remainingBase)) + ' ' + displayUnit;
        modalRestanteEmbalagens.textContent = buildRestanteEmbalagens(pendingItem, remainingBase);
        modalLiveSummary.classList.toggle('invalid', isInvalid);
        modalSummaryWarning.classList.toggle('show', isInvalid);

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
                        return qtdEmbalagens + ' ' + tipoEmbalagem + plural + ' + ' + soltaTxt + ' ' + unidadeSolta;
                    }
                    return qtdEmbalagens + ' ' + tipoEmbalagem + plural;
                }

                const totalTxt = (unidadeSolta === 'un') ? Math.round(saldo) : saldo.toFixed(2);
                return totalTxt + ' ' + unidadeSolta;
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
                (item.categoria ? ' | Categoria: ' + item.categoria : '') + '</div>' +
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
            const response = await fetch('/movimentos/item-info/' + encodeURIComponent(codigo));
            const data = await response.json();
            
            if (!data.found || !data.descricao) {
                throw new Error('Item não encontrado');
            }
            
            if (data.permite_saida_fracionada) {
                // Abre modal para entrada manual
                pendingItem = {
                    codigo: codigo,
                    descricao: data.descricao,
                    unidade: data.nome_embalagem || data.unidade || 'un',
                    usuario: usuario,
                    local: local,
                    defaultFractionUnit: String(data.fracao_unidade_padrao || '').toLowerCase(),
                    totalBase: Number(data.saldo_total_fracionado || data.saldo || 0),
                    displayUnit: String(data.unidade_exibicao_total || 'L'),
                    packageCapacity: Number(data.capacidade_embalagem || 0),
                    packageName: String(data.nome_embalagem || 'embalagem'),
                    packagePlural: String(data.nome_embalagem_plural || 'embalagens'),
                    fotoUrl: data.foto_url || null
                };
                
                mostrarModalQuantidade(pendingItem);
                
            } else {
                // Item não fracionável - não pode usar esta tela
                alert('Este item não requer saída fracionada. Use a tela de "Registro de Saída" normal.');
                inputCodigo.value = '';
                inputCodigo.focus();
            }
            
        } catch (error) {
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
        
        const defaultUnit = String(item.defaultFractionUnit || '').toLowerCase();
        radioKg.checked = defaultUnit !== 'litro';
        radioLitro.checked = defaultUnit === 'litro';
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
            // Atenção: não usar template string com ${...} aqui, pois o Mako interpreta e quebra a página.
            formData.append('observacao', 'Retirada fracionada: ' + quantidade + ' ' + String(unidadeSelecionada || '').toUpperCase());
            
            const response = await fetch('${url_for("movements.registrar_saida")}', {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: formData
            });
            
            if (response.ok) {
                const data = await response.json();
                
                // Sucesso - fechar modal e limpar campos
                modalQuantidade.hide();
                
                // Mostrar mensagem de sucesso
                alert(data.message || 'Saída registrada com sucesso!');
                
                // Limpar campos para nova entrada
                inputUsuario.value = '';
                inputLocal.value = '';
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
    
    // Foco inicial
    inputUsuario.focus();
})();
</script>
</%block>
