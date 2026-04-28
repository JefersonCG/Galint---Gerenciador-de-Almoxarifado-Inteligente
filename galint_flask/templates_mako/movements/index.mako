<%inherit file="/base.mako"/>
<%!
    import json
%>

<%block name="title">Lançamentos</%block>

<%block name="extra_css">
<link rel="stylesheet" href="${url_for('static', filename='css/autocomplete.css')}">
<style>
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
    
    .autocomplete-wrapper {
        position: relative;
    }
</style>
</%block>

<%block name="content">
<div class="d-flex justify-content-between align-items-center mb-3">
    <div>
        <p class="text-muted mb-1">Registro de movimentações</p>
        <h2 class="fw-bold">Controle de Saídas e Devoluções</h2>
    </div>
    <span class="tag-pill">Bip conectado</span>
</div>
<p class="text-muted">
    Para registrar, aproxime o crachá do leitor (QR Code com a matrícula) e o código do item.
    As seções abaixo exibem os últimos registros e mantêm a separação de Saídas e Devoluções.
</p>

<div class="movement-stack">
    <section class="movement-panel mb-4">
        <div class="panel-header mb-3">
            <h3 class="mb-0">Registro de Saída</h3>
            <small class="text-muted">Bipe confirmado após cada envio.</small>
        </div>
        % if can_manage:
        <form class="scan-form" method="post" action="${url_for('movements.registrar_saida')}">
            <input type="hidden" name="liquido_habilitado" value="0">
            <div class="row g-3">
                <div class="col-md-4 autocomplete-wrapper">
                    <label class="form-label">Crachá/Matrícula</label>
                    <input id="input-usuario-saida" class="form-control" name="usuario" list="usuario-list"
                        placeholder="Leia ou digite o crachá ou nome" autocomplete="off" required>
                    <div id="autocomplete-dropdown-usuario-saida" class="autocomplete-dropdown"></div>
                </div>
                <div class="col-md-4 autocomplete-wrapper">
                    <label class="form-label">Código do item</label>
                    <input id="input-codigo-saida" class="form-control" name="codigo" list="item-list"
                        placeholder="Digite o nome ou código do item" autocomplete="off" required>
                    <div id="autocomplete-dropdown-saida" class="autocomplete-dropdown"></div>
                </div>
                <div class="col-md-2">
                    <label class="form-label">Quantidade</label>
                    <input class="form-control" type="number" name="quantidade" value="1" min="0.01" step="0.01" required>
                </div>
                <div class="col-md-2 d-flex align-items-end">
                    <button class="btn btn-primary w-100" type="submit">Registrar Saída</button>
                </div>

                <div class="col-12">
                    <label class="form-label">Local do Serviço / Finalidade</label>
                    <textarea name="local_servico" id="local_servico" class="form-control" rows="3"
                        placeholder="Onde o material será utilizado? (Ex: Instalação elétrica no bloco 5, Serra granito no hall de entrada)"></textarea>
                    <small class="form-text text-muted">
                        <i class="bi bi-info-circle"></i> Opcional, mas recomendado para rastreabilidade.
                    </small>
                </div>
            </div>
        </form>
        % else:
        <div class="alert alert-info mb-0" role="alert">
            Apenas administradores podem registrar novas saídas.
        </div>
        % endif
        <div class="mt-4">
            <h4 class="h6 text-uppercase text-muted">Últimas saídas</h4>
            <div class="table-responsive">
                <table class="table table-dark table-striped mb-0">
                    <thead>
                        <tr>
                            <th>Usuário</th>
                            <th>Matrícula</th>
                            <th>Item</th>
                            <th>Qtd.</th>
                            <th>Data</th>
                        </tr>
                    </thead>
                    <tbody>
                        % if saidas:
                            % for saida in saidas[:6]:
                                <tr>
                                    <td>${saida.get('usuario') or '-'}</td>
                                    <td>${saida.get('matricula') or '-'}</td>
                                    <td>${saida.get('descricao') or saida.get('codigo')}</td>
                                    <td>${saida.get('quantidade')}</td>
                                    <td>${saida.get('data')}</td>
                                </tr>
                            % endfor
                        % else:
                            <tr>
                                <td colspan="5" class="text-center text-muted">Nenhuma saída recente.</td>
                            </tr>
                        % endif
                    </tbody>
                </table>
            </div>
        </div>
    </section>

    <section class="movement-panel">
        <div class="panel-header mb-3">
            <h3 class="mb-0">Registro de Devolução</h3>
            <small class="text-muted">Observações são registradas junto à entrada.</small>
        </div>
        % if can_manage:
        <form class="scan-form" method="post" action="${url_for('movements.registrar_entrada')}">
            <div class="row g-3">
                <div class="col-md-4 autocomplete-wrapper">
                    <label class="form-label">Crachá/Matrícula</label>
                    <input id="input-usuario-devolucao" class="form-control" name="usuario"
                        placeholder="Leia ou digite o crachá ou nome" autocomplete="off" required>
                    <div id="autocomplete-dropdown-usuario-devolucao" class="autocomplete-dropdown"></div>
                </div>
                <div class="col-md-4 autocomplete-wrapper">
                    <label class="form-label">Código do item</label>
                    <input id="input-codigo-devolucao" class="form-control" name="codigo"
                        placeholder="Digite o nome ou código do item" autocomplete="off" required>
                    <div id="autocomplete-dropdown-devolucao" class="autocomplete-dropdown"></div>
                </div>
                <div class="col-md-2">
                    <label class="form-label">Quantidade</label>
                    <input class="form-control" type="number" name="quantidade" value="1" min="1" required>
                </div>
                <div class="col-md-2 d-flex align-items-end">
                    <button class="btn btn-success w-100" type="submit">Registrar Devolução</button>
                </div>
            </div>
        </form>
        % else:
        <div class="alert alert-info mb-0" role="alert">
            Apenas administradores podem registrar novas entradas.
        </div>
        % endif
        <div class="mt-4">
            <h4 class="h6 text-uppercase text-muted">Últimas devoluções</h4>
            <div class="table-responsive">
                <table class="table table-dark table-striped mb-0">
                    <thead>
                        <tr>
                            <th>Usuário</th>
                            <th>Matrícula</th>
                            <th>Item</th>
                            <th>Qtd.</th>
                            <th>Observação</th>
                            <th>Data</th>
                        </tr>
                    </thead>
                    <tbody>
                        % if entradas:
                            % for entrada in entradas[:6]:
                                <tr>
                                    <td>${entrada.get('usuario') or '-'}</td>
                                    <td>${entrada.get('matricula') or '-'}</td>
                                    <td>${entrada.get('descricao') or entrada.get('codigo')}</td>
                                    <td>${entrada.get('quantidade')}</td>
                                    <td>${entrada.get('nota_fiscal') or '-'}</td>
                                    <td>${entrada.get('data')}</td>
                                </tr>
                            % endfor
                        % else:
                            <tr>
                                <td colspan="6" class="text-center text-muted">Nenhuma entrada recente.</td>
                            </tr>
                        % endif
                    </tbody>
                </table>
            </div>
        </div>
    </section>
</div>

<datalist id="usuario-list">
    % for usuario in usuarios:
        <option value="${usuario.get('nome')} — ${usuario.get('matricula')}">${usuario.get('matricula')}</option>
    % endfor
</datalist>
<datalist id="item-list">
    % for item in itens:
        <option value="${item.get('codigo')}">${item.get('descricao')}</option>
    % endfor
</datalist>

<!-- Modal para escolher tipo de unidade (embalagens vs unidades) -->
<div class="modal fade" id="modalUnidade" tabindex="-1" aria-labelledby="modalUnidadeLabel" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content bg-dark text-white">
            <div class="modal-header border-secondary">
                <h5 class="modal-title" id="modalUnidadeLabel">
                    <i class="bi bi-box-seam me-2"></i>Escolher Tipo de Unidade
                </h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <div class="alert alert-info mb-3">
                    <strong id="itemNomeModal"></strong>
                    <div class="mt-2">
                        <small id="itemInfoModal" class="text-muted"></small>
                    </div>
                </div>
                <p class="mb-3">Este item usa sistema de embalagens. Você deseja registrar a devolução em:</p>
                <div class="d-grid gap-2" id="modal-opcoes-padrao">
                    <button type="button" class="btn btn-lg btn-primary" onclick="confirmarUnidade('embalagem')">
                        <i class="bi bi-boxes me-2"></i>
                        <span id="btnEmbalagemText">Embalagens</span>
                    </button>
                    <button type="button" class="btn btn-lg btn-outline-light" onclick="confirmarUnidade('unidade')">
                        <i class="bi bi-box me-2"></i>
                        <span id="btnUnidadeBase">Unidades soltas</span>
                    </button>
                </div>
                <div class="d-grid gap-2 mt-2" id="modal-opcoes-rolo" style="display: none;">
                    <button type="button" class="btn btn-lg btn-primary" onclick="confirmarUnidade('embalagem')">
                        <i class="bi bi-boxes me-2"></i>
                        <span id="btnRoloText">Rolos</span>
                    </button>
                    <button type="button" class="btn btn-lg btn-outline-light" onclick="confirmarUnidade('metros')">
                        <i class="bi bi-rulers me-2"></i>
                        Metros
                    </button>
                    <button type="button" class="btn btn-lg btn-outline-light" onclick="confirmarUnidade('centimetros')">
                        <i class="bi bi-rulers me-2"></i>
                        Centímetros
                    </button>
                </div>
            </div>
        </div>
    </div>
</div>

</%block>

<%block name="scripts">
${parent.scripts()}
<script src="${url_for('static', filename='js/autocomplete-itens.js')}"></script>
<script>
    let itemEmbalagemAtual = null;
    let formEntradaAtual = null;
    let quantidadeOriginal = null;

    // Inicializar autocomplete
    document.addEventListener('DOMContentLoaded', function() {
        const inputSaida = document.getElementById('input-codigo-saida');
        const dropdownSaida = document.getElementById('autocomplete-dropdown-saida');
        const inputDevolucao = document.getElementById('input-codigo-devolucao');
        const dropdownDevolucao = document.getElementById('autocomplete-dropdown-devolucao');
        
        const inputUsuarioSaida = document.getElementById('input-usuario-saida');
        const dropdownUsuarioSaida = document.getElementById('autocomplete-dropdown-usuario-saida');
        const inputUsuarioDevolucao = document.getElementById('input-usuario-devolucao');
        const dropdownUsuarioDevolucao = document.getElementById('autocomplete-dropdown-usuario-devolucao');
        
        // Autocomplete de item
        if (inputSaida && dropdownSaida) {
            initItemAutocomplete(inputSaida, dropdownSaida, '/movimentos/api/buscar-item?only_available=1', {
                hideUnavailable: true,
                unavailableEmptyMessage: 'Nenhum item disponível para saída.'
            });
        }
        
        if (inputDevolucao && dropdownDevolucao) {
            initItemAutocomplete(inputDevolucao, dropdownDevolucao, '/movimentos/api/buscar-item');
        }
        
        // Autocomplete de usuário
        if (inputUsuarioSaida && dropdownUsuarioSaida) {
            initUsuarioAutocomplete(inputUsuarioSaida, dropdownUsuarioSaida);
        }
        
        if (inputUsuarioDevolucao && dropdownUsuarioDevolucao) {
            initUsuarioAutocomplete(inputUsuarioDevolucao, dropdownUsuarioDevolucao);
        }
    });
    
    // Função de autocomplete para usuário
    function initUsuarioAutocomplete(inputElement, dropdownElement) {
        let debounceTimer = null;
        let currentFuncionarios = [];
        
        inputElement.addEventListener('input', function() {
            const query = this.value.trim();
            clearTimeout(debounceTimer);
            
            if (query.length < 1) {
                dropdownElement.classList.remove('show');
                return;
            }
            
            debounceTimer = setTimeout(async () => {
                try {
                    const response = await fetch('/ferramentas/buscar-funcionario?q=' + encodeURIComponent(query));
                    if (response.ok) {
                        const data = await response.json();
                        currentFuncionarios = data.funcionarios || [];
                        showAutocompleteUsuario(dropdownElement, currentFuncionarios);
                    }
                } catch (error) {
                    console.error('Erro ao buscar funcionário:', error);
                }
            }, 300);
        });
        
        // Keyboard navigation
        inputElement.addEventListener('keydown', function(e) {
            const items = dropdownElement.querySelectorAll('.autocomplete-item');
            const activeItem = dropdownElement.querySelector('.autocomplete-item.active');
            let currentIndex = -1;
            
            if (activeItem) {
                currentIndex = Array.from(items).indexOf(activeItem);
            }
            
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                if (currentIndex < items.length - 1) {
                    setActive(items, currentIndex + 1);
                }
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (currentIndex > 0) {
                    setActive(items, currentIndex - 1);
                }
            } else if (e.key === 'Enter' && activeItem) {
                e.preventDefault();
                const index = parseInt(activeItem.getAttribute('data-index'));
                selectUsuario(inputElement, dropdownElement, currentFuncionarios[index]);
            } else if (e.key === 'Escape') {
                dropdownElement.classList.remove('show');
            }
        });
        
        // Click fora fecha dropdown
        document.addEventListener('click', function(e) {
            if (e.target !== inputElement && !dropdownElement.contains(e.target)) {
                dropdownElement.classList.remove('show');
            }
        });
    }
    
    function showAutocompleteUsuario(dropdownElement, funcionarios) {
        if (funcionarios.length === 0) {
            dropdownElement.classList.remove('show');
            return;
        }
        
        dropdownElement.innerHTML = funcionarios.map((func, index) => {
            return '<div class="autocomplete-item" data-index="' + index + '">' +
                '<div class="autocomplete-item-title">' + func.nome + '</div>' +
                '<div class="autocomplete-item-details">Matrícula: ' + func.matricula +
                (func.setor ? ' | Setor: ' + func.setor : '') +
                (func.cargo ? ' | Cargo: ' + func.cargo : '') + '</div>' +
                '</div>';
        }).join('');
        
        dropdownElement.classList.add('show');
        
        dropdownElement.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('click', function() {
                const index = parseInt(this.getAttribute('data-index'));
                const inputElement = dropdownElement.previousElementSibling;
                selectUsuario(inputElement, dropdownElement, funcionarios[index]);
            });
        });
    }
    
    function selectUsuario(inputElement, dropdownElement, func) {
        inputElement.value = func.nome + ' — ' + func.matricula;
        dropdownElement.classList.remove('show');
    }
    
    function setActive(items, index) {
        items.forEach(item => item.classList.remove('active'));
        if (items[index]) {
            items[index].classList.add('active');
            items[index].scrollIntoView({ block: 'nearest' });
        }
    }

    const unidadeBaseEmbalagem = {
        'lata': 'litros',
        'bombona': 'litros',
        'rolo': 'metros',
        'pacote': 'unidades',
        'caixa': 'unidades',
        'litro': 'litros',
        'balde': 'kg'
    };

    function playBeep() {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.frequency.value = 880;
        gain.gain.value = 0.2;
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        setTimeout(() => {
            osc.stop();
            ctx.close();
        }, 120);
    }

    // Interceptar envio do formulário de entrada
    document.querySelectorAll('.scan-form').forEach((form) => {
        form.addEventListener('submit', function(e) {
            const actionUrl = form.getAttribute('action');
            
            // Só interceptar formulário de entrada/devolução
            if (actionUrl && actionUrl.includes('registrar_entrada')) {
                e.preventDefault();
                formEntradaAtual = form;
                
                const codigoInput = form.querySelector('input[name="codigo"]');
                const codigo = codigoInput ? codigoInput.value : '';
                
                if (codigo) {
                    // Buscar informações do item
                    fetch('/movimentos/item-info/' + encodeURIComponent(codigo))
                        .then(response => response.json())
                        .then(data => {
                            if (data.tipo_embalagem_novo) {
                                // Item usa embalagem - mostrar modal
                                itemEmbalagemAtual = data;
                                mostrarModalUnidadeEntrada(data);
                            } else {
                                // Item não usa embalagem - submeter direto
                                formEntradaAtual.submit();
                                playBeep();
                            }
                        })
                        .catch(error => {
                            console.error('Erro ao buscar item:', error);
                            // Em caso de erro, submeter mesmo assim
                            formEntradaAtual.submit();
                            playBeep();
                        });
                } else {
                    form.submit();
                    playBeep();
                }
            } else {
                playBeep();
            }
        });
    });

    function mostrarModalUnidadeEntrada(item) {
        const unidadeBase = unidadeBaseEmbalagem[item.tipo_embalagem_novo] || 'unidades';
        document.getElementById('itemNomeModal').textContent = item.descricao;
        document.getElementById('itemInfoModal').textContent = 
            'Embalagem: ' + item.tipo_embalagem_novo + ' (' + item.unidades_por_embalagem + ' ' + unidadeBase + ' por ' + item.tipo_embalagem_novo + ')';
        
        const btnText = document.getElementById('btnEmbalagemText');
        btnText.textContent = item.tipo_embalagem_novo + 's';
        const btnUnidadeBase = document.getElementById('btnUnidadeBase');
        if (btnUnidadeBase) {
            btnUnidadeBase.textContent = unidadeBase;
        }

        const opcoesPadrao = document.getElementById('modal-opcoes-padrao');
        const opcoesRolo = document.getElementById('modal-opcoes-rolo');
        const isRolo = item.tipo_embalagem_novo === 'rolo';
        if (opcoesPadrao && opcoesRolo) {
            opcoesPadrao.style.display = isRolo ? 'none' : 'grid';
            opcoesRolo.style.display = isRolo ? 'grid' : 'none';
        }
        if (isRolo) {
            const btnRoloText = document.getElementById('btnRoloText');
            if (btnRoloText) {
                btnRoloText.textContent = 'Rolos';
            }
        }
        
        const modal = new bootstrap.Modal(document.getElementById('modalUnidade'));
        modal.show();
    }

    function confirmarUnidade(modo) {
        if (!formEntradaAtual) return;

        const quantidadeInput = formEntradaAtual.querySelector('input[name="quantidade"]');
        if (!quantidadeOriginal && quantidadeInput) {
            quantidadeOriginal = quantidadeInput.value;
        }
        let quantidadeFinal = quantidadeInput ? parseFloat(quantidadeInput.value || '0') : 0;
        let tipoEntrada = 'unidades';

        if (modo === 'embalagem') {
            tipoEntrada = 'embalagem';
        } else if (modo === 'centimetros') {
            // converter cm -> metros
            quantidadeFinal = quantidadeFinal / 100;
        }
        
        if (quantidadeInput && Number.isFinite(quantidadeFinal) && quantidadeFinal > 0) {
            quantidadeInput.value = quantidadeFinal.toString();
        }
        
        // Adicionar campo hidden com a escolha (compatível com movements.registrar_entrada)
        const hiddenInput = document.createElement('input');
        hiddenInput.type = 'hidden';
        hiddenInput.name = 'tipo_entrada';
        hiddenInput.value = tipoEntrada;
        formEntradaAtual.appendChild(hiddenInput);
        
        // Fechar modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('modalUnidade'));
        if (modal) {
            modal.hide();
        }
        
        // Submeter formulário
        formEntradaAtual.submit();
        playBeep();
        
        // Limpar estado
        itemEmbalagemAtual = null;
        formEntradaAtual = null;
        quantidadeOriginal = null;
    }

</script>

</%block>
