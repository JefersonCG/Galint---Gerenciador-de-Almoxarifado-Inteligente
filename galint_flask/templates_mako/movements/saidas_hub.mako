<%inherit file="/base.mako"/>

<%block name="title">Registro de Saídas</%block>

<%block name="extra_css">
<style>
    .hub-container {
        max-width: 1120px;
        margin: 0 auto;
        padding: 2rem 1rem;
    }

    .hub-shell {
        background: linear-gradient(180deg, #eef2f7 0%, #f8fafc 100%);
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 30px;
        padding: 1.85rem;
        box-shadow: 0 24px 54px rgba(15, 23, 42, 0.1);
    }
    
    .hub-header {
        position: relative;
        overflow: hidden;
        text-align: center;
        margin-bottom: 2rem;
        border-radius: 26px;
        padding: 2rem 1.5rem;
        background: linear-gradient(135deg, #020617 0%, #172554 45%, #2563eb 100%);
        box-shadow: 0 28px 64px rgba(15, 23, 42, 0.2);
    }

    .hub-header::before {
        content: "";
        position: absolute;
        inset: 0;
        background:
            radial-gradient(circle at 16% 18%, rgba(56, 189, 248, 0.22), transparent 28%),
            radial-gradient(circle at 84% 16%, rgba(96, 165, 250, 0.18), transparent 22%),
            linear-gradient(180deg, rgba(255,255,255,0.04), transparent 60%);
        pointer-events: none;
    }

    .hub-header > * {
        position: relative;
        z-index: 1;
    }

    .hub-eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.38rem 0.72rem;
        border-radius: 999px;
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(226,232,240,0.14);
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: rgba(226,232,240,0.92);
        margin-bottom: 0.9rem;
    }
    
    .hub-header h2 {
        font-size: clamp(2rem, 3vw, 2.6rem);
        font-weight: 800;
        color: #f8fafc;
        margin-bottom: 0.55rem;
        letter-spacing: -0.03em;
    }
    
    .hub-header p {
        font-size: 1.1rem;
        color: rgba(226,232,240,0.82);
        margin-bottom: 0;
    }

    .hub-command-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 1rem;
        margin-bottom: 1.4rem;
    }

    .hub-command-card {
        border-radius: 1.1rem;
        border: 1px solid rgba(148, 163, 184, 0.16);
        background: linear-gradient(180deg, rgba(8, 17, 31, 0.98), rgba(15, 27, 45, 0.96));
        padding: 1rem 1.05rem;
        color: #e2e8f0;
        box-shadow: 0 18px 42px rgba(15, 23, 42, 0.18);
    }

    .hub-command-label {
        display: block;
        margin-bottom: 0.45rem;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: rgba(226, 232, 240, 0.68);
    }

    .hub-command-value {
        font-size: 1.18rem;
        font-weight: 700;
        color: #ffffff;
    }

    .hub-command-copy {
        margin: 0.4rem 0 0;
        font-size: 0.84rem;
        color: rgba(226, 232, 240, 0.78);
        line-height: 1.55;
    }

    .hub-guidance {
        display: grid;
        grid-template-columns: 1.1fr 0.9fr;
        gap: 1rem;
        margin-bottom: 1.4rem;
    }

    .hub-guidance-card,
    .hub-guidance-note {
        border-radius: 1.15rem;
        border: 1px solid rgba(148, 163, 184, 0.16);
        background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(241,245,249,0.96));
        padding: 1.15rem 1.2rem;
        box-shadow: 0 18px 42px rgba(15, 23, 42, 0.08);
    }

    .hub-guidance-kicker {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
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

    .hub-guidance-title {
        margin: 0.7rem 0 0;
        font-size: 1.05rem;
        font-weight: 800;
        color: #0f172a;
    }

    .hub-guidance-copy {
        margin: 0.4rem 0 0;
        color: #475569;
        font-size: 0.9rem;
        line-height: 1.6;
    }

    .hub-guidance-list {
        margin: 0.9rem 0 0;
        padding-left: 1.05rem;
        color: #334155;
    }

    .hub-guidance-list li + li {
        margin-top: 0.4rem;
    }
    
    .saidas-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 2rem;
        margin-top: 1.5rem;
    }
    
    .saida-card {
        position: relative;
        overflow: hidden;
        background: linear-gradient(145deg, #0f172a 0%, #1e293b 68%, #334155 100%);
        border-radius: 24px;
        padding: 2rem;
        text-align: center;
        cursor: pointer;
        transition: transform 0.28s ease, box-shadow 0.28s ease, border-color 0.28s ease;
        border: 1px solid rgba(148, 163, 184, 0.18);
        box-shadow: 0 20px 42px rgba(15, 23, 42, 0.18);
    }

    .saida-card::before {
        content: "";
        position: absolute;
        inset: 0;
        background: radial-gradient(circle at 18% 18%, rgba(59, 130, 246, 0.18), transparent 32%);
        pointer-events: none;
    }

    .saida-card > * {
        position: relative;
        z-index: 1;
    }
    
    .saida-card:hover {
        transform: translateY(-8px);
        box-shadow: 0 28px 52px rgba(15, 23, 42, 0.28);
    }
    
    .saida-card.materiais:hover {
        border-color: rgba(59, 130, 246, 0.42);
    }
    
    .saida-card.ferramentas:hover {
        border-color: rgba(245, 158, 11, 0.42);
    }
    
    .saida-card.fracionados:hover {
        border-color: rgba(16, 185, 129, 0.42);
    }
    
    .saida-card-icon {
        font-size: 4rem;
        margin-bottom: 1rem;
        transition: transform 0.3s ease;
    }
    
    .saida-card:hover .saida-card-icon {
        transform: scale(1.1);
    }
    
    .saida-card.materiais .saida-card-icon {
        color: #3b82f6;
    }
    
    .saida-card.ferramentas .saida-card-icon {
        color: #f59e0b;
    }
    
    .saida-card.fracionados .saida-card-icon {
        color: #10b981;
    }
    
    .saida-card-title {
        font-size: 1.5rem;
        font-weight: 800;
        color: #f8fafc;
        margin-bottom: 0.75rem;
        letter-spacing: -0.02em;
    }
    
    .saida-card-description {
        font-size: 0.95rem;
        color: rgba(226,232,240,0.76);
        line-height: 1.6;
    }
    
    .saida-card-badge {
        display: inline-block;
        margin-top: 1rem;
        padding: 0.5rem 1rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    
    .saida-card.materiais .saida-card-badge {
        background: rgba(59, 130, 246, 0.16);
        color: #bfdbfe;
        border: 1px solid rgba(59, 130, 246, 0.24);
    }
    
    .saida-card.ferramentas .saida-card-badge {
        background: rgba(245, 158, 11, 0.16);
        color: #fde68a;
        border: 1px solid rgba(245, 158, 11, 0.24);
    }
    
    .saida-card.fracionados .saida-card-badge {
        background: rgba(16, 185, 129, 0.16);
        color: #a7f3d0;
        border: 1px solid rgba(16, 185, 129, 0.24);
    }

    .saida-card.ferramentas::before {
        background: radial-gradient(circle at 18% 18%, rgba(245, 158, 11, 0.2), transparent 32%);
    }

    .saida-card.fracionados::before {
        background: radial-gradient(circle at 18% 18%, rgba(16, 185, 129, 0.18), transparent 32%);
    }

    @media (max-width: 768px) {
        .hub-shell {
            padding: 1rem;
            border-radius: 22px;
        }

        .hub-header {
            padding: 1.35rem 1rem;
            border-radius: 20px;
        }

        .saidas-grid {
            gap: 1rem;
        }

        .hub-guidance {
            grid-template-columns: 1fr;
        }
    }
</style>
</%block>

<%block name="content">
<div class="hub-container">
    <div class="hub-shell">
        <div class="hub-header">
            <div class="hub-eyebrow"><i class="bi bi-grid-1x2"></i> Central de lançamentos</div>
            <h2><i class="bi bi-box-arrow-up-right me-2"></i>Registro de Saídas</h2>
            <p>Selecione o tipo de retirada e siga com o fluxo adequado sem perder a organização centralizada dos cards.</p>
        </div>

        <div class="hub-command-grid">
            <div class="hub-command-card">
                <span class="hub-command-label">Decisão</span>
                <div class="hub-command-value">Escolha por contexto</div>
                <p class="hub-command-copy">A central separa o fluxo comum, a custódia de ferramentas e a retirada fracionada antes do lançamento.</p>
            </div>
            <div class="hub-command-card">
                <span class="hub-command-label">Rastreamento</span>
                <div class="hub-command-value">Operação segmentada</div>
                <p class="hub-command-copy">Cada card envia para a rotina certa, evitando mistura de regras e reduzindo retrabalho no estoque.</p>
            </div>
            <div class="hub-command-card">
                <span class="hub-command-label">Velocidade</span>
                <div class="hub-command-value">Acesso direto</div>
                <p class="hub-command-copy">Os atalhos permanecem objetivos para uso com leitor, teclado ou navegação rápida da operação.</p>
            </div>
        </div>

        <div class="hub-guidance">
            <div class="hub-guidance-card">
                <span class="hub-guidance-kicker"><i class="bi bi-signpost"></i> Como escolher</span>
                <h3 class="hub-guidance-title">Use o card pelo tipo real da retirada</h3>
                <p class="hub-guidance-copy">A escolha certa aqui evita retrabalho, garante a validação correta do estoque e mantém o histórico coerente para auditoria e Telegram.</p>
            </div>
            <div class="hub-guidance-note">
                <span class="hub-guidance-kicker"><i class="bi bi-clipboard2-pulse"></i> Regra prática</span>
                <ul class="hub-guidance-list">
                    <li>Materiais comuns: saída padrão por unidade, caixa ou pacote.</li>
                    <li>Ferramentas: retirada com custódia e controle especial.</li>
                    <li>Fracionados: produtos com pesagem ou volume real em kg e litros.</li>
                </ul>
            </div>
        </div>
        
        <div class="saidas-grid">
            <!-- Card Materiais Comuns -->
            <div class="saida-card materiais" onclick="window.location.href='${url_for('movements.saida_page')}'">
                <div class="saida-card-icon">
                    <i class="bi bi-box-seam"></i>
                </div>
                <div class="saida-card-title">Materiais Comuns</div>
                <div class="saida-card-description">
                    Retirada de materiais em unidades padrão, como pacote, caixa e unidade, com fluxo direto para o estoque geral.
                </div>
                <span class="saida-card-badge">Estoque Geral</span>
            </div>
            
            <!-- Card Ferramentas -->
            <div class="saida-card ferramentas" onclick="window.location.href='${url_for('ferramentas.retirar_page')}'">
                <div class="saida-card-icon">
                    <i class="bi bi-tools"></i>
                </div>
                <div class="saida-card-title">Ferramentas</div>
                <div class="saida-card-description">
                    Controle de retirada e custódia de ferramentas, incluindo operações permanentes ou temporárias com rastreabilidade especial.
                </div>
                <span class="saida-card-badge">Controle Especial</span>
            </div>
            
            <!-- Card Fracionados -->
            <div class="saida-card fracionados" onclick="window.location.href='${url_for('movements.saida_fracionada_page')}'">
                <div class="saida-card-icon">
                    <i class="bi bi-droplet-half"></i>
                </div>
                <div class="saida-card-title">Fracionados</div>
                <div class="saida-card-description">
                    Retirada com pesagem manual para produtos líquidos ou fracionados, mantendo o fluxo específico para kg e litros.
                </div>
                <span class="saida-card-badge">Pesagem Manual</span>
            </div>
        </div>
    </div>
</div>
</%block>

<%block name="scripts">
${parent.scripts()}
</%block>
