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
        return Number.isFinite(parsed)
            ? parsed.toLocaleString('pt-BR', { maximumFractionDigits: digits ?? 3 })
            : '0';
    }

    async function fetchJson(url) {
        const response = window.galintFetchWithAuth
            ? await window.galintFetchWithAuth(url, { headers: { Accept: 'application/json' } }, 'Não foi possível carregar a análise de consumo.')
            : await window.fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
        let payload = null;
        try {
            payload = await response.json();
        } catch (error) {
            throw new Error('O servidor retornou uma resposta inválida.');
        }
        if (!response.ok || !payload?.success) {
            throw new Error(String(payload?.message || 'Não foi possível carregar a análise de consumo.'));
        }
        return payload;
    }

    function renderRanking(title, rows, unit) {
        const contents = rows.length
            ? rows.map((row) => ''
                + '<tr><td>' + escapeHtml(row.name) + '</td>'
                + '<td class="text-end">' + escapeHtml(formatNumber(row.quantity)) + ' ' + escapeHtml(unit) + '</td>'
                + '<td class="text-end">' + escapeHtml(formatNumber(row.count, 0)) + '</td></tr>').join('')
            : '<tr><td colspan="3" class="text-center text-secondary py-3">Nenhum registro neste período.</td></tr>';
        return ''
            + '<section class="consumption-section">'
            + '<h3>' + escapeHtml(title) + '</h3>'
            + '<div class="table-responsive"><table class="table table-sm align-middle">'
            + '<thead><tr><th>Nome</th><th class="text-end">Quantidade</th><th class="text-end">Retiradas</th></tr></thead>'
            + '<tbody>' + contents + '</tbody></table></div>'
            + '</section>';
    }

    function renderDailySeries(rows, unit) {
        const maxValue = Math.max(...rows.map((row) => Number(row.quantity) || 0), 0);
        if (!rows.length) {
            return '<p class="mb-0 text-secondary">Não há retiradas registradas neste intervalo.</p>';
        }
        return '<div class="consumption-daily-list">' + rows.map((row) => {
            const quantity = Number(row.quantity) || 0;
            const width = maxValue > 0 ? Math.max((quantity / maxValue) * 100, quantity > 0 ? 2 : 0) : 0;
            return ''
                + '<div class="consumption-daily-row ' + (row.period === 'anterior' ? 'is-previous' : '') + '">'
                + '<span>' + escapeHtml(row.date_label) + '</span>'
                + '<div class="consumption-daily-track" aria-hidden="true"><div class="consumption-daily-fill" style="width:' + width.toFixed(1) + '%"></div></div>'
                + '<strong class="text-end">' + escapeHtml(formatNumber(quantity)) + ' ' + escapeHtml(unit) + '</strong>'
                + '</div>';
        }).join('') + '</div>';
    }

    function renderMovements(rows, unit) {
        const visibleRows = rows.slice(0, 100);
        const body = visibleRows.length
            ? visibleRows.map((row) => ''
                + '<tr><td>' + escapeHtml(row.date) + '</td>'
                + '<td>' + escapeHtml(row.employee) + '<br><small class="text-secondary">' + escapeHtml(row.employee_id) + '</small></td>'
                + '<td class="text-end">' + escapeHtml(formatNumber(row.quantity)) + ' ' + escapeHtml(unit) + '</td>'
                + '<td>' + escapeHtml(row.location) + '</td></tr>').join('')
            : '<tr><td colspan="4" class="text-center text-secondary py-3">Nenhuma retirada registrada no intervalo.</td></tr>';
        const note = rows.length > visibleRows.length
            ? '<p class="small text-secondary mt-2 mb-0">Exibindo as 100 retiradas mais recentes. O PDF contém o histórico completo do período.</p>'
            : '';
        return ''
            + '<section class="consumption-section consumption-section--wide">'
            + '<h3>Retiradas do período comparado</h3>'
            + '<div class="consumption-movement-scroll"><table class="table table-sm align-middle">'
            + '<thead><tr><th>Data</th><th>Colaborador</th><th class="text-end">Quantidade</th><th>Local</th></tr></thead>'
            + '<tbody>' + body + '</tbody></table></div>' + note
            + '</section>';
    }

    function renderReport(payload) {
        const item = payload.item || {};
        const period = payload.period || {};
        const summary = payload.summary || {};
        const unit = item.unidade || 'unidade(s)';
        const percent = summary.percent_change;
        const trendClass = percent > 0 ? 'consumption-trend-up' : (percent < 0 ? 'consumption-trend-down' : '');
        const changeLabel = percent === null || percent === undefined
            ? 'Sem base de comparação'
            : (percent > 0 ? '+' : '') + formatNumber(percent, 1) + '%';
        const historyNote = item.historical_only
            ? '<p class="alert alert-warning py-2">Este material aparece apenas no histórico fiscal; não há cadastro ativo do item.</p>'
            : '';
        const subtitle = [item.codigo, item.categoria].filter(Boolean).join(' · ');
        document.getElementById('itemConsumptionModalTitle').textContent = item.descricao || 'Análise de consumo';
        document.getElementById('itemConsumptionSubtitle').textContent = subtitle;

        const pdfLink = payload.pdf_url || '#';
        document.getElementById('itemConsumptionContent').innerHTML = ''
            + historyNote
            + '<div class="consumption-period"><strong>' + escapeHtml(period.label) + ':</strong> ' + escapeHtml(period.current_start) + ' a ' + escapeHtml(period.current_end)
            + ' &nbsp;·&nbsp; <strong>' + escapeHtml(period.previous_label) + ':</strong> ' + escapeHtml(period.previous_start) + ' a ' + escapeHtml(period.previous_end) + '</div>'
            + '<div class="consumption-summary-grid">'
            + '<article class="consumption-summary-card"><small>Consumo no período</small><strong>' + escapeHtml(formatNumber(summary.current_quantity)) + ' ' + escapeHtml(unit) + '</strong><span>' + escapeHtml(formatNumber(summary.current_withdrawals, 0)) + ' retiradas</span></article>'
            + '<article class="consumption-summary-card"><small>Período anterior</small><strong>' + escapeHtml(formatNumber(summary.previous_quantity)) + ' ' + escapeHtml(unit) + '</strong><span>' + escapeHtml(formatNumber(summary.previous_withdrawals, 0)) + ' retiradas</span></article>'
            + '<article class="consumption-summary-card"><small>Variação</small><strong class="' + trendClass + '">' + escapeHtml(changeLabel) + '</strong><span>' + escapeHtml(formatNumber(summary.difference)) + ' ' + escapeHtml(unit) + ' de diferença</span></article>'
            + '<article class="consumption-summary-card"><small>Tendência</small><strong class="' + trendClass + '">' + escapeHtml(summary.trend || 'Sem dados') + '</strong><span>Comparação entre intervalos equivalentes</span></article>'
            + '</div>'
            + '<div class="consumption-report-link"><a class="btn btn-outline-info btn-sm" href="' + escapeHtml(pdfLink) + '" target="_blank" rel="noopener"><i class="bi bi-file-earmark-pdf"></i> Baixar relatório PDF</a></div>'
            + '<div class="consumption-sections-grid">'
            + renderRanking('Quem mais retirou', Array.isArray(payload.top_employees) ? payload.top_employees : [], unit)
            + renderRanking('Locais com mais retiradas', Array.isArray(payload.top_locations) ? payload.top_locations : [], unit)
            + '<section class="consumption-section"><h3>Evolução do consumo</h3>' + renderDailySeries(Array.isArray(payload.daily_totals) ? payload.daily_totals : [], unit) + '</section>'
            + renderMovements(Array.isArray(payload.movements) ? payload.movements : [], unit)
            + '</div>';
    }

    function initialize() {
        const searchForm = document.getElementById('topbar-item-search');
        const searchInput = document.getElementById('topbar-item-query');
        const suggestions = document.getElementById('topbar-item-suggestions');
        const modalElement = document.getElementById('itemConsumptionModal');
        const content = document.getElementById('itemConsumptionContent');
        const periodSelect = document.getElementById('itemConsumptionPeriod');
        const nfForm = document.querySelector('.topbar-nf-search');
        const nfInput = document.getElementById('topbar-nf-query');
        const invoiceSearchAvailable = Boolean(nfForm && nfInput);
        const itemSearchAvailable = searchForm?.dataset.itemSearchAvailable === 'true'
            && Boolean(modalElement && content && periodSelect);
        if (!searchForm || !searchInput || !suggestions || !window.bootstrap) {
            return;
        }

        const modal = itemSearchAvailable ? window.bootstrap.Modal.getOrCreateInstance(modalElement) : null;
        let timer = 0;
        let stockCountTimer = 0;
        let requestId = 0;
        let selectedCode = '';
        let suggestionsData = [];
        let latestQuery = '';

        function searchInvoice(query) {
            if (!invoiceSearchAvailable) {
                return;
            }
            nfInput.value = String(query || '').replace(/^(?:nf|chave)\s*[:#-]?\s*/i, '').trim();
            nfForm.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
        }

        function looksLikeAccessKey(query) {
            return String(query || '').replace(/\D/g, '').length === 44;
        }

        function looksLikeInvoiceQuery(query) {
            return /^(?:nf|chave)(?:\s*[:#-]\s*|\s+)/i.test(String(query || '').trim());
        }

        function scheduleStockCountLookup(query) {
            if (typeof window.galintTryOpenStockCountModal !== 'function'
                || query.length < 3
                || looksLikeAccessKey(query)
                || looksLikeInvoiceQuery(query)) {
                return;
            }
            window.clearTimeout(stockCountTimer);
            stockCountTimer = window.setTimeout(async () => {
                if (searchInput.value.trim() !== query) {
                    return;
                }
                const opened = await window.galintTryOpenStockCountModal(query);
                if (opened) {
                    hideSuggestions();
                }
            }, 420);
        }

        async function handleEnterQuery(query) {
            if (invoiceSearchAvailable && (looksLikeAccessKey(query) || looksLikeInvoiceQuery(query))) {
                searchInvoice(query);
                hideSuggestions();
                return;
            }

            if (typeof window.galintTryOpenStockCountModal === 'function') {
                const opened = await window.galintTryOpenStockCountModal(query);
                if (opened) {
                    hideSuggestions();
                    return;
                }
            }

            if (invoiceSearchAvailable && !itemSearchAvailable) {
                searchInvoice(query);
                hideSuggestions();
                return;
            }

            if (invoiceSearchAvailable && !suggestionsData.length) {
                searchInvoice(query);
                hideSuggestions();
            } else if (suggestionsData.length) {
                void openItem(suggestionsData[0]);
            }
        }

        function renderInvoiceOption(query) {
            if (!invoiceSearchAvailable) {
                return '';
            }
            return ''
                + '<button type="button" class="topbar-item-suggestion topbar-item-suggestion--invoice" data-search-invoice="1">'
                + '<span class="topbar-item-suggestion-title"><i class="bi bi-receipt me-2"></i>Buscar nota fiscal ou chave de acesso</span>'
                + '<span class="topbar-item-suggestion-meta"><span>' + escapeHtml(query) + '</span></span>'
                + '</button>';
        }

        function hideSuggestions() {
            suggestions.classList.add('d-none');
            suggestions.setAttribute('aria-expanded', 'false');
            searchInput.setAttribute('aria-expanded', 'false');
        }

        async function openItem(item) {
            if (!itemSearchAvailable || !modal || !content) {
                return;
            }
            selectedCode = String(item.codigo_item || item.id || '').trim();
            if (!selectedCode) {
                return;
            }
            searchInput.value = item.title || '';
            hideSuggestions();
            content.innerHTML = '<div class="consumption-loading"><span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Calculando consumo...</div>';
            document.getElementById('itemConsumptionModalTitle').textContent = item.title || 'Análise de consumo';
            document.getElementById('itemConsumptionSubtitle').textContent = item.subtitle || '';
            modal.show();
            await loadReport();
        }

        async function loadReport() {
            if (!selectedCode) {
                return;
            }
            const currentRequest = ++requestId;
            content.innerHTML = '<div class="consumption-loading"><span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Calculando consumo...</div>';
            const template = searchForm.dataset.reportUrlTemplate || '';
            const encodedCode = encodeURIComponent(selectedCode);
            const reportPath = template.replace('__CODIGO__', encodedCode);
            const reportUrl = new URL(reportPath, window.location.origin);
            reportUrl.searchParams.set('period', periodSelect.value);
            try {
                const payload = await fetchJson(reportUrl.toString());
                if (currentRequest === requestId) {
                    renderReport(payload);
                }
            } catch (error) {
                if (currentRequest === requestId) {
                    content.innerHTML = '<div class="consumption-message consumption-error" role="alert">' + escapeHtml(error?.message || 'Falha ao carregar o relatório.') + '</div>';
                }
            }
        }

        function renderSuggestions(rows) {
            suggestionsData = Array.isArray(rows) ? rows : [];
            const itemMarkup = suggestionsData.map((item, index) => ''
                + '<button type="button" class="topbar-item-suggestion" role="option" aria-selected="false" data-item-index="' + index + '">'
                + '<span class="topbar-item-suggestion-title">' + escapeHtml(item.title || item.codigo_item || 'Material') + '</span>'
                + '<span class="topbar-item-suggestion-meta"><span>' + escapeHtml(item.subtitle || '') + '</span><span>' + escapeHtml(item.badge || '') + '</span></span>'
                + '</button>').join('');
            suggestions.innerHTML = (itemMarkup || (itemSearchAvailable
                ? '<div class="topbar-item-suggestion-empty">Nenhum material ou ferramenta localizado.</div>'
                : '')) + renderInvoiceOption(latestQuery);
            suggestions.classList.remove('d-none');
            suggestions.setAttribute('aria-expanded', 'true');
            searchInput.setAttribute('aria-expanded', 'true');
            suggestions.querySelectorAll('[data-item-index]').forEach((button) => {
                button.addEventListener('click', () => {
                    const item = suggestionsData[Number(button.dataset.itemIndex)];
                    if (item) {
                        void openItem(item);
                    }
                });
            });
            suggestions.querySelector('[data-search-invoice]')?.addEventListener('click', () => {
                searchInvoice(latestQuery);
                hideSuggestions();
            });
        }

        async function searchItems(query) {
            latestQuery = query;
            if (!itemSearchAvailable) {
                suggestionsData = [];
                renderSuggestions([]);
                return;
            }
            const url = new URL(searchForm.dataset.suggestionsUrl || '', window.location.origin);
            url.searchParams.set('scope', 'item');
            url.searchParams.set('q', query);
            try {
                const payload = await fetchJson(url.toString());
                if (query === searchInput.value.trim()) {
                    renderSuggestions(payload.results);
                }
            } catch (error) {
                if (query === searchInput.value.trim()) {
                    suggestions.innerHTML = '<div class="topbar-item-suggestion-empty" role="alert">' + escapeHtml(error?.message || 'Falha ao pesquisar materiais.') + '</div>';
                    suggestions.classList.remove('d-none');
                }
            }
        }

        searchInput.addEventListener('input', () => {
            window.clearTimeout(timer);
            const query = searchInput.value.trim();
            scheduleStockCountLookup(query);
            if (query.length < 2) {
                latestQuery = query;
                hideSuggestions();
                return;
            }
            timer = window.setTimeout(() => { void searchItems(query); }, 220);
        });

        searchInput.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                hideSuggestions();
            } else if (event.key === 'Enter') {
                event.preventDefault();
                const query = searchInput.value.trim();
                void handleEnterQuery(query);
            }
        });

        searchForm.addEventListener('submit', (event) => {
            event.preventDefault();
            void handleEnterQuery(searchInput.value.trim());
        });

        document.addEventListener('click', (event) => {
            if (!searchForm.contains(event.target)) {
                hideSuggestions();
            }
        });

        periodSelect?.addEventListener('change', () => { void loadReport(); });
        modalElement?.addEventListener('hidden.bs.modal', () => {
            selectedCode = '';
            requestId += 1;
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize, { once: true });
    } else {
        initialize();
    }
})();
