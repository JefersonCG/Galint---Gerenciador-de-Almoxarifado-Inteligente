<%inherit file="/base.mako"/>

<%block name="title">Registro de Saídas</%block>

<%block name="extra_css">
<style>
    .hub-container {
        max-width: 1000px;
        margin: 0 auto;
        padding: 2rem 1rem;
    }
    
    .hub-header {
        text-align: center;
        margin-bottom: 3rem;
    }
    
    .hub-header h2 {
        font-size: 2rem;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 0.5rem;
    }
    
    .hub-header p {
        font-size: 1.1rem;
        color: #64748b;
    }
    
    .saidas-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 2rem;
        margin-top: 2rem;
    }
    
    .saida-card {
        background: white;
        border-radius: 16px;
        padding: 2rem;
        text-align: center;
        cursor: pointer;
        transition: all 0.3s ease;
        border: 2px solid #e2e8f0;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    }
    
    .saida-card:hover {
        transform: translateY(-8px);
        box-shadow: 0 12px 24px rgba(0, 0, 0, 0.15);
        border-color: #3b82f6;
    }
    
    .saida-card.materiais:hover {
        border-color: #3b82f6;
    }
    
    .saida-card.ferramentas:hover {
        border-color: #f59e0b;
    }
    
    .saida-card.fracionados:hover {
        border-color: #10b981;
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
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 0.75rem;
    }
    
    .saida-card-description {
        font-size: 0.95rem;
        color: #64748b;
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
        background: #dbeafe;
        color: #1e40af;
    }
    
    .saida-card.ferramentas .saida-card-badge {
        background: #fef3c7;
        color: #92400e;
    }
    
    .saida-card.fracionados .saida-card-badge {
        background: #d1fae5;
        color: #065f46;
    }
</style>
</%block>

<%block name="content">
<div class="hub-container">
    <div class="hub-header">
        <h2><i class="bi bi-box-arrow-up-right me-2"></i>Registro de Saídas</h2>
        <p>Selecione o tipo de retirada que deseja registrar</p>
    </div>
    
    <div class="saidas-grid">
        <!-- Card Materiais Comuns -->
        <div class="saida-card materiais" onclick="window.location.href='${url_for('movements.saida_page')}'">
            <div class="saida-card-icon">
                <i class="bi bi-box-seam"></i>
            </div>
            <div class="saida-card-title">Materiais Comuns</div>
            <div class="saida-card-description">
                Retirada de materiais em unidades padrão (pacote, caixa, unidade)
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
                Controle de retirada e custódia de ferramentas (permanente ou temporária)
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
                Retirada pesada de produtos líquidos ou fracionados (kg, litros)
            </div>
            <span class="saida-card-badge">Pesagem Manual</span>
        </div>
    </div>
</div>
</%block>

<%block name="scripts">
${parent.scripts()}
</%block>
