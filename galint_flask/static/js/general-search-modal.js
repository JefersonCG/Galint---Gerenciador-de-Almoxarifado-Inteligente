(function () {
    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function formatNumber(value, digits) {
        const parsed = Number(value ?? 0);
        if (!Number.isFinite(parsed)) {
            return '0';
        }
        const maxDigits = typeof digits === 'number' ? digits : 3;
        return parsed.toLocaleString('pt-BR', {
            minimumFractionDigits: 0,
            maximumFractionDigits: maxDigits,
        });
    }

    function buildStatusBadge(statusLabel, statusKind) {
        const badgeClass = statusKind === 'pending' ? 'is-pending' : 'is-resolved';
        return '<span class="general-search-status-badge ' + badgeClass + '">' + escapeHtml(statusLabel || 'Status') + '</span>';
    }

    function buildPeriodBadge(value) {
        return '<span class="general-search-period-badge">' + escapeHtml(value || 'Expediente') + '</span>';
    }

    function buildCustodyBadge(value, kind) {
        const badgeClass = kind === 'permanente' ? 'is-permanent' : '';
        return '<span class="general-search-custody-badge ' + badgeClass + '">' + escapeHtml(value || 'Temporaria') + '</span>';
    }

    async function fetchJson(url, fallbackMessage) {
        const response = window.galintFetchWithAuth
            ? await window.galintFetchWithAuth(url, { headers: { Accept: 'application/json' } }, fallbackMessage)
            : await window.fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });

        if (!response.ok) {
            let message = 'Falha ao carregar a pesquisa geral.';
            try {
                const payload = await response.clone().json();
                message = String(payload?.message || payload?.error || message);
            } catch (error) {
                message = fallbackMessage || message;
            }
            throw new Error(message);
        }
        return response.json();
    }

    function setScopeButtonState(buttons, scope) {
        buttons.forEach((button) => {
            button.classList.toggle('is-active', button.dataset.generalSearchScope === scope);
        });
    }

    function buildSummaryCards(cards) {
        return cards.map((card) => {
            return ''
                + '<article class="general-search-summary-card">'
                + '<small>' + escapeHtml(card.label) + '</small>'
                + '<strong>' + escapeHtml(card.value) + '</strong>'
                + '<span>' + escapeHtml(card.help || '') + '</span>'
                + '</article>';
        }).join('');
    }

    document.addEventListener('DOMContentLoaded', function () {
        const modalEl = document.getElementById('modalPesquisaGeral');
        if (!modalEl || !window.bootstrap) {
            return;
        }

        const modal = new bootstrap.Modal(modalEl);
        const scopeButtons = Array.from(modalEl.querySelectorAll('[data-general-search-scope]'));
        const triggers = Array.from(document.querySelectorAll('[data-general-search-open]'));
        const form = document.getElementById('generalSearchForm');
        const inputLabel = document.getElementById('generalSearchInputLabel');
        const inputHelp = document.getElementById('generalSearchInputHelp');
        const searchInput = document.getElementById('generalSearchInput');
        const searchDate = document.getElementById('generalSearchDate');
        const searchPeriod = document.getElementById('generalSearchPeriod');
        const suggestionsEl = document.getElementById('generalSearchSuggestions');
        const clearBtn = document.getElementById('generalSearchClearBtn');
        const statsEl = document.getElementById('generalSearchStats');
        const resultsEl = document.getElementById('generalSearchResults');
        const emptyStateEl = document.getElementById('generalSearchEmptyState');
        const messageEl = document.getElementById('generalSearchMessage');
        const heroBadgePrimary = document.getElementById('generalSearchHeroBadgePrimary');
        const heroBadgeSecondary = document.getElementById('generalSearchHeroBadgeSecondary');
        const heroTitle = document.getElementById('generalSearchHeroTitle');
        const heroText = document.getElementById('generalSearchHeroText');
        const dateColumn = document.getElementById('generalSearchDateColumn');
        const periodColumn = document.getElementById('generalSearchPeriodColumn');

        const suggestionsUrl = modalEl.dataset.suggestionsUrl;
        const employeeUrlTemplate = modalEl.dataset.employeeUrlTemplate;
        const itemUrlTemplate = modalEl.dataset.itemUrlTemplate;
        const dailyUrl = modalEl.dataset.dailyUrl;

        const scopeMeta = {
            funcionario: {
                inputLabel: 'Buscar colaborador',
                inputPlaceholder: 'Digite nome ou matricula',
                inputHelp: 'Localize a pessoa e carregue historico completo, checklist do dia e pendencias.',
                heroBadgePrimary: 'Consulta de pessoas',
                heroBadgeSecondary: 'Historico completo e pendencias em um painel',
                heroTitle: 'Tudo sobre o colaborador em uma unica leitura',
                heroText: 'A pesquisa carrega identidade, checklist do dia, materiais, ferramentas, devolucoes e linha do tempo operacional sem abrir outras paginas.',
                showDate: false,
                showPeriod: false,
            },
            item: {
                inputLabel: 'Buscar item',
                inputPlaceholder: 'Digite descricao ou codigo',
                inputHelp: 'Localize o item e acompanhe foto, saldo, retiradas, usuarios e resumo por dia.',
                heroBadgePrimary: 'Consulta de itens',
                heroBadgeSecondary: 'Foto, saldo e historico operacional',
                heroTitle: 'O item vira um dossie operacional',
                heroText: 'A leitura por item concentra foto, saldo fisico, movimentacoes, colaboradores envolvidos e um resumo diario sem depender de pagina separada.',
                showDate: false,
                showPeriod: true,
            },
            diario: {
                inputLabel: 'Filtro opcional',
                inputPlaceholder: 'Item, codigo, colaborador, local ou observacao',
                inputHelp: 'Use quando quiser reduzir o dia a um item, colaborador ou detalhe especifico.',
                heroBadgePrimary: 'Conciliacao diaria',
                heroBadgeSecondary: 'Retiradas agrupadas por item no mesmo modal',
                heroTitle: 'A operacao do dia reunida em um unico lugar',
                heroText: 'A visao diaria agrupa as saidas do dia selecionado por item, mantendo foto, total retirado, historico linha a linha e contexto operacional.',
                showDate: true,
                showPeriod: false,
            },
        };

        const state = {
            scope: 'funcionario',
            suggestions: [],
            selectedSuggestion: null,
            suggestionTimer: null,
        };

        function setMessage(text, kind) {
            const normalized = String(text || '').trim();
            if (!normalized) {
                messageEl.className = 'general-search-message d-none';
                messageEl.textContent = '';
                return;
            }
            messageEl.className = 'general-search-message is-' + (kind || 'info');
            messageEl.textContent = normalized;
        }

        function hideSuggestions() {
            state.suggestions = [];
            suggestionsEl.innerHTML = '';
            suggestionsEl.classList.add('d-none');
        }

        function resetResults() {
            statsEl.innerHTML = '';
            statsEl.classList.add('d-none');
            resultsEl.innerHTML = '';
            if (emptyStateEl) {
                resultsEl.appendChild(emptyStateEl);
                emptyStateEl.classList.remove('d-none');
            }
        }

        function setLoading() {
            hideSuggestions();
            if (emptyStateEl) {
                emptyStateEl.classList.add('d-none');
            }
            resultsEl.innerHTML = ''
                + '<div class="general-search-empty-state">'
                + '<div class="spinner-border text-info" role="status"><span class="visually-hidden">Carregando...</span></div>'
                + '<h3>Montando a leitura operacional</h3>'
                + '<p>Consultando historico, agrupamentos e sinais do escopo selecionado.</p>'
                + '</div>';
        }

        function renderSummary(cards) {
            if (!Array.isArray(cards) || !cards.length) {
                statsEl.innerHTML = '';
                statsEl.classList.add('d-none');
                return;
            }
            statsEl.innerHTML = buildSummaryCards(cards);
            statsEl.classList.remove('d-none');
        }

        function applyScope(scope) {
            const nextScope = scopeMeta[scope] ? scope : 'funcionario';
            state.scope = nextScope;
            state.selectedSuggestion = null;
            setScopeButtonState(scopeButtons, nextScope);
            const meta = scopeMeta[nextScope];
            inputLabel.innerHTML = '<i class="bi bi-search"></i> ' + escapeHtml(meta.inputLabel);
            searchInput.placeholder = meta.inputPlaceholder;
            inputHelp.textContent = meta.inputHelp;
            heroBadgePrimary.innerHTML = '<i class="bi bi-compass"></i> ' + escapeHtml(meta.heroBadgePrimary);
            heroBadgeSecondary.innerHTML = '<i class="bi bi-lightning-charge"></i> ' + escapeHtml(meta.heroBadgeSecondary);
            heroTitle.textContent = meta.heroTitle;
            heroText.textContent = meta.heroText;
            dateColumn.classList.toggle('d-none', !meta.showDate);
            periodColumn.classList.toggle('d-none', !meta.showPeriod);
            if (!meta.showDate) {
                searchDate.value = searchDate.value || new Date().toISOString().slice(0, 10);
            }
            if (!meta.showPeriod) {
                searchPeriod.value = '0';
            }
            hideSuggestions();
            setMessage('', 'info');
        }

        function renderSuggestions(results) {
            const rows = Array.isArray(results) ? results : [];
            if (!rows.length) {
                suggestionsEl.innerHTML = '<div class="general-search-suggestion-btn"><div class="general-search-suggestion-title">Nenhum resultado localizado</div><div class="general-search-suggestion-meta"><span>Refine o termo de busca ou mude o foco da consulta.</span></div></div>';
                suggestionsEl.classList.remove('d-none');
                return;
            }
            suggestionsEl.innerHTML = rows.map((row, index) => {
                return ''
                    + '<button type="button" class="general-search-suggestion-btn" data-general-search-suggestion-index="' + String(index) + '">'
                    + '<div class="general-search-suggestion-title">' + escapeHtml(row.title || row.name || row.id || 'Resultado') + '</div>'
                    + '<div class="general-search-suggestion-meta">'
                    + '<span>' + escapeHtml(row.subtitle || '') + '</span>'
                    + '<span>' + escapeHtml(row.badge || '') + '</span>'
                    + '</div>'
                    + '</button>';
            }).join('');
            suggestionsEl.classList.remove('d-none');
            suggestionsEl.querySelectorAll('[data-general-search-suggestion-index]').forEach((button) => {
                button.addEventListener('click', function () {
                    const index = Number(button.dataset.generalSearchSuggestionIndex || '-1');
                    const picked = state.suggestions[index];
                    if (!picked) {
                        return;
                    }
                    state.selectedSuggestion = picked;
                    searchInput.value = picked.title || '';
                    hideSuggestions();
                    void runSearch();
                });
            });
        }

        async function loadSuggestions() {
            if (state.scope === 'diario') {
                hideSuggestions();
                return;
            }
            const query = String(searchInput.value || '').trim();
            if (!query) {
                hideSuggestions();
                return;
            }
            const url = new URL(suggestionsUrl, window.location.origin);
            url.searchParams.set('scope', state.scope);
            url.searchParams.set('q', query);
            try {
                const payload = await fetchJson(url.toString(), 'Nao foi possivel buscar sugestoes agora.');
                state.suggestions = Array.isArray(payload?.results) ? payload.results : [];
                renderSuggestions(state.suggestions);
            } catch (error) {
                setMessage(error?.message || 'Falha ao buscar sugestoes.', 'error');
            }
        }

        function scheduleSuggestions() {
            window.clearTimeout(state.suggestionTimer);
            state.selectedSuggestion = null;
            if (state.scope === 'diario') {
                hideSuggestions();
                return;
            }
            const query = String(searchInput.value || '').trim();
            if (!query) {
                hideSuggestions();
                return;
            }
            state.suggestionTimer = window.setTimeout(function () {
                void loadSuggestions();
            }, 220);
        }

        async function resolveSelection() {
            if (state.scope === 'diario') {
                return null;
            }
            if (state.selectedSuggestion) {
                return state.selectedSuggestion;
            }
            const query = String(searchInput.value || '').trim();
            if (!query) {
                return null;
            }
            const url = new URL(suggestionsUrl, window.location.origin);
            url.searchParams.set('scope', state.scope);
            url.searchParams.set('q', query);
            const payload = await fetchJson(url.toString(), 'Nao foi possivel localizar o registro solicitado.');
            const rows = Array.isArray(payload?.results) ? payload.results : [];
            state.suggestions = rows;
            const queryLower = query.toLowerCase();
            const exact = rows.find((row) => {
                return String(row.matricula || row.codigo_item || row.id || '').toLowerCase() === queryLower;
            });
            return exact || rows[0] || null;
        }

        function renderEmployee(payload) {
            const employee = payload.employee || {};
            const summary = payload.summary || {};
            renderSummary([
                { label: 'Linha do tempo', value: formatNumber(summary.timeline_count, 0), help: 'Eventos consolidados entre retiradas e devolucoes.' },
                { label: 'Total retirado', value: formatNumber(summary.total_withdrawn_quantity, 3), help: 'Soma das quantidades retiradas pelo colaborador.' },
                { label: 'Ferramentas pendentes', value: formatNumber(summary.pending_tools_count, 0), help: 'Retiradas de ferramentas ainda sem devolucao localizada.' },
                { label: 'Checklist do dia', value: formatNumber(summary.today_count, 0), help: 'Itens retirados no dia atual pelo colaborador.' },
            ]);

            const timelineRows = Array.isArray(payload.timeline) && payload.timeline.length
                ? payload.timeline.map((row) => {
                    return ''
                        + '<tr>'
                        + '<td>' + escapeHtml(row.date_label) + '</td>'
                        + '<td>' + escapeHtml(row.time_label) + '</td>'
                        + '<td><strong>' + escapeHtml(row.type_label) + '</strong></td>'
                        + '<td><strong>' + escapeHtml(row.item_description) + '</strong><br><small class="general-search-inline-note">' + escapeHtml(row.item_code) + '</small></td>'
                        + '<td class="text-center"><strong>' + escapeHtml(formatNumber(row.quantity, 3)) + '</strong></td>'
                        + '<td>' + buildPeriodBadge(row.period_label) + '</td>'
                        + '<td>' + escapeHtml(row.context) + '</td>'
                        + '</tr>';
                }).join('')
                : '<tr><td colspan="7" class="text-center py-4">Nenhum evento encontrado para este colaborador.</td></tr>';

            const materialRows = Array.isArray(payload.materials) && payload.materials.length
                ? payload.materials.map((row) => {
                    return ''
                        + '<tr>'
                        + '<td>' + escapeHtml(row.date_label) + '</td>'
                        + '<td>' + escapeHtml(row.time_label) + '</td>'
                        + '<td><strong>' + escapeHtml(row.item_description) + '</strong><br><small class="general-search-inline-note">' + escapeHtml(row.item_code) + '</small></td>'
                        + '<td class="text-center"><strong>' + escapeHtml(formatNumber(row.quantity, 3)) + '</strong></td>'
                        + '<td>' + escapeHtml(row.local) + '</td>'
                        + '<td>' + escapeHtml(row.observation || '-') + '</td>'
                        + '</tr>';
                }).join('')
                : '<tr><td colspan="6" class="text-center py-4">Nenhuma retirada de material registrada.</td></tr>';

            const toolRows = Array.isArray(payload.tools) && payload.tools.length
                ? payload.tools.map((row) => {
                    return ''
                        + '<tr>'
                        + '<td>' + escapeHtml(row.date_label) + '</td>'
                        + '<td>' + escapeHtml(row.time_label) + '</td>'
                        + '<td><strong>' + escapeHtml(row.item_description) + '</strong><br><small class="general-search-inline-note">' + escapeHtml(row.item_code) + '</small></td>'
                        + '<td class="text-center"><strong>' + escapeHtml(formatNumber(row.quantity, 3)) + '</strong></td>'
                        + '<td>' + escapeHtml(row.local) + '</td>'
                        + '<td>' + buildStatusBadge(row.status_label, row.status_kind) + '</td>'
                        + '</tr>';
                }).join('')
                : '<tr><td colspan="6" class="text-center py-4">Nenhuma retirada de ferramenta registrada.</td></tr>';

            const checklistRows = Array.isArray(payload.today_checklist) && payload.today_checklist.length
                ? payload.today_checklist.map((row) => {
                    return ''
                        + '<tr>'
                        + '<td><strong>' + escapeHtml(row.item_description) + '</strong></td>'
                        + '<td>' + escapeHtml(row.item_code) + '</td>'
                        + '<td class="text-center"><strong>' + escapeHtml(formatNumber(row.quantity, 3)) + '</strong></td>'
                        + '</tr>';
                }).join('')
                : '<tr><td colspan="3" class="text-center py-4">Nenhuma retirada localizada hoje.</td></tr>';

            resultsEl.innerHTML = ''
                + '<div class="general-search-result-stack">'
                + '<section class="general-search-surface general-search-employee-hero">'
                + '<div class="general-search-employee-identity">'
                + '<span class="general-search-kicker"><i class="bi bi-person-badge"></i> Colaborador em foco</span>'
                + '<h3>' + escapeHtml(employee.name || 'Funcionario') + '</h3>'
                + '<div class="general-search-meta-row">'
                + '<span class="general-search-meta-pill"><i class="bi bi-upc-scan"></i> ' + escapeHtml(employee.matricula || 'N/D') + '</span>'
                + '<span class="general-search-meta-pill"><i class="bi bi-briefcase"></i> ' + escapeHtml(employee.role || 'N/D') + '</span>'
                + '<span class="general-search-meta-pill"><i class="bi bi-diagram-3"></i> ' + escapeHtml(employee.sector || 'N/D') + '</span>'
                + '</div>'
                + '<p class="mt-3 general-search-inline-note">A consulta combina historico de retiradas, devolucoes identificadas, checklist do dia e pendencias de ferramentas em uma unica leitura operacional.</p>'
                + '</div>'
                + '<div class="general-search-surface">'
                + '<div class="general-search-surface-title">'
                + '<div><h4>Acao rapida</h4><p>Baixe o relatorio historico completo ou siga a linha do tempo abaixo.</p></div>'
                + (payload.download_url ? '<a class="btn btn-outline-info general-search-download-link" href="' + escapeHtml(payload.download_url) + '" target="_blank" rel="noopener"><i class="bi bi-filetype-pdf"></i> Baixar PDF</a>' : '')
                + '</div>'
                + '<div class="general-search-chip-row">'
                + '<span class="general-search-chip"><i class="bi bi-box-seam"></i> Materiais: ' + escapeHtml(formatNumber(summary.materials_count, 0)) + '</span>'
                + '<span class="general-search-chip"><i class="bi bi-tools"></i> Ferramentas: ' + escapeHtml(formatNumber(summary.tools_count, 0)) + '</span>'
                + '<span class="general-search-chip"><i class="bi bi-arrow-counterclockwise"></i> Devolucoes: ' + escapeHtml(formatNumber(summary.returns_count, 0)) + '</span>'
                + '</div>'
                + '</div>'
                + '</section>'

                + '<section class="general-search-surface">'
                + '<div class="general-search-surface-title"><div><h4>Checklist do dia</h4><p>Itens retirados hoje para conferencias rapidas.</p></div></div>'
                + '<div class="general-search-table-wrap">'
                + '<table class="table general-search-table"><thead><tr><th>Item</th><th>Codigo</th><th class="text-center">Qtd.</th></tr></thead><tbody>' + checklistRows + '</tbody></table>'
                + '</div>'
                + '</section>'

                + '<section class="general-search-surface">'
                + '<div class="general-search-surface-title"><div><h4>Linha do tempo consolidada</h4><p>Retiradas e devolucoes em ordem cronologica para leitura completa.</p></div></div>'
                + '<div class="general-search-table-wrap">'
                + '<table class="table general-search-table"><thead><tr><th>Data</th><th>Hora</th><th>Tipo</th><th>Item</th><th class="text-center">Qtd.</th><th>Periodo</th><th>Contexto</th></tr></thead><tbody>' + timelineRows + '</tbody></table>'
                + '</div>'
                + '</section>'

                + '<div class="general-search-grid-two">'
                + '<section class="general-search-surface"><div class="general-search-surface-title"><div><h4>Materiais</h4><p>Historico detalhado de retiradas de materiais.</p></div></div><div class="general-search-table-wrap"><table class="table general-search-table"><thead><tr><th>Data</th><th>Hora</th><th>Item</th><th class="text-center">Qtd.</th><th>Local</th><th>Observacao</th></tr></thead><tbody>' + materialRows + '</tbody></table></div></section>'
                + '<section class="general-search-surface"><div class="general-search-surface-title"><div><h4>Ferramentas</h4><p>Status atual das retiradas de ferramentas.</p></div></div><div class="general-search-table-wrap"><table class="table general-search-table"><thead><tr><th>Data</th><th>Hora</th><th>Ferramenta</th><th class="text-center">Qtd.</th><th>Local</th><th>Status</th></tr></thead><tbody>' + toolRows + '</tbody></table></div></section>'
                + '</div>'
                + '</div>';
        }

        function renderItem(payload) {
            const item = payload.item || {};
            const summary = payload.summary || {};
            renderSummary([
                { label: 'Movimentacoes', value: formatNumber(summary.movement_count, 0), help: 'Retiradas localizadas para o periodo selecionado.' },
                { label: 'Total retirado', value: formatNumber(summary.total_quantity, 3), help: 'Soma das quantidades movimentadas no periodo.' },
                { label: 'Colaboradores', value: formatNumber(summary.users_count, 0), help: 'Pessoas diferentes que retiraram o item.' },
                { label: 'Dias com giro', value: formatNumber(summary.days_count, 0), help: 'Datas em que o item apareceu nas retiradas.' },
            ]);

            const movementRows = Array.isArray(payload.movements) && payload.movements.length
                ? payload.movements.map((row) => {
                    return ''
                        + '<tr>'
                        + '<td>' + escapeHtml(row.date_label) + '</td>'
                        + '<td>' + escapeHtml(row.time_label) + '</td>'
                        + '<td><strong>' + escapeHtml(row.user_name) + '</strong><br><small class="general-search-inline-note">' + escapeHtml(row.user_matricula) + '</small></td>'
                        + '<td class="text-center"><strong>' + escapeHtml(formatNumber(row.quantity, 3)) + '</strong></td>'
                        + '<td>' + buildPeriodBadge(row.period_label) + '</td>'
                        + '<td>' + escapeHtml(row.local_info) + '</td>'
                        + '</tr>';
                }).join('')
                : '<tr><td colspan="6" class="text-center py-4">Nenhuma retirada encontrada para o item neste periodo.</td></tr>';

            const dailyRows = Array.isArray(payload.daily_totals) && payload.daily_totals.length
                ? payload.daily_totals.map((row) => {
                    return ''
                        + '<tr>'
                        + '<td>' + escapeHtml(row.date_label) + '</td>'
                        + '<td class="text-center"><strong>' + escapeHtml(formatNumber(row.movement_count, 0)) + '</strong></td>'
                        + '<td class="text-center"><strong>' + escapeHtml(formatNumber(row.total_quantity, 3)) + '</strong></td>'
                        + '<td class="text-center">' + escapeHtml(formatNumber(row.users_count, 0)) + '</td>'
                        + '</tr>';
                }).join('')
                : '<tr><td colspan="4" class="text-center py-4">Nenhum resumo diario encontrado.</td></tr>';

            const photoPanel = item.photo_url
                ? '<div class="general-search-photo-panel"><img src="' + escapeHtml(item.photo_url) + '" alt="' + escapeHtml(item.descricao || 'Item') + '"></div>'
                : '<div class="general-search-photo-panel"><div class="general-search-photo-placeholder"><i class="bi bi-box-seam"></i><span>Item sem foto cadastrada</span></div></div>';

            resultsEl.innerHTML = ''
                + '<div class="general-search-result-stack">'
                + '<section class="general-search-surface general-search-item-hero">'
                + '<div class="general-search-item-identity">'
                + '<span class="general-search-kicker"><i class="bi bi-box-seam"></i> Item em foco</span>'
                + '<h3>' + escapeHtml(item.descricao || 'Item') + '</h3>'
                + '<div class="general-search-chip-row">'
                + '<span class="general-search-chip"><i class="bi bi-upc"></i> ' + escapeHtml(item.codigo_curto || item.codigo || 'N/D') + '</span>'
                + '<span class="general-search-chip"><i class="bi bi-tags"></i> ' + escapeHtml(item.categoria || 'Sem categoria') + '</span>'
                + '<span class="general-search-chip"><i class="bi bi-award"></i> ' + escapeHtml(item.marca || 'Sem marca') + '</span>'
                + '<span class="general-search-chip"><i class="bi bi-box"></i> Saldo fisico: ' + escapeHtml(formatNumber(item.saldo_atual, 3)) + '</span>'
                + '</div>'
                + '<p class="mt-3 general-search-inline-note">A leitura do item concentra retirada por colaborador, periodo operacional e resumo diario do giro encontrado.</p>'
                + (payload.download_url ? '<a class="btn btn-outline-info general-search-download-link mt-3" href="' + escapeHtml(payload.download_url) + '" target="_blank" rel="noopener"><i class="bi bi-filetype-pdf"></i> Baixar PDF do item</a>' : '')
                + '</div>'
                + photoPanel
                + '</section>'

                + '<section class="general-search-surface">'
                + '<div class="general-search-surface-title"><div><h4>Movimentacoes do item</h4><p>Historico detalhado por colaborador e contexto operacional.</p></div></div>'
                + '<div class="general-search-table-wrap"><table class="table general-search-table"><thead><tr><th>Data</th><th>Hora</th><th>Colaborador</th><th class="text-center">Qtd.</th><th>Periodo</th><th>Local / Observacao</th></tr></thead><tbody>' + movementRows + '</tbody></table></div>'
                + '</section>'

                + '<section class="general-search-surface">'
                + '<div class="general-search-surface-title"><div><h4>Resumo diario do item</h4><p>Datas em que o item apareceu nas retiradas do periodo filtrado.</p></div></div>'
                + '<div class="general-search-table-wrap"><table class="table general-search-table"><thead><tr><th>Data</th><th class="text-center">Mov.</th><th class="text-center">Total</th><th class="text-center">Colab.</th></tr></thead><tbody>' + dailyRows + '</tbody></table></div>'
                + '</section>'
                + '</div>';
        }

        function renderDaily(payload) {
            const summary = payload.summary || {};
            renderSummary([
                { label: 'Itens no dia', value: formatNumber(summary.total_items, 0), help: 'Itens distintos com retirada registrada.' },
                { label: 'Movimentacoes', value: formatNumber(summary.total_movements, 0), help: 'Lancamentos individuais localizados para a data.' },
                { label: 'Total retirado', value: formatNumber(summary.total_quantity, 3), help: 'Soma das quantidades movimentadas no dia.' },
                { label: 'Itens com foto', value: formatNumber(summary.items_with_photo, 0), help: 'Grupos que ja possuem imagem cadastrada.' },
            ]);

            const items = Array.isArray(payload.grouped_items) ? payload.grouped_items : [];
            if (!items.length) {
                resultsEl.innerHTML = ''
                    + '<div class="general-search-empty-state">'
                    + '<i class="bi bi-moon-stars"></i>'
                    + '<h3>Nenhuma retirada encontrada</h3>'
                    + '<p>Nao ha saidas registradas para ' + escapeHtml(payload.selected_date_label || '') + (payload.search_term ? ' com o filtro informado.' : '.') + '</p>'
                    + '</div>';
                return;
            }

            resultsEl.innerHTML = ''
                + '<div class="general-search-result-stack">'
                + items.map((item) => {
                    const photoPanel = item.foto_url
                        ? '<div class="general-search-photo-panel"><img src="' + escapeHtml(item.foto_url) + '" alt="' + escapeHtml(item.descricao || 'Item') + '"></div>'
                        : '<div class="general-search-photo-panel"><div class="general-search-photo-placeholder"><i class="bi bi-box-seam"></i><span>Sem foto cadastrada</span></div></div>';

                    const movementRows = Array.isArray(item.movements) && item.movements.length
                        ? item.movements.map((row) => {
                            return ''
                                + '<tr>'
                                + '<td>' + escapeHtml(row.time_label) + '</td>'
                                + '<td><strong>' + escapeHtml(row.user_name) + '</strong><br><small class="general-search-inline-note">' + escapeHtml(row.user_matricula) + '</small></td>'
                                + '<td class="text-center"><strong>' + escapeHtml(formatNumber(row.quantity, 3)) + '</strong></td>'
                                + '<td>' + buildCustodyBadge(row.custody_label, row.custody_kind) + '</td>'
                                + '<td>' + buildPeriodBadge(row.period_label) + '</td>'
                                + '<td>' + escapeHtml(row.local_info) + '</td>'
                                + '</tr>';
                        }).join('')
                        : '<tr><td colspan="6" class="text-center py-4">Nenhuma retirada encontrada para o item.</td></tr>';

                    return ''
                        + '<article class="general-search-item-card">'
                        + '<div class="general-search-item-heading">'
                        + '<div>'
                        + '<h4>' + escapeHtml(item.descricao || 'Item') + '</h4>'
                        + '<p>Codigo completo: ' + escapeHtml(item.codigo || 'N/D') + '</p>'
                        + '<div class="general-search-chip-row">'
                        + '<span class="general-search-chip"><i class="bi bi-upc"></i> ' + escapeHtml(item.codigo_curto || item.codigo || 'N/D') + '</span>'
                        + '<span class="general-search-chip"><i class="bi bi-tags"></i> ' + escapeHtml(item.categoria || 'Sem categoria') + '</span>'
                        + '<span class="general-search-chip"><i class="bi bi-award"></i> ' + escapeHtml(item.marca || 'Sem marca') + '</span>'
                        + '</div>'
                        + '</div>'
                        + '<div class="general-search-kpi-stack">'
                        + '<span class="general-search-kpi-chip">Total: ' + escapeHtml(formatNumber(item.total_quantity, 3)) + '</span>'
                        + '<span class="general-search-kpi-chip">Mov.: ' + escapeHtml(formatNumber(item.movement_count, 0)) + '</span>'
                        + '<span class="general-search-kpi-chip">Colab.: ' + escapeHtml(formatNumber(item.unique_user_count, 0)) + '</span>'
                        + '</div>'
                        + '</div>'
                        + '<div class="general-search-grid-two">'
                        + photoPanel
                        + '<div class="general-search-table-wrap"><table class="table general-search-table"><thead><tr><th>Hora</th><th>Colaborador</th><th class="text-center">Qtd.</th><th>Custodia</th><th>Periodo</th><th>Local / Observacao</th></tr></thead><tbody>' + movementRows + '</tbody></table></div>'
                        + '</div>'
                        + '</article>';
                }).join('')
                + '</div>';
        }

        async function runSearch() {
            setMessage('', 'info');
            setLoading();

            try {
                if (state.scope === 'diario') {
                    const url = new URL(dailyUrl, window.location.origin);
                    const selectedDate = String(searchDate.value || '').trim() || new Date().toISOString().slice(0, 10);
                    url.searchParams.set('date', selectedDate);
                    const filterQuery = String(searchInput.value || '').trim();
                    if (filterQuery) {
                        url.searchParams.set('search', filterQuery);
                    }
                    const payload = await fetchJson(url.toString(), 'Nao foi possivel carregar a visao diaria.');
                    renderDaily(payload);
                    return;
                }

                const selection = await resolveSelection();
                if (!selection) {
                    resetResults();
                    setMessage('Nenhum resultado localizado para o termo informado.', 'error');
                    return;
                }
                state.selectedSuggestion = selection;
                searchInput.value = selection.title || searchInput.value;

                if (state.scope === 'funcionario') {
                    const url = employeeUrlTemplate.replace('__MATRICULA__', encodeURIComponent(selection.matricula || selection.id || ''));
                    const payload = await fetchJson(url, 'Nao foi possivel carregar o historico do colaborador.');
                    renderEmployee(payload);
                    return;
                }

                const url = new URL(itemUrlTemplate.replace('__CODIGO__', encodeURIComponent(selection.codigo_item || selection.id || '')), window.location.origin);
                url.searchParams.set('period', String(searchPeriod.value || '0'));
                const payload = await fetchJson(url.toString(), 'Nao foi possivel carregar o historico do item.');
                renderItem(payload);
            } catch (error) {
                resetResults();
                setMessage(error?.message || 'Falha ao executar a pesquisa geral.', 'error');
            }
        }

        function resetForm() {
            searchInput.value = '';
            searchPeriod.value = '0';
            searchDate.value = new Date().toISOString().slice(0, 10);
            state.selectedSuggestion = null;
            hideSuggestions();
            setMessage('', 'info');
            resetResults();
        }

        function openWithOptions(options) {
            const data = options || {};
            applyScope(data.scope || 'funcionario');
            searchInput.value = data.query || '';
            searchDate.value = data.date || new Date().toISOString().slice(0, 10);
            searchPeriod.value = data.period || '0';
            state.selectedSuggestion = null;
            modal.show();
            window.setTimeout(function () {
                searchInput.focus();
                if (data.autoSearch) {
                    void runSearch();
                }
            }, 180);
        }

        scopeButtons.forEach((button) => {
            button.addEventListener('click', function () {
                applyScope(button.dataset.generalSearchScope || 'funcionario');
                resetResults();
            });
        });

        triggers.forEach((trigger) => {
            trigger.addEventListener('click', function () {
                openWithOptions({
                    scope: trigger.dataset.generalSearchScope || state.scope,
                    query: trigger.dataset.generalSearchQuery || '',
                    date: trigger.dataset.generalSearchDate || '',
                    period: trigger.dataset.generalSearchPeriod || '0',
                    autoSearch: trigger.dataset.generalSearchAutoSearch === '1',
                });
            });
        });

        form?.addEventListener('submit', function (event) {
            event.preventDefault();
            void runSearch();
        });

        searchInput?.addEventListener('input', function () {
            scheduleSuggestions();
        });

        searchInput?.addEventListener('focus', function () {
            if (searchInput.value.trim() && state.scope !== 'diario' && state.suggestions.length) {
                suggestionsEl.classList.remove('d-none');
            }
        });

        searchInput?.addEventListener('blur', function () {
            window.setTimeout(hideSuggestions, 160);
        });

        clearBtn?.addEventListener('click', function () {
            resetForm();
        });

        modalEl.addEventListener('hidden.bs.modal', function () {
            resetForm();
            applyScope('funcionario');
        });

        applyScope('funcionario');
        resetForm();

        const params = new URLSearchParams(window.location.search || '');
        if (params.get('open_general_search') === '1') {
            const scope = params.get('general_scope') || 'funcionario';
            const query = params.get('general_query') || '';
            const date = params.get('general_date') || '';
            const period = params.get('general_period') || '0';
            openWithOptions({
                scope,
                query,
                date,
                period,
                autoSearch: Boolean(query || date || scope === 'diario'),
            });

            params.delete('open_general_search');
            params.delete('general_scope');
            params.delete('general_query');
            params.delete('general_date');
            params.delete('general_period');
            const cleanedQuery = params.toString();
            const nextUrl = window.location.pathname + (cleanedQuery ? ('?' + cleanedQuery) : '') + window.location.hash;
            window.history.replaceState({}, document.title, nextUrl);
        }
    });
})();