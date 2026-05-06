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

<%block name="title">Retirada de Ferramentas</%block>

<%block name="extra_css">
<style>
    @import url('${url_for("static", filename="css/express-return-modal.css")}?v=20260414b');

    .tool-shell {
        background: linear-gradient(180deg, #eef2f7 0%, #f8fafc 100%);
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 30px;
        padding: 1.85rem;
        box-shadow: 0 24px 54px rgba(15, 23, 42, 0.1);
    }

    .page-header {
        position: relative;
        overflow: hidden;
        background: linear-gradient(135deg, #020617 0%, #1e293b 42%, #2563eb 100%);
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
        padding: 2rem;
        box-shadow: 0 22px 48px rgba(15, 23, 42, 0.16);
        margin-bottom: 1.5rem;
        border: 1px solid rgba(148, 163, 184, 0.18);
        position: relative;
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
    }

    .input-card .form-control::placeholder {
        color: #94a3b8;
    }
    
    .input-card .form-control:focus {
        border-color: #3b82f6;
        box-shadow: 0 0 0 0.2rem rgba(37, 99, 235, 0.15);
        background: rgba(15, 23, 42, 0.92);
    }
    
    .btn-submit {
        background: linear-gradient(120deg, #2563eb 0%, #3b82f6 100%);
        border: none;
        border-radius: 8px;
        padding: 1rem 2rem;
        font-weight: 700;
        color: white;
        font-size: 1.1rem;
        transition: all 0.3s ease;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
    }
    
    .btn-submit:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5);
    }
    
    .alert-info-custom {
        background: rgba(245, 158, 11, 0.12);
        border: 1px solid rgba(245, 158, 11, 0.22);
        border-radius: 18px;
        padding: 1rem;
        color: #78350f;
        margin-bottom: 1.5rem;
    }
    
    /* Autocomplete dropdown */
    .autocomplete-dropdown {
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        max-height: 300px;
        overflow-y: auto;
        background: white;
        border: 1px solid #dee2e6;
        border-top: none;
        border-radius: 0 0 8px 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 1000;
        display: none;
    }
    
    .autocomplete-dropdown.show {
        display: block;
    }
    
    .autocomplete-item {
        padding: 0.75rem 1rem;
        cursor: pointer;
        border-bottom: 1px solid #f1f3f5;
        transition: background 0.2s;
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

    .autocomplete-item.is-unavailable {
        background: #fff1f2;
        cursor: not-allowed;
    }

    .autocomplete-item.is-unavailable:hover,
    .autocomplete-item.is-unavailable.active {
        background: #ffe4e6;
    }

    .autocomplete-item.is-unavailable .autocomplete-item-title,
    .autocomplete-item.is-unavailable .autocomplete-item-details,
    .autocomplete-item.is-unavailable .autocomplete-item-code {
        color: #b91c1c;
    }

    .autocomplete-item-status {
        margin-top: 0.35rem;
        font-size: 0.78rem;
        font-weight: 700;
        color: #b91c1c;
    }

    .items-table {
        background: linear-gradient(145deg, #0f172a 0%, #1e293b 100%);
        border-radius: 24px;
        overflow: hidden;
        box-shadow: 0 22px 48px rgba(15, 23, 42, 0.16);
        border: 1px solid rgba(148, 163, 184, 0.18);
        margin-top: 1.25rem;
        margin-bottom: 1rem;
    }

    .items-table-header {
        background: linear-gradient(120deg, #1d4ed8 0%, #38bdf8 100%);
        color: white;
        padding: 1rem 1.5rem;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }

    .total-items-badge {
        background: rgba(255, 255, 255, 0.25);
        padding: 0.35rem 0.75rem;
        border-radius: 20px;
        font-weight: 600;
        margin-left: auto;
    }

    .btn-add-item {
        background: #0d6efd;
        border: none;
        border-radius: 8px;
        padding: 1rem 1.25rem;
        font-weight: 700;
        color: white;
        transition: all 0.2s ease;
        box-shadow: 0 4px 12px rgba(13, 110, 253, 0.2);
    }

    .btn-add-item:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 18px rgba(13, 110, 253, 0.35);
    }

    .btn-new-group {
        background: rgba(148, 163, 184, 0.12);
        border: 1px solid rgba(148, 163, 184, 0.28);
        border-radius: 8px;
        padding: 0.9rem 1.25rem;
        font-weight: 700;
        color: #e2e8f0;
        transition: all 0.2s ease;
    }

    .btn-new-group:hover {
        background: rgba(148, 163, 184, 0.2);
        color: #ffffff;
    }

    .quantity-control {
        display: flex;
        align-items: stretch;
        gap: 0.65rem;
    }

    .quantity-step-btn {
        width: 3.25rem;
        border: 1px solid rgba(148, 163, 184, 0.24);
        border-radius: 16px;
        background: rgba(15, 23, 42, 0.7);
        color: #e2e8f0;
        font-size: 1rem;
        font-weight: 700;
        transition: all 0.2s ease;
        flex: 0 0 auto;
    }

    .quantity-step-btn:hover {
        background: rgba(37, 99, 235, 0.22);
        border-color: rgba(96, 165, 250, 0.55);
        color: #ffffff;
    }

    .quantity-step-btn:focus-visible {
        outline: none;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.22);
    }

    .quantity-input {
        text-align: center;
        font-weight: 700;
        letter-spacing: 0.02em;
    }

    .quantity-hint {
        margin-top: 0.45rem;
        color: rgba(226, 232, 240, 0.72);
        font-size: 0.78rem;
    }

    .btn-remove-item {
        background: #dc3545;
        border: none;
        color: white;
        padding: 0.5rem 0.75rem;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.9rem;
    }

    .btn-remove-item:hover {
        background: #bb2d3b;
    }

    .badge-qty {
        background: rgba(59, 130, 246, 0.16);
        color: #bfdbfe;
        padding: 0.35rem 0.75rem;
        border-radius: 20px;
        font-weight: 700;
        font-size: 0.9rem;
        display: inline-block;
    }

    .item-value-cell {
        min-width: 120px;
    }

    .item-value-total {
        color: #0f172a;
        font-weight: 800;
        font-size: 0.95rem;
    }

    .item-value-detail {
        margin-top: 0.15rem;
        color: #64748b;
        font-size: 0.75rem;
        line-height: 1.3;
    }

    .items-table thead th {
        background: rgba(255, 255, 255, 0.06);
        color: #cbd5e1;
        border-bottom: 1px solid rgba(148, 163, 184, 0.16);
    }

    .items-table tbody td {
        color: #0f172a;
        border-bottom: 1px solid rgba(148, 163, 184, 0.12);
    }

    .items-table tbody tr:not(.group-row) td {
        background: #ffffff;
    }

    .items-table tbody tr:not(.group-row):hover td {
        background: #eff6ff;
    }

    .group-row td {
        background: rgba(59, 130, 246, 0.16);
        color: #eff6ff;
        font-weight: 700;
    }

    .group-meta {
        font-size: 0.9rem;
        color: #dbeafe;
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

    .item-thumb-cell {
        display: flex;
        align-items: center;
        gap: 0.85rem;
    }

    .item-thumb {
        width: 56px;
        height: 56px;
        border-radius: 12px;
        object-fit: cover;
        flex-shrink: 0;
        border: 1px solid rgba(148, 163, 184, 0.22);
        background: rgba(255, 255, 255, 0.04);
    }

    .item-thumb-placeholder {
        width: 56px;
        height: 56px;
        border-radius: 12px;
        flex-shrink: 0;
        border: 1px dashed rgba(148, 163, 184, 0.3);
        display: inline-flex;
        align-items: center;
        justify-content: center;
        color: #93c5fd;
        background: rgba(255, 255, 255, 0.03);
    }

    .item-desc-meta {
        display: block;
        margin-top: 0.2rem;
        color: #475569;
        font-size: 0.8rem;
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
    <h2><i class="bi bi-tools me-2"></i>Retirada de Ferramentas</h2>
    <p>Registre retiradas com o novo padrão visual dark, preservando o fluxo especial de custódia temporária.</p>
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
<div class="container-fluid" style="max-width: 900px;">
    <div class="tool-shell">

    <div class="alert-info-custom">
        <i class="bi bi-info-circle me-2"></i>
        <strong>Importante:</strong> As ferramentas devem ser devolvidas até o final do dia. Você pode montar vários funcionários na mesma coleta; o envio continua separado por ferramenta.
    </div>
    
    <form id="form-retirada" autocomplete="off">
        <div class="input-card">
            <div class="row g-3">
                <div class="col-md-6">
                    <label class="form-label"><i class="bi bi-person-badge me-1"></i>Matrícula do Funcionário</label>
                    <div class="position-relative">
                        <input class="form-control" id="input-matricula" name="matricula" placeholder="Digite o nome ou matrícula" autocomplete="off" required autofocus>
                        <div id="autocomplete-matricula-dropdown" class="autocomplete-dropdown"></div>
                    </div>
                </div>
                <div class="col-md-6">
                    <label class="form-label"><i class="bi bi-tools me-1"></i>Código da Ferramenta</label>
                    <div class="position-relative">
                        <input class="form-control" id="input-codigo" name="codigo" placeholder="Digite o nome ou código da ferramenta" autocomplete="off" required>
                        <div id="autocomplete-dropdown" class="autocomplete-dropdown"></div>
                    </div>
                </div>
                <div class="col-md-6">
                    <label class="form-label"><i class="bi bi-hash me-1"></i>Quantidade</label>
                    <div class="quantity-control">
                        <button class="quantity-step-btn" type="button" id="btn-quantidade-minus" aria-label="Diminuir quantidade">
                            <i class="bi bi-dash-lg"></i>
                        </button>
                        <input class="form-control quantity-input" type="number" id="input-quantidade" name="quantidade" value="1" min="1" step="1" inputmode="numeric" pattern="[0-9]*" required>
                        <button class="quantity-step-btn" type="button" id="btn-quantidade-plus" aria-label="Aumentar quantidade">
                            <i class="bi bi-plus-lg"></i>
                        </button>
                    </div>
                    <div class="quantity-hint">Use os botões ou digite a quantidade inteira desejada.</div>
                </div>
                <div class="col-md-6">
                    <label class="form-label"><i class="bi bi-geo-alt me-1"></i>Local do Serviço</label>
                    <input class="form-control" id="input-local" name="local_servico" placeholder="Ex: Bloco 5 - Manutenção elétrica" autocomplete="off">
                </div>
                <div class="col-12">
                    <label class="form-label"><i class="bi bi-chat-left-text me-1"></i>Observação (opcional)</label>
                    <textarea class="form-control" name="observacao" rows="2" placeholder="Informações adicionais sobre a retirada"></textarea>
                </div>
                <div class="col-12 d-grid gap-2">
                    <button class="btn btn-add-item" type="button" id="btn-adicionar">
                        <i class="bi bi-plus-circle me-2"></i>Adicionar Ferramenta
                    </button>
                    <button class="btn btn-new-group" type="button" id="btn-novo-funcionario">
                        <i class="bi bi-people me-2"></i>Adicionar Funcionário
                    </button>
                </div>
            </div>
        </div>

        <div class="operation-preview is-empty" id="current-item-preview">
            <div class="operation-preview-body">
                <span class="operation-preview-eyebrow"><i class="bi bi-display"></i> Painel operacional</span>
                <div class="operation-preview-placeholder">
                    <i class="bi bi-tools"></i>
                    <div>
                        <strong>Nenhuma ferramenta em foco</strong>
                        <div class="operation-preview-note">Selecione ou adicione uma ferramenta para exibir foto, quantidade e contexto da retirada.</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="items-table" id="items-container" style="display: none;">
            <div class="items-table-header">
                <i class="bi bi-list-check"></i>
                <span>Ferramentas para Retirada</span>
                <span class="total-items-badge" id="total-items-badge">0 itens</span>
            </div>
            <table class="table mb-0">
                <thead>
                    <tr>
                        <th style="width: 18%;">Código</th>
                        <th style="width: 39%;">Descrição</th>
                        <th style="width: 15%;" class="text-center">Quantidade</th>
                        <th style="width: 13%;" class="text-end">Valor</th>
                        <th style="width: 15%;" class="text-end">Ações</th>
                    </tr>
                </thead>
                <tbody id="items-list"></tbody>
            </table>
        </div>

        <div class="d-grid gap-2 mt-3">
            <button class="btn btn-submit" type="button" id="btn-registrar" disabled>
                <i class="bi bi-box-arrow-right me-2"></i>Registrar Retirada
            </button>
        </div>
    </form>
    
    <div class="alert alert-info mt-4" role="alert">
        <i class="bi bi-info-circle me-2"></i>
        <strong>Nota:</strong> Para visualizar ferramentas em uso, alertas e gerenciar devoluções, acesse <a href="/controle-ferramentas" class="alert-link"><strong>Auditar Ferramentas</strong></a>.
    </div>
    </div>
</div>

<!-- Modal: mensagens simpáticas (saldo insuficiente / erros) -->
<div class="modal fade" id="modalErroRetirada" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title" id="modalErroRetiradaTitle">
                    <i class="bi bi-exclamation-triangle me-2"></i>Atenção
                </h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <p class="mb-2" id="modalErroRetiradaMsg"></p>
                <div id="modalErroRetiradaDetailsWrap" style="display: none;">
                    <hr class="my-3">
                    <div class="fw-semibold mb-2">Detalhes:</div>
                    <ul class="mb-0" id="modalErroRetiradaDetails"></ul>
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Entendi</button>
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
                <div class="express-return-window-note">A devolução expressa mostra ferramentas em aberto do colaborador selecionado.</div>
                <div class="alert alert-secondary express-return-status" data-express-return-role="status" role="status">Abra o painel para carregar os colaboradores com ferramentas em aberto.</div>
                <section class="express-return-section">
                    <div class="express-return-section-title"><i class="bi bi-people"></i>Colaboradores com ferramentas em aberto</div>
                    <div class="express-return-collaborators" data-express-return-role="collaborators">
                        <div class="express-return-empty">Abra o painel para carregar os colaboradores.</div>
                    </div>
                </section>
                <section class="express-return-section">
                    <div class="express-return-section-title"><i class="bi bi-tools"></i>Ferramentas do colaborador selecionado</div>
                    <div class="express-return-list" data-express-return-role="items">
                        <div class="express-return-empty">Selecione um colaborador acima.</div>
                    </div>
                </section>
                <div class="express-return-detail is-empty" data-express-return-role="detail">
                    <strong>Nenhum item selecionado.</strong>
                    <div class="express-return-hint">Escolha uma ferramenta da lista abaixo para liberar a devolução.</div>
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Fechar</button>
                <button type="button" class="btn btn-submit" data-express-return-role="submit" disabled>Fazer devolução</button>
            </div>
        </div>
    </div>
</div>

</%block>

<%block name="scripts">
${parent.scripts()}
<script src="${url_for('static', filename='js/mirror-screen-launcher.js')}"></script>
<script src="${url_for('static', filename='js/express-return-modal.js')}?v=20260414b"></script>
<script>
(function() {
    const usuariosAutocompleteData = ${tojson(usuarios)|n};
    const itemSearchUrl = '${url_for("ferramentas.buscar_item")}';

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
            throw new Error('Falha ao buscar ferramentas');
        }
        const data = await response.json();
        return (data.items || data.itens || []).slice(0, 20);
    }

    function getUnavailableMessage(item) {
        return String(item?.unavailable_detail || item?.unavailable_reason || 'Ferramenta indisponível para retirada.').trim();
    }

    const inputMatricula = document.getElementById('input-matricula');
    const inputCodigo = document.getElementById('input-codigo');
    const inputQuantidade = document.getElementById('input-quantidade');
    const btnQuantidadeMinus = document.getElementById('btn-quantidade-minus');
    const btnQuantidadePlus = document.getElementById('btn-quantidade-plus');
    const inputLocal = document.getElementById('input-local');
    const inputObservacao = document.querySelector('textarea[name="observacao"]');
    const dropdown = document.getElementById('autocomplete-dropdown');
    const dropdownMatricula = document.getElementById('autocomplete-matricula-dropdown');
    const formEl = document.getElementById('form-retirada');
    const btnAdicionar = document.getElementById('btn-adicionar');
    const btnNovoFuncionario = document.getElementById('btn-novo-funcionario');
    const btnRegistrar = document.getElementById('btn-registrar');
    const itemsContainer = document.getElementById('items-container');
    const itemsList = document.getElementById('items-list');
    const totalBadge = document.getElementById('total-items-badge');
    const currentItemPreview = document.getElementById('current-item-preview');
    const mirrorChannelName = 'galint-operation-mirror-v1';
    const mirrorStorageKey = 'galint.operationMirrorState.v1';
    const mirrorChannel = typeof window.BroadcastChannel !== 'undefined' ? new BroadcastChannel(mirrorChannelName) : null;

    const items = [];
    const groups = [];
    let itemCounter = 0;
    let groupCounter = 0;
    let currentGroupId = null;
    let currentPreviewItem = null;
    let debounceTimer;
    let debounceTimerMatricula;
    let itemSearchRequestId = 0;
    let currentFocus = -1;
    let currentFocusMatricula = -1;
    let currentItems = [];
    let currentFuncionarios = [];

    // Nunca permitir submit "normal" do form (fluxo é via JS + endpoint em lote)
    if (formEl) {
        formEl.addEventListener('submit', function(e) {
            e.preventDefault();
        });

        // Evita submissão automática ao pressionar Enter (scanner).
        // A retirada só deve ocorrer ao clicar em "Registrar Retirada".
        formEl.addEventListener('keydown', function(e) {
            if (e.key !== 'Enter') return;

            const tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : '';
            if (tag === 'TEXTAREA' || tag === 'BUTTON') return;

            e.preventDefault();

            if (e.target === inputMatricula) {
                inputCodigo && inputCodigo.focus();
            } else if (e.target === inputCodigo) {
                inputQuantidade && inputQuantidade.focus();
            } else if (e.target === inputQuantidade) {
                inputLocal && inputLocal.focus();
            }
        });
    }
    
    function getSanitizedQuantity(value) {
        const digits = String(value || '').replace(/[^\d]/g, '');
        const parsed = parseInt(digits, 10);
        return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
    }

    function formatCurrencyBR(value) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue) || numericValue <= 0) {
            return '';
        }
        return numericValue.toLocaleString('pt-BR', {
            style: 'currency',
            currency: 'BRL'
        });
    }

    function getToolFinancialReference(item) {
        const reference = item && item.valor_referencia && typeof item.valor_referencia === 'object'
            ? item.valor_referencia
            : null;
        const unitPriceBase = Number(reference?.valor_unitario_base);
        const hasValue = Boolean(reference?.disponivel) && Number.isFinite(unitPriceBase) && unitPriceBase > 0;
        return {
            hasValue: hasValue,
            unitPriceBase: hasValue ? unitPriceBase : 0,
            unitPriceDisplay: String(reference?.valor_unitario_display || '').trim(),
            unitPriceDisplayFull: String(reference?.valor_unitario_display_full || '').trim(),
            sourceLabel: String(reference?.origem_label || '').trim(),
        };
    }

    function buildToolFinancialSummary(item) {
        const reference = getToolFinancialReference(item);
        if (!reference.hasValue) {
            return null;
        }
        const quantidade = getSanitizedQuantity(item && item.quantidade);
        const totalValue = reference.unitPriceBase * quantidade;
        if (!(totalValue > 0)) {
            return null;
        }
        return {
            totalValue: totalValue,
            totalDisplay: formatCurrencyBR(totalValue),
            detailDisplay: quantidade > 1 && reference.unitPriceDisplay
                ? quantidade + ' x ' + reference.unitPriceDisplay
                : reference.unitPriceDisplay,
            sourceLabel: reference.sourceLabel,
        };
    }

    function buildToolValueHtml(item) {
        const summary = buildToolFinancialSummary(item);
        if (!summary || !summary.totalDisplay) {
            return '<span class="text-muted small">—</span>';
        }
        return '<div class="item-value-total">' + escapeHtml(summary.totalDisplay) + '</div>'
            + (summary.detailDisplay
                ? '<div class="item-value-detail">' + escapeHtml(summary.detailDisplay) + '</div>'
                : '');
    }

    function syncQuantityValue(value) {
        const quantidade = getSanitizedQuantity(value);
        inputQuantidade.value = String(quantidade);
        if (currentPreviewItem) {
            currentPreviewItem.quantidade = quantidade;
            renderCurrentPreview(currentPreviewItem, 'preview');
        }
        return quantidade;
    }

    // Força quantidade inteira e permite ajustar por botões próprios.
    inputQuantidade.addEventListener('input', function() {
        syncQuantityValue(this.value);
    });

    inputQuantidade.addEventListener('blur', function() {
        syncQuantityValue(this.value);
    });

    btnQuantidadeMinus?.addEventListener('click', function() {
        const quantidadeAtual = getSanitizedQuantity(inputQuantidade.value);
        syncQuantityValue(Math.max(1, quantidadeAtual - 1));
        inputQuantidade.focus();
    });

    btnQuantidadePlus?.addEventListener('click', function() {
        const quantidadeAtual = getSanitizedQuantity(inputQuantidade.value);
        syncQuantityValue(quantidadeAtual + 1);
        inputQuantidade.focus();
    });

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

    function clearSelectedCollaborator() {
        delete inputMatricula.dataset.nome;
        delete inputMatricula.dataset.matricula;
    }

    function getCollaboratorDisplayName(rawValue, explicitName) {
        const knownName = String(explicitName || '').trim();
        if (knownName) {
            return knownName;
        }

        const raw = String(rawValue || '').trim();
        const selectedName = String(inputMatricula.dataset.nome || '').trim();
        const selectedMatricula = String(inputMatricula.dataset.matricula || '').trim();

        if (selectedName && (!raw || raw === selectedMatricula || raw === selectedName)) {
            return selectedName;
        }

        return raw;
    }

    function buildMirrorPayload(status, item, extra) {
        const actor = String((item && item.matricula) || inputMatricula.value || '').trim();
        const actorName = getCollaboratorDisplayName(actor, item && item.colaborador_nome);
        const local = String((item && item.local) || inputLocal.value || '').trim();
        const observacao = String(inputObservacao && inputObservacao.value ? inputObservacao.value : '').trim();
        const financial = item ? buildToolFinancialSummary(item) : null;
        const payload = {
            kind: 'ferramenta',
            kind_label: 'Ferramenta',
            status: status,
            generated_at: new Date().toISOString(),
            source_label: 'retirada de ferramenta',
            batch_label: ((extra && extra.itemCount) || items.length || 0) + ' ferramenta(s) na coleta',
            actor: {
                matricula: actor,
                nome: actorName || actor,
            },
            context: {
                local_servico: local,
                observacao: observacao,
            },
        };

        if (item) {
            payload.item = {
                codigo: item.codigo || '',
                descricao: item.descricao || item.codigo || '',
                categoria: item.categoria || '',
                marca: item.marca || '',
                foto_url: item.foto_url || '',
                saldo: item.saldo,
                saldo_display: item.saldo_display || '',
                financial: financial ? {
                    valor_total_display: financial.totalDisplay,
                    valor_detalhe_display: financial.detailDisplay || '',
                    valor_origem_label: financial.sourceLabel || '',
                } : null,
            };
            payload.movement = {
                quantidade: item.quantidade || 1,
                quantidade_display: String(item.quantidade || 1),
                valor_total_display: financial?.totalDisplay || '',
                valor_detalhe_display: financial?.detailDisplay || '',
            };
        }

        return payload;
    }

    function renderCurrentPreview(item, status, publishState) {
        const previewStatus = status || (item ? 'preview' : 'idle');
        const shouldPublish = publishState !== false;
        if (!currentItemPreview) return;
        if (!item) {
            currentItemPreview.className = 'operation-preview is-empty';
            currentItemPreview.innerHTML = '' +
                '<div class="operation-preview-body">' +
                    '<span class="operation-preview-eyebrow"><i class="bi bi-display"></i> Painel operacional</span>' +
                    '<div class="operation-preview-placeholder">' +
                        '<i class="bi bi-tools"></i>' +
                        '<div><strong>Nenhuma ferramenta em foco</strong><div class="operation-preview-note">Selecione ou adicione uma ferramenta para exibir foto, quantidade e contexto da retirada.</div></div>' +
                    '</div>' +
                '</div>';
            if (shouldPublish) {
                publishMirrorState(buildMirrorPayload(previewStatus, null));
            }
            return;
        }

        const fotoHtml = item.foto_url
            ? '<img src="' + escapeHtml(item.foto_url) + '" alt="' + escapeHtml(item.descricao || item.codigo || 'Ferramenta') + '">'
            : '<div class="operation-preview-placeholder"><i class="bi bi-image"></i><div>Sem foto da ferramenta</div></div>';
        const matricula = String(item.matricula || inputMatricula.value || '').trim() || 'Nao informado';
        const collaboratorLabel = getCollaboratorDisplayName(matricula, item && item.colaborador_nome) || matricula || 'Nao informado';
        const local = String(item.local || inputLocal.value || '').trim() || 'Nao informado';
        const saldo = String(item.saldo_display || item.saldo || '').trim() || 'Nao informado';
        const observacao = String(item.observacao || (inputObservacao && inputObservacao.value) || '').trim() || 'Sem observacao';
        const financialSummary = buildToolFinancialSummary(item);
        const financialStatHtml = financialSummary && financialSummary.totalDisplay
            ? '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Valor estimado</span><span class="operation-preview-stat-value">' + escapeHtml(financialSummary.totalDisplay) + '</span></div>'
            : '';
        const eyebrowLabel = previewStatus === 'completed'
            ? '<i class="bi bi-check2-circle"></i> Ultima retirada registrada'
            : '<i class="bi bi-tools"></i> Custodia diaria';
        const previewNoteBase = previewStatus === 'completed'
            ? 'Ultima ferramenta registrada. Confira os dados antes de iniciar a proxima retirada.'
            : observacao;
        const previewNote = financialSummary && financialSummary.detailDisplay
            ? previewNoteBase + ' Valor: ' + financialSummary.detailDisplay + (financialSummary.sourceLabel ? ' (' + financialSummary.sourceLabel + ').' : '.')
            : previewNoteBase;

        currentItemPreview.className = 'operation-preview';
        currentItemPreview.innerHTML = '' +
            '<div class="operation-preview-media">' + fotoHtml + '</div>' +
            '<div class="operation-preview-body">' +
                '<span class="operation-preview-eyebrow">' + eyebrowLabel + '</span>' +
                '<div>' +
                    '<h3 class="operation-preview-title">' + escapeHtml(item.descricao || item.codigo || 'Ferramenta') + '</h3>' +
                    '<div class="operation-preview-subtitle">Codigo ' + escapeHtml(item.codigo || '—') + (item.categoria ? ' • ' + escapeHtml(item.categoria) : '') + (item.marca ? ' • ' + escapeHtml(item.marca) : '') + '</div>' +
                '</div>' +
                '<div class="operation-preview-grid">' +
                    '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Quantidade</span><span class="operation-preview-stat-value">' + escapeHtml(String(item.quantidade || 1)) + '</span></div>' +
                    '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Saldo</span><span class="operation-preview-stat-value">' + escapeHtml(saldo) + '</span></div>' +
                    financialStatHtml +
                    '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Colaborador</span><span class="operation-preview-stat-value">' + escapeHtml(collaboratorLabel) + '</span></div>' +
                    '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Local</span><span class="operation-preview-stat-value">' + escapeHtml(local) + '</span></div>' +
                '</div>' +
                '<div class="operation-preview-note">' + escapeHtml(previewNote) + '</div>' +
            '</div>';
        if (shouldPublish) {
            publishMirrorState(buildMirrorPayload(previewStatus, item));
        }
    }
        // Autocomplete para matrícula/nome do funcionário
    inputMatricula.addEventListener('input', function() {
        clearTimeout(debounceTimerMatricula);
        const query = this.value.trim();
        const selectedMatricula = String(this.dataset.matricula || '').trim();
        const selectedName = String(this.dataset.nome || '').trim();

        if ((selectedMatricula || selectedName) && query !== selectedMatricula && query !== selectedName) {
            clearSelectedCollaborator();
        }
        
        if (query.length < 1) {
            dropdownMatricula.classList.remove('show');
            return;
        }
        
        debounceTimerMatricula = setTimeout(function() {
            const normalizedQuery = normalizeAutocompleteText(query);
            const resultados = usuariosAutocompleteData.filter(func => {
                const nome = normalizeAutocompleteText(func.nome);
                const matricula = normalizeAutocompleteText(func.matricula);
                return nome.includes(normalizedQuery) || matricula.includes(normalizedQuery);
            }).slice(0, 20);

            if (resultados.length > 0) {
                showAutocompleteFuncionario(resultados);
            } else {
                dropdownMatricula.classList.remove('show');
            }
        }, 150);
    });
    
    function showAutocompleteFuncionario(funcionarios) {
        currentFuncionarios = funcionarios;
        currentFocusMatricula = -1;
        dropdownMatricula.innerHTML = '';
        
        funcionarios.forEach((func, index) => {
            const div = document.createElement('div');
            div.className = 'autocomplete-item';
            div.innerHTML = 
                '<div class="autocomplete-item-title">' + escapeHtml(func.nome) + '</div>' +
                '<div class="autocomplete-item-details">' +
                '  <span class="autocomplete-item-code">Matrícula: ' + escapeHtml(func.matricula) + '</span>' +
                (func.setor !== 'N/D' ? ' | Setor: ' + escapeHtml(func.setor) : '') +
                (func.cargo !== 'N/D' ? ' | ' + escapeHtml(func.cargo) : '') +
                '</div>';
            
            div.addEventListener('click', function() {
                selectFuncionario(func);
            });
            
            dropdownMatricula.appendChild(div);
        });
        
        dropdownMatricula.classList.add('show');
    }
    
    function selectFuncionario(func) {
        inputMatricula.value = func.matricula;
        inputMatricula.dataset.nome = String(func.nome || '').trim();
        inputMatricula.dataset.matricula = String(func.matricula || '').trim();
        dropdownMatricula.classList.remove('show');
        if (currentPreviewItem) {
            currentPreviewItem.matricula = func.matricula;
            currentPreviewItem.colaborador_nome = String(func.nome || '').trim();
            renderCurrentPreview(currentPreviewItem, 'preview');
        }
        inputCodigo.focus();
    }
    
    // Navegação por teclado no dropdown de matrícula
    inputMatricula.addEventListener('keydown', function(e) {
        const items = dropdownMatricula.querySelectorAll('.autocomplete-item');
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            currentFocusMatricula++;
            if (currentFocusMatricula >= items.length) currentFocusMatricula = 0;
            setActiveMatricula(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            currentFocusMatricula--;
            if (currentFocusMatricula < 0) currentFocusMatricula = items.length - 1;
            setActiveMatricula(items);
        } else if (e.key === 'Enter' && currentFocusMatricula > -1) {
            e.preventDefault();
            if (items[currentFocusMatricula]) {
                selectFuncionario(currentFuncionarios[currentFocusMatricula]);
            }
        } else if (e.key === 'Escape') {
            dropdownMatricula.classList.remove('show');
        }
    });
    
    function setActiveMatricula(items) {
        items.forEach((item, index) => {
            item.classList.toggle('active', index === currentFocusMatricula);
        });
        
        if (items[currentFocusMatricula]) {
            items[currentFocusMatricula].scrollIntoView({ block: 'nearest' });
        }
    }
        // Autocomplete para busca por nome ou código
    inputCodigo.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        const query = this.value.trim();
        
        if (query.length < 1) {
            dropdown.classList.remove('show');
            return;
        }
        
        debounceTimer = setTimeout(async function() {
            const requestId = ++itemSearchRequestId;
            try {
                const resultados = await fetchItemSuggestions(query);
                if (requestId !== itemSearchRequestId) {
                    return;
                }

                if (resultados.length > 0) {
                    showAutocomplete(resultados);
                } else {
                    dropdown.classList.remove('show');
                }
            } catch (error) {
                console.error('Erro ao buscar ferramentas:', error);
                if (requestId === itemSearchRequestId) {
                    currentItems = [];
                    dropdown.classList.remove('show');
                }
            }
        }, 150);
    });
    
    function showAutocomplete(items) {
        const availableItems = items.filter((item) => !item || item.is_available !== false);
        currentItems = availableItems;
        currentFocus = -1;
        dropdown.innerHTML = '';

        if (availableItems.length === 0) {
            dropdown.innerHTML = '<div class="autocomplete-item">Nenhuma ferramenta disponível para retirada.</div>';
            dropdown.classList.add('show');
            return;
        }
        
        availableItems.forEach((item, index) => {
            const div = document.createElement('div');
            div.className = 'autocomplete-item';
            const saldoDisplay = item.saldo_display || item.saldo;
            div.innerHTML = 
                '<div class="autocomplete-item-title">' + escapeHtml(item.descricao) + '</div>' +
                '<div class="autocomplete-item-details">' +
                '  <span class="autocomplete-item-code">Código: ' + escapeHtml(item.codigo) + '</span>' +
                '  | Saldo: ' + escapeHtml(String(saldoDisplay ?? '0')) +
                (item.categoria ? ' | ' + escapeHtml(item.categoria) : '') +
                (item.marca ? ' | Marca: ' + escapeHtml(item.marca) : '') +
                '</div>';
            
            div.addEventListener('click', function() {
                selectItem(item);
            });
            
            dropdown.appendChild(div);
        });
        
        dropdown.classList.add('show');
    }
    
    function selectItem(item) {
        if (item && item.is_available === false) {
            showErrorModal('Ferramenta indisponível', getUnavailableMessage(item));
            return;
        }
        inputCodigo.value = item.codigo;
        dropdown.classList.remove('show');
        currentPreviewItem = {
            ...currentPreviewItem,
            codigo: item.codigo,
            descricao: item.descricao || item.codigo,
            categoria: item.categoria,
            marca: item.marca,
            saldo: item.saldo,
            saldo_display: item.saldo_display,
            foto_url: item.foto_url,
            valor_referencia: item.valor_referencia || null,
            matricula: String(inputMatricula.value || '').trim(),
            colaborador_nome: getCollaboratorDisplayName(inputMatricula.value),
            local: String(inputLocal.value || '').trim(),
            observacao: String(inputObservacao && inputObservacao.value ? inputObservacao.value : '').trim(),
            quantidade: getSanitizedQuantity(inputQuantidade.value),
        };
        renderCurrentPreview(currentPreviewItem, 'preview');
        inputQuantidade.focus();
    }

    function renderItems() {
        if (items.length === 0) {
            itemsContainer.style.display = 'none';
            btnRegistrar.disabled = true;
            totalBadge.textContent = '0 itens';
            itemsList.innerHTML = '';
            return;
        }

        itemsContainer.style.display = 'block';
        btnRegistrar.disabled = false;

        const itemText = items.length === 1 ? 'item' : 'itens';
        totalBadge.textContent = items.length + ' ' + itemText;

        itemsList.innerHTML = groups.filter(group => group.itens.length > 0).map(group => {
            const localLabel = String(group.local || '').trim();
            const groupHeader = '<tr class="group-row"><td colspan="5">' + escapeHtml(group.matricula) + (localLabel ? ' <span class="group-meta">• ' + escapeHtml(localLabel) + '</span>' : '') + '</td></tr>';
            const groupItems = group.itens.map(item =>
                '<tr>' +
                    '<td><code>' + escapeHtml(item.codigo) + '</code></td>' +
                    '<td>' +
                        '<div class="item-thumb-cell">' +
                            (item.foto_url
                                ? '<img class="item-thumb" src="' + escapeHtml(item.foto_url) + '" alt="' + escapeHtml(item.descricao || item.codigo) + '">'
                                : '<span class="item-thumb-placeholder"><i class="bi bi-image"></i></span>') +
                            '<div><strong>' + escapeHtml(item.descricao || '-') + '</strong><span class="item-desc-meta">' + escapeHtml(item.categoria || 'Sem categoria') + (item.marca ? ' • ' + escapeHtml(item.marca) : '') + '</span></div>' +
                        '</div>' +
                    '</td>' +
                    '<td class="text-center"><span class="badge-qty">' + item.quantidade + '</span></td>' +
                    '<td class="text-end item-value-cell">' + buildToolValueHtml(item) + '</td>' +
                    '<td class="text-end">' +
                        '<button type="button" class="btn-remove-item" onclick="removeItem(' + item.id + ')">' +
                            '<i class="bi bi-trash me-1"></i>Remover' +
                        '</button>' +
                    '</td>' +
                '</tr>'
            ).join('');
            return groupHeader + groupItems;
        }).join('');
    }

    window.removeItem = function(id) {
        const index = items.findIndex(i => i.id === id);
        if (index > -1) {
            const removed = items.splice(index, 1)[0];
            groups.forEach((group) => {
                const itemIndex = group.itens.findIndex(item => item.id === removed.id);
                if (itemIndex > -1) {
                    group.itens.splice(itemIndex, 1);
                }
            });
            for (let idx = groups.length - 1; idx >= 0; idx -= 1) {
                if (!groups[idx].itens.length) {
                    if (groups[idx].id === currentGroupId) {
                        currentGroupId = null;
                    }
                    groups.splice(idx, 1);
                }
            }
            currentPreviewItem = items.length ? { ...items[items.length - 1] } : null;
            renderCurrentPreview(currentPreviewItem, currentPreviewItem ? 'queued' : 'idle');
            renderItems();
        }
    };

    function resetCurrentGroupForm(suppressMirrorReset, preservedPreview) {
        currentGroupId = null;
        inputMatricula.value = '';
        clearSelectedCollaborator();
        inputCodigo.value = '';
        inputQuantidade.value = '1';
        inputLocal.value = '';
        if (inputObservacao) {
            inputObservacao.value = '';
        }
        dropdown.classList.remove('show');
        dropdownMatricula.classList.remove('show');
        if (preservedPreview) {
            currentPreviewItem = { ...preservedPreview };
            renderCurrentPreview(currentPreviewItem, 'completed', false);
        } else {
            currentPreviewItem = null;
            renderCurrentPreview(null, 'idle', suppressMirrorReset !== true);
        }
        inputMatricula.focus();
    }

    btnNovoFuncionario?.addEventListener('click', function() {
        if (items.length === 0 && !inputMatricula.value.trim() && !inputLocal.value.trim()) {
            inputMatricula.focus();
            return;
        }
        resetCurrentGroupForm();
    });

    async function buscarInfoFerramenta(codigo) {
        try {
            const response = await fetch('/ferramentas/item-info/' + encodeURIComponent(codigo));
            if (!response.ok) return null;
            const data = await response.json();
            return data && data.descricao ? data : null;
        } catch (e) {
            return null;
        }
    }

    btnAdicionar.addEventListener('click', async function() {
        const matricula = (inputMatricula.value || '').trim();
        const codigo = (inputCodigo.value || '').trim();
        const quantidade = getSanitizedQuantity(inputQuantidade.value);

        if (!matricula) {
            alert('Informe a matrícula do funcionário');
            inputMatricula.focus();
            return;
        }

        if (!codigo) {
            alert('Informe o código da ferramenta');
            inputCodigo.focus();
            return;
        }

        if (quantidade < 1) {
            alert('Quantidade deve ser maior que zero');
            inputQuantidade.focus();
            return;
        }

        btnAdicionar.disabled = true;
        btnAdicionar.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Adicionando...';

        try {
            const itemInfo = await buscarInfoFerramenta(codigo);
            if (itemInfo && itemInfo.is_available === false) {
                showErrorModal('Ferramenta indisponível', getUnavailableMessage(itemInfo));
                inputCodigo.focus();
                return;
            }
            const matriculaAtual = String(inputMatricula.value || '').trim();
            const localAtual = String(inputLocal.value || '').trim();
            const observacaoAtual = (inputObservacao && inputObservacao.value ? inputObservacao.value.trim() : '') || '';
            let group = groups.find((entry) => entry.id === currentGroupId);
            if (!group || group.matricula !== matriculaAtual || group.local !== localAtual) {
                group = {
                    id: ++groupCounter,
                    matricula: matriculaAtual,
                    local: localAtual,
                    observacao: observacaoAtual,
                    itens: []
                };
                groups.push(group);
                currentGroupId = group.id;
            }

            const toolItem = {
                id: ++itemCounter,
                codigo: codigo,
                descricao: itemInfo && itemInfo.descricao ? itemInfo.descricao : codigo,
                quantidade: quantidade,
                categoria: itemInfo ? itemInfo.categoria : '',
                marca: itemInfo ? itemInfo.marca : '',
                saldo: itemInfo ? itemInfo.saldo : null,
                saldo_display: itemInfo ? itemInfo.saldo_display : '',
                foto_url: itemInfo ? itemInfo.foto_url : null,
                valor_referencia: itemInfo ? (itemInfo.valor_referencia || null) : null,
                matricula: matriculaAtual,
                colaborador_nome: getCollaboratorDisplayName(matriculaAtual),
                local: localAtual,
                observacao: observacaoAtual,
            };
            group.itens.push(toolItem);
            items.push(toolItem);
            currentPreviewItem = { ...toolItem };
            renderCurrentPreview(currentPreviewItem, 'queued');
            renderItems();

            inputCodigo.value = '';
            inputQuantidade.value = '1';
            inputCodigo.focus();
        } catch (e) {
            alert('Erro ao adicionar ferramenta');
        } finally {
            btnAdicionar.disabled = false;
            btnAdicionar.innerHTML = '<i class="bi bi-plus-circle me-2"></i>Adicionar Ferramenta';
        }
    });

    btnRegistrar.addEventListener('click', async function() {
        if (items.length === 0) {
            alert('Adicione pelo menos uma ferramenta');
            return;
        }

        const matricula = (inputMatricula.value || '').trim();
        if (!matricula) {
            alert('Informe a matrícula do funcionário');
            inputMatricula.focus();
            return;
        }

        const itemText = items.length === 1 ? 'ferramenta' : 'ferramentas';
        if (!confirm('Confirmar retirada de ' + items.length + ' ' + itemText + '?')) {
            return;
        }

        btnRegistrar.disabled = true;
        btnRegistrar.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Registrando...';

        try {
            const failedItems = [];
            let successCount = 0;
            const completedSnapshot = items.length ? { ...items[items.length - 1] } : null;
            const completedCount = items.length;

            for (const group of groups.filter(entry => entry.itens.length > 0)) {
                const payload = {
                    matricula: group.matricula,
                    local_servico: group.local || null,
                    observacao: group.observacao || null,
                    itens: group.itens.map(item => ({
                        codigo: item.codigo,
                        quantidade: item.quantidade,
                    }))
                };

                const response = await fetch('/ferramentas/retirar-multipla', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                const result = await response.json().catch(() => ({}));
                const falhas = Array.isArray(result.resultados) ? result.resultados.filter(r => !r.success) : [];

                if (response.ok && falhas.length === 0) {
                    successCount += group.itens.length;
                } else if (falhas.length > 0) {
                    const falhasPorCodigo = new Map();
                    falhas.forEach((falha) => {
                        const codigoFalha = String(falha.codigo || '');
                        falhasPorCodigo.set(codigoFalha, String(falha.message || 'Erro ao registrar retirada'));
                    });

                    group.itens.forEach((item) => {
                        const detalhe = falhasPorCodigo.get(String(item.codigo));
                        if (detalhe) {
                            failedItems.push({
                                ...item,
                                matricula: group.matricula,
                                local: group.local,
                                observacao: group.observacao,
                                error: detalhe,
                            });
                        } else {
                            successCount += 1;
                        }
                    });
                } else {
                    const detalheGeral = String(result.message || 'Erro ao registrar retirada');
                    group.itens.forEach((item) => {
                        failedItems.push({
                            ...item,
                            matricula: group.matricula,
                            local: group.local,
                            observacao: group.observacao,
                            error: detalheGeral,
                        });
                    });
                }
            }

            items.length = 0;
            groups.length = 0;

            failedItems.forEach((item) => {
                let group = groups.find((entry) => entry.matricula === item.matricula && entry.local === item.local && entry.observacao === item.observacao);
                if (!group) {
                    group = {
                        id: ++groupCounter,
                        matricula: item.matricula,
                        local: item.local,
                        observacao: item.observacao,
                        itens: []
                    };
                    groups.push(group);
                }
                const toolItem = {
                    id: item.id,
                    codigo: item.codigo,
                    descricao: item.descricao,
                    quantidade: item.quantidade,
                    categoria: item.categoria,
                    marca: item.marca,
                    saldo: item.saldo,
                    saldo_display: item.saldo_display,
                    foto_url: item.foto_url,
                    valor_referencia: item.valor_referencia || null,
                    matricula: item.matricula,
                    colaborador_nome: item.colaborador_nome,
                    local: item.local,
                    observacao: item.observacao,
                };
                group.itens.push(toolItem);
                items.push(toolItem);
            });
            renderItems();

            if (failedItems.length === 0) {
                if (completedSnapshot && successCount > 0) {
                    publishMirrorState(buildMirrorPayload('completed', completedSnapshot, { itemCount: completedCount }));
                    renderCurrentPreview(completedSnapshot, 'completed', false);
                }
                alert('✓ Retiradas registradas com sucesso.');
                resetCurrentGroupForm(true, completedSnapshot && successCount > 0 ? completedSnapshot : null);
            } else {
                showErrorModal(
                    'Parte das retiradas falhou',
                    'As retiradas com erro permaneceram na lista para nova tentativa.',
                    failedItems.map(item => item.codigo + ': ' + item.error)
                );
            }
        } catch (error) {
            showErrorModal(
                'Erro de comunicação',
                'Não consegui concluir o registro agora. Verifique sua conexão e tente novamente.',
                [String(error && error.message ? error.message : error)]
            );
        } finally {
            btnRegistrar.disabled = (items.length === 0);
            btnRegistrar.innerHTML = '<i class="bi bi-box-arrow-right me-2"></i>Registrar Retirada';
        }
    });
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function showErrorModal(title, message, details) {
        const modalEl = document.getElementById('modalErroRetirada');
        const titleEl = document.getElementById('modalErroRetiradaTitle');
        const msgEl = document.getElementById('modalErroRetiradaMsg');
        const detailsWrap = document.getElementById('modalErroRetiradaDetailsWrap');
        const detailsEl = document.getElementById('modalErroRetiradaDetails');

        if (!modalEl || !titleEl || !msgEl || !detailsWrap || !detailsEl) {
            alert(message || 'Erro');
            return;
        }

        titleEl.textContent = title || 'Atenção';
        msgEl.textContent = message || '';

        const detailLines = Array.isArray(details) ? details.filter(Boolean) : [];
        if (detailLines.length > 0) {
            detailsEl.innerHTML = detailLines.map(d => '<li>' + escapeHtml(String(d)) + '</li>').join('');
            detailsWrap.style.display = 'block';
        } else {
            detailsEl.innerHTML = '';
            detailsWrap.style.display = 'none';
        }

        try {
            const modal = new bootstrap.Modal(modalEl);
            modal.show();
        } catch (e) {
            alert(message || 'Erro');
        }
    }
    
    // Navegação por teclado
    inputCodigo.addEventListener('keydown', function(e) {
        const items = dropdown.querySelectorAll('.autocomplete-item');
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            currentFocus++;
            if (currentFocus >= items.length) currentFocus = 0;
            setActive(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            currentFocus--;
            if (currentFocus < 0) currentFocus = items.length - 1;
            setActive(items);
        } else if (e.key === 'Enter' && currentFocus > -1) {
            e.preventDefault();
            if (items[currentFocus]) {
                selectItem(currentItems[currentFocus]);
            }
        } else if (e.key === 'Enter') {
            // Mesmo sem item ativo no dropdown, nunca submeter o form pelo Enter.
            e.preventDefault();
            inputQuantidade && inputQuantidade.focus();
        } else if (e.key === 'Escape') {
            dropdown.classList.remove('show');
        }
    });

    inputLocal.addEventListener('input', function() {
        if (currentPreviewItem) {
            currentPreviewItem.local = String(inputLocal.value || '').trim();
            renderCurrentPreview(currentPreviewItem, 'preview');
        }
    });

    inputObservacao.addEventListener('input', function() {
        if (currentPreviewItem) {
            currentPreviewItem.observacao = String(inputObservacao.value || '').trim();
            renderCurrentPreview(currentPreviewItem, 'preview');
        }
    });

    inputCodigo.addEventListener('blur', async function() {
        const codigo = String(inputCodigo.value || '').trim();
        if (!codigo) return;
        const itemInfo = await buscarInfoFerramenta(codigo);
        if (!itemInfo) return;
        currentPreviewItem = {
            ...currentPreviewItem,
            ...itemInfo,
            quantidade: getSanitizedQuantity(inputQuantidade.value),
            matricula: String(inputMatricula.value || '').trim(),
            colaborador_nome: getCollaboratorDisplayName(inputMatricula.value),
            local: String(inputLocal.value || '').trim(),
            observacao: String(inputObservacao.value || '').trim(),
            foto_url: itemInfo.foto_url,
            valor_referencia: itemInfo.valor_referencia || null,
        };
        renderCurrentPreview(currentPreviewItem, 'preview');
    });

    renderCurrentPreview(null, 'idle');

    if (window.GalintExpressReturnModal) {
        window.GalintExpressReturnModal.init({
            openButtonId: 'btn-open-express-return',
            modalId: 'modalDevolucaoExpressa',
            authMessageLoad: 'Sua sessão expirou durante a carga da devolução expressa. Faça login novamente.',
            authMessageSubmit: 'Sua sessão expirou antes de concluir a devolução expressa. Faça login novamente.',
            getInitialCollaboratorIdentifier: function() {
                return String(inputMatricula.value || '').trim();
            },
            buildCollaboratorsUrl: function() {
                return '${url_for("ferramentas.devolucao_expressa_colaboradores_api")}';
            },
            buildItemsUrl: function(collaborator) {
                return window.GalintExpressReturnModal.buildUrl('${url_for("ferramentas.devolucao_expressa_itens_api")}', {
                    matricula: collaborator && collaborator.matricula ? collaborator.matricula : ''
                });
            },
            getItemIdentity: function(item) {
                return item && item.saida_id ? item.saida_id : (item && item.codigo ? item.codigo : '');
            },
            renderItemButtonContent: function(item) {
                var localTexto = String(item.local_servico || '').trim();
                var custodyLabel = String(item.tipo_custodia || '').trim();
                var custodyText = custodyLabel === 'permanente' ? 'Custódia permanente' : 'Custódia diária';
                return '' +
                    '<div class="express-return-item-title">' + escapeHtml(item.descricao || item.codigo || 'Ferramenta') + '</div>' +
                    '<div class="express-return-item-meta">' +
                        '<span class="express-return-item-code">Código: ' + escapeHtml(item.codigo || '') + '</span>' +
                        '<span>' + escapeHtml(custodyText) + '</span>' +
                        '<span>' + escapeHtml(String(item.days_in_use || 0)) + ' dia(s)</span>' +
                    '</div>' +
                    '<div class="express-return-item-meta">' +
                        '<span>Retirada: ' + escapeHtml(item.data_saida_label || 'N/D') + '</span>' +
                        (localTexto ? '<span>Local: ' + escapeHtml(localTexto) + '</span>' : '') +
                        (item.is_alert ? '<span class="text-warning">Acima do prazo</span>' : '') +
                    '</div>';
            },
            renderDetail: function(context) {
                var item = context.item;
                var collaborator = context.collaborator;
                var custodyLabel = String(item.tipo_custodia || '').trim();
                var custodyText = custodyLabel === 'permanente' ? 'Permanente' : 'Diária';
                return '' +
                    '<div class="express-return-detail-title">' + escapeHtml(item.descricao || item.codigo || 'Ferramenta') + '</div>' +
                    '<div class="express-return-detail-subtitle">Código ' + escapeHtml(item.codigo || '') + (item.marca ? ' • ' + escapeHtml(item.marca) : '') + '</div>' +
                    '<div class="express-return-kpis">' +
                        '<div class="express-return-kpi"><span class="express-return-kpi-label">Colaborador</span><span class="express-return-kpi-value">' + escapeHtml((collaborator && collaborator.nome) || (collaborator && collaborator.matricula) || '-') + '</span></div>' +
                        '<div class="express-return-kpi"><span class="express-return-kpi-label">Custódia</span><span class="express-return-kpi-value">' + escapeHtml(custodyText) + '</span></div>' +
                        '<div class="express-return-kpi"><span class="express-return-kpi-label">Retirada</span><span class="express-return-kpi-value">' + escapeHtml(item.data_saida_label || '-') + '</span></div>' +
                        '<div class="express-return-kpi"><span class="express-return-kpi-label">Local</span><span class="express-return-kpi-value">' + escapeHtml(item.local_servico || 'Não informado') + '</span></div>' +
                    '</div>' +
                    '<div class="row g-3">' +
                        '<div class="col-12">' +
                            '<label class="form-label" for="express-return-observation">Observação</label>' +
                            '<input class="form-control" id="express-return-observation" value="Devolução expressa via tela de retirada de ferramentas" maxlength="200">' +
                            '<div class="express-return-hint">A devolução vai registrar a baixa diretamente na custódia desta ferramenta.</div>' +
                        '</div>' +
                    '</div>';
            },
            buildSubmitRequest: function(context) {
                if (!context.item || !context.item.saida_id) {
                    throw new Error('Não foi possível identificar a retirada da ferramenta.');
                }
                var observationField = context.modalEl.querySelector('#express-return-observation');
                var observacao = observationField ? String(observationField.value || '').trim() : '';
                var payload = new URLSearchParams();
                payload.append('observacao', observacao || 'Devolução expressa via tela de retirada de ferramentas');
                payload.append('matricula', context.collaborator && context.collaborator.matricula ? context.collaborator.matricula : '');
                payload.append('codigo_item', context.item && context.item.codigo ? context.item.codigo : '');
                return {
                    url: '/controle-ferramentas/devolucao/' + encodeURIComponent(String(context.item.saida_id)) + '/api',
                    options: {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                            'Accept': 'application/json'
                        },
                        body: payload.toString()
                    }
                };
            },
            messages: {
                initialStatus: 'Abra o painel para carregar os colaboradores com ferramentas em aberto.',
                loadingCollaborators: 'Carregando colaboradores com ferramentas em aberto...',
                loadingItems: 'Carregando ferramentas do colaborador...',
                selectCollaborator: 'Escolha o colaborador para carregar as ferramentas em aberto.',
                selectCollaboratorFirst: 'Selecione um colaborador acima.',
                selectItem: 'Escolha a ferramenta para concluir a devolução expressa.',
                readyToSubmit: 'Revise os dados e confirme a devolução.',
                noCollaborators: 'Nenhum colaborador com ferramenta em aberto foi encontrado.',
                noItems: 'Nenhuma ferramenta em aberto foi encontrada para este colaborador.',
                emptyDetailTitle: 'Nenhuma ferramenta selecionada.',
                emptyDetailHint: 'Escolha uma ferramenta da lista abaixo para liberar a devolução.',
                submitButton: 'Fazer devolução',
                submitBusy: 'Devolvendo...',
                submitSuccess: 'Devolução expressa registrada com sucesso.',
                submitError: 'Falha ao registrar a devolução expressa.'
            }
        });
    }
    
    function setActive(items) {
        items.forEach((item, index) => {
            item.classList.toggle('active', index === currentFocus);
        });
        
        if (items[currentFocus]) {
            items[currentFocus].scrollIntoView({ block: 'nearest' });
        }
    }
    
    // Fechar dropdown ao clicar fora
    document.addEventListener('click', function(e) {
        if (e.target !== inputCodigo && !dropdown.contains(e.target)) {
            dropdown.classList.remove('show');
        }
        if (e.target !== inputMatricula && !dropdownMatricula.contains(e.target)) {
            dropdownMatricula.classList.remove('show');
        }
    });
})();
</script>
</%block>
