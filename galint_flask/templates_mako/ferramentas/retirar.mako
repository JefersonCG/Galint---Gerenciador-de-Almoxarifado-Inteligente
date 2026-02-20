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
    .page-header {
        background: linear-gradient(120deg, #2563eb 0%, #3b82f6 100%);
        color: white;
        padding: 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 20px rgba(37, 99, 235, 0.4);
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
    
    .input-card {
        background: #ffffff;
        border-radius: 12px;
        padding: 2rem;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
        margin-bottom: 1.5rem;
        border: 1px solid #e9ecef;
        position: relative;
    }
    
    .input-card .form-label {
        font-weight: 600;
        color: #495057;
        margin-bottom: 0.5rem;
        font-size: 0.9rem;
    }
    
    .input-card .form-control {
        border-radius: 8px;
        border: 2px solid #e9ecef;
        padding: 0.75rem 1rem;
        transition: all 0.3s ease;
    }
    
    .input-card .form-control:focus {
        border-color: #3b82f6;
        box-shadow: 0 0 0 0.2rem rgba(37, 99, 235, 0.15);
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
        background: #e7f3ff;
        border: 1px solid #b3d9ff;
        border-radius: 8px;
        padding: 1rem;
        color: #004085;
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

</style>
</%block>

<%block name="content">
<div class="container-fluid" style="max-width: 900px;">
    <div class="page-header">
        <h2><i class="bi bi-tools me-2"></i>Retirada de Ferramentas</h2>
        <p>Registre a retirada de ferramentas para uso temporário</p>
    </div>
    
    <div class="alert-info-custom">
        <i class="bi bi-info-circle me-2"></i>
        <strong>Importante:</strong> As ferramentas devem ser devolvidas até o final do dia. Ferramentas não devolvidas aparecerão como <strong>atrasadas</strong> no painel.
    </div>
    
    <form method="post" action="${url_for('ferramentas.retirar')}">
        <div class="input-card">
            <div class="row g-3">
                <div class="col-md-6">
                    <label class="form-label"><i class="bi bi-person-badge me-1"></i>Matrícula do Funcionário</label>
                    <input class="form-control" id="input-matricula" name="matricula" list="usuario-list" placeholder="Leia ou digite a matrícula" autocomplete="off" required autofocus>
                </div>
                <div class="col-md-6">
                    <label class="form-label"><i class="bi bi-tools me-1"></i>Código da Ferramenta</label>
                    <input class="form-control" id="input-codigo" name="codigo" placeholder="Digite o nome ou código da ferramenta" autocomplete="off" required>
                    <div id="autocomplete-dropdown" class="autocomplete-dropdown"></div>
                </div>
                <div class="col-md-6">
                    <label class="form-label"><i class="bi bi-hash me-1"></i>Quantidade</label>
                    <input class="form-control" type="number" id="input-quantidade" name="quantidade" value="1" min="1" step="1" required>
                </div>
                <div class="col-md-6">
                    <label class="form-label"><i class="bi bi-geo-alt me-1"></i>Local do Serviço</label>
                    <input class="form-control" id="input-local" name="local_servico" placeholder="Ex: Bloco 5 - Manutenção elétrica" autocomplete="off">
                </div>
                <div class="col-12">
                    <label class="form-label"><i class="bi bi-chat-left-text me-1"></i>Observação (opcional)</label>
                    <textarea class="form-control" name="observacao" rows="2" placeholder="Informações adicionais sobre a retirada"></textarea>
                </div>
            </div>
        </div>
        
        <div class="d-grid gap-2">
            <button class="btn btn-submit" type="submit">
                <i class="bi bi-box-arrow-right me-2"></i>Registrar Retirada
            </button>
        </div>
    </form>
    
    <div class="alert alert-info mt-4" role="alert">
        <i class="bi bi-info-circle me-2"></i>
        <strong>Nota:</strong> Para visualizar ferramentas em uso, alertas e gerenciar devoluções, acesse <a href="/controle-ferramentas" class="alert-link"><strong>Auditar Ferramentas</strong></a>.
    </div>
</div>

<datalist id="usuario-list">
    % for usuario in usuarios:
        <option value="${usuario.get('matricula')}">${usuario.get('nome')} — ${usuario.get('matricula')}</option>
    % endfor
</datalist>
</%block>

<%block name="scripts">
$${parent.scripts()}
<script>
(function() {
    const inputCodigo = document.getElementById('input-codigo');
    const inputQuantidade = document.getElementById('input-quantidade');
    const dropdown = document.getElementById('autocomplete-dropdown');
    let debounceTimer;
    let currentFocus = -1;
    let currentItems = [];
    
    // Força quantidade inteira
    inputQuantidade.addEventListener('input', function() {
        this.value = this.value.replace(/[^\\d]/g, '');
        if (this.value === '' || parseInt(this.value) < 1) {
            this.value = '1';
        }
    });
    
    // Autocomplete para busca por nome ou código
    inputCodigo.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        const query = this.value.trim();
        
        if (query.length < 2) {
            dropdown.classList.remove('show');
            return;
        }
        
        debounceTimer = setTimeout(async function() {
            try {
                const response = await fetch('/ferramentas/buscar-item?q=' + encodeURIComponent(query));
                const data = await response.json();
                
                if (data.items && data.items.length > 0) {
                    showAutocomplete(data.items);
                } else {
                    dropdown.classList.remove('show');
                }
            } catch (error) {
                console.error('Erro ao buscar itens:', error);
                dropdown.classList.remove('show');
            }
        }, 300);
    });
    
    function showAutocomplete(items) {
        currentItems = items;
        currentFocus = -1;
        dropdown.innerHTML = '';
        
        items.forEach((item, index) => {
            const div = document.createElement('div');
            div.className = 'autocomplete-item';
            div.innerHTML = 
                '<div class="autocomplete-item-title">' + escapeHtml(item.descricao) + '</div>' +
                '<div class="autocomplete-item-details">' +
                '  <span class="autocomplete-item-code">Código: ' + escapeHtml(item.codigo) + '</span>' +
                '  | Saldo: ' + item.saldo +
                (item.categoria ? ' | ' + escapeHtml(item.categoria) : '') +
                '</div>';
            
            div.addEventListener('click', function() {
                selectItem(item);
            });
            
            dropdown.appendChild(div);
        });
        
        dropdown.classList.add('show');
    }
    
    function selectItem(item) {
        inputCodigo.value = item.codigo;
        dropdown.classList.remove('show');
        inputQuantidade.focus();
    }
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
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
        } else if (e.key === 'Escape') {
            dropdown.classList.remove('show');
        }
    });
    
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
    });
})();
</script>
</%block>
