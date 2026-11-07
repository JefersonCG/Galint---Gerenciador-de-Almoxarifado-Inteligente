(function () {
    const form = document.querySelector('.topbar-nf-search');
    const modalElement = document.getElementById('nfSearchModal');
    const input = document.getElementById('topbar-nf-query');
    const feedback = document.getElementById('nfSearchModalFeedback');
    const content = document.getElementById('nfSearchModalContent');
    const title = document.getElementById('nfSearchModalTitle');
    const subtitle = document.getElementById('nfSearchModalSubtitle');

    if (!form || !modalElement || !input || !window.bootstrap?.Modal) {
        return;
    }

    const modal = window.bootstrap.Modal.getOrCreateInstance(modalElement);
    const submitButton = form.querySelector('button[type="submit"]');

    function addText(parent, tag, className, value) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        element.textContent = value == null || value === '' ? '-' : String(value);
        parent.appendChild(element);
        return element;
    }

    function formatDate(value) {
        if (!value) return '-';
        const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
        if (match) return `${match[3]}/${match[2]}/${match[1]}`;
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString('pt-BR');
    }

    function formatNumber(value) {
        if (value == null || value === '') return '-';
        const number = Number(value);
        return Number.isFinite(number) ? number.toLocaleString('pt-BR', { maximumFractionDigits: 3 }) : String(value);
    }

    function formatCurrency(value) {
        if (value == null || value === '') return '-';
        const number = Number(value);
        return Number.isFinite(number)
            ? number.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
            : String(value);
    }

    function addField(parent, label, value, className) {
        const wrapper = document.createElement('div');
        wrapper.className = className || 'col-6 col-md-4';
        addText(wrapper, 'div', 'nf-search-field-label', label);
        addText(wrapper, 'div', 'nf-search-field-value', value);
        parent.appendChild(wrapper);
    }

    function renderDocument(invoice) {
        const documentType = String(invoice.tipo_documento || 'NF').toUpperCase();
        title.textContent = `${documentType} ${invoice.numero_documento || ''}`.trim();
        subtitle.textContent = invoice.fornecedor_nome || '';
        content.replaceChildren();

        const fields = document.createElement('div');
        fields.className = 'row g-2 nf-search-fields';
        addField(fields, 'Tipo', invoice.tipo_documento);
        addField(fields, 'Emissão', formatDate(invoice.data_emissao));
        addField(fields, 'Recebimento', formatDate(invoice.data_recebimento));
        addField(fields, 'CNPJ', invoice.cnpj_emitente);
        addField(fields, 'Registro', formatDate(invoice.data));
        addField(fields, 'Estoque', invoice.movimenta_estoque == null ? '-' : (invoice.movimenta_estoque ? 'Movimenta' : 'Sem movimentação'));
        addField(fields, 'Status', invoice.status_integracao);
        if (invoice.criado_por || (Array.isArray(invoice.usuarios) && invoice.usuarios.length)) {
            addField(fields, 'Registrado por', invoice.criado_por || invoice.usuarios.join(', '));
        }
        content.appendChild(fields);

        if (invoice.chave_acesso) {
            const key = document.createElement('div');
            key.className = 'nf-search-access-key';
            addText(key, 'div', 'nf-search-field-label', 'Chave de acesso');
            const keyValue = addText(key, 'code', 'nf-search-key-value', invoice.chave_acesso);
            keyValue.title = invoice.chave_acesso;
            content.appendChild(key);
        }

        const totals = document.createElement('div');
        totals.className = 'nf-search-totals';
        addText(totals, 'span', '', `${formatNumber(invoice.total_itens)} itens`);
        addText(totals, 'span', '', `Qtd. ${formatNumber(invoice.total_quantidade)}`);
        addText(totals, 'strong', '', formatCurrency(invoice.total_valor));
        content.appendChild(totals);

        if (invoice.observacao || invoice.mensagem_integracao) {
            const notes = document.createElement('div');
            notes.className = 'nf-search-notes';
            if (invoice.observacao) addText(notes, 'div', '', invoice.observacao);
            if (invoice.mensagem_integracao) addText(notes, 'div', 'text-muted', invoice.mensagem_integracao);
            content.appendChild(notes);
        }

        const items = Array.isArray(invoice.itens) ? invoice.itens : [];
        if (items.length) {
            const heading = addText(content, 'h3', 'nf-search-items-title', 'Itens');
            heading.id = 'nfSearchItemsTitle';
            const tableWrap = document.createElement('div');
            tableWrap.className = 'table-responsive nf-search-table-wrap';
            const table = document.createElement('table');
            table.className = 'table table-sm align-middle mb-0';
            table.setAttribute('aria-labelledby', heading.id);
            const thead = document.createElement('thead');
            const headerRow = document.createElement('tr');
            ['Produto', 'Qtd.', 'Unitário', 'Total'].forEach((label) => addText(headerRow, 'th', '', label));
            thead.appendChild(headerRow);
            table.appendChild(thead);

            const tbody = document.createElement('tbody');
            items.forEach((item) => {
                const row = document.createElement('tr');
                const productCell = document.createElement('td');
                addText(productCell, 'div', 'nf-search-item-description', item.descricao || item.codigo);
                if (item.codigo) addText(productCell, 'small', 'text-muted', item.codigo);
                const details = [
                    item.lote && `Lote: ${item.lote}`,
                    item.data_validade && `Val.: ${formatDate(item.data_validade)}`,
                    item.observacao,
                    item.status_processamento && `Status: ${item.status_processamento}`,
                    item.erro_processamento,
                ]
                    .filter(Boolean)
                    .join(' · ');
                if (details) addText(productCell, 'small', 'nf-search-item-details', details);
                row.appendChild(productCell);
                addText(row, 'td', 'text-nowrap', `${formatNumber(item.quantidade)}${item.unidade_quantidade ? ` ${item.unidade_quantidade}` : ''}`);
                const unitPrice = `${formatCurrency(item.valor_unitario)}${item.unidade_preco ? ` / ${item.unidade_preco}` : ''}`;
                addText(row, 'td', 'text-nowrap', unitPrice);
                const total = item.valor_total == null && item.valor_unitario != null
                    ? Number(item.valor_unitario) * Number(item.quantidade || 0)
                    : item.valor_total;
                addText(row, 'td', 'text-nowrap', formatCurrency(total));
                tbody.appendChild(row);
            });
            table.appendChild(tbody);
            tableWrap.appendChild(table);
            content.appendChild(tableWrap);
        }

        content.classList.remove('d-none');
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const query = input.value.trim();
        if (!query) {
            input.focus();
            return;
        }

        feedback.textContent = 'Buscando...';
        feedback.className = 'small text-muted';
        feedback.setAttribute('aria-busy', 'true');
        content.replaceChildren();
        content.classList.add('d-none');
        title.textContent = 'Nota fiscal';
        subtitle.textContent = '';
        modal.show();
        if (submitButton) submitButton.disabled = true;

        try {
            const url = new URL(form.dataset.searchUrl, window.location.href);
            url.searchParams.set('q', query);
            const response = await fetch(url, {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
            });
            const payload = await response.json();
            if (!response.ok || !payload.success) {
                throw new Error(payload.message || 'Não foi possível buscar a nota fiscal.');
            }

            feedback.textContent = '';
            renderDocument(payload.document);
        } catch (error) {
            feedback.textContent = error.message || 'Erro ao buscar nota fiscal.';
            feedback.className = 'small text-danger';
        } finally {
            feedback.removeAttribute('aria-busy');
            if (submitButton) submitButton.disabled = false;
        }
    });
})();
