<%inherit file="/base.mako"/>
<%!
%>

<%block name="title">Registro de Saída</%block>

<%block name="extra_css">
<style>
    @import url('${url_for("static", filename="css/express-return-modal.css")}?v=20260414b');

    .saida-container {
        max-width: 1200px;
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
    
    .btn-add-item {
        background: linear-gradient(120deg, #2563eb 0%, #3b82f6 100%);
        border: none;
        border-radius: 8px;
        padding: 0.75rem 1.5rem;
        font-weight: 600;
        color: white;
        transition: all 0.3s ease;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
    }
    
    .btn-add-item:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5);
    }

    .btn-new-group {
        background: rgba(148, 163, 184, 0.12);
        border: 1px solid rgba(148, 163, 184, 0.28);
        border-radius: 8px;
        padding: 0.75rem 1.25rem;
        font-weight: 600;
        color: #e2e8f0;
        transition: all 0.2s ease;
    }

    .btn-new-group:hover {
        background: rgba(148, 163, 184, 0.2);
        color: #ffffff;
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
    
    .items-table {
        background: linear-gradient(145deg, #0f172a 0%, #1e293b 100%);
        border-radius: 24px;
        overflow: hidden;
        box-shadow: 0 22px 48px rgba(15, 23, 42, 0.16);
        margin-bottom: 1.5rem;
        border: 1px solid rgba(148, 163, 184, 0.18);
    }
    
    .items-table-header {
        background: linear-gradient(120deg, #1d4ed8 0%, #38bdf8 100%);
        color: white;
        padding: 1rem 1.5rem;
        font-weight: 700;
        font-size: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    .items-table table {
        width: 100%;
        margin: 0;
    }
    
    .items-table thead th {
        background: rgba(255, 255, 255, 0.06);
        color: #cbd5e1;
        font-weight: 600;
        padding: 1rem;
        border-bottom: 1px solid rgba(148, 163, 184, 0.16);
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .items-table tbody td {
        padding: 1rem;
        vertical-align: middle;
        border-bottom: 1px solid rgba(148, 163, 184, 0.12);
        color: #e2e8f0;
    }
    
    .items-table tbody tr:hover {
        background: rgba(59, 130, 246, 0.06);
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
    
    .btn-remove-item {
        background: #dc3545;
        border: none;
        border-radius: 6px;
        padding: 0.4rem 0.8rem;
        color: white;
        font-size: 0.85rem;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    
    .btn-remove-item:hover {
        background: #c82333;
        transform: scale(1.05);
    }
    
    .empty-state {
        text-align: center;
        padding: 3rem 2rem;
        color: #dbeafe;
        background: linear-gradient(145deg, #0f172a 0%, #1e293b 100%);
        border-radius: 24px;
        border: 1px solid rgba(148, 163, 184, 0.18);
        box-shadow: 0 22px 48px rgba(15, 23, 42, 0.16);
    }
    
    .empty-state i {
        font-size: 4rem;
        margin-bottom: 1rem;
        opacity: 0.5;
    }
    
    .empty-state p {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 700;
        color: #f8fafc;
    }

    .empty-state small {
        display: block;
        margin-top: 0.45rem;
        color: #93c5fd !important;
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

    .item-thumb-placeholder i {
        font-size: 1.2rem;
    }

    .item-desc-meta {
        display: block;
        margin-top: 0.2rem;
        color: #94a3b8;
        font-size: 0.8rem;
    }

    @media (max-width: 991.98px) {
        .operation-preview {
            grid-template-columns: 1fr;
        }

        .operation-preview-media img {
            height: 180px;
        }

        .operation-preview-grid {
            grid-template-columns: 1fr;
        }
    }
    
    .badge-qty {
        background: linear-gradient(120deg, #2563eb 0%, #3b82f6 100%);
        color: white;
        padding: 0.35rem 0.75rem;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.9rem;
    }
    
    .alert-info-custom {
        background: linear-gradient(145deg, rgba(15, 23, 42, 0.94) 0%, rgba(30, 41, 59, 0.92) 100%);
        border: 1px solid rgba(56, 189, 248, 0.28);
        border-radius: 18px;
        padding: 1rem;
        color: #dbeafe;
        margin-bottom: 1.5rem;
        box-shadow: 0 16px 34px rgba(15, 23, 42, 0.14);
    }

    .alert-info-custom strong {
        color: #ffffff;
    }

    .alert-info-custom i {
        color: #7dd3fc;
    }
    
    .total-items-badge {
        background: rgba(255, 255, 255, 0.25);
        padding: 0.35rem 0.75rem;
        border-radius: 20px;
        font-weight: 600;
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

    .btn-express-return {
        cursor: pointer;
    }

    .express-return-modal .modal-content {
        background: linear-gradient(145deg, #0f172a 0%, #1e293b 100%);
        color: #e2e8f0;
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 24px;
        box-shadow: 0 22px 48px rgba(15, 23, 42, 0.24);
    }

    .express-return-modal .modal-header {
        background: linear-gradient(120deg, #2563eb 0%, #3b82f6 100%);
        color: #ffffff;
        border-bottom: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 24px 24px 0 0;
    }

    .express-return-modal .modal-footer {
        border-top: 1px solid rgba(148, 163, 184, 0.16);
    }

    .express-return-toolbar {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 0.75rem;
        align-items: end;
    }

    .express-return-window-note {
        margin-top: 0.9rem;
        color: #93c5fd;
        font-size: 0.88rem;
    }

    .express-return-status {
        margin-top: 1rem;
        border-radius: 16px;
        border: 1px solid rgba(148, 163, 184, 0.16);
        background: rgba(15, 23, 42, 0.7);
        color: #e2e8f0;
    }

    .express-return-list {
        display: grid;
        gap: 0.75rem;
        margin-top: 1rem;
        max-height: 280px;
        overflow-y: auto;
        padding-right: 0.15rem;
    }

    .express-return-empty {
        border-radius: 18px;
        border: 1px dashed rgba(148, 163, 184, 0.28);
        padding: 1rem;
        color: #cbd5e1;
        text-align: center;
        background: rgba(15, 23, 42, 0.45);
    }

    .express-return-item {
        width: 100%;
        text-align: left;
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.04);
        color: #e2e8f0;
        padding: 0.95rem 1rem;
        transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
    }

    .express-return-item:hover {
        transform: translateY(-1px);
        border-color: rgba(96, 165, 250, 0.48);
        background: rgba(59, 130, 246, 0.1);
    }

    .express-return-item.is-active {
        border-color: rgba(96, 165, 250, 0.78);
        background: rgba(59, 130, 246, 0.18);
        box-shadow: inset 0 0 0 1px rgba(191, 219, 254, 0.12);
    }

    .express-return-item-title {
        font-weight: 700;
        color: #f8fafc;
    }

    .express-return-item-meta {
        margin-top: 0.35rem;
        font-size: 0.85rem;
        color: #cbd5e1;
        display: flex;
        flex-wrap: wrap;
        gap: 0.85rem;
    }

    .express-return-item-code {
        color: #93c5fd;
        font-family: monospace;
    }

    .express-return-detail {
        margin-top: 1rem;
        border-radius: 18px;
        border: 1px solid rgba(148, 163, 184, 0.18);
        background: rgba(255, 255, 255, 0.04);
        padding: 1rem;
    }

    .express-return-detail.is-empty {
        color: #cbd5e1;
    }

    .express-return-detail-title {
        font-size: 1.05rem;
        font-weight: 800;
        color: #f8fafc;
        margin-bottom: 0.2rem;
    }

    .express-return-detail-subtitle {
        color: #93c5fd;
        font-size: 0.88rem;
        margin-bottom: 1rem;
    }

    .express-return-kpis {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.75rem;
        margin-bottom: 1rem;
    }

    .express-return-kpi {
        border-radius: 14px;
        border: 1px solid rgba(148, 163, 184, 0.16);
        background: rgba(15, 23, 42, 0.55);
        padding: 0.8rem 0.9rem;
    }

    .express-return-kpi-label {
        display: block;
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #94a3b8;
        margin-bottom: 0.25rem;
    }

    .express-return-kpi-value {
        font-size: 1rem;
        font-weight: 800;
        color: #f8fafc;
    }

    .express-return-detail .form-label {
        color: #e2e8f0;
        font-weight: 600;
    }

    .express-return-detail .form-control {
        border-radius: 10px;
        border: 1px solid rgba(148, 163, 184, 0.22);
        background: rgba(15, 23, 42, 0.82);
        color: #f8fafc;
    }

    .express-return-detail .form-control[readonly] {
        opacity: 1;
    }

    .express-return-hint {
        margin-top: 0.45rem;
        color: #cbd5e1;
        font-size: 0.84rem;
    }

    @media (max-width: 767.98px) {
        .express-return-toolbar {
            grid-template-columns: 1fr;
        }

        .express-return-kpis {
            grid-template-columns: 1fr;
        }
    }
</style>
</%block>

<%block name="content">
<div class="saida-container">
    <div class="saida-shell">
    <div class="page-header">
        <h2><i class="bi bi-box-arrow-right me-2"></i>Registro de Saída</h2>
        <p>Adicione itens à lista e registre a saída em lote com o novo padrão visual dark do fluxo de lançamentos.</p>
        <div class="page-header-actions">
            <a class="btn-mirror-screen" data-mirror-screen="1" href="${url_for('movements.painel_espelho_page', mode='saida')}" target="_blank" rel="noopener">
                <span class="btn-mirror-screen-icon"><img src="${url_for('static', filename='img/galint-icon.png')}" alt="GALINT"></span>
                <span class="btn-mirror-screen-label">Painel de Visualização</span>
            </a>
            <button class="btn-mirror-screen btn-express-return" type="button" id="btn-open-express-return">
                <span class="btn-mirror-screen-icon"><i class="bi bi-arrow-return-left"></i></span>
                <span class="btn-mirror-screen-label">Devolução Expressa</span>
            </button>
        </div>
    </div>
    
    <div class="alert-info-custom">
        <i class="bi bi-info-circle me-2"></i>
        <strong>Dica:</strong> Você pode montar a coleta com vários funcionários. O envio continua item por item, com notificações separadas.
    </div>

    <div class="input-card">
        <div class="row g-3">
            <div class="col-md-6 position-relative">
                <label class="form-label"><i class="bi bi-person-badge me-1"></i>Crachá/Matrícula</label>
                <input class="form-control" id="input-usuario" placeholder="Leia ou digite o crachá ou nome" autocomplete="off">
                <div id="autocomplete-dropdown-usuario" class="autocomplete-dropdown"></div>
            </div>
            <div class="col-md-6">
                <label class="form-label"><i class="bi bi-geo-alt me-1"></i>Local do Serviço / Finalidade</label>
                <input class="form-control" id="input-local" placeholder="Ex: Instalação elétrica no bloco 5" autocomplete="off">
            </div>
        </div>
        
        <hr class="my-3">
        
        <div class="row g-3">
            <div class="col-md-6 position-relative">
                <label class="form-label"><i class="bi bi-upc-scan me-1"></i>Código do Item</label>
                <input class="form-control" id="input-codigo" placeholder="Leia ou digite o código do item" autocomplete="off">
                <div id="autocomplete-dropdown-codigo" class="autocomplete-dropdown"></div>
            </div>
            <div class="col-md-3">
                <label class="form-label"><i class="bi bi-hash me-1"></i>Quantidade (inteira)</label>
                <input class="form-control" type="number" id="input-quantidade" value="1" min="1" step="1" pattern="[0-9]*">
            </div>
            <div class="col-md-3 d-flex align-items-end">
                <button class="btn btn-add-item w-100" type="button" id="btn-adicionar">
                    <i class="bi bi-plus-circle me-1"></i>Adicionar Item
                </button>
            </div>
            <div class="col-12 d-grid gap-2">
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
                <i class="bi bi-card-image"></i>
                <div>
                    <strong>Nenhum item em foco</strong>
                    <div class="operation-preview-note">Selecione ou adicione um item para ver foto, quantidade e contexto da saida.</div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="items-table" id="items-container" style="display: none;">
        <div class="items-table-header">
            <i class="bi bi-list-check"></i>
            <span>Itens para Saída</span>
            <span class="total-items-badge ms-auto" id="total-items-badge">0 itens</span>
        </div>
        <table class="table mb-0">
            <thead>
                <tr>
                    <th style="width: 25%;">Código</th>
                    <th style="width: 40%;">Descrição</th>
                    <th style="width: 15%;" class="text-center">Quantidade</th>
                    <th style="width: 20%;" class="text-end">Ações</th>
                </tr>
            </thead>
            <tbody id="items-list">
            </tbody>
        </table>
    </div>
    
    <div class="empty-state" id="empty-state">
        <i class="bi bi-inbox"></i>
        <p>Nenhum item adicionado ainda</p>
        <small class="text-muted">Use o formulário acima para adicionar itens</small>
    </div>
    
    <div class="d-grid gap-2 mt-4">
        <button class="btn btn-register" type="button" id="btn-registrar" disabled>
            <i class="bi bi-check-circle me-2"></i>Registrar Saída
        </button>
    </div>
    </div>
</div>

<!-- Modal de Escolha de Unidade -->
<div class="modal fade" id="modalUnidade" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
            <div class="modal-header" style="background: linear-gradient(120deg, #2563eb 0%, #3b82f6 100%); color: white;">
                <h5 class="modal-title"><i class="bi bi-question-circle me-2"></i>Escolha a Unidade</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <p class="mb-3">O item <strong id="modal-item-desc"></strong> usa sistema de embalagens.</p>
                <p class="mb-3">Você quer dar saída de <strong id="modal-qtd"></strong>:</p>
                
                <div class="d-grid gap-2" id="modal-opcoes-padrao">
                    <button type="button" class="btn btn-lg btn-outline-primary" id="btn-embalagens">
                        <i class="bi bi-box-seam me-2"></i><strong id="modal-qtd-emb"></strong> <span id="modal-nome-emb-plural"></span>
                        <small class="d-block text-muted" id="modal-total-emb"></small>
                    </button>
                    <button type="button" class="btn btn-lg btn-outline-secondary" id="btn-unidades">
                        <i class="bi bi-upc me-2"></i><strong id="modal-qtd-unit"></strong> <span id="modal-unidade-base">unidades</span>
                        <small class="d-block text-muted" id="modal-unidade-desc">(quantidade individual)</small>
                    </button>
                    <button type="button" class="btn btn-lg btn-outline-secondary" id="btn-centimetros" style="display: none;">
                        <i class="bi bi-rulers me-2"></i><strong id="modal-qtd-centimetros"></strong> cm
                        <small class="d-block text-muted">(convertido para metros)</small>
                    </button>
                </div>
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
                <div class="express-return-window-note" id="express-return-window-note">A devolução expressa mostra só retiradas do dia e some automaticamente às 17:00.</div>
                <div class="alert alert-secondary express-return-status" data-express-return-role="status" role="status">Abra o painel para carregar os colaboradores com devolução pendente.</div>
                <section class="express-return-section">
                    <div class="express-return-section-title"><i class="bi bi-people"></i>Colaboradores com saídas pendentes</div>
                    <div class="express-return-collaborators" data-express-return-role="collaborators">
                        <div class="express-return-empty">Abra o painel para carregar os colaboradores.</div>
                    </div>
                </section>
                <section class="express-return-section">
                    <div class="express-return-section-title"><i class="bi bi-box-seam"></i>Itens do colaborador selecionado</div>
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
    <input type="hidden" name="liquido_habilitado" value="0">
</form>

</%block>

<%block name="scripts">
${parent.scripts()}
<script src="${url_for('static', filename='js/mirror-screen-launcher.js')}"></script>
<script src="${url_for('static', filename='js/express-return-modal.js')}?v=20260414b"></script>
<script>
(function() {
    const items = [];
    let itemCounter = 0;
    let pendingItem = null; // Item aguardando escolha de unidade
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
    const inputCodigo = document.getElementById('input-codigo');
    const inputQuantidade = document.getElementById('input-quantidade');
    const btnAdicionar = document.getElementById('btn-adicionar');
    const btnNovoFuncionario = document.getElementById('btn-novo-funcionario');
    const btnRegistrar = document.getElementById('btn-registrar');
    const itemsContainer = document.getElementById('items-container');
    const itemsList = document.getElementById('items-list');
    const emptyState = document.getElementById('empty-state');
    const totalBadge = document.getElementById('total-items-badge');
    const groups = [];
    let groupCounter = 0;
    let currentGroupId = null;
    let currentPreviewItem = null;
    
    // Modal
    const modalUnidade = new bootstrap.Modal(document.getElementById('modalUnidade'));
    const modalItemDesc = document.getElementById('modal-item-desc');
    const modalQtd = document.getElementById('modal-qtd');
    const modalQtdEmb = document.getElementById('modal-qtd-emb');
    const modalQtdUnit = document.getElementById('modal-qtd-unit');
    const modalNomeEmbPlural = document.getElementById('modal-nome-emb-plural');
    const modalTotalEmb = document.getElementById('modal-total-emb');
    const modalUnidadeBase = document.getElementById('modal-unidade-base');
    const modalUnidadeDesc = document.getElementById('modal-unidade-desc');
    const modalOpcoesPadrao = document.getElementById('modal-opcoes-padrao');
    const modalQtdCentimetros = document.getElementById('modal-qtd-centimetros');
    const btnEmbalagens = document.getElementById('btn-embalagens');
    const btnUnidades = document.getElementById('btn-unidades');
    const btnCentimetros = document.getElementById('btn-centimetros');
    const currentItemPreview = document.getElementById('current-item-preview');
    const mirrorChannelName = 'galint-operation-mirror-v1';
    const mirrorStorageKey = 'galint.operationMirrorState.v1';
    const mirrorChannel = typeof window.BroadcastChannel !== 'undefined' ? new BroadcastChannel(mirrorChannelName) : null;
        let mirrorActivityTimer = null;
    
    const nomesEmbalagem = {
        'lata': { singular: 'lata', plural: 'latas' },
        'bombona': { singular: 'bombona', plural: 'bombonas' },
        'rolo': { singular: 'rolo', plural: 'rolos' },
        'pacote': { singular: 'pacote', plural: 'pacotes' },
        'caixa': { singular: 'caixa', plural: 'caixas' },
        'balde': { singular: 'balde', plural: 'baldes' },
        'litro': { singular: 'litro', plural: 'litros' },
        'saco': { singular: 'saco', plural: 'sacos' }
    };

    function clearCurrentItemInputs() {
        inputCodigo.value = '';
        inputQuantidade.value = '1';
        dropdownCodigo.classList.remove('show');
    }

    function normalizePackageText(value) {
        return String(value || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .trim();
    }

    function inferPackagingType(item) {
        const directCandidates = [item?.tipo_embalagem, item?.tipo_embalagem_novo, item?.nome_embalagem];
        for (const candidate of directCandidates) {
            const normalized = normalizePackageText(candidate);
            if (normalized && nomesEmbalagem[normalized]) {
                return normalized;
            }
        }

        const fallbackText = [item?.unidade, item?.categoria, item?.descricao]
            .map(normalizePackageText)
            .join(' ');

        for (const candidate of Object.keys(nomesEmbalagem)) {
            if (fallbackText.includes(candidate)) {
                return candidate;
            }
        }

        if (fallbackText.includes('fita') && normalizarUnidadeMedida(item) === 'metro') {
            return 'rolo';
        }

        return '';
    }

    function getPackagingCapacity(item) {
        const candidates = [
            item?.unidades_por_embalagem,
            item?.capacidade_embalagem,
            item?.grandeza_referencia,
            item?.litros_por_embalagem,
        ];

        for (const candidate of candidates) {
            const parsed = parseFloat(candidate);
            if (Number.isFinite(parsed) && parsed > 0) {
                return parsed;
            }
        }

        return 0;
    }

    function formatPreviewQuantity(item) {
        if (!item) return '1';
        const quantidade = Number(item.quantidade_exibicao || item.quantidade_input || item.quantidade || inputQuantidade.value || 1);
        const unidade = String(item.unidade_label || '').trim();
        return unidade ? quantidade + ' ' + unidade : String(quantidade);
    }

    function buildMirrorDraftPayload() {
        const quantidadeDigitada = parseInt(inputQuantidade.value, 10) || 1;
        return {
            codigo: String(inputCodigo.value || '').trim(),
            quantidade: quantidadeDigitada,
            quantidade_display: String(quantidadeDigitada),
            usuario: String(inputUsuario.value || '').trim(),
            local_servico: String(inputLocal.value || '').trim(),
        };
    }

    function cloneMirrorBatchItem(item, status) {
        if (!item) {
            return null;
        }

        return {
            codigo: item.codigo || '',
            descricao: item.descricao || item.codigo || '',
            quantidade: item.quantidade_exibicao || item.quantidade_input || item.quantidade || 1,
            quantidade_display: formatPreviewQuantity(item),
            usuario: String(item.usuario || inputUsuario.value || '').trim(),
            local: String(item.local || inputLocal.value || '').trim(),
            foto_url: item.foto_url || '',
            status: status || 'queued',
        };
    }

    function buildMirrorBatchItems(previewItem, config) {
        const extraConfig = config || {};
        const defaultStatus = String(extraConfig.defaultStatus || 'queued').trim().toLowerCase() || 'queued';
        const sourceItems = Array.isArray(extraConfig.batchItems) ? extraConfig.batchItems : items;
        const batchItems = sourceItems
            .map((entry) => cloneMirrorBatchItem(entry, defaultStatus))
            .filter(Boolean);

        if (previewItem && String(extraConfig.previewStatus || '').trim().toLowerCase() === 'preview') {
            const previewEntry = cloneMirrorBatchItem(previewItem, 'preview');
            const duplicateIndex = batchItems.findIndex((entry) => {
                return entry.codigo === previewEntry.codigo
                    && entry.usuario === previewEntry.usuario
                    && entry.local === previewEntry.local
                    && entry.quantidade_display === previewEntry.quantidade_display;
            });
            if (duplicateIndex === -1) {
                batchItems.push(previewEntry);
            }
        }

        return batchItems.slice(-8);
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

    function buildMirrorPayload(status, item, extra) {
        const extraConfig = extra || {};
        const actor = String((item && item.usuario) || inputUsuario.value || '').trim();
        const local = String((item && item.local) || inputLocal.value || '').trim();
        const batchItems = buildMirrorBatchItems(item, {
            batchItems: extraConfig.batchItems,
            previewStatus: status,
            defaultStatus: extraConfig.batchItemStatus || (status === 'completed' ? 'completed' : 'queued'),
        });
        const batchTotalCandidate = Number(extraConfig.batchTotal);
        const batchTotal = Number.isFinite(batchTotalCandidate) && batchTotalCandidate > 0
            ? batchTotalCandidate
            : batchItems.length;
        const payload = {
            kind: 'saida',
            kind_label: 'Saida',
            status: status,
            generated_at: new Date().toISOString(),
            source_label: String(extraConfig.sourceLabel || 'registro de saida'),
            batch_label: String(extraConfig.batchLabel || (batchTotal + ' item(ns) na coleta')),
            batch_total: batchTotal,
            batch_items: batchItems,
            draft: buildMirrorDraftPayload(),
            actor: {
                nome: actor,
            },
            context: {
                local_servico: local,
            },
        };

        if (extraConfig.operatorActive) {
            payload.operator_active = true;
        }

        if (item) {
            payload.item = {
                codigo: item.codigo || '',
                descricao: item.descricao || item.codigo || '',
                categoria: item.categoria || '',
                marca: item.marca || '',
                foto_url: item.foto_url || '',
                saldo: item.saldo,
                saldo_display: item.saldo_display || '',
            };
            payload.movement = {
                quantidade: item.quantidade_exibicao || item.quantidade_input || item.quantidade || 1,
                quantidade_display: formatPreviewQuantity(item),
            };
        }

        return payload;
    }

    function scheduleMirrorOperatorHeartbeat() {
        if (currentPreviewItem) {
            renderCurrentPreview(currentPreviewItem, 'preview');
            return;
        }

        if (mirrorActivityTimer !== null) {
            window.clearTimeout(mirrorActivityTimer);
        }

        mirrorActivityTimer = window.setTimeout(function() {
            mirrorActivityTimer = null;
            publishMirrorState(buildMirrorPayload('idle', null, {
                operatorActive: true,
                sourceLabel: 'preparacao da saida',
            }));
        }, 80);
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
                        '<i class="bi bi-card-image"></i>' +
                        '<div><strong>Nenhum item em foco</strong><div class="operation-preview-note">Selecione ou adicione um item para ver foto, quantidade e contexto da saida.</div></div>' +
                    '</div>' +
                '</div>';
            if (shouldPublish) {
                publishMirrorState(buildMirrorPayload(previewStatus, null));
            }
            return;
        }

        const fotoHtml = item.foto_url
            ? '<img src="' + escapeHtml(item.foto_url) + '" alt="' + escapeHtml(item.descricao || item.codigo || 'Item') + '">' 
            : '<div class="operation-preview-placeholder"><i class="bi bi-image"></i><div>Sem foto do item</div></div>';
        const usuario = String(item.usuario || inputUsuario.value || '').trim() || 'Nao informado';
        const local = String(item.local || inputLocal.value || '').trim() || 'Nao informado';
        const saldo = String(item.saldo_display || item.saldo || '').trim() || 'Nao informado';
        const quantidade = formatPreviewQuantity(item);

        currentItemPreview.className = 'operation-preview';
        currentItemPreview.innerHTML = '' +
            '<div class="operation-preview-media">' + fotoHtml + '</div>' +
            '<div class="operation-preview-body">' +
                '<span class="operation-preview-eyebrow"><i class="bi bi-box-arrow-right"></i> Em preparacao</span>' +
                '<div>' +
                    '<h3 class="operation-preview-title">' + escapeHtml(item.descricao || item.codigo || 'Item') + '</h3>' +
                    '<div class="operation-preview-subtitle">Codigo ' + escapeHtml(item.codigo || '—') + (item.categoria ? ' • ' + escapeHtml(item.categoria) : '') + (item.marca ? ' • ' + escapeHtml(item.marca) : '') + '</div>' +
                '</div>' +
                '<div class="operation-preview-grid">' +
                    '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Quantidade</span><span class="operation-preview-stat-value">' + escapeHtml(quantidade) + '</span></div>' +
                    '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Saldo</span><span class="operation-preview-stat-value">' + escapeHtml(saldo) + '</span></div>' +
                    '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Colaborador</span><span class="operation-preview-stat-value">' + escapeHtml(usuario) + '</span></div>' +
                    '<div class="operation-preview-stat"><span class="operation-preview-stat-label">Local</span><span class="operation-preview-stat-value">' + escapeHtml(local) + '</span></div>' +
                '</div>' +
                '<div class="operation-preview-note">Este painel e a base da futura tela espelho para segundo monitor.</div>' +
            '</div>';
        if (shouldPublish) {
            publishMirrorState(buildMirrorPayload(previewStatus, item));
        }
    }

    async function loadPreviewForCode(codigo) {
        const rawCodigo = String(codigo || '').trim();
        if (!rawCodigo) {
            currentPreviewItem = null;
            renderCurrentPreview(null);
            return;
        }
        try {
            const response = await window.galintFetchWithAuth(
                '/movimentos/item-info/' + encodeURIComponent(rawCodigo),
                undefined,
                'Sua sessão expirou ao carregar o item. Faça login novamente.'
            );
            const data = await response.json();
            if (!response.ok || !data?.found) {
                return;
            }
            currentPreviewItem = {
                ...currentPreviewItem,
                ...data,
                codigo: data.codigo || rawCodigo,
                usuario: String(inputUsuario.value || '').trim(),
                local: String(inputLocal.value || '').trim(),
                quantidade_input: parseInt(inputQuantidade.value, 10) || 1,
            };
            renderCurrentPreview(currentPreviewItem, 'preview');
        } catch (error) {
            if (error && error.isAuthRedirect) {
                return;
            }
            console.error('Erro ao carregar preview do item:', error);
        }
    }
    
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
        dropdownUsuario.classList.remove('show');
        if (!inputLocal.value) {
            inputLocal.focus();
        } else {
            inputCodigo.focus();
        }
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
        scheduleMirrorOperatorHeartbeat();
        
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
            const tipoEmbalagem = inferPackagingType(item);
            const unidadesPorEmb = getPackagingCapacity(item);
            const grandezaRef = parseFloat(item.grandeza_referencia) || 0;
            const litrosPorEmb = parseFloat(item.litros_por_embalagem) || 0;
            
            // Se tem embalagem com unidades_por_embalagem
            if (tipoEmbalagem && unidadesPorEmb > 0) {
                const qtdEmbalagens = Math.floor(saldo / unidadesPorEmb);
                const unidadesSoltas = saldo - (qtdEmbalagens * unidadesPorEmb);
                const plural = (qtdEmbalagens !== 1 ? 's' : '');

                // No sistema, `grandeza_referencia` e `litros_por_embalagem` são numéricos.
                // Usamos isso para inferir a unidade interna (kg/L/m/un).
                let unidadeSolta = 'un';
                if (litrosPorEmb > 0) {
                    unidadeSolta = 'L';
                } else if (grandezaRef > 0 && (tipoEmbalagem === 'balde' || tipoEmbalagem === 'bombona' || tipoEmbalagem === 'lata' || tipoEmbalagem === 'pacote' || tipoEmbalagem === 'saco')) {
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

                // Sem embalagens completas: mostra o total na unidade interna.
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

    function normalizarUnidadeMedida(item) {
        const fracaoPadrao = String(item.fracao_unidade_padrao || '').trim().toLowerCase();
        const unidadeItem = String(item.unidade || '').trim().toLowerCase();
        const unidadeExibicao = String(item.unidade_exibicao_total || '').trim().toLowerCase();
        const litrosPorEmb = parseFloat(item.litros_por_embalagem) || 0;
        const grandezaRef = parseFloat(item.grandeza_referencia) || 0;
        const tipoEmbalagem = inferPackagingType(item);

        if (fracaoPadrao === 'litro' || unidadeExibicao === 'l') return 'litro';
        if (fracaoPadrao === 'quilo' || unidadeExibicao === 'kg') return 'kg';
        if (litrosPorEmb > 0) return 'litro';
        if (grandezaRef > 0 && (tipoEmbalagem === 'balde' || tipoEmbalagem === 'bombona' || tipoEmbalagem === 'lata' || tipoEmbalagem === 'pacote' || tipoEmbalagem === 'saco')) return 'kg';
        if (tipoEmbalagem === 'rolo') return 'metro';
        if (/(^|\b)(litro|litros|l|lt|lts)(\b|$)/.test(unidadeItem)) return 'litro';
        if (/(^|\b)(kg|quilo|quilos)(\b|$)/.test(unidadeItem)) return 'kg';
        if (/(^|\b)(metro|metros|m)(\b|$)/.test(unidadeItem)) return 'metro';
        return 'unidade';
    }

    function obterRotuloMedida(item, quantidade) {
        const medida = normalizarUnidadeMedida(item);
        const qty = Number(quantidade) || 0;

        if (medida === 'litro') {
            return { singular: 'litro', plural: 'litros' };
        }
        if (medida === 'kg') {
            return { singular: 'kg', plural: 'kg' };
        }
        if (medida === 'metro') {
            return { singular: 'metro', plural: 'metros' };
        }
        return {
            singular: 'unidade',
            plural: qty === 1 ? 'unidade' : 'unidades'
        };
    }

    function formatarQuantidadeMedida(valor, rotulo) {
        const numero = Number(valor) || 0;
        const precisaDecimal = Math.abs(numero - Math.round(numero)) > 0.000001;
        const textoNumero = precisaDecimal ? numero.toFixed(2) : String(Math.round(numero));
        const unidade = numero === 1 ? rotulo.singular : rotulo.plural;
        return textoNumero + ' ' + unidade;
    }

    function buildObservationUnitCode(item, unidadeLabel) {
        const medida = normalizarUnidadeMedida(item);
        if (medida === 'litro') return 'L';
        if (medida === 'kg') return 'KG';
        if (medida === 'metro') return 'METROS';
        return String(unidadeLabel || 'unidade').toUpperCase();
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
        dropdownCodigo.classList.remove('show');
        loadPreviewForCode(item.codigo);
        inputQuantidade.focus();
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
    
    btnEmbalagens.addEventListener('click', () => {
        if (pendingItem) {
            const nomes = nomesEmbalagem[pendingItem.tipo_embalagem] || { singular: 'embalagem', plural: 'embalagens' };
            pendingItem.em_embalagens = true;
            pendingItem.quantidade = pendingItem.quantidade_input;
            pendingItem.unidade_label = pendingItem.quantidade_input === 1 ? nomes.singular : nomes.plural;
            pendingItem.quantidade_exibicao = pendingItem.quantidade_input;
            pendingItem.observacao_unit = null;
            adicionarItemFinal(pendingItem);
            modalUnidade.hide();
            pendingItem = null;
            clearCurrentItemInputs();
            inputCodigo.focus();
        }
    });
    
    btnUnidades.addEventListener('click', () => {
        if (pendingItem) {
            const rotuloMedida = obterRotuloMedida(pendingItem, pendingItem.quantidade_input);
            const unidadeBaseSafe = String(pendingItem.quantidade_input === 1 ? rotuloMedida.singular : rotuloMedida.plural);
            pendingItem.em_embalagens = false;
            pendingItem.quantidade = pendingItem.quantidade_input;
            pendingItem.unidade_label = unidadeBaseSafe;
            pendingItem.quantidade_exibicao = pendingItem.quantidade_input;
            pendingItem.observacao_unit = 'UNIDADE=' + buildObservationUnitCode(pendingItem, unidadeBaseSafe) + ';QTD_ORIGINAL=' + pendingItem.quantidade_input;
            adicionarItemFinal(pendingItem);
            modalUnidade.hide();
            pendingItem = null;
            clearCurrentItemInputs();
            inputCodigo.focus();
        }
    });

    btnCentimetros.addEventListener('click', () => {
        if (pendingItem) {
            const convertido = pendingItem.quantidade_input / 100;
            pendingItem.em_embalagens = false;
            pendingItem.quantidade = convertido;
            pendingItem.unidade_label = 'cm';
            pendingItem.quantidade_exibicao = pendingItem.quantidade_input;
            pendingItem.observacao_unit = 'UNIDADE=CM;QTD_ORIGINAL=' + pendingItem.quantidade_input;
            adicionarItemFinal(pendingItem);
            modalUnidade.hide();
            pendingItem = null;
            clearCurrentItemInputs();
            inputCodigo.focus();
        }
    });
    
    // Previne envio ao pressionar Enter no código
    inputCodigo.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            btnAdicionar.click();
        }
    });
    
    // Força apenas valores inteiros
    inputQuantidade.addEventListener('input', function() {
        this.value = this.value.replace(/[^0-9]/g, '');
        if (this.value === '' || parseInt(this.value) < 1) {
            this.value = '1';
        }
        if (currentPreviewItem) {
            currentPreviewItem.quantidade_input = parseInt(this.value, 10) || 1;
            renderCurrentPreview(currentPreviewItem, 'preview');
            return;
        }
        scheduleMirrorOperatorHeartbeat();
    });

    inputUsuario.addEventListener('input', function() {
        scheduleMirrorOperatorHeartbeat();
    });

    inputUsuario.addEventListener('focus', function() {
        scheduleMirrorOperatorHeartbeat();
    });

    inputUsuario.addEventListener('blur', function() {
        if (currentPreviewItem) {
            currentPreviewItem.usuario = String(inputUsuario.value || '').trim();
            renderCurrentPreview(currentPreviewItem, 'preview');
        }
    });

    inputLocal.addEventListener('input', function() {
        if (currentPreviewItem) {
            currentPreviewItem.local = String(inputLocal.value || '').trim();
            renderCurrentPreview(currentPreviewItem, 'preview');
            return;
        }
        scheduleMirrorOperatorHeartbeat();
    });

    inputLocal.addEventListener('focus', function() {
        scheduleMirrorOperatorHeartbeat();
    });

    inputCodigo.addEventListener('focus', function() {
        scheduleMirrorOperatorHeartbeat();
    });

    inputQuantidade.addEventListener('focus', function() {
        scheduleMirrorOperatorHeartbeat();
    });

    inputCodigo.addEventListener('blur', function() {
        const codigo = String(inputCodigo.value || '').trim();
        if (codigo) {
            loadPreviewForCode(codigo);
        }
    });
    
    btnAdicionar.addEventListener('click', async function() {
        const usuario = inputUsuario.value.trim();
        const local = inputLocal.value.trim();
        const codigo = inputCodigo.value.trim();
        const quantidade = parseInt(inputQuantidade.value) || 1;
        
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
        
        if (quantidade < 1) {
            alert('Quantidade deve ser maior que zero');
            inputQuantidade.focus();
            return;
        }
        
        // Busca informações do item
        btnAdicionar.disabled = true;
        btnAdicionar.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Buscando...';
        
        try {
            const response = await window.galintFetchWithAuth(
                '/movimentos/item-info/' + encodeURIComponent(codigo),
                undefined,
                'Sua sessão expirou ao consultar o item. Faça login novamente.'
            );
            const data = await response.json();
            
            if (!data.descricao) {
                throw new Error('Item não encontrado');
            }
            
            // Verificar se o item usa sistema de embalagens
            const tipoEmbalagemDetectado = inferPackagingType(data);
            const capacidadeEmbalagem = getPackagingCapacity(data);
            if (tipoEmbalagemDetectado && capacidadeEmbalagem > 0) {
                // Tem embalagem - mostrar modal
                pendingItem = {
                    id: ++itemCounter,
                    codigo: codigo,
                    descricao: data.descricao,
                    quantidade: quantidade,
                    quantidade_input: quantidade,
                    usuario: usuario,
                    local: local,
                    tipo_embalagem: tipoEmbalagemDetectado,
                    unidades_por_embalagem: capacidadeEmbalagem,
                    nome_embalagem: data.nome_embalagem,
                    nome_embalagem_plural: data.nome_embalagem_plural,
                    unidade: data.unidade,
                    categoria: data.categoria,
                    marca: data.marca,
                    fracao_unidade_padrao: data.fracao_unidade_padrao,
                    unidade_exibicao_total: data.unidade_exibicao_total,
                    grandeza_referencia: data.grandeza_referencia,
                    litros_por_embalagem: data.litros_por_embalagem,
                    capacidade_embalagem: data.capacidade_embalagem,
                    em_embalagens: null,
                    saldo: data.saldo,
                    saldo_display: data.saldo_display,
                    foto_url: data.foto_url
                };

                currentPreviewItem = { ...pendingItem };
                renderCurrentPreview(currentPreviewItem, 'preview');
                
                mostrarModalUnidade(pendingItem);
                return;
                
            } else {
                // Não tem embalagem - adiciona direto
                adicionarItemFinal({
                    id: ++itemCounter,
                    codigo: codigo,
                    descricao: data.descricao,
                    quantidade: quantidade,
                    usuario: usuario,
                    local: local,
                    em_embalagens: null,
                    categoria: data.categoria,
                    marca: data.marca,
                    saldo: data.saldo,
                    saldo_display: data.saldo_display,
                    foto_url: data.foto_url
                });
            }
            
            // Limpa campos
            clearCurrentItemInputs();
            inputCodigo.focus();
            
        } catch (error) {
            if (error && error.isAuthRedirect) {
                return;
            }
            alert(error.message || 'Erro ao buscar item');
        } finally {
            btnAdicionar.disabled = false;
            btnAdicionar.innerHTML = '<i class="bi bi-plus-circle me-1"></i>Adicionar Item';
        }
    });
    
    function mostrarModalUnidade(item) {
        const nomes = nomesEmbalagem[item.tipo_embalagem] || { singular: 'embalagem', plural: 'embalagens' };
        const totalUnidades = item.quantidade_input * item.unidades_por_embalagem;
        const rotuloMedida = obterRotuloMedida(item, item.quantidade_input);
        const permiteCentimetros = item.tipo_embalagem === 'rolo' && normalizarUnidadeMedida(item) === 'metro';
        
        modalItemDesc.textContent = item.descricao;
        modalQtd.textContent = item.quantidade_input;
        modalOpcoesPadrao.style.display = 'grid';
        modalQtdEmb.textContent = item.quantidade_input;
        modalQtdUnit.textContent = item.quantidade_input;
        modalNomeEmbPlural.textContent = item.quantidade_input === 1 ? nomes.singular : nomes.plural;
        modalTotalEmb.textContent = '= ' + formatarQuantidadeMedida(totalUnidades, rotuloMedida) + ' no total';
        modalUnidadeBase.textContent = item.quantidade_input === 1 ? rotuloMedida.singular : rotuloMedida.plural;
        modalUnidadeDesc.textContent = permiteCentimetros ? '(saída em metros)' : '(quantidade individual)';
        btnCentimetros.style.display = permiteCentimetros ? '' : 'none';
        modalQtdCentimetros.textContent = item.quantidade_input;
        
        modalUnidade.show();
    }
    
    function adicionarItemFinal(item) {
        const usuario = String(item.usuario || '').trim();
        const local = String(item.local || '').trim();
        let group = groups.find((entry) => entry.id === currentGroupId);
        if (!group || group.usuario !== usuario || group.local !== local) {
            group = {
                id: ++groupCounter,
                usuario: usuario,
                local: local,
                itens: []
            };
            groups.push(group);
            currentGroupId = group.id;
        }
        group.itens.push(item);
        items.push(item);
        currentPreviewItem = { ...item };
        renderCurrentPreview(currentPreviewItem, 'queued');
        renderItems();
    }

    function normalizeGroupLabel(usuario, local) {
        const localLabel = String(local || '').trim();
        return localLabel ? (escapeHtml(usuario) + ' <span class="group-meta">• ' + escapeHtml(localLabel) + '</span>') : escapeHtml(usuario);
    }

    function resetCurrentGroupForm(suppressMirrorReset) {
        currentGroupId = null;
        inputUsuario.value = '';
        inputLocal.value = '';
        inputCodigo.value = '';
        inputQuantidade.value = '1';
        dropdownUsuario.classList.remove('show');
        dropdownCodigo.classList.remove('show');
        currentPreviewItem = null;
        renderCurrentPreview(null, 'idle', suppressMirrorReset !== true);
        inputUsuario.focus();
    }
    
    function renderItems() {
        if (items.length === 0) {
            itemsContainer.style.display = 'none';
            emptyState.style.display = 'block';
            btnRegistrar.disabled = true;
            return;
        }
        
        itemsContainer.style.display = 'block';
        emptyState.style.display = 'none';
        btnRegistrar.disabled = false;
        
        const itemText = items.length === 1 ? 'item' : 'itens';
        totalBadge.textContent = items.length + ' ' + itemText;

        const activeGroups = groups.filter(group => Array.isArray(group.itens) && group.itens.length > 0);
        itemsList.innerHTML = activeGroups.map(group => {
            const groupHeader =
                '<tr class="group-row">' +
                    '<td colspan="4">' + normalizeGroupLabel(group.usuario, group.local) + '</td>' +
                '</tr>';
            const groupItems = group.itens.map(item =>
                '<tr>' +
                    '<td><code>' + escapeHtml(item.codigo) + '</code></td>' +
                    '<td>' +
                        '<div class="item-thumb-cell">' +
                            (item.foto_url
                                ? '<img class="item-thumb" src="' + escapeHtml(item.foto_url) + '" alt="' + escapeHtml(item.descricao || item.codigo) + '">'
                                : '<span class="item-thumb-placeholder"><i class="bi bi-image"></i></span>') +
                            '<div><strong>' + escapeHtml(item.descricao) + '</strong>' +
                            '<span class="item-desc-meta">' + escapeHtml(item.categoria || 'Sem categoria') + (item.marca ? ' • ' + escapeHtml(item.marca) : '') + '</span></div>' +
                        '</div>' +
                    '</td>' +
                    '<td class="text-center"><span class="badge-qty">' + (item.quantidade_exibicao || item.quantidade) + (item.unidade_label ? ' ' + item.unidade_label : '') + '</span></td>' +
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
        const index = items.findIndex(item => item.id === id);
        if (index > -1) {
            const [removedItem] = items.splice(index, 1);
            groups.forEach((group) => {
                const itemIndex = group.itens.findIndex(item => item.id === removedItem.id);
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

    btnNovoFuncionario?.addEventListener('click', function() {
        if (items.length === 0 && !inputUsuario.value.trim() && !inputLocal.value.trim()) {
            inputUsuario.focus();
            return;
        }
        resetCurrentGroupForm();
    });
    
    btnRegistrar.addEventListener('click', async function() {
        if (items.length === 0) {
            alert('Adicione pelo menos um item');
            return;
        }
        
        const itemText = items.length === 1 ? 'item' : 'itens';
        if (!confirm('Confirmar registro de saída de ' + items.length + ' ' + itemText + '?')) {
            return;
        }
        
        btnRegistrar.disabled = true;
        btnRegistrar.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Registrando...';
        
        try {
            const failedItems = [];
            let successCount = 0;
            const completedBatchItems = items.map((entry) => ({ ...entry }));
            const completedSnapshot = completedBatchItems.length ? { ...completedBatchItems[completedBatchItems.length - 1] } : null;
            const completedCount = items.length;

            for (const group of groups.filter(entry => entry.itens.length > 0)) {
                const payload = {
                    usuario: group.usuario,
                    local_servico: group.local,
                    itens: group.itens.map(item => ({
                        codigo: item.codigo,
                        quantidade: item.quantidade,
                        observacao: item.observacao_unit || null,
                        em_embalagens: item.em_embalagens
                    }))
                };

                const response = await window.galintFetchWithAuth('/movimentos/saida-multipla', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                }, 'Sua sessão expirou antes de concluir o registro da saída. Faça login novamente.');

                const result = await response.json();
                const resultados = Array.isArray(result && result.resultados) ? result.resultados : [];
                const falhas = resultados.filter(r => !r.success);

                if (response.ok && falhas.length === 0) {
                    successCount += group.itens.length;
                } else if (falhas.length > 0) {
                    const falhasPorCodigo = new Map();
                    falhas.forEach((falha) => {
                        const codigoFalha = String(falha.codigo || '');
                        falhasPorCodigo.set(codigoFalha, String(falha.message || 'Erro ao registrar saída'));
                    });

                    group.itens.forEach((item) => {
                        const detalhe = falhasPorCodigo.get(String(item.codigo));
                        if (detalhe) {
                            failedItems.push({
                                ...item,
                                usuario: group.usuario,
                                local: group.local,
                                error: detalhe
                            });
                        } else {
                            successCount += 1;
                        }
                    });
                } else {
                    const detalheGeral = (result && result.message) || 'Erro ao registrar saída';
                    group.itens.forEach((item) => {
                        failedItems.push({
                            ...item,
                            usuario: group.usuario,
                            local: group.local,
                            error: detalheGeral
                        });
                    }
                    );
                }
            }

            items.length = 0;
            groups.length = 0;

            failedItems.forEach((item) => {
                adicionarItemFinal(item);
            });
            renderItems();

            if (failedItems.length === 0) {
                if (completedSnapshot && successCount > 0) {
                    publishMirrorState(buildMirrorPayload('completed', completedSnapshot, {
                        itemCount: completedCount,
                        batchItems: completedBatchItems,
                        batchTotal: completedCount,
                        batchItemStatus: 'completed',
                    }));
                }
                alert('✓ Saídas registradas com sucesso.');
                resetCurrentGroupForm(true);
            } else {
                const erros = failedItems.map(item => item.codigo + ': ' + item.error).join('\n');
                alert('⚠️ Parte das saídas não foi registrada. Os itens com falha permaneceram na lista.\n' + erros);
            }
        } catch (error) {
            if (error && error.isAuthRedirect) {
                return;
            }
            alert('❌ Erro ao registrar saída: ' + error.message);
        } finally {
            btnRegistrar.disabled = (items.length === 0);
            btnRegistrar.innerHTML = '<i class="bi bi-check-circle me-2"></i>Registrar Saída';
        }
    });
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    renderCurrentPreview(null, 'idle');

    if (window.GalintExpressReturnModal) {
        window.GalintExpressReturnModal.init({
            openButtonId: 'btn-open-express-return',
            modalId: 'modalDevolucaoExpressa',
            authMessageLoad: 'Sua sessão expirou durante a carga da devolução expressa. Faça login novamente.',
            authMessageSubmit: 'Sua sessão expirou antes de concluir a devolução expressa. Faça login novamente.',
            getInitialCollaboratorIdentifier: function() {
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
                    scope: 'padrao'
                });
            },
            buildItemsUrl: function(collaborator) {
                return window.GalintExpressReturnModal.buildUrl('${url_for("movements.devolucao_expressa_payload")}', {
                    scope: 'padrao',
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
                            '<input class="form-control" id="express-return-observation" value="Devolução expressa via tela de saída" maxlength="200">' +
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
                            observacao: observacao || 'Devolução expressa via tela de saída'
                        })
                    }
                };
            },
            messages: {
                initialStatus: 'Abra o painel para carregar os colaboradores com devolução pendente.',
                loadingCollaborators: 'Carregando colaboradores com saídas pendentes...',
                loadingItems: 'Carregando itens do colaborador...',
                selectCollaborator: 'Escolha o colaborador para carregar os itens pendentes.',
                selectCollaboratorFirst: 'Selecione um colaborador acima.',
                selectItem: 'Escolha o item para concluir a devolução expressa.',
                readyToSubmit: 'Revise os dados e confirme a devolução.',
                noCollaborators: 'Nenhum colaborador com saída comum pendente foi encontrado hoje.',
                noItems: 'Nenhum item elegível foi encontrado para este colaborador.',
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
