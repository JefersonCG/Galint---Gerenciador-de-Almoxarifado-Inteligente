<%inherit file="/base.mako"/>

<%block name="title">Registro de Saída Fracionada</%block>

<%block name="extra_css">
<style>
    .saida-container {
        max-width: 900px;
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
        <h2><i class="bi bi-droplet-half me-2"></i>Registro de Saída Fracionada</h2>
        <p>Insira manualmente a quantidade pesada para itens fracionados (Lata, Rolo, Pacote, Caixa, Litro)</p>
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

<!-- Modal de Quantidade Manual -->
<div class="modal fade" id="modalQuantidade" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
            <div class="modal-header" style="background: linear-gradient(120deg, #2563eb 0%, #3b82f6 100%); color: white;">
                <h5 class="modal-title"><i class="bi bi-calculator me-2"></i>Quantidade Retirada</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <p class="mb-2">Item: <strong id="modal-item-desc"></strong></p>
                <p class="mb-3">Unidade: <strong id="modal-item-unidade"></strong></p>
                
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
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                <button type="button" class="btn btn-primary" id="btn-confirmar-quantidade">Confirmar</button>
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
    const btnRegistrar = document.getElementById('btn-registrar');
    
    // Modal
    const modalQuantidade = new bootstrap.Modal(document.getElementById('modalQuantidade'));
    const modalItemDesc = document.getElementById('modal-item-desc');
    const modalItemUnidade = document.getElementById('modal-item-unidade');
    const modalQuantidadeInput = document.getElementById('modal-quantidade-input');
    const modalQuantidadeUnidade = document.getElementById('modal-quantidade-unidade');
    const btnConfirmarQuantidade = document.getElementById('btn-confirmar-quantidade');
    
    // Radio buttons de unidade
    const radioKg = document.getElementById('unidade-kg');
    const radioLitro = document.getElementById('unidade-litro');
    const hintUnidade = document.getElementById('hint-unidade');
    
    // Atualizar display da unidade selecionada
    function atualizarUnidadeModal() {
        const unidadeSelecionada = document.querySelector('input[name="unidade-tipo"]:checked').value;
        modalQuantidadeUnidade.textContent = unidadeSelecionada === 'kg' ? 'kg' : 'L';
        hintUnidade.textContent = unidadeSelecionada === 'kg' ? 'ou LITRO' : 'ou KG';
    }
    
    radioKg.addEventListener('change', atualizarUnidadeModal);
    radioLitro.addEventListener('change', atualizarUnidadeModal);
    
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
    
    function showAutocompleteCodigo(itens) {
        if (itens.length === 0) {
            dropdownCodigo.classList.remove('show');
            return;
        }
        
        dropdownCodigo.innerHTML = itens.map((item, index) => {
            return '<div class=\"autocomplete-item\" data-index=\"' + index + '\">' +
                '<div class=\"autocomplete-item-title\">' + (item.descricao || item.codigo) + '</div>' +
                '<div class=\"autocomplete-item-details\">' +
                '<span class=\"autocomplete-item-code\">Código: ' + item.codigo + '</span>' +
                (item.saldo !== undefined ? ' | Saldo: ' + item.saldo : '') +
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
            
            // Verificar se é item fracionável (Lata, Rolo, Pacote, Caixa, Litro)
            const tiposFracionaveis = ['lata', 'rolo', 'pacote', 'caixa', 'litro'];
            if (data.tipo_embalagem_novo && tiposFracionaveis.includes(data.tipo_embalagem_novo.toLowerCase())) {
                // Abre modal para entrada manual
                pendingItem = {
                    codigo: codigo,
                    descricao: data.descricao,
                    unidade: data.unidade || 'un',
                    usuario: usuario,
                    local: local
                };
                
                mostrarModalQuantidade(pendingItem);
                
            } else {
                // Item não fracionável - não pode usar esta tela
                alert('Este item não requer entrada fracionada. Use a tela de "Registro de Saída" normal.');
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
        
        // Resetar para KG por padrão
        radioKg.checked = true;
        atualizarUnidadeModal();
        
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
    
    // Foco inicial
    inputUsuario.focus();
})();
</script>
</%block>
