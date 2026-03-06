<%inherit file="/base.mako"/>
<%!
    import json
%>

<%block name="title">Registro de Saída Fracionada</%block>

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

    .card-fracoes {
        background: #1b2333;
        padding: 16px;
        border-radius: 10px;
        border: 1px solid #2f3a4c;
        color: #ffffff;
        margin-top: 20px;
    }

    .titulo-fracoes {
        color: #3b82f6;
        margin-bottom: 10px;
        font-size: 20px;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .rotulo {
        display: block;
        font-size: 14px;
        font-weight: 600;
        color: #ffffff;
        margin-bottom: 6px;
    }

    .info-bloco {
        background: rgba(255, 255, 255, 0.04);
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 16px;
        line-height: 1.5;
    }

    .info-linha {
        margin: 0;
        font-size: 14px;
        color: #d4dde8;
    }

    .info-linha + .info-linha {
        margin-top: 6px;
    }

    .info-titulo {
        color: #8fb5ff;
    }

    .fraction-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 6px;
        margin-bottom: 16px;
    }

    .botao-fracao {
        padding: 8px;
        border-radius: 6px;
        border: 1px solid #3b82f6;
        background: #e0edff;
        color: #0a3d91;
        cursor: pointer;
        font-weight: 600;
        text-align: center;
        transition: background 0.2s, color 0.2s, transform 0.2s;
        width: 100%;
    }

    .botao-fracao:hover,
    .botao-fracao:focus {
        background: #c4dbff;
        color: #083572;
        outline: none;
        transform: translateY(-1px);
    }

    .botao-fracao.selecionada,
    .botao-fracao.active {
        background: linear-gradient(120deg, #2563eb 0%, #3b82f6 100%);
        color: #ffffff;
        border-color: #3b82f6;
    }

    .input-text {
        width: 100%;
        background: #121726;
        border: 1px solid #2f3a4c;
        border-radius: 8px;
        padding: 10px;
        color: #ffffff;
        font-size: 14px;
    }

    .input-text:focus {
        border-color: #4db8ff;
        box-shadow: 0 0 0 0.15rem rgba(77, 184, 255, 0.25);
        outline: none;
    }

    .input-text[readonly] {
        background: #151d2c;
        cursor: default;
    }

    .hint-text {
        display: block;
        margin-top: 4px;
        font-size: 12px;
        color: #9ca9c9;
    }

    .resultado-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 12px;
    }

    .botao-desativar {
        border-color: #4db8ff;
        color: #4db8ff;
    }

    .botao-desativar:hover,
    .botao-desativar:focus {
        background: rgba(77, 184, 255, 0.12);
        border-color: #4db8ff;
        color: #ffffff;
    }

    @media (max-width: 768px) {
        .fraction-grid {
            grid-template-columns: repeat(3, 1fr);
        }
    }

    @media (max-width: 576px) {
        .fraction-grid {
            grid-template-columns: repeat(2, 1fr);
        }
    }
</style>
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
</style>
</%block>

<%block name="content">
<div class="page-header">
    <h2><i class="bi bi-droplet-half me-2"></i>Registro de Saída Fracionada</h2>
    <p>Use esta tela para registrar saídas fracionadas de líquidos. A quantidade é calculada automaticamente pela fração</p>
</div>
<form method="post" action="${url_for('movements.registrar_saida')}" data-liquid-form="true">
    <input type="hidden" name="liquido_habilitado" value="1" data-liquid-field="enabled">
    <input type="hidden" name="liquido_fracao_numerador" data-liquid-field="numerator">
    <input type="hidden" name="liquido_fracao_denominador" data-liquid-field="denominator">
    <div class="row g-3">
        <div class="col-md-4 position-relative">
            <label class="form-label">Crachá/Matrícula</label>
            <input id="input-usuario-fracionada" class="form-control" name="usuario" placeholder="Leia ou digite o crachá ou nome" autocomplete="off" required>
            <div id="autocomplete-dropdown-usuario-fracionada" class="autocomplete-dropdown"></div>
        </div>
        <div class="col-md-4 autocomplete-wrapper position-relative">
            <label class="form-label">Código do item</label>
            <input id="input-codigo-fracionada" class="form-control" name="codigo" placeholder="Digite o nome ou código do item" autocomplete="off" required>
            <div id="autocomplete-dropdown-fracionada" class="autocomplete-dropdown"></div>
        </div>
        <div class="col-md-2">
            <label class="form-label">Quantidade (calculada)</label>
            <input class="form-control" type="number" name="quantidade" value="0" min="0.01" step="0.01" data-liquid-element="quantity" readonly required>
        </div>
        <div class="col-md-2 d-flex align-items-end">
            <button class="btn btn-primary w-100" type="submit">Registrar Saída Fracionada</button>
        </div>
        <div class="col-12">
            <label class="form-check form-switch d-inline-flex align-items-center gap-2 mb-2">
                <input class="form-check-input" type="checkbox" data-liquid-toggle checked>
                <span class="form-check-label" data-liquid-toggle-label>Habilitar cálculo por frações</span>
            </label>
            <small class="form-text text-muted" data-liquid-hint="toggle">Calculadora fracionada ativa.</small>
        </div>
        <div class="col-12" data-liquid-panel>
            <div class="card-fracoes">
                <h3 class="titulo-fracoes">Cálculo por Frações</h3>
                <div class="info-bloco">
                    <p class="info-linha"><span class="info-titulo">Produto selecionado:</span> <span data-liquid-output="produto">-</span></p>
                </div>
                <div class="mb-3">
                    <label class="rotulo" for="tipoProduto">Tipo de produto</label>
                    <select class="input-text" name="liquido_tipo_produto" data-liquid-element="type-select" id="tipoProduto">
                        % for tipo in liquid_types:
                            <option value="${tipo['id']}">${tipo['label']}</option>
                        % endfor
                    </select>
                </div>
                <div class="mb-3">
                    <label class="rotulo">Escolha a fração</label>
                    <div class="fraction-grid" data-liquid-element="fractions">
                        % for frac in liquid_fractions:
                            <button class="botao-fracao" type="button" data-liquid-fraction data-num="${frac[0]}" data-den="${frac[1]}">
                                ${frac[0]}/${frac[1]}
                            </button>
                        % endfor
                    </div>
                </div>
                <div class="mb-3">
                    <label class="rotulo" for="totalEmbalagem">Quantidade total da embalagem</label>
                    <input class="input-text" type="number" min="0.01" step="0.01" name="liquido_total_embalagem" placeholder="Ex.: 18" data-liquid-element="total" id="totalEmbalagem">
                    <small class="hint-text" data-liquid-output="embalagem-unidade">Informe na unidade do item.</small>
                </div>
                <div class="mb-3">
                    <label class="rotulo">Resultado da fração</label>
                    <div class="resultado-grid">
                        <div>
                            <label class="rotulo" for="litrosCalculados">Litros calculados</label>
                            <input class="input-text" type="text" data-liquid-output="litros" id="litrosCalculados" readonly placeholder="-">
                        </div>
                        <div>
                            <label class="rotulo" for="quilosCalculados">Quilos calculados</label>
                            <input class="input-text" type="text" data-liquid-output="quilos" id="quilosCalculados" readonly placeholder="-">
                        </div>
                        <div>
                            <label class="rotulo" for="fracaoAplicada">Fração aplicada</label>
                            <input class="input-text" type="text" data-liquid-output="fracao" id="fracaoAplicada" readonly placeholder="-">
                        </div>
                    </div>
                </div>
                <div class="mb-3">
                    <label class="rotulo" for="quantidadeRestante">Quantidade restante</label>
                    <input class="input-text" type="text" data-liquid-output="restante" id="quantidadeRestante" readonly placeholder="-">
                </div>
                <div class="text-end">
                    <button class="btn btn-outline-secondary btn-sm botao-desativar" type="button" data-liquid-disable>
                        Desativar cálculo por frações
                    </button>
                </div>
            </div>
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

<datalist id="usuario-list">
    % for usuario in usuarios:
        <option value="${usuario.get('nome')} — ${usuario.get('matricula')}">${usuario.get('matricula')}</option>
    % endfor
</datalist>
</%block>

<%block name="scripts">
${parent.scripts()}
<script src="${url_for('static', filename='js/autocomplete-itens.js')}"></script>
<script src="${url_for('static', filename='js/liquid-fractions.js')}"></script>
<script>
    // Inicializar autocomplete
    document.addEventListener('DOMContentLoaded', function() {
        const inputFracionada = document.getElementById('input-codigo-fracionada');
        const dropdownFracionada = document.getElementById('autocomplete-dropdown-fracionada');
        const inputUsuarioFracionada = document.getElementById('input-usuario-fracionada');
        const dropdownUsuarioFracionada = document.getElementById('autocomplete-dropdown-usuario-fracionada');
        
        // Autocomplete de item
        if (inputFracionada && dropdownFracionada) {
            initItemAutocomplete(inputFracionada, dropdownFracionada, '/movimentos/api/buscar-item');
        }
        
        // Autocomplete de usuário
        if (inputUsuarioFracionada && dropdownUsuarioFracionada) {
            initUsuarioAutocompleteFrac(inputUsuarioFracionada, dropdownUsuarioFracionada);
        }
    });
    
    // Função de autocomplete para usuário
    function initUsuarioAutocompleteFrac(inputElement, dropdownElement) {
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
                        showAutocompleteFuncFrac(dropdownElement, currentFuncionarios);
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
                    setActiveFrac(items, currentIndex + 1);
                }
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (currentIndex > 0) {
                    setActiveFrac(items, currentIndex - 1);
                }
            } else if (e.key === 'Enter' && activeItem) {
                e.preventDefault();
                const index = parseInt(activeItem.getAttribute('data-index'));
                selectUsuarioFrac(inputElement, dropdownElement, currentFuncionarios[index]);
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
    
    function showAutocompleteFuncFrac(dropdownElement, funcionarios) {
        if (funcionarios.length === 0) {
            dropdownElement.classList.remove('show');
            return;
        }
        
        dropdownElement.innerHTML = funcionarios.map((func, index) => {
            return '<div class=\"autocomplete-item\" data-index=\"' + index + '\">' +
                '<div class=\"autocomplete-item-title\">' + func.nome + '</div>' +
                '<div class=\"autocomplete-item-details\">Matrícula: ' + func.matricula +
                (func.setor ? ' | Setor: ' + func.setor : '') +
                (func.cargo ? ' | Cargo: ' + func.cargo : '') + '</div>' +
                '</div>';
        }).join('');
        
        dropdownElement.classList.add('show');
        
        dropdownElement.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('click', function() {
                const index = parseInt(this.getAttribute('data-index'));
                const inputElement = dropdownElement.previousElementSibling;
                selectUsuarioFrac(inputElement, dropdownElement, funcionarios[index]);
            });
        });
    }
    
    function selectUsuarioFrac(inputElement, dropdownElement, func) {
        inputElement.value = func.nome + ' — ' + func.matricula;
        dropdownElement.classList.remove('show');
    }
    
    function setActiveFrac(items, index) {
        items.forEach(item => item.classList.remove('active'));
        if (items[index]) {
            items[index].classList.add('active');
            items[index].scrollIntoView({ block: 'nearest' });
        }
    }

    (function () {
        if (window.initLiquidFractionForms) {
            window.initLiquidFractionForms({
                fractions: ${json.dumps(liquid_fractions) | n},
                types: ${json.dumps(liquid_types) | n},
                itemInfoUrlTemplate: "${url_for('movements.item_info', codigo='__codigo__')}"
            });
        }

        const toggle = document.querySelector('[data-liquid-toggle]');
        if (toggle) {
            toggle.checked = true;
            toggle.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }());
</script>
</%block>
