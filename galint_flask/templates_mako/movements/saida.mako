<%inherit file="/base.mako"/>
<%!
%>

<%block name="title">Registro de Saída</%block>

<%block name="extra_css">
<style>
    .saida-container {
        max-width: 1200px;
        margin: 0 auto;
    }
    
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
        padding: 1.5rem;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
        margin-bottom: 1.5rem;
        border: 1px solid #e9ecef;
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
        font-size: 1rem;
    }
    
    .input-card .form-control:focus {
        border-color: #3b82f6;
        box-shadow: 0 0 0 0.2rem rgba(37, 99, 235, 0.15);
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
        background: #ffffff;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
        margin-bottom: 1.5rem;
        border: 1px solid #e9ecef;
    }
    
    .items-table-header {
        background: linear-gradient(120deg, #2563eb 0%, #3b82f6 100%);
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
        background: #f8f9fa;
        color: #495057;
        font-weight: 600;
        padding: 1rem;
        border-bottom: 2px solid #dee2e6;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .items-table tbody td {
        padding: 1rem;
        vertical-align: middle;
        border-bottom: 1px solid #e9ecef;
        color: #212529;
    }
    
    .items-table tbody tr:hover {
        background: #f8f9fa;
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
        color: #6c757d;
    }
    
    .empty-state i {
        font-size: 4rem;
        margin-bottom: 1rem;
        opacity: 0.3;
    }
    
    .empty-state p {
        margin: 0;
        font-size: 1.1rem;
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
        background: #e7f3ff;
        border: 1px solid #b3d9ff;
        border-radius: 8px;
        padding: 1rem;
        color: #004085;
        margin-bottom: 1.5rem;
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
</style>
</%block>

<%block name="content">
<div class="saida-container">
    <div class="page-header">
        <h2><i class="bi bi-box-arrow-right me-2"></i>Registro de Saída</h2>
        <p>Adicione itens à lista e registre a saída de uma só vez</p>
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
                </div>
                <div class="d-grid gap-2 mt-2" id="modal-opcoes-rolo" style="display: none;">
                    <button type="button" class="btn btn-lg btn-outline-primary" id="btn-embalagens-rolo">
                        <i class="bi bi-box-seam me-2"></i><strong id="modal-qtd-emb-rolo"></strong> rolo(s)
                        <small class="d-block text-muted" id="modal-total-rolo"></small>
                    </button>
                    <button type="button" class="btn btn-lg btn-outline-secondary" id="btn-metros">
                        <i class="bi bi-rulers me-2"></i><strong id="modal-qtd-metros"></strong> metros
                        <small class="d-block text-muted">(saída em metros)</small>
                    </button>
                    <button type="button" class="btn btn-lg btn-outline-secondary" id="btn-centimetros">
                        <i class="bi bi-rulers me-2"></i><strong id="modal-qtd-centimetros"></strong> cm
                        <small class="d-block text-muted">(convertido para metros)</small>
                    </button>
                </div>
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
<script>
(function() {
    const items = [];
    let itemCounter = 0;
    let pendingItem = null; // Item aguardando escolha de unidade
    const usuariosAutocompleteData = ${tojson(usuarios)|n};
    const itensAutocompleteData = ${tojson(itens)|n};

    function normalizeAutocompleteText(value) {
        return String(value || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .trim();
    }
    
    const inputUsuario = document.getElementById('input-usuario');
    const inputLocal = document.getElementById('input-local');
    const inputCodigo = document.getElementById('input-codigo');
    const inputQuantidade = document.getElementById('input-quantidade');
    const btnAdicionar = document.getElementById('btn-adicionar');
    const btnRegistrar = document.getElementById('btn-registrar');
    const itemsContainer = document.getElementById('items-container');
    const itemsList = document.getElementById('items-list');
    const emptyState = document.getElementById('empty-state');
    const totalBadge = document.getElementById('total-items-badge');
    
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
    const modalOpcoesRolo = document.getElementById('modal-opcoes-rolo');
    const modalQtdEmbRolo = document.getElementById('modal-qtd-emb-rolo');
    const modalTotalRolo = document.getElementById('modal-total-rolo');
    const modalQtdMetros = document.getElementById('modal-qtd-metros');
    const modalQtdCentimetros = document.getElementById('modal-qtd-centimetros');
    const btnEmbalagens = document.getElementById('btn-embalagens');
    const btnUnidades = document.getElementById('btn-unidades');
    const btnEmbalagensRolo = document.getElementById('btn-embalagens-rolo');
    const btnMetros = document.getElementById('btn-metros');
    const btnCentimetros = document.getElementById('btn-centimetros');
    
    const nomesEmbalagem = {
        'lata': { singular: 'lata', plural: 'latas' },
        'rolo': { singular: 'rolo', plural: 'rolos' },
        'pacote': { singular: 'pacote', plural: 'pacotes' },
        'caixa': { singular: 'caixa', plural: 'caixas' },
        'balde': { singular: 'balde', plural: 'baldes' }
    };
    
    const unidadeBaseEmbalagem = {
        'lata': 'litros',
        'rolo': 'metros',
        'pacote': 'unidades',
        'caixa': 'unidades',
        'balde': 'kg'
    };
    
    const dropdownUsuario = document.getElementById('autocomplete-dropdown-usuario');
    const dropdownCodigo = document.getElementById('autocomplete-dropdown-codigo');
    let debounceTimerUsuario = null;
    let debounceTimerCodigo = null;
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
        
        if (query.length < 1) {
            dropdownCodigo.classList.remove('show');
            return;
        }
        
        debounceTimerCodigo = setTimeout(() => {
            const normalizedQuery = normalizeAutocompleteText(query);
            currentItens = itensAutocompleteData.filter(item => {
                const codigo = normalizeAutocompleteText(item.codigo);
                const descricao = normalizeAutocompleteText(item.descricao);
                return codigo.includes(normalizedQuery) || descricao.includes(normalizedQuery);
            }).slice(0, 20);

            showAutocompleteCodigo(currentItens);
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

                // No sistema, `grandeza_referencia` e `litros_por_embalagem` são numéricos.
                // Usamos isso para inferir a unidade interna (kg/L/m/un).
                let unidadeSolta = 'un';
                if (litrosPorEmb > 0) {
                    unidadeSolta = 'L';
                } else if (grandezaRef > 0 && (tipoEmbalagem === 'balde' || tipoEmbalagem === 'lata')) {
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
            return item.saldo ? String(item.saldo) : '';
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
        dropdownCodigo.classList.remove('show');
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
        }
    });
    
    btnUnidades.addEventListener('click', () => {
        if (pendingItem) {
            const unidadeBase = unidadeBaseEmbalagem[pendingItem.tipo_embalagem] || 'unidades';
            const unidadeBaseSafe = String(unidadeBase || 'unidades');
            pendingItem.em_embalagens = false;
            pendingItem.quantidade = pendingItem.quantidade_input;
            pendingItem.unidade_label = unidadeBaseSafe;
            pendingItem.quantidade_exibicao = pendingItem.quantidade_input;
            pendingItem.observacao_unit = 'UNIDADE=' + unidadeBaseSafe.toUpperCase() + ';QTD_ORIGINAL=' + pendingItem.quantidade_input;
            adicionarItemFinal(pendingItem);
            modalUnidade.hide();
            pendingItem = null;
        }
    });

    btnEmbalagensRolo.addEventListener('click', () => {
        if (pendingItem) {
            pendingItem.em_embalagens = true;
            pendingItem.quantidade = pendingItem.quantidade_input;
            pendingItem.unidade_label = pendingItem.quantidade_input === 1 ? 'rolo' : 'rolos';
            pendingItem.quantidade_exibicao = pendingItem.quantidade_input;
            pendingItem.observacao_unit = null;
            adicionarItemFinal(pendingItem);
            modalUnidade.hide();
            pendingItem = null;
        }
    });

    btnMetros.addEventListener('click', () => {
        if (pendingItem) {
            pendingItem.em_embalagens = false;
            pendingItem.quantidade = pendingItem.quantidade_input;
            pendingItem.unidade_label = 'metros';
            pendingItem.quantidade_exibicao = pendingItem.quantidade_input;
            pendingItem.observacao_unit = 'UNIDADE=METROS;QTD_ORIGINAL=' + pendingItem.quantidade_input;
            adicionarItemFinal(pendingItem);
            modalUnidade.hide();
            pendingItem = null;
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
            const response = await fetch('/movimentos/item-info/' + encodeURIComponent(codigo));
            const data = await response.json();
            
            if (!data.descricao) {
                throw new Error('Item não encontrado');
            }
            
            // Verificar se o item usa sistema de embalagens
            if (data.tipo_embalagem_novo && data.unidades_por_embalagem && data.unidades_por_embalagem > 0) {
                // Tem embalagem - mostrar modal
                pendingItem = {
                    id: ++itemCounter,
                    codigo: codigo,
                    descricao: data.descricao,
                    quantidade: quantidade,
                    quantidade_input: quantidade,
                    usuario: usuario,
                    local: local,
                    tipo_embalagem: data.tipo_embalagem_novo,
                    unidades_por_embalagem: data.unidades_por_embalagem,
                    em_embalagens: null
                };
                
                mostrarModalUnidade(pendingItem);
                
            } else {
                // Não tem embalagem - adiciona direto
                adicionarItemFinal({
                    id: ++itemCounter,
                    codigo: codigo,
                    descricao: data.descricao,
                    quantidade: quantidade,
                    usuario: usuario,
                    local: local,
                    em_embalagens: null
                });
            }
            
            // Limpa campos
            inputCodigo.value = '';
            inputQuantidade.value = '1';
            inputCodigo.focus();
            
        } catch (error) {
            alert(error.message || 'Erro ao buscar item');
        } finally {
            btnAdicionar.disabled = false;
            btnAdicionar.innerHTML = '<i class="bi bi-plus-circle me-1"></i>Adicionar Item';
        }
    });
    
    function mostrarModalUnidade(item) {
        const nomes = nomesEmbalagem[item.tipo_embalagem] || { singular: 'embalagem', plural: 'embalagens' };
        const unidadeBase = unidadeBaseEmbalagem[item.tipo_embalagem] || 'unidades';
        const totalUnidades = item.quantidade_input * item.unidades_por_embalagem;
        const isRolo = item.tipo_embalagem === 'rolo';
        
        modalItemDesc.textContent = item.descricao;
        modalQtd.textContent = item.quantidade_input;

        if (isRolo) {
            modalOpcoesPadrao.style.display = 'none';
            modalOpcoesRolo.style.display = 'grid';
            modalQtdEmbRolo.textContent = item.quantidade_input;
            modalTotalRolo.textContent = '= ' + totalUnidades.toFixed(2) + ' metros no total';
            modalQtdMetros.textContent = item.quantidade_input;
            modalQtdCentimetros.textContent = item.quantidade_input;
        } else {
            modalOpcoesPadrao.style.display = 'grid';
            modalOpcoesRolo.style.display = 'none';
            modalQtdEmb.textContent = item.quantidade_input;
            modalQtdUnit.textContent = item.quantidade_input;
            modalNomeEmbPlural.textContent = item.quantidade_input === 1 ? nomes.singular : nomes.plural;
            modalTotalEmb.textContent = '= ' + totalUnidades.toFixed(2) + ' ' + unidadeBase + ' no total';
            modalUnidadeBase.textContent = unidadeBase;
            modalUnidadeDesc.textContent = '(quantidade individual)';
        }
        
        modalUnidade.show();
    }
    
    function adicionarItemFinal(item) {
        items.push(item);
        renderItems();
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
        
        itemsList.innerHTML = items.map(item => 
            '<tr>' +
                '<td><code>' + escapeHtml(item.codigo) + '</code></td>' +
                '<td><strong>' + escapeHtml(item.descricao) + '</strong></td>' +
                '<td class="text-center"><span class="badge-qty">' + (item.quantidade_exibicao || item.quantidade) + (item.unidade_label ? ' ' + item.unidade_label : '') + '</span></td>' +
                '<td class="text-end">' +
                    '<button type="button" class="btn-remove-item" onclick="removeItem(' + item.id + ')">' +
                        '<i class="bi bi-trash me-1"></i>Remover' +
                    '</button>' +
                '</td>' +
            '</tr>'
        ).join('');
    }
    
    window.removeItem = function(id) {
        const index = items.findIndex(item => item.id === id);
        if (index > -1) {
            items.splice(index, 1);
            renderItems();
        }
    };
    
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
            // Preparar payload para envio único
            const payload = {
                usuario: items[0].usuario,
                local_servico: items[0].local,
                itens: items.map(item => ({
                    codigo: item.codigo,
                    quantidade: item.quantidade,
                    observacao: item.observacao_unit || null,
                    em_embalagens: item.em_embalagens
                }))
            };
            
            const response = await fetch('/movimentos/saida-multipla', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            const result = await response.json();
            
            if (result.success) {
                alert('✓ ' + result.message);
                items.length = 0;
                renderItems();
                inputUsuario.value = '';
                inputLocal.value = '';
                inputCodigo.value = '';
                inputQuantidade.value = '1';
                inputUsuario.focus();
            } else {
                const erros = result.resultados
                    ? result.resultados.filter(r => !r.success).map(r => r.codigo + ': ' + r.message).join('\n')
                    : result.message;
                alert('⚠️ Erro:\n' + erros);
            }
        } catch (error) {
            alert('❌ Erro ao registrar saída: ' + error.message);
        } finally {
            btnRegistrar.disabled = false;
            btnRegistrar.innerHTML = '<i class="bi bi-check-circle me-2"></i>Registrar Saída';
        }
    });
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Foco inicial
    inputUsuario.focus();
})();
</script>
</%block>
