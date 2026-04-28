<%inherit file="/base.mako"/>

<%block name="title">Registro de Saídas</%block>

<%block name="extra_css">
<style>
    .hub-container {
        max-width: 1360px;
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
    
    .saidas-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 1.4rem;
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

    .saida-card.devolucoes:hover {
        border-color: rgba(168, 85, 247, 0.42);
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

    .saida-card.devolucoes .saida-card-icon {
        color: #a855f7;
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

    .saida-card.devolucoes .saida-card-badge {
        background: rgba(168, 85, 247, 0.16);
        color: #e9d5ff;
        border: 1px solid rgba(168, 85, 247, 0.24);
    }

    .saida-card.ferramentas::before {
        background: radial-gradient(circle at 18% 18%, rgba(245, 158, 11, 0.2), transparent 32%);
    }

    .saida-card.fracionados::before {
        background: radial-gradient(circle at 18% 18%, rgba(16, 185, 129, 0.18), transparent 32%);
    }

    .saida-card.devolucoes::before {
        background: radial-gradient(circle at 18% 18%, rgba(168, 85, 247, 0.2), transparent 32%);
    }

    @media (max-width: 1200px) {
        .saidas-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
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
            grid-template-columns: 1fr;
            gap: 1rem;
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
        
        <div class="saidas-grid">
            <!-- Card Materiais Comuns -->
            <div class="saida-card materiais" onclick="window.location.href='${url_for('movements.saida_page')}'">
                <div class="saida-card-icon">
                    <i class="bi bi-box-seam"></i>
                </div>
                <div class="saida-card-title">Materiais Comuns</div>
                <div class="saida-card-description">
                    Retirada de materiais em unidades padrão, como pacote, caixa e unidade, com suporte também para ferramentas disponíveis e abertura automática da custódia.
                </div>
                <span class="saida-card-badge">Estoque Geral + Ferramentas</span>
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

            <!-- Card Devoluções -->
            <div class="saida-card devolucoes" onclick="window.location.href='${url_for('movements.entrada_page')}'">
                <div class="saida-card-icon">
                    <i class="bi bi-arrow-return-left"></i>
                </div>
                <div class="saida-card-title">Devoluções</div>
                <div class="saida-card-description">
                    Registro centralizado de devolução para materiais e itens retornados ao estoque, com conferência rápida e rastreabilidade do retorno.
                </div>
                <span class="saida-card-badge">Retorno ao Estoque</span>
            </div>
        </div>
    </div>
</div>
</%block>

<%block name="scripts">
${parent.scripts()}
</%block>
