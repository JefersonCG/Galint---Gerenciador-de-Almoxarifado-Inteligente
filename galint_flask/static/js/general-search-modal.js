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

    function getLocalDateInputValue(referenceDate) {
        const source = referenceDate instanceof Date ? new Date(referenceDate.getTime()) : new Date();
        if (Number.isNaN(source.getTime())) {
            return '';
        }
        const year = String(source.getFullYear());
        const month = String(source.getMonth() + 1).padStart(2, '0');
        const day = String(source.getDate()).padStart(2, '0');
        return year + '-' + month + '-' + day;
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

    function buildTableWrapper(headMarkup, bodyMarkup) {
        return ''
            + '<div class="general-search-table-wrap">'
            + '<table class="table general-search-table">'
            + '<thead>' + headMarkup + '</thead>'
            + '<tbody>' + bodyMarkup + '</tbody>'
            + '</table>'
            + '</div>';
    }

    function buildExpandableSection(title, description, badgeText, content, isOpen, extraClass) {
        return ''
            + '<details class="general-search-expandable' + (extraClass ? ' ' + extraClass : '') + '"' + (isOpen ? ' open' : '') + '>'
            + '<summary class="general-search-expandable-summary">'
            + '<div class="general-search-expandable-copy">'
            + '<h4>' + escapeHtml(title || '') + '</h4>'
            + (description ? '<p>' + escapeHtml(description) + '</p>' : '')
            + '</div>'
            + '<div class="general-search-expandable-meta">'
            + (badgeText ? '<span class="general-search-expandable-badge">' + escapeHtml(badgeText) + '</span>' : '')
            + '<span class="general-search-expandable-icon" aria-hidden="true"><i class="bi bi-chevron-down"></i></span>'
            + '</div>'
            + '</summary>'
            + '<div class="general-search-expandable-body">' + (content || '') + '</div>'
            + '</details>';
    }

    function buildPhotoPanel(photoUrl, altText, extraClass) {
        const normalizedUrl = String(photoUrl || '').trim();
        if (!normalizedUrl) {
            return '';
        }
        return ''
            + '<figure class="general-search-photo-panel' + (extraClass ? ' ' + extraClass : '') + '">'
            + '<img src="' + escapeHtml(normalizedUrl) + '" alt="' + escapeHtml(altText || 'Item') + '" loading="lazy">'
            + '</figure>';
    }

    function setResultsMode(modalEl, enabled) {
        modalEl.classList.toggle('is-results-mode', Boolean(enabled));
    }

    function wireExpandableAccordions(root) {
        if (!root) {
            return;
        }
        root.querySelectorAll('.general-search-expandable').forEach((detailsEl) => {
            if (detailsEl.dataset.accordionBound === '1') {
                return;
            }
            detailsEl.dataset.accordionBound = '1';
            detailsEl.addEventListener('toggle', function () {
                if (!detailsEl.open) {
                    return;
                }
                const parent = detailsEl.parentElement;
                if (!parent) {
                    return;
                }
                parent.querySelectorAll(':scope > .general-search-expandable[open]').forEach((sibling) => {
                    if (sibling !== detailsEl) {
                        sibling.open = false;
                    }
                });
            });
        });
    }

    function initializeGeneralSearchModal() {
        const modalEl = document.getElementById('modalPesquisaGeral');
        if (!modalEl || !window.bootstrap) {
            return;
        }
        if (modalEl.dataset.generalSearchInitialized === '1') {
            return;
        }
        modalEl.dataset.generalSearchInitialized = '1';

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
                inputPlaceholder: 'Digite nome ou matrícula',
                inputHelp: 'Localize a pessoa e carregue histórico completo, checklist do dia e pendências.',
                heroBadgePrimary: 'Consulta de pessoas',
                heroBadgeSecondary: 'Histórico completo e pendências em um painel',
                heroTitle: 'Tudo sobre o colaborador em uma única leitura',
                heroText: 'A pesquisa carrega identidade, checklist do dia, materiais, ferramentas, devoluções e linha do tempo operacional sem abrir outras páginas.',
                showDate: false,
                showPeriod: false,
            },
            item: {
                inputLabel: 'Buscar item',
                inputPlaceholder: 'Digite descrição ou código',
                inputHelp: 'Localize o item e acompanhe foto, saldo, retiradas, usuários e resumo por dia.',
                heroBadgePrimary: 'Consulta de itens',
                heroBadgeSecondary: 'Foto, saldo e histórico operacional',
                heroTitle: 'O item vira um dossie operacional',
                heroText: 'A leitura por item concentra foto, saldo físico, movimentações, colaboradores envolvidos e um resumo diário sem depender de página separada.',
                showDate: false,
                showPeriod: true,
            },
            diario: {
                inputLabel: 'Filtro opcional',
                inputPlaceholder: 'Item, código, colaborador, local ou observação',
                inputHelp: 'Use quando quiser reduzir o dia a um item, colaborador ou detalhe específico.',
                heroBadgePrimary: 'Conciliação diária',
                heroBadgeSecondary: 'Retiradas agrupadas por item no mesmo modal',
                heroTitle: 'A operação do dia reunida em um único lugar',
                heroText: 'A visão diária agrupa as saídas do dia selecionado por item, mantendo foto, total retirado, histórico linha a linha e contexto operacional.',
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
            setResultsMode(modalEl, false);
            statsEl.innerHTML = '';
            statsEl.classList.add('d-none');
            resultsEl.innerHTML = '';
            if (emptyStateEl) {
                resultsEl.appendChild(emptyStateEl);
                emptyStateEl.classList.remove('d-none');
            }
        }

        function setLoading() {
            setResultsMode(modalEl, false);
            hideSuggestions();
            if (emptyStateEl) {
                emptyStateEl.classList.add('d-none');
            }
            resultsEl.innerHTML = ''
                + '<div class="general-search-empty-state">'
                + '<div class="spinner-border text-info" role="status"><span class="visually-hidden">Carregando...</span></div>'
                + '<h3>Montando a leitura operacional</h3>'
                + '<p>Consultando histórico, agrupamentos e sinais do escopo selecionado.</p>'
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
                searchDate.value = searchDate.value || getLocalDateInputValue();
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
                const payload = await fetchJson(url.toString(), 'Não foi possível buscar sugestões agora.');
                state.suggestions = Array.isArray(payload?.results) ? payload.results : [];
                renderSuggestions(state.suggestions);
            } catch (error) {
                setMessage(error?.message || 'Falha ao buscar sugestões.', 'error');
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
            const payload = await fetchJson(url.toString(), 'Não foi possível localizar o registro solicitado.');
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
            setResultsMode(modalEl, true);
            renderSummary([
                { label: 'Linha do tempo', value: formatNumber(summary.timeline_count, 0), help: 'Eventos consolidados entre retiradas e devoluções.' },
                { label: 'Total retirado', value: formatNumber(summary.total_withdrawn_quantity, 3), help: 'Soma das quantidades retiradas pelo colaborador.' },
                { label: 'Ferramentas pendentes', value: formatNumber(summary.pending_tools_count, 0), help: 'Retiradas de ferramentas ainda sem devolução localizada.' },
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

            const checklistTable = buildTableWrapper(
                '<tr><th>Item</th><th>Código</th><th class="text-center">Qtd.</th></tr>',
                checklistRows
            );
            const timelineTable = buildTableWrapper(
                '<tr><th>Data</th><th>Hora</th><th>Tipo</th><th>Item</th><th class="text-center">Qtd.</th><th>Período</th><th>Contexto</th></tr>',
                timelineRows
            );
            const materialsTable = buildTableWrapper(
                '<tr><th>Data</th><th>Hora</th><th>Item</th><th class="text-center">Qtd.</th><th>Local</th><th>Observação</th></tr>',
                materialRows
            );
            const toolsTable = buildTableWrapper(
                '<tr><th>Data</th><th>Hora</th><th>Ferramenta</th><th class="text-center">Qtd.</th><th>Local</th><th>Status</th></tr>',
                toolRows
            );

            resultsEl.innerHTML = ''
                + '<div class="general-search-result-stack">'
                + '<section class="general-search-employee-hero">'
                + '<div class="general-search-surface general-search-hero-pane general-search-employee-identity">'
                + '<span class="general-search-kicker"><i class="bi bi-person-badge"></i> Colaborador em foco</span>'
                + '<h3>' + escapeHtml(employee.name || 'Funcionário') + '</h3>'
                + '<div class="general-search-meta-row">'
                + '<span class="general-search-meta-pill"><i class="bi bi-upc-scan"></i> Matrícula: ' + escapeHtml(employee.matricula || 'N/D') + '</span>'
                + '<span class="general-search-meta-pill"><i class="bi bi-briefcase"></i> ' + escapeHtml(employee.role || 'N/D') + '</span>'
                + '<span class="general-search-meta-pill"><i class="bi bi-diagram-3"></i> ' + escapeHtml(employee.sector || 'N/D') + '</span>'
                + '</div>'
                + '<p class="mt-3 general-search-inline-note">A consulta combina histórico de retiradas, devoluções identificadas, checklist do dia e pendências de ferramentas em uma única leitura operacional.</p>'
                + '</div>'
                + '<aside class="general-search-surface general-search-quick-pane">'
                + '<div class="general-search-surface-title">'
                + '<div><h4>Ação rápida</h4><p>Baixe o relatório histórico completo ou siga a linha do tempo abaixo.</p></div>'
                + (payload.download_url ? '<a class="btn btn-outline-info general-search-download-link" href="' + escapeHtml(payload.download_url) + '" target="_blank" rel="noopener"><i class="bi bi-filetype-pdf"></i> Baixar PDF</a>' : '')
                + '</div>'
                + '<div class="general-search-chip-row">'
                + '<span class="general-search-chip"><i class="bi bi-box-seam"></i> Materiais: ' + escapeHtml(formatNumber(summary.materials_count, 0)) + '</span>'
                + '<span class="general-search-chip"><i class="bi bi-tools"></i> Ferramentas: ' + escapeHtml(formatNumber(summary.tools_count, 0)) + '</span>'
                + '<span class="general-search-chip"><i class="bi bi-arrow-counterclockwise"></i> Devoluções: ' + escapeHtml(formatNumber(summary.returns_count, 0)) + '</span>'
                + '</div>'
                + '</aside>'
                + '</section>'
                + buildExpandableSection('Checklist do dia', 'Itens retirados hoje para conferências rápidas.', formatNumber(summary.today_count, 0) + ' itens', checklistTable, false, 'general-search-surface')
                + buildExpandableSection('Linha do tempo consolidada', 'Retiradas e devoluções em ordem cronológica para leitura completa.', formatNumber(summary.timeline_count, 0) + ' eventos', timelineTable, true, 'general-search-surface')
                + '<div class="general-search-grid-two">'
                + buildExpandableSection('Materiais', 'Histórico detalhado de retiradas de materiais.', formatNumber(summary.materials_count, 0) + ' itens', materialsTable, false, 'general-search-surface')
                + buildExpandableSection('Ferramentas', 'Status atual das retiradas de ferramentas.', formatNumber(summary.tools_count, 0) + ' itens', toolsTable, false, 'general-search-surface')
                + '</div>'
                + '</div>';
            wireExpandableAccordions(resultsEl);
        }

        function renderItem(payload) {
            const item = payload.item || {};
            const summary = payload.summary || {};
            setResultsMode(modalEl, true);
            renderSummary([
                { label: 'Movimentações', value: formatNumber(summary.movement_count, 0), help: 'Retiradas localizadas para o período selecionado.' },
                { label: 'Total retirado', value: formatNumber(summary.total_quantity, 3), help: 'Soma das quantidades movimentadas no período.' },
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
                : '<tr><td colspan="6" class="text-center py-4">Nenhuma retirada encontrada para o item neste período.</td></tr>';

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
                : '<tr><td colspan="4" class="text-center py-4">Nenhum resumo diário encontrado.</td></tr>';

            const photoPanel = buildPhotoPanel(item.photo_url, item.descricao || 'Item', 'is-compact');
            const movementTable = buildTableWrapper(
                '<tr><th>Data</th><th>Hora</th><th>Colaborador</th><th class="text-center">Qtd.</th><th>Período</th><th>Local / Observação</th></tr>',
                movementRows
            );
            const dailyTable = buildTableWrapper(
                '<tr><th>Data</th><th class="text-center">Mov.</th><th class="text-center">Total</th><th class="text-center">Colab.</th></tr>',
                dailyRows
            );

            resultsEl.innerHTML = ''
                + '<div class="general-search-result-stack">'
                + '<section class="general-search-item-hero' + (photoPanel ? ' has-photo' : '') + '">'
                + '<div class="general-search-surface general-search-hero-pane general-search-item-identity">'
                + '<span class="general-search-kicker"><i class="bi bi-box-seam"></i> Item em foco</span>'
                + '<h3>' + escapeHtml(item.descricao || 'Item') + '</h3>'
                + '<div class="general-search-chip-row">'
                + '<span class="general-search-chip"><i class="bi bi-upc"></i> ' + escapeHtml(item.codigo_curto || item.codigo || 'N/D') + '</span>'
                + '<span class="general-search-chip"><i class="bi bi-tags"></i> ' + escapeHtml(item.categoria || 'Sem categoria') + '</span>'
                + '<span class="general-search-chip"><i class="bi bi-award"></i> ' + escapeHtml(item.marca || 'Sem marca') + '</span>'
                + '<span class="general-search-chip"><i class="bi bi-box"></i> Saldo físico: ' + escapeHtml(formatNumber(item.saldo_atual, 3)) + '</span>'
                + '</div>'
                + '<p class="mt-3 general-search-inline-note">A leitura do item concentra retirada por colaborador, período operacional e resumo diário do giro encontrado.</p>'
                + (payload.download_url ? '<a class="btn btn-outline-info general-search-download-link mt-3" href="' + escapeHtml(payload.download_url) + '" target="_blank" rel="noopener"><i class="bi bi-filetype-pdf"></i> Baixar PDF do item</a>' : '')
                + '</div>'
                + (photoPanel ? '<aside class="general-search-surface general-search-photo-aside">' + photoPanel + '</aside>' : '')
                + '</section>'
                + buildExpandableSection('Movimentações do item', 'Histórico detalhado por colaborador e contexto operacional.', formatNumber(summary.movement_count, 0) + ' mov.', movementTable, true, 'general-search-surface')
                + buildExpandableSection('Resumo diário do item', 'Datas em que o item apareceu nas retiradas do período filtrado.', formatNumber(summary.days_count, 0) + ' dias', dailyTable, false, 'general-search-surface')
                + '</div>';
            wireExpandableAccordions(resultsEl);
        }

        function renderDaily(payload) {
            const summary = payload.summary || {};
            renderSummary([
                { label: 'Itens no dia', value: formatNumber(summary.total_items, 0), help: 'Itens distintos com retirada registrada.' },
                { label: 'Movimentações', value: formatNumber(summary.total_movements, 0), help: 'Lançamentos individuais localizados para a data.' },
                { label: 'Total retirado', value: formatNumber(summary.total_quantity, 3), help: 'Soma das quantidades movimentadas no dia.' },
                { label: 'Itens com foto', value: formatNumber(summary.items_with_photo, 0), help: 'Grupos que já possuem imagem cadastrada.' },
            ]);

            const items = Array.isArray(payload.grouped_items) ? payload.grouped_items : [];
            if (!items.length) {
                setResultsMode(modalEl, false);
                resultsEl.innerHTML = ''
                    + '<div class="general-search-empty-state">'
                    + '<i class="bi bi-moon-stars"></i>'
                    + '<h3>Nenhuma retirada encontrada</h3>'
                    + '<p>Não há saídas registradas para ' + escapeHtml(payload.selected_date_label || '') + (payload.search_term ? ' com o filtro informado.' : '.') + '</p>'
                    + '</div>';
                return;
            }

            setResultsMode(modalEl, true);

            resultsEl.innerHTML = ''
                + '<div class="general-search-result-stack">'
                + items.map((item) => {
                    const photoPanel = buildPhotoPanel(item.foto_url, item.descricao || 'Item', 'is-thumb');

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

                    const movementTable = buildTableWrapper(
                        '<tr><th>Hora</th><th>Colaborador</th><th class="text-center">Qtd.</th><th>Custódia</th><th>Período</th><th>Local / Observação</th></tr>',
                        movementRows
                    );

                    return ''
                        + '<article class="general-search-item-card">'
                        + '<div class="general-search-item-summary' + (photoPanel ? ' has-photo' : '') + '">'
                        + '<div class="general-search-item-summary-copy">'
                        + '<h4>' + escapeHtml(item.descricao || 'Item') + '</h4>'
                        + '<p>Código completo: ' + escapeHtml(item.codigo || 'N/D') + '</p>'
                        + '<div class="general-search-chip-row">'
                        + '<span class="general-search-chip"><i class="bi bi-upc"></i> ' + escapeHtml(item.codigo_curto || item.codigo || 'N/D') + '</span>'
                        + '<span class="general-search-chip"><i class="bi bi-tags"></i> ' + escapeHtml(item.categoria || 'Sem categoria') + '</span>'
                        + '<span class="general-search-chip"><i class="bi bi-award"></i> ' + escapeHtml(item.marca || 'Sem marca') + '</span>'
                        + '</div>'
                        + '</div>'
                        + '<div class="general-search-item-summary-side">'
                        + photoPanel
                        + '<div class="general-search-kpi-stack">'
                        + '<span class="general-search-kpi-chip">Total: ' + escapeHtml(formatNumber(item.total_quantity, 3)) + '</span>'
                        + '<span class="general-search-kpi-chip">Mov.: ' + escapeHtml(formatNumber(item.movement_count, 0)) + '</span>'
                        + '<span class="general-search-kpi-chip">Colab.: ' + escapeHtml(formatNumber(item.unique_user_count, 0)) + '</span>'
                        + '</div>'
                        + '</div>'
                        + '</div>'
                        + buildExpandableSection('Saídas do item', 'Detalhe das retiradas do dia para este item.', formatNumber(item.movement_count, 0) + ' mov.', movementTable, false, 'general-search-surface is-nested')
                        + '</article>';
                }).join('')
                + '</div>';
                    wireExpandableAccordions(resultsEl);
        }

        async function runSearch() {
            setMessage('', 'info');
            setLoading();

            try {
                if (state.scope === 'diario') {
                    const url = new URL(dailyUrl, window.location.origin);
                    const selectedDate = String(searchDate.value || '').trim() || getLocalDateInputValue();
                    url.searchParams.set('date', selectedDate);
                    const filterQuery = String(searchInput.value || '').trim();
                    if (filterQuery) {
                        url.searchParams.set('search', filterQuery);
                    }
                    const payload = await fetchJson(url.toString(), 'Não foi possível carregar a visão diária.');
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
                    const payload = await fetchJson(url, 'Não foi possível carregar o histórico do colaborador.');
                    renderEmployee(payload);
                    return;
                }

                const url = new URL(itemUrlTemplate.replace('__CODIGO__', encodeURIComponent(selection.codigo_item || selection.id || '')), window.location.origin);
                url.searchParams.set('period', String(searchPeriod.value || '0'));
                const payload = await fetchJson(url.toString(), 'Não foi possível carregar o histórico do item.');
                renderItem(payload);
            } catch (error) {
                resetResults();
                setMessage(error?.message || 'Falha ao executar a pesquisa geral.', 'error');
            }
        }

        function resetForm() {
            searchInput.value = '';
            searchPeriod.value = '0';
            searchDate.value = getLocalDateInputValue();
            state.selectedSuggestion = null;
            hideSuggestions();
            setMessage('', 'info');
            resetResults();
        }

        function openWithOptions(options) {
            const data = options || {};
            applyScope(data.scope || 'funcionario');
            searchInput.value = data.query || '';
            searchDate.value = data.date || getLocalDateInputValue();
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
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeGeneralSearchModal);
    } else {
        initializeGeneralSearchModal();
    }
})();