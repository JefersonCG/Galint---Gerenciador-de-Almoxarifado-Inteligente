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

    .items-table {
        background: white;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
        border: 1px solid #e9ecef;
        margin-top: 1.25rem;
        margin-bottom: 1rem;
    }

    .items-table-header {
        background: linear-gradient(120deg, #2563eb 0%, #3b82f6 100%);
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
        background: rgba(37, 99, 235, 0.12);
        color: #1e40af;
        padding: 0.35rem 0.75rem;
        border-radius: 20px;
        font-weight: 700;
        font-size: 0.9rem;
        display: inline-block;
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
                <div class="col-12 d-grid gap-2">
                    <button class="btn btn-add-item" type="button" id="btn-adicionar">
                        <i class="bi bi-plus-circle me-2"></i>Adicionar Ferramenta
                    </button>
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
                        <th style="width: 25%;">Código</th>
                        <th style="width: 45%;">Descrição</th>
                        <th style="width: 15%;" class="text-center">Quantidade</th>
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

</%block>

<%block name="scripts">
${parent.scripts()}
<script>
(function() {
    const usuariosAutocompleteData = ${tojson(usuarios)|n};
    const itensAutocompleteData = ${tojson(itens)|n};

    function normalizeAutocompleteText(value) {
        return String(value || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .trim();
    }

    const inputMatricula = document.getElementById('input-matricula');
    const inputCodigo = document.getElementById('input-codigo');
    const inputQuantidade = document.getElementById('input-quantidade');
    const inputLocal = document.getElementById('input-local');
    const inputObservacao = document.querySelector('textarea[name="observacao"]');
    const dropdown = document.getElementById('autocomplete-dropdown');
    const dropdownMatricula = document.getElementById('autocomplete-matricula-dropdown');
    const formEl = document.getElementById('form-retirada');
    const btnAdicionar = document.getElementById('btn-adicionar');
    const btnRegistrar = document.getElementById('btn-registrar');
    const itemsContainer = document.getElementById('items-container');
    const itemsList = document.getElementById('items-list');
    const totalBadge = document.getElementById('total-items-badge');

    const items = [];
    let itemCounter = 0;
    let debounceTimer;
    let debounceTimerMatricula;
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
    
    // Força quantidade inteira
    inputQuantidade.addEventListener('input', function() {
        this.value = this.value.replace(/[^\\d]/g, '');
        if (this.value === '' || parseInt(this.value) < 1) {
            this.value = '1';
        }
    });
        // Autocomplete para matrícula/nome do funcionário
    inputMatricula.addEventListener('input', function() {
        clearTimeout(debounceTimerMatricula);
        const query = this.value.trim();
        
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
        dropdownMatricula.classList.remove('show');
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
        
        debounceTimer = setTimeout(function() {
            const normalizedQuery = normalizeAutocompleteText(query);
            const resultados = itensAutocompleteData.filter(item => {
                const codigo = normalizeAutocompleteText(item.codigo);
                const descricao = normalizeAutocompleteText(item.descricao);
                return codigo.includes(normalizedQuery) || descricao.includes(normalizedQuery);
            }).slice(0, 20);

            if (resultados.length > 0) {
                showAutocomplete(resultados);
            } else {
                dropdown.classList.remove('show');
            }
        }, 150);
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

        itemsList.innerHTML = items.map(item =>
            '<tr>' +
                '<td><code>' + escapeHtml(item.codigo) + '</code></td>' +
                '<td><strong>' + escapeHtml(item.descricao || '-') + '</strong></td>' +
                '<td class="text-center"><span class="badge-qty">' + item.quantidade + '</span></td>' +
                '<td class="text-end">' +
                    '<button type="button" class="btn-remove-item" onclick="removeItem(' + item.id + ')">' +
                        '<i class="bi bi-trash me-1"></i>Remover' +
                    '</button>' +
                '</td>' +
            '</tr>'
        ).join('');
    }

    window.removeItem = function(id) {
        const index = items.findIndex(i => i.id === id);
        if (index > -1) {
            items.splice(index, 1);
            renderItems();
        }
    };

    async function buscarDescricaoPorCodigo(codigo) {
        try {
            const response = await fetch('/ferramentas/item-info/' + encodeURIComponent(codigo));
            if (!response.ok) return null;
            const data = await response.json();
            return data && data.descricao ? data.descricao : null;
        } catch (e) {
            return null;
        }
    }

    btnAdicionar.addEventListener('click', async function() {
        const matricula = (inputMatricula.value || '').trim();
        const codigo = (inputCodigo.value || '').trim();
        const quantidade = parseInt(inputQuantidade.value) || 1;

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
            const descricao = await buscarDescricaoPorCodigo(codigo);
            items.push({
                id: ++itemCounter,
                codigo: codigo,
                descricao: descricao || codigo,
                quantidade: quantidade,
            });
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
            const payload = {
                matricula: matricula,
                local_servico: (inputLocal && inputLocal.value ? inputLocal.value.trim() : null) || null,
                observacao: (inputObservacao && inputObservacao.value ? inputObservacao.value.trim() : null) || null,
                itens: items.map(i => ({
                    codigo: i.codigo,
                    quantidade: i.quantidade,
                }))
            };

            const response = await fetch('/ferramentas/retirar-multipla', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const contentType = (response.headers.get('content-type') || '').toLowerCase();
            if (!contentType.includes('application/json')) {
                const rawText = await response.text();
                const host = window.location && window.location.host ? window.location.host : '';
                const dicaHost = host
                    ? ('Você está acessando por ' + host + '. Se você fez login em outro endereço (ex.: localhost), faça login novamente neste mesmo endereço.')
                    : 'Faça login novamente e tente de novo.';

                if (response.status === 404) {
                    showErrorModal(
                        'Atualização necessária',
                        'O servidor não encontrou a rota de retirada em lote. Isso costuma acontecer quando o servidor ainda não foi reiniciado após a atualização.',
                        ['HTTP 404', 'Reinicie o servidor e atualize a página (Ctrl+F5).']
                    );
                    return;
                }

                if (response.status === 401 || response.status === 403 || (rawText || '').toLowerCase().includes('<!doctype')) {
                    showErrorModal(
                        'Sessão necessária',
                        'Para registrar a retirada, é necessário estar logado como administrador.',
                        [dicaHost]
                    );
                } else {
                    showErrorModal(
                        'Resposta inesperada',
                        'O servidor retornou uma resposta inesperada ao registrar a retirada.',
                        ['HTTP ' + response.status, dicaHost]
                    );
                }
                return;
            }

            const result = await response.json();

            if (response.status === 401 || response.status === 403) {
                const host = window.location && window.location.host ? window.location.host : '';
                const dicaHost = host
                    ? ('Você está acessando por ' + host + '. Se você fez login em outro endereço (ex.: localhost), faça login novamente neste mesmo endereço.')
                    : 'Faça login novamente e tente de novo.';

                showErrorModal(
                    'Sessão necessária',
                    (result && result.message) ? String(result.message) : 'Para registrar a retirada, é necessário estar logado como administrador.',
                    [dicaHost]
                );
                return;
            }

            if (result && result.success) {
                alert('✓ ' + (result.message || 'Retirada registrada'));
                items.length = 0;
                renderItems();
                inputCodigo.value = '';
                inputQuantidade.value = '1';
                inputCodigo.focus();
            } else {
                const falhas = (result && Array.isArray(result.resultados))
                    ? result.resultados.filter(r => !r.success)
                    : [];

                const detalhes = falhas.map(r => {
                    const codigoFalha = r && r.codigo ? String(r.codigo) : '?';
                    const msgFalha = r && r.message ? String(r.message) : 'Erro';
                    return codigoFalha + ': ' + msgFalha;
                });

                const msgGeral = (result && result.message) ? String(result.message) : 'Erro ao registrar retirada';
                const temSaldoInsuficiente = detalhes.some(d => (d || '').toLowerCase().includes('saldo insuficiente'))
                    || msgGeral.toLowerCase().includes('saldo insuficiente');

                if (temSaldoInsuficiente) {
                    showErrorModal(
                        'Quantidade acima do disponível',
                        'Ops! Parece que você pediu mais do que temos disponível agora. Ajuste a quantidade (ou devolva alguma ferramenta) e tente novamente.',
                        detalhes.length > 0 ? detalhes : [msgGeral]
                    );
                } else {
                    showErrorModal(
                        'Não foi possível registrar',
                        msgGeral,
                        detalhes
                    );
                }
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
