(function () {
    const form = document.querySelector('.topbar-nf-search');
    const modalElement = document.getElementById('nfSearchModal');
    const input = document.getElementById('topbar-nf-query');
    const feedback = document.getElementById('nfSearchModalFeedback');
    const content = document.getElementById('nfSearchModalContent');
    const title = document.getElementById('nfSearchModalTitle');
    const subtitle = document.getElementById('nfSearchModalSubtitle');
    const createPrompt = document.getElementById('nfSearchCreatePrompt');
    const createStartButton = document.getElementById('nfSearchCreateStart');
    const createForm = document.getElementById('nfQuickCreateForm');
    const createCancelButton = document.getElementById('nfQuickCreateCancel');
    const createSubmitButton = document.getElementById('nfQuickCreateSubmit');
    const createNumberInput = document.getElementById('nfQuickNumber');
    const createAccessKeyInput = document.getElementById('nfQuickAccessKey');
    const createCnpjInput = document.getElementById('nfQuickCnpj');
    const createSupplierInput = document.getElementById('nfQuickSupplier');

    if (!form || !modalElement || !input || !window.bootstrap?.Modal) {
        return;
    }

    const modal = window.bootstrap.Modal.getOrCreateInstance(modalElement);
    const submitButton = form.querySelector('button[type="submit"]');
    let activeQuery = '';
    let autoFilledNumber = false;
    let autoFilledCnpj = false;

    function hideCreateFlow() {
        createPrompt?.classList.add('d-none');
        createForm?.classList.add('d-none');
    }

    function prefillCreateForm(query) {
        if (!createForm) return;
        createForm.reset();
        autoFilledNumber = false;
        autoFilledCnpj = false;
        const cleaned = String(query || '').replace(/^(?:nf|chave)\s*[:#-]?\s*/i, '').trim();
        const digits = cleaned.replace(/\D/g, '');
        if (digits.length === 44) {
            createAccessKeyInput.value = digits;
            createNumberInput.value = digits.slice(25, 34).replace(/^0+/, '') || '0';
            createCnpjInput.value = digits.slice(6, 20);
            autoFilledNumber = true;
            autoFilledCnpj = true;
        } else {
            createNumberInput.value = cleaned;
        }
    }

    function showCreateResult(message, href, linkLabel) {
        hideCreateFlow();
        title.textContent = 'Cadastro de NF';
        subtitle.textContent = '';
        feedback.textContent = message;
        feedback.className = 'small text-success';
        if (href) {
            const link = document.createElement('a');
            link.className = 'btn btn-primary btn-sm mt-3';
            link.href = href;
            link.textContent = linkLabel;
            content.replaceChildren(link);
            content.classList.remove('d-none');
        }
    }

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

        if (invoice.inbox_url) {
            const inboxLink = document.createElement('a');
            inboxLink.className = 'btn btn-outline-primary btn-sm mt-3';
            inboxLink.href = invoice.inbox_url;
            inboxLink.textContent = 'Abrir NF recebida pela SEFAZ';
            content.appendChild(inboxLink);
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

        activeQuery = query;
        hideCreateFlow();
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
            if (payload.can_register && (response.status === 404 || !payload.success)) {
                feedback.textContent = createPrompt
                    ? ''
                    : 'Não encontramos esta NF no GALINT. Deseja cadastrar um novo documento fiscal?';
                feedback.className = createPrompt ? 'small text-muted' : 'small text-warning';
                content.replaceChildren();
                content.classList.add('d-none');
                createPrompt?.classList.remove('d-none');
                return;
            }
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

    createStartButton?.addEventListener('click', () => {
        prefillCreateForm(activeQuery);
        createPrompt?.classList.add('d-none');
        createForm?.classList.remove('d-none');
        title.textContent = 'Cadastrar nova NF';
        subtitle.textContent = 'Dados essenciais do documento';
        feedback.textContent = '';
        createNumberInput?.focus();
    });

    createCancelButton?.addEventListener('click', () => {
        createForm?.classList.add('d-none');
        createPrompt?.classList.remove('d-none');
        title.textContent = 'Nota fiscal';
        subtitle.textContent = '';
    });

    createAccessKeyInput?.addEventListener('input', () => {
        const digits = createAccessKeyInput.value.replace(/\D/g, '');
        if (digits.length !== 44) return;
        createAccessKeyInput.value = digits;
        if (autoFilledNumber || !createNumberInput.value.trim()) {
            createNumberInput.value = digits.slice(25, 34).replace(/^0+/, '') || '0';
            autoFilledNumber = true;
        }
        if (autoFilledCnpj || !createCnpjInput.value.trim()) {
            createCnpjInput.value = digits.slice(6, 20);
            autoFilledCnpj = true;
        }
    });
    createNumberInput?.addEventListener('input', () => { autoFilledNumber = false; });
    createCnpjInput?.addEventListener('input', () => { autoFilledCnpj = false; });

    createForm?.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (!createForm.reportValidity()) return;
        if (createSubmitButton) createSubmitButton.disabled = true;
        feedback.textContent = 'Salvando rascunho...';
        feedback.className = 'small text-muted';
        feedback.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(form.dataset.createUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
                body: JSON.stringify(Object.fromEntries(new FormData(createForm).entries())),
            });
            const payload = await response.json();
            if (response.status === 409 && payload.existing_url) {
                showCreateResult(payload.message || 'Esta NF já está cadastrada.', payload.existing_url, 'Abrir NF existente');
                return;
            }
            if (!response.ok || !payload.success) {
                throw new Error(payload.message || 'Não foi possível cadastrar a NF.');
            }
            showCreateResult(payload.message, payload.url, 'Adicionar itens e conferir');
        } catch (error) {
            feedback.textContent = error.message || 'Erro ao cadastrar a NF.';
            feedback.className = 'small text-danger';
        } finally {
            feedback.removeAttribute('aria-busy');
            if (createSubmitButton) createSubmitButton.disabled = false;
        }
    });
})();
