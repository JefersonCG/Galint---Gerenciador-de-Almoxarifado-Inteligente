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
    const createHeaderFields = document.getElementById('nfQuickHeaderFields');
    const createItemsPanel = document.getElementById('nfQuickItemsPanel');
    const createItemsList = document.getElementById('nfQuickItemsList');
    const createAddItemButton = document.getElementById('nfQuickAddItem');
    const createCancelButton = document.getElementById('nfQuickCreateCancel');
    const createItemsCancelButton = document.getElementById('nfQuickItemsCancel');
    const createHeaderSubmitButton = document.getElementById('nfQuickHeaderSubmit');
    const createItemsSubmitButton = document.getElementById('nfQuickItemsSubmit');
    const createNumberInput = document.getElementById('nfQuickNumber');
    const createAccessKeyInput = document.getElementById('nfQuickAccessKey');
    const createCnpjInput = document.getElementById('nfQuickCnpj');
    const createSupplierInput = document.getElementById('nfQuickSupplier');
    const quickDraftRestore = document.getElementById('nfQuickDraftRestore');
    const quickDraftRestoreDetail = document.getElementById('nfQuickDraftRestoreDetail');
    const quickDraftRestoreButton = document.getElementById('nfQuickDraftRestoreButton');
    const quickDraftDiscardButton = document.getElementById('nfQuickDraftDiscardButton');
    const quickDraftStatus = document.getElementById('nfQuickDraftStatus');

    if (!form || !modalElement || !input || !window.bootstrap?.Modal) {
        return;
    }

    const modal = window.bootstrap.Modal.getOrCreateInstance(modalElement);
    const submitButton = form.querySelector('button[type="submit"]');
    let activeQuery = '';
    let activeDocumentId = null;
    let activeDocumentUrl = '';
    let activeInvoice = null;
    let autoFilledNumber = false;
    let autoFilledCnpj = false;
    let quickFieldCounter = 0;
    let quickItemOptions = null;
    let quickItemOptionsRequest = null;
    const quickDraftStorageKey = `galint.nfQuickRegistrationDraft.v1.${String(createForm?.dataset.userKey || 'default').replace(/[^a-zA-Z0-9_-]/g, '_')}`;
    const quickDraftMaxAgeMs = 24 * 60 * 60 * 1000;
    const quickDraftAutoSaveIntervalMs = 60000;
    let pendingQuickDraft = null;
    let quickDraftPersistTimer = null;
    let quickDraftAutoSaveTimer = null;
    let quickDraftRestoring = false;
    let quickDraftPhotoDatabasePromise = null;

    function hideCreateFlow() {
        createPrompt?.classList.add('d-none');
        createForm?.classList.add('d-none');
        createHeaderFields?.classList.remove('d-none');
        createItemsPanel?.classList.add('d-none');
        activeDocumentId = null;
        activeDocumentUrl = '';
        activeInvoice = null;
    }

    function collectQuickItems() {
        return Array.from(createItemsList?.querySelectorAll('.nf-quick-item-row') || []).map((row) => ({
            modo: row.querySelector('[data-item-mode]')?.value || '',
            codigo_item: row.querySelector('[data-item-code]')?.value || '',
            codigo_novo: row.querySelector('[data-new-code]')?.value || '',
            descricao_nova: row.querySelector('[data-new-description]')?.value || '',
            unidade_nova: row.querySelector('[data-new-unit]')?.value || '',
            categoria: row.querySelector('[data-new-category]')?.value || '',
            marca_nova: row.querySelector('[data-new-brand]')?.value || '',
            foto_url: row.querySelector('[data-photo-url]')?.value.trim() || '',
            foto_atual_url: row.dataset.currentPhotoUrl || '',
            foto_arquivo_key: row.dataset.photoDraftKey || '',
            quantidade: row.querySelector('[data-item-quantity]')?.value || '',
            unidade_quantidade: row.querySelector('[data-quantity-unit]')?.value || '',
            valor_unitario: row.querySelector('[data-unit-price]')?.value || '',
            valor_total: row.querySelector('[data-total-price]')?.value || '',
            item_search: row.querySelector('[data-item-search]')?.value || '',
            item_selected_label: row.querySelector('[data-item-selected]')?.textContent || '',
        }));
    }

    function buildQuickDraftSnapshot() {
        const header = {};
        createForm.querySelectorAll('#nfQuickHeaderFields [name]').forEach((field) => {
            header[field.name] = field.value;
        });
        return {
            version: 1,
            savedAt: new Date().toISOString(),
            stage: activeDocumentId !== null ? 'items' : 'header',
            activeQuery,
            documentId: activeDocumentId,
            documentUrl: activeDocumentUrl,
            header,
            items: collectQuickItems(),
        };
    }

    function setQuickDraftStatus(message, isError = false) {
        if (!quickDraftStatus) return;
        quickDraftStatus.textContent = message;
        quickDraftStatus.classList.toggle('text-danger', isError);
        quickDraftStatus.classList.toggle('text-muted', !isError);
    }

    function openQuickDraftPhotoDatabase() {
        if (quickDraftPhotoDatabasePromise) return quickDraftPhotoDatabasePromise;
        quickDraftPhotoDatabasePromise = new Promise((resolve, reject) => {
            const request = window.indexedDB.open('galint-nf-quick-drafts', 1);
            request.onupgradeneeded = () => {
                const database = request.result;
                if (!database.objectStoreNames.contains('photos')) {
                    database.createObjectStore('photos', { keyPath: 'key' });
                }
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error || new Error('Não foi possível abrir o armazenamento local das fotos.'));
        });
        quickDraftPhotoDatabasePromise.catch(() => {
            quickDraftPhotoDatabasePromise = null;
        });
        return quickDraftPhotoDatabasePromise;
    }

    async function saveQuickDraftPhoto(key, file) {
        const database = await openQuickDraftPhotoDatabase();
        await new Promise((resolve, reject) => {
            const transaction = database.transaction('photos', 'readwrite');
            transaction.objectStore('photos').put({ key, file });
            transaction.oncomplete = resolve;
            transaction.onerror = () => reject(transaction.error || new Error('Não foi possível salvar a foto do rascunho.'));
            transaction.onabort = () => reject(transaction.error || new Error('O salvamento da foto do rascunho foi interrompido.'));
        });
    }

    async function loadQuickDraftPhoto(key) {
        const database = await openQuickDraftPhotoDatabase();
        return new Promise((resolve, reject) => {
            const transaction = database.transaction('photos', 'readonly');
            const request = transaction.objectStore('photos').get(key);
            request.onsuccess = () => resolve(request.result?.file || null);
            request.onerror = () => reject(request.error || new Error('Não foi possível recuperar a foto do rascunho.'));
        });
    }

    async function clearQuickDraftPhotos() {
        try {
            const database = await openQuickDraftPhotoDatabase();
            await new Promise((resolve, reject) => {
                const transaction = database.transaction('photos', 'readwrite');
                const store = transaction.objectStore('photos');
                const request = store.openCursor();
                request.onsuccess = () => {
                    const cursor = request.result;
                    if (!cursor) return;
                    if (String(cursor.key).startsWith(`${quickDraftStorageKey}:`)) {
                        cursor.delete();
                    }
                    cursor.continue();
                };
                transaction.oncomplete = resolve;
                transaction.onerror = () => reject(transaction.error || new Error('Não foi possível limpar as fotos do rascunho.'));
            });
        } catch (error) {
            console.warn('Não foi possível limpar as fotos do rascunho da NF:', error);
        }
    }

    function clearQuickDraft() {
        clearTimeout(quickDraftPersistTimer);
        pendingQuickDraft = null;
        try {
            window.localStorage.removeItem(quickDraftStorageKey);
            clearQuickDraftPhotos();
            quickDraftRestore?.classList.add('d-none');
            setQuickDraftStatus('');
        } catch (error) {
            console.warn('Não foi possível limpar o rascunho do cadastro rápido de NF:', error);
            setQuickDraftStatus('Não foi possível limpar o rascunho salvo neste navegador.', true);
        }
    }

    function persistQuickDraft() {
        if (quickDraftRestoring || !createForm || createForm.classList.contains('d-none')) return false;
        try {
            const snapshot = buildQuickDraftSnapshot();
            const hasHeader = Object.values(snapshot.header).some((value) => String(value || '').trim());
            if (!hasHeader && snapshot.items.length === 0) {
                window.localStorage.removeItem(quickDraftStorageKey);
                setQuickDraftStatus('');
                return false;
            }
            window.localStorage.setItem(quickDraftStorageKey, JSON.stringify(snapshot));
            const savedAt = new Date(snapshot.savedAt);
            setQuickDraftStatus(
                `Rascunho salvo automaticamente às ${savedAt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}.`
            );
            return true;
        } catch (error) {
            console.warn('Não foi possível salvar o rascunho da NF neste navegador:', error);
            setQuickDraftStatus('Não foi possível salvar o rascunho automaticamente neste navegador.', true);
            return false;
        }
    }

    function schedulePersistQuickDraft() {
        if (quickDraftRestoring) return;
        clearTimeout(quickDraftPersistTimer);
        quickDraftPersistTimer = window.setTimeout(persistQuickDraft, 400);
    }

    function readQuickDraft() {
        let draft;
        try {
            const raw = window.localStorage.getItem(quickDraftStorageKey);
            if (!raw) return null;
            draft = JSON.parse(raw);
        } catch (error) {
            console.warn('O rascunho salvo do cadastro rápido de NF está ilegível:', error);
            clearQuickDraft();
            return null;
        }
        if (!draft || draft.version !== 1 || !draft.header || typeof draft.header !== 'object') {
            clearQuickDraft();
            return null;
        }
        const savedAt = Date.parse(String(draft.savedAt || ''));
        if (!Number.isFinite(savedAt) || Date.now() - savedAt > quickDraftMaxAgeMs || savedAt > Date.now() + 60000) {
            clearQuickDraft();
            return null;
        }
        const header = Object.values(draft.header).some((value) => String(value || '').trim());
        const items = Array.isArray(draft.items) ? draft.items : [];
        if (!header && items.length === 0) {
            clearQuickDraft();
            return null;
        }
        draft.items = items;
        return draft;
    }

    function showQuickDraftRestore(draft) {
        pendingQuickDraft = draft;
        if (!quickDraftRestore) return;
        const savedAt = new Date(draft.savedAt);
        if (quickDraftRestoreDetail) {
            quickDraftRestoreDetail.textContent = `Último salvamento: ${savedAt.toLocaleString('pt-BR')}. Os dados ficam somente neste navegador.`;
        }
        quickDraftRestore.classList.remove('d-none');
    }

    async function restoreQuickDraft() {
        if (!pendingQuickDraft) return;
        const draft = pendingQuickDraft;
        quickDraftRestoring = true;
        try {
            createForm.reset();
            Object.entries(draft.header).forEach(([name, value]) => {
                const field = Array.from(createForm.querySelectorAll('#nfQuickHeaderFields [name]'))
                    .find((candidate) => candidate.name === name);
                if (field) field.value = String(value ?? '');
            });
            activeQuery = String(draft.activeQuery || draft.header.numero_documento || '');
            activeDocumentId = Number.isSafeInteger(Number(draft.documentId)) && Number(draft.documentId) > 0
                ? Number(draft.documentId)
                : null;
            activeDocumentUrl = String(draft.documentUrl || '');
            activeInvoice = null;
            createPrompt?.classList.add('d-none');
            createForm.classList.remove('d-none');
            content.replaceChildren();
            content.classList.add('d-none');
            title.textContent = activeDocumentId
                ? `Itens da NF ${draft.header.numero_documento || ''}`.trim()
                : 'Cadastrar nova NF';
            subtitle.textContent = activeDocumentId
                ? 'Rascunho recuperado. Confira os itens antes de concluir.'
                : 'Rascunho recuperado. Continue preenchendo os dados da NF.';
            if (activeDocumentId) {
                createHeaderFields?.classList.add('d-none');
                createItemsPanel?.classList.remove('d-none');
                const restored = await renderQuickItems(
                    draft.items.map((item) => ({ ...item, _draftItem: true })),
                    { restored: true },
                );
                if (!restored) {
                    throw new Error('Os dados do rascunho foram mantidos. Tente recuperar novamente.');
                }
                createItemsList?.querySelector('[data-item-search]')?.focus();
            } else {
                createHeaderFields?.classList.remove('d-none');
                createItemsPanel?.classList.add('d-none');
                setQuickDraftStatus('Rascunho recuperado. As próximas alterações serão salvas automaticamente.');
                createNumberInput?.focus();
            }
            pendingQuickDraft = null;
            quickDraftRestore?.classList.add('d-none');
        } catch (error) {
            console.error('Não foi possível recuperar o rascunho da NF:', error);
            pendingQuickDraft = draft;
            quickDraftRestore?.classList.remove('d-none');
            createForm?.classList.add('d-none');
            setQuickDraftStatus(error.message || 'Não foi possível recuperar o rascunho da NF.', true);
        } finally {
            quickDraftRestoring = false;
            schedulePersistQuickDraft();
        }
    }

    function prefillCreateForm(query, invoice = null) {
        if (!createForm) return;
        createForm.reset();
        activeDocumentId = null;
        activeDocumentUrl = '';
        createHeaderFields?.classList.remove('d-none');
        createItemsPanel?.classList.add('d-none');
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
        if (invoice) {
            createNumberInput.value = invoice.numero_documento || createNumberInput.value;
            createAccessKeyInput.value = invoice.chave_acesso || createAccessKeyInput.value;
            createCnpjInput.value = invoice.cnpj_emitente || createCnpjInput.value;
            createSupplierInput.value = invoice.fornecedor_nome || createSupplierInput.value;
            const emissionDate = String(invoice.data_emissao || '').slice(0, 10);
            if (emissionDate) document.getElementById('nfQuickEmissionDate').value = emissionDate;
        }
    }

    function startQuickRegistration(invoice = null) {
        const savedDraft = pendingQuickDraft || readQuickDraft();
        if (savedDraft) {
            showQuickDraftRestore(savedDraft);
            setQuickDraftStatus('Recupere ou descarte o rascunho salvo antes de iniciar outro cadastro.', true);
            return;
        }
        activeInvoice = invoice;
        activeQuery = invoice?.chave_acesso || invoice?.numero_documento || activeQuery;
        prefillCreateForm(activeQuery, invoice);
        createItemsList?.replaceChildren();
        createPrompt?.classList.add('d-none');
        createForm?.classList.remove('d-none');
        content.replaceChildren();
        content.classList.add('d-none');
        title.textContent = 'Cadastrar nova NF';
        subtitle.textContent = 'Dados essenciais do documento';
        feedback.textContent = '';
        setQuickDraftStatus('Salvamento automático ativo: alterações são guardadas neste computador.');
        createNumberInput?.focus();
        schedulePersistQuickDraft();
    }

    async function continueQuickRegistration(invoice) {
        activeInvoice = invoice;
        activeQuery = invoice.chave_acesso || invoice.numero_documento || activeQuery;
        prefillCreateForm(activeQuery, invoice);
        activeDocumentId = Number(invoice.id_documento);
        activeDocumentUrl = invoice.registration_url || '';
        createPrompt?.classList.add('d-none');
        createForm?.classList.remove('d-none');
        createHeaderFields?.classList.add('d-none');
        createItemsPanel?.classList.remove('d-none');
        content.replaceChildren();
        content.classList.add('d-none');
        title.textContent = `Itens da NF ${invoice.numero_documento || ''}`.trim();
        subtitle.textContent = 'Continue o rascunho e confira os itens antes de concluir';
        await renderQuickItems(invoice.itens_sugeridos || []);
        persistQuickDraft();
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
        if (invoice.can_register) {
            const registerButton = document.createElement('button');
            registerButton.className = 'btn btn-primary btn-sm mt-3 ms-2';
            registerButton.type = 'button';
            registerButton.textContent = 'Cadastrar esta NF no GALINT';
            registerButton.addEventListener('click', () => startQuickRegistration(invoice));
            content.appendChild(registerButton);
        }
        if (invoice.can_continue_registration) {
            const continueButton = document.createElement('button');
            continueButton.className = 'btn btn-primary btn-sm mt-3 ms-2';
            continueButton.type = 'button';
            continueButton.textContent = 'Continuar cadastro dos itens';
            continueButton.addEventListener('click', () => continueQuickRegistration(invoice));
            content.appendChild(continueButton);
        }

        content.classList.remove('d-none');
    }

    function createInput(labelText, type, value = '', className = 'form-control') {
        const wrapper = document.createElement('div');
        const label = document.createElement('label');
        label.className = 'form-label small mb-1';
        const id = `nfQuickItemField${++quickFieldCounter}`;
        label.htmlFor = id;
        label.textContent = labelText;
        const inputElement = document.createElement('input');
        inputElement.id = id;
        inputElement.type = type;
        inputElement.className = className;
        inputElement.value = value == null ? '' : String(value);
        if (type === 'number') {
            inputElement.min = '0';
            inputElement.step = 'any';
        }
        wrapper.append(label, inputElement);
        return { wrapper, input: inputElement };
    }

    async function loadQuickItemOptions() {
        if (quickItemOptions) return quickItemOptions;
        if (!quickItemOptionsRequest) {
            quickItemOptionsRequest = (async () => {
                const response = await fetch(createForm.dataset.optionsUrl, {
                    credentials: 'same-origin',
                    headers: { Accept: 'application/json' },
                });
                const payload = await response.json();
                if (!response.ok || !payload.success) {
                    throw new Error(payload.message || 'Não foi possível carregar as opções de categoria e unidade.');
                }
                const options = {
                    categories: Array.isArray(payload.categorias) ? payload.categorias : [],
                    units: Array.isArray(payload.unidades) ? payload.unidades : [],
                    defaultCategory: payload.categoria_padrao || '',
                };
                if (!options.categories.length || !options.units.length) {
                    throw new Error('As opções de categoria ou unidade não estão configuradas no sistema.');
                }
                quickItemOptions = options;
                return quickItemOptions;
            })();
        }
        try {
            return await quickItemOptionsRequest;
        } catch (error) {
            quickItemOptionsRequest = null;
            throw error;
        }
    }

    function createSelect(labelText, options, value = '') {
        const wrapper = document.createElement('div');
        const label = document.createElement('label');
        label.className = 'form-label small mb-1';
        const id = `nfQuickItemField${++quickFieldCounter}`;
        label.htmlFor = id;
        label.textContent = labelText;
        const select = document.createElement('select');
        select.id = id;
        select.className = 'form-select';
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'Selecione';
        select.appendChild(placeholder);
        options.forEach((optionValue) => {
            const option = document.createElement('option');
            option.value = optionValue;
            option.textContent = optionValue;
            select.appendChild(option);
        });
        if (value && !options.includes(value)) {
            const savedOption = document.createElement('option');
            savedOption.value = value;
            savedOption.textContent = `${value} (salvo no rascunho)`;
            select.appendChild(savedOption);
        }
        select.value = value || (options[0] || '');
        wrapper.append(label, select);
        return { wrapper, input: select };
    }

    function renderQuickItem(sourceItem = null) {
        if (!createItemsList) return;
        const isDraftItem = Boolean(sourceItem?._draftItem);
        const row = document.createElement('article');
        row.className = 'card border-secondary-subtle nf-quick-item-row';
        row.dataset.photoDraftKey = sourceItem?._draftItem && sourceItem.foto_arquivo_key
            ? sourceItem.foto_arquivo_key
            : `${quickDraftStorageKey}:${Date.now()}-${++quickFieldCounter}`;

        const body = document.createElement('div');
        body.className = 'card-body p-3';
        const heading = document.createElement('div');
        heading.className = 'd-flex justify-content-between align-items-start gap-2 mb-3';
        const headingText = document.createElement('div');
        headingText.className = 'fw-semibold';
        headingText.textContent = sourceItem?.descricao || sourceItem?.descricao_nova || 'Novo item da NF';
        heading.appendChild(headingText);
        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.className = 'btn btn-sm btn-outline-danger';
        removeButton.textContent = 'Remover';
        removeButton.addEventListener('click', () => {
            row.dispatchEvent(new Event('remove'));
            row.remove();
            schedulePersistQuickDraft();
        });
        heading.appendChild(removeButton);
        body.appendChild(heading);

        if (sourceItem?.codigo) {
            const sourceLabel = document.createElement('div');
            sourceLabel.className = 'small text-muted mb-2';
            sourceLabel.textContent = `Código na NF: ${sourceItem.codigo}`;
            body.appendChild(sourceLabel);
        }

        const modeGroup = document.createElement('div');
        modeGroup.className = 'mb-3';
        const modeLabel = document.createElement('label');
        modeLabel.className = 'form-label small mb-1';
        const mode = document.createElement('select');
        mode.id = `nfQuickItemMode${++quickFieldCounter}`;
        mode.className = 'form-select form-select-sm';
        modeLabel.htmlFor = mode.id;
        modeLabel.textContent = 'Vincular o item';
        mode.dataset.itemMode = '';
        [
            ['existente', 'Usar item já cadastrado'],
            ['novo', 'Cadastrar item novo'],
        ].forEach(([value, label]) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = label;
            mode.appendChild(option);
        });
        modeGroup.append(modeLabel, mode);
        body.appendChild(modeGroup);

        const existingPanel = document.createElement('div');
        existingPanel.className = 'mb-3 position-relative';
        const searchField = createInput('Buscar por código ou descrição', 'text');
        searchField.input.className = 'form-control';
        searchField.input.autocomplete = 'off';
        searchField.input.placeholder = 'Digite pelo menos 1 caractere';
        searchField.input.dataset.itemSearch = '';
        const codeField = document.createElement('input');
        codeField.type = 'hidden';
        codeField.dataset.itemCode = '';
        const selectedLabel = document.createElement('div');
        selectedLabel.className = 'form-text';
        selectedLabel.dataset.itemSelected = '';
        const results = document.createElement('div');
        results.className = 'list-group position-absolute w-100 shadow d-none';
        results.style.zIndex = '10';
        existingPanel.append(searchField.wrapper, codeField, selectedLabel, results);

        const newPanel = document.createElement('div');
        newPanel.className = 'row g-2 mb-3 d-none';
        const newCode = createInput('Código interno (opcional)', 'text', sourceItem?.codigo_novo || '');
        newCode.input.maxLength = 120;
        newCode.input.placeholder = 'Gerado automaticamente se vazio';
        newCode.input.dataset.newCode = '';
        const generateWrap = document.createElement('div');
        generateWrap.className = 'col-md-4';
        newCode.wrapper.className = 'col-md-8';
        const generateButton = document.createElement('button');
        generateButton.type = 'button';
        generateButton.className = 'btn btn-outline-secondary btn-sm mt-4';
        generateButton.textContent = 'Gerar código';
        generateWrap.appendChild(generateButton);

        const newDescription = createInput('Descrição do item novo', 'text', sourceItem?.descricao_nova || '');
        newDescription.input.maxLength = 255;
        newDescription.input.required = true;
        newDescription.input.dataset.newDescription = '';
        newDescription.wrapper.className = 'col-md-8';
        const newUnit = createSelect('Unidade', quickItemOptions.units, sourceItem?.unidade_nova || 'Unidade');
        newUnit.input.dataset.newUnit = '';
        newUnit.wrapper.className = 'col-md-4';
        const newCategory = createSelect(
            'Categoria',
            quickItemOptions.categories,
            sourceItem?.categoria || quickItemOptions.defaultCategory,
        );
        newCategory.input.dataset.newCategory = '';
        newCategory.wrapper.className = 'col-md-6';
        const newBrand = createInput('Marca (opcional)', 'text', sourceItem?.marca_nova || '');
        newBrand.input.maxLength = 200;
        newBrand.input.dataset.newBrand = '';
        newBrand.wrapper.className = 'col-md-6';
        newPanel.append(
            newCode.wrapper,
            generateWrap,
            newDescription.wrapper,
            newUnit.wrapper,
            newCategory.wrapper,
            newBrand.wrapper,
        );

        const photoPanel = document.createElement('section');
        photoPanel.className = 'border rounded p-3 mb-3';
        const photoHeading = document.createElement('div');
        photoHeading.className = 'fw-semibold mb-2';
        photoHeading.textContent = 'Foto do item';
        const photoContent = document.createElement('div');
        photoContent.className = 'd-flex flex-column flex-sm-row gap-3 align-items-start';
        const photoPreview = document.createElement('img');
        photoPreview.alt = 'Foto do item';
        photoPreview.className = 'rounded border bg-light';
        photoPreview.style.width = '112px';
        photoPreview.style.height = '112px';
        photoPreview.style.objectFit = 'contain';
        photoPreview.style.display = 'none';
        const photoPlaceholder = document.createElement('div');
        photoPlaceholder.className = 'd-flex align-items-center justify-content-center rounded border bg-light text-muted';
        photoPlaceholder.style.width = '112px';
        photoPlaceholder.style.height = '112px';
        photoPlaceholder.innerHTML = '<i class="bi bi-image fs-2" aria-hidden="true"></i>';
        const photoFields = document.createElement('div');
        photoFields.className = 'flex-grow-1 w-100';
        const photoFileLabel = document.createElement('label');
        photoFileLabel.className = 'form-label small mb-1';
        photoFileLabel.textContent = 'Enviar imagem do computador';
        const photoFile = document.createElement('input');
        photoFile.type = 'file';
        photoFile.accept = 'image/png,image/jpeg,image/webp,image/gif';
        photoFile.className = 'form-control form-control-sm';
        photoFile.dataset.photoFile = '';
        photoFileLabel.appendChild(photoFile);
        const photoSearchActions = document.createElement('div');
        photoSearchActions.className = 'd-flex flex-wrap gap-2 mt-2';
        const googleSearchButton = document.createElement('button');
        googleSearchButton.type = 'button';
        googleSearchButton.className = 'btn btn-sm btn-outline-primary';
        googleSearchButton.innerHTML = '<i class="bi bi-google me-1" aria-hidden="true"></i>Buscar imagem';
        const bingSearchButton = document.createElement('button');
        bingSearchButton.type = 'button';
        bingSearchButton.className = 'btn btn-sm btn-outline-secondary';
        bingSearchButton.innerHTML = '<i class="bi bi-search me-1" aria-hidden="true"></i>Bing Imagens';
        photoSearchActions.append(googleSearchButton, bingSearchButton);
        const photoUrl = createInput('Ou cole o link direto da imagem', 'url', sourceItem?._draftItem ? sourceItem.foto_url : '');
        photoUrl.input.className = 'form-control form-control-sm';
        photoUrl.input.placeholder = 'https://site.com/imagem.jpg';
        photoUrl.input.dataset.photoUrl = '';
        photoUrl.wrapper.className = 'mt-2';
        const photoStatus = document.createElement('div');
        photoStatus.className = 'form-text';
        photoStatus.textContent = 'A foto será vinculada ao item ao salvar a NF. Você pode substituir a foto existente.';
        photoFields.append(photoFileLabel, photoSearchActions, photoUrl.wrapper, photoStatus);
        photoContent.append(photoPlaceholder, photoPreview, photoFields);
        photoPanel.append(photoHeading, photoContent);

        let currentPhotoUrl = '';
        let currentPhotoObjectUrl = '';
        let photoClipboardTimer = null;
        const isLikelyImageUrl = (value) => {
            const raw = String(value || '').trim();
            return /^https?:\/\//i.test(raw)
                && (/\.(png|jpe?g|webp|gif|bmp|svg)(\?.*)?$/i.test(raw) || /image|img|photo|cdn/i.test(raw));
        };
        const inspectPhotoClipboard = async (announce = false) => {
            if (!navigator.clipboard?.readText || !window.isSecureContext) return;
            try {
                const copiedUrl = String(await navigator.clipboard.readText() || '').trim();
                if (!isLikelyImageUrl(copiedUrl)) return;
                photoUrl.input.value = copiedUrl;
                photoFile.value = '';
                updatePhotoPreview();
                schedulePersistQuickDraft();
                if (announce) photoStatus.textContent = 'Link de imagem copiado e preenchido automaticamente.';
                window.clearInterval(photoClipboardTimer);
                photoClipboardTimer = null;
                window.removeEventListener('focus', inspectPhotoClipboardOnFocus);
            } catch (_) {
                // O navegador pode negar a leitura da área de transferência.
            }
        };
        const inspectPhotoClipboardOnFocus = () => inspectPhotoClipboard(true);
        const startPhotoClipboardMonitor = () => {
            window.clearInterval(photoClipboardTimer);
            inspectPhotoClipboard(false);
            window.addEventListener('focus', inspectPhotoClipboardOnFocus);
            photoClipboardTimer = window.setInterval(() => inspectPhotoClipboard(false), 1400);
        };
        const updatePhotoPreview = () => {
            row.dataset.currentPhotoUrl = currentPhotoUrl;
            if (currentPhotoObjectUrl) {
                URL.revokeObjectURL(currentPhotoObjectUrl);
                currentPhotoObjectUrl = '';
            }
            const file = photoFile.files?.[0];
            const imageUrl = String(photoUrl.input.value || '').trim();
            const previewUrl = file
                ? (currentPhotoObjectUrl = URL.createObjectURL(file))
                : imageUrl || currentPhotoUrl;
            if (previewUrl) {
                photoPreview.src = previewUrl;
                photoPreview.style.display = '';
                photoPlaceholder.style.display = 'none';
                photoPreview.onerror = () => {
                    photoPreview.style.display = 'none';
                    photoPlaceholder.style.display = '';
                    photoStatus.textContent = 'Não foi possível exibir esta imagem. Confira o arquivo ou o link.';
                };
                photoPreview.onload = () => {
                    photoStatus.textContent = file
                        ? 'Imagem pronta para envio junto ao item.'
                        : imageUrl
                            ? 'Link de imagem preparado para salvar junto ao item.'
                            : 'Foto atual do item. Escolha um arquivo ou link para substituí-la.';
                };
            } else {
                photoPreview.removeAttribute('src');
                photoPreview.style.display = 'none';
                photoPlaceholder.style.display = '';
                photoStatus.textContent = 'Ainda sem foto. Envie uma imagem ou busque uma imagem para vincular.';
            }
        };
        const openImageSearch = (provider) => {
            const description = newDescription.input.value.trim()
                || searchField.input.value.split(' — ').slice(1).join(' — ').trim()
                || sourceItem?.descricao
                || '';
            const brand = newBrand.input.value.trim() || sourceItem?.item_existente?.marca || '';
            const query = [description, brand].filter(Boolean).join(' ');
            if (!query) {
                photoStatus.textContent = 'Preencha a descrição do item para buscar uma imagem.';
                return;
            }
            const url = provider === 'bing'
                ? `https://www.bing.com/images/search?q=${encodeURIComponent(query)}`
                : `https://www.google.com/search?tbm=isch&q=${encodeURIComponent(query)}`;
            window.open(url, '_blank', 'noopener');
            startPhotoClipboardMonitor();
            photoStatus.textContent = 'Abra a imagem desejada, copie o link direto e cole no campo acima.';
        };
        photoUrl.input.addEventListener('paste', () => {
            window.setTimeout(() => {
                const pastedUrl = String(photoUrl.input.value || '').trim();
                if (isLikelyImageUrl(pastedUrl)) {
                    photoFile.value = '';
                    updatePhotoPreview();
                }
            }, 0);
        });
        row.addEventListener('remove', () => {
            window.clearInterval(photoClipboardTimer);
            window.removeEventListener('focus', inspectPhotoClipboardOnFocus);
            if (currentPhotoObjectUrl) URL.revokeObjectURL(currentPhotoObjectUrl);
        }, { once: true });
        googleSearchButton.addEventListener('click', () => openImageSearch('google'));
        bingSearchButton.addEventListener('click', () => openImageSearch('bing'));
        photoFile.addEventListener('change', () => {
            if (photoFile.files?.length) {
                photoUrl.input.value = '';
                saveQuickDraftPhoto(row.dataset.photoDraftKey, photoFile.files[0])
                    .then(schedulePersistQuickDraft)
                    .catch((error) => {
                        console.warn('Não foi possível preservar a foto no rascunho da NF:', error);
                        setQuickDraftStatus('A foto foi selecionada, mas não pôde ser preservada no rascunho deste navegador.', true);
                        schedulePersistQuickDraft();
                    });
            }
            updatePhotoPreview();
            schedulePersistQuickDraft();
        });
        photoUrl.input.addEventListener('input', () => {
            if (photoUrl.input.value) {
                photoFile.value = '';
            }
            updatePhotoPreview();
            schedulePersistQuickDraft();
        });

        const valuesRow = document.createElement('div');
        valuesRow.className = 'row g-2';
        const quantity = createInput('Quantidade', 'number', sourceItem?.quantidade ?? '');
        quantity.input.min = '0.0001';
        quantity.input.required = true;
        quantity.input.dataset.itemQuantity = '';
        quantity.wrapper.className = 'col-6 col-md-3';
        const quantityUnit = createInput('Unidade da NF', 'text', sourceItem?.unidade_quantidade || sourceItem?.unidade || '');
        quantityUnit.input.maxLength = 30;
        quantityUnit.input.dataset.quantityUnit = '';
        quantityUnit.wrapper.className = 'col-6 col-md-3';
        const unitPrice = createInput('Valor unitário', 'number', sourceItem?.valor_unitario ?? '');
        unitPrice.input.min = '0';
        unitPrice.input.dataset.unitPrice = '';
        unitPrice.wrapper.className = 'col-6 col-md-3';
        const totalPrice = createInput('Valor total', 'number', sourceItem?.valor_total ?? '');
        totalPrice.input.min = '0';
        totalPrice.input.dataset.totalPrice = '';
        totalPrice.wrapper.className = 'col-6 col-md-3';
        valuesRow.append(quantity.wrapper, quantityUnit.wrapper, unitPrice.wrapper, totalPrice.wrapper);
        const updateTotal = () => {
            const quantityValue = Number(quantity.input.value);
            const unitPriceValue = Number(unitPrice.input.value);
            if (quantity.input.value && unitPrice.input.value && quantityValue > 0) {
                totalPrice.input.value = (quantityValue * unitPriceValue).toFixed(2);
            }
        };
        quantity.input.addEventListener('input', updateTotal);
        unitPrice.input.addEventListener('input', updateTotal);

        let suggestions = [];
        let searchTimer = null;
        const setMode = () => {
            const isNew = mode.value === 'novo';
            existingPanel.classList.toggle('d-none', isNew);
            newPanel.classList.toggle('d-none', !isNew);
            newDescription.input.required = isNew;
            newUnit.input.required = isNew;
            newCategory.input.required = isNew;
            codeField.required = !isNew;
        };
        mode.addEventListener('change', setMode);
        searchField.input.addEventListener('input', () => {
            codeField.value = '';
            selectedLabel.textContent = '';
            if (searchTimer) clearTimeout(searchTimer);
            const query = searchField.input.value.trim();
            if (!query) {
                results.classList.add('d-none');
                return;
            }
            searchTimer = setTimeout(async () => {
                try {
                    const url = new URL(createForm.dataset.itemSearchUrl, window.location.href);
                    url.searchParams.set('q', query);
                    const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
                    const payload = await response.json();
                    if (!response.ok || !payload.success) {
                        throw new Error(payload.message || 'Não foi possível buscar os itens.');
                    }
                    suggestions = payload.items || [];
                    results.replaceChildren();
                    if (!suggestions.length) {
                        const empty = document.createElement('div');
                        empty.className = 'list-group-item small text-muted';
                        empty.textContent = 'Nenhum item encontrado. Selecione “Cadastrar item novo”.';
                        results.appendChild(empty);
                    } else {
                        suggestions.forEach((item) => {
                            const option = document.createElement('button');
                            option.type = 'button';
                            option.className = 'list-group-item list-group-item-action';
                            option.textContent = `${item.codigo} — ${item.descricao}${item.unidade ? ` (${item.unidade})` : ''}`;
                            option.addEventListener('click', () => {
                                codeField.value = item.codigo;
                                searchField.input.value = `${item.codigo} — ${item.descricao}`;
                                selectedLabel.textContent = `Selecionado: ${item.descricao}${item.categoria ? ` · ${item.categoria}` : ''}`;
                                currentPhotoUrl = item.foto_url || '';
                                updatePhotoPreview();
                                if (!quantityUnit.input.value) {
                                    quantityUnit.input.value = item.unidade || '';
                                }
                                results.classList.add('d-none');
                                schedulePersistQuickDraft();
                            });
                            results.appendChild(option);
                        });
                    }
                    results.classList.remove('d-none');
                } catch (error) {
                    results.replaceChildren();
                    const errorOption = document.createElement('div');
                    errorOption.className = 'list-group-item small text-danger';
                    errorOption.textContent = error.message || 'Erro ao buscar itens.';
                    results.appendChild(errorOption);
                    results.classList.remove('d-none');
                }
            }, 180);
        });
        generateButton.addEventListener('click', async () => {
            generateButton.disabled = true;
            try {
                const response = await fetch(createForm.dataset.codeUrl, { credentials: 'same-origin' });
                const payload = await response.json();
                if (!response.ok || !payload.success) {
                    throw new Error(payload.message || 'Não foi possível gerar um código.');
                }
                newCode.input.value = payload.codigo;
                schedulePersistQuickDraft();
            } catch (error) {
                feedback.textContent = error.message || 'Erro ao gerar código.';
                feedback.className = 'small text-danger';
            } finally {
                generateButton.disabled = false;
            }
        });

        const matched = sourceItem?.item_existente;
        if (isDraftItem) {
            mode.value = sourceItem.modo === 'existente' ? 'existente' : 'novo';
            codeField.value = sourceItem.codigo_item || '';
            searchField.input.value = sourceItem.item_search || '';
            selectedLabel.textContent = sourceItem.item_selected_label || '';
            quantity.input.value = sourceItem.quantidade ?? '';
            unitPrice.input.value = sourceItem.valor_unitario ?? '';
            totalPrice.input.value = sourceItem.valor_total ?? '';
            currentPhotoUrl = sourceItem.foto_atual_url || '';
        } else if (matched) {
            mode.value = 'existente';
            codeField.value = matched.codigo;
            searchField.input.value = `${matched.codigo} — ${matched.descricao}`;
            selectedLabel.textContent = `Correspondência automática: ${matched.descricao}`;
            currentPhotoUrl = matched.foto_url || '';
            if (!quantityUnit.input.value) {
                quantityUnit.input.value = matched.unidade || '';
            }
        } else if (sourceItem) {
            mode.value = 'novo';
            newDescription.input.value = sourceItem.descricao || '';
            searchField.input.value = sourceItem.descricao || '';
        }
        if (isDraftItem && sourceItem.foto_url) {
            photoUrl.input.value = sourceItem.foto_url;
        }
        setMode();
        updatePhotoPreview();
        body.append(existingPanel, newPanel, photoPanel, valuesRow);
        row.appendChild(body);
        createItemsList.appendChild(row);
        if (!isDraftItem && sourceItem && !matched && searchField.input.value) {
            searchField.input.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }

    async function renderQuickItems(sourceItems, { restored = false } = {}) {
        try {
            await loadQuickItemOptions();
        } catch (error) {
            feedback.textContent = error.message || 'Não foi possível carregar as opções do cadastro.';
            feedback.className = 'small text-danger';
            return false;
        }
        createItemsList?.replaceChildren();
        if (Array.isArray(sourceItems) && sourceItems.length) {
            sourceItems.forEach(renderQuickItem);
            if (restored) {
                for (const row of Array.from(createItemsList?.querySelectorAll('.nf-quick-item-row') || [])) {
                    const key = row.dataset.photoDraftKey;
                    if (!key) continue;
                    const savedFile = await loadQuickDraftPhoto(key);
                    if (!savedFile) continue;
                    const fileInput = row.querySelector('[data-photo-file]');
                    if (!fileInput || typeof DataTransfer === 'undefined') continue;
                    const transfer = new DataTransfer();
                    transfer.items.add(savedFile);
                    fileInput.files = transfer.files;
                    fileInput.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
            feedback.textContent = restored
                ? `${sourceItems.length} item(ns) recuperado(s) do rascunho. Confira antes de salvar.`
                : `${sourceItems.length} item(ns) carregados do XML. Confira os vínculos sugeridos antes de salvar.`;
            feedback.className = restored ? 'small text-info' : 'small text-success';
            if (restored) {
                setQuickDraftStatus('Rascunho recuperado. As próximas alterações serão salvas automaticamente.');
            }
            return true;
        }
        renderQuickItem();
        feedback.textContent = restored
            ? 'Rascunho recuperado sem itens. Adicione e vincule os itens da NF.'
            : 'Não há itens disponíveis no XML. Adicione e vincule os itens da NF manualmente.';
        feedback.className = 'small text-muted';
        if (restored) {
            setQuickDraftStatus('Rascunho recuperado. As próximas alterações serão salvas automaticamente.');
        }
        return true;
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const query = input.value.trim();
        if (!query) {
            input.focus();
            return;
        }

        persistQuickDraft();
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

    createStartButton?.addEventListener('click', () => startQuickRegistration());

    createCancelButton?.addEventListener('click', () => {
        persistQuickDraft();
        createForm?.classList.add('d-none');
        if (activeInvoice) {
            feedback.textContent = '';
            renderDocument(activeInvoice);
            return;
        }
        createPrompt?.classList.remove('d-none');
        title.textContent = 'Nota fiscal';
        subtitle.textContent = '';
    });

    createItemsCancelButton?.addEventListener('click', () => {
        persistQuickDraft();
        showCreateResult(
            'Rascunho salvo. Você pode concluir a inclusão e conferência dos itens na página da NF.',
            activeDocumentUrl,
            'Abrir NF para continuar',
        );
    });

    createAddItemButton?.addEventListener('click', async () => {
        try {
            await loadQuickItemOptions();
        } catch (error) {
            feedback.textContent = error.message || 'Não foi possível carregar as opções do cadastro.';
            feedback.className = 'small text-danger';
            return;
        }
        renderQuickItem();
        schedulePersistQuickDraft();
        const lastRow = createItemsList?.lastElementChild;
        lastRow?.querySelector('[data-item-search]')?.focus();
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
        const isSavingItems = activeDocumentId !== null;
        if (!isSavingItems && !createForm.reportValidity()) return;
        const currentSubmitButton = isSavingItems ? createItemsSubmitButton : createHeaderSubmitButton;
        if (currentSubmitButton) currentSubmitButton.disabled = true;
        feedback.textContent = isSavingItems ? 'Salvando itens para conferência...' : 'Salvando os dados da NF...';
        feedback.className = 'small text-muted';
        feedback.setAttribute('aria-busy', 'true');
        try {
            let response;
            if (isSavingItems) {
                const itemsUrl = createForm.dataset.itemsUrlTemplate.replace('/0/', `/${activeDocumentId}/`);
                const itemRows = Array.from(createItemsList?.querySelectorAll('.nf-quick-item-row') || []);
                const itemsPayload = collectQuickItems();
                const formData = new FormData();
                formData.append('payload', JSON.stringify({ itens: itemsPayload }));
                itemRows.forEach((row, index) => {
                    const file = row.querySelector('[data-photo-file]')?.files?.[0];
                    if (file) formData.append(`foto_${index}`, file, file.name);
                });
                response = await fetch(itemsUrl, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { Accept: 'application/json' },
                    body: formData,
                });
            } else {
                response = await fetch(form.dataset.createUrl, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
                    body: JSON.stringify(Object.fromEntries(new FormData(createForm).entries())),
                });
            }
            const payload = await response.json();
            if (!isSavingItems && response.status === 409 && payload.existing_url) {
                showCreateResult(payload.message || 'Esta NF já está cadastrada.', payload.existing_url, 'Abrir NF existente');
                return;
            }
            if (!response.ok || !payload.success) {
                throw new Error(payload.message || (isSavingItems
                    ? 'Não foi possível salvar os itens da NF.'
                    : 'Não foi possível cadastrar a NF.'));
            }
            if (!isSavingItems) {
                activeDocumentId = payload.document.id_documento;
                activeDocumentUrl = payload.url;
                createHeaderFields?.classList.add('d-none');
                createItemsPanel?.classList.remove('d-none');
                createItemsSubmitButton.textContent = 'Salvar itens';
                title.textContent = `Itens da NF ${payload.document.numero_documento}`;
                subtitle.textContent = 'Associe cada produto ao estoque ou cadastre-o como novo';
                await renderQuickItems(payload.itens_sugeridos || []);
                createItemsList?.querySelector('[data-item-search]')?.focus();
                persistQuickDraft();
                return;
            }
            clearQuickDraft();
            showCreateResult(payload.message, payload.url, 'Abrir NF para conferir');
        } catch (error) {
            feedback.textContent = error.message || 'Erro ao cadastrar a NF.';
            feedback.className = 'small text-danger';
        } finally {
            feedback.removeAttribute('aria-busy');
            if (currentSubmitButton) currentSubmitButton.disabled = false;
        }
    });

    createForm?.addEventListener('input', schedulePersistQuickDraft);
    createForm?.addEventListener('change', schedulePersistQuickDraft);
    createForm?.addEventListener('submit', schedulePersistQuickDraft, true);
    createItemsList?.addEventListener('click', (event) => {
        if (event.target.closest('button')) {
            schedulePersistQuickDraft();
        }
    });
    quickDraftRestoreButton?.addEventListener('click', restoreQuickDraft);
    quickDraftDiscardButton?.addEventListener('click', () => {
        clearQuickDraft();
        quickDraftRestore?.classList.add('d-none');
        setQuickDraftStatus('Rascunho descartado.');
    });
    modalElement.addEventListener('show.bs.modal', () => {
        if (!pendingQuickDraft) {
            const savedDraft = readQuickDraft();
            if (savedDraft) {
                showQuickDraftRestore(savedDraft);
            }
        }
        if (pendingQuickDraft) {
            quickDraftRestore?.classList.remove('d-none');
        }
    });
    modalElement.addEventListener('hidden.bs.modal', () => {
        persistQuickDraft();
    });
    window.addEventListener('pagehide', persistQuickDraft);
    window.addEventListener('beforeunload', persistQuickDraft);
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
            persistQuickDraft();
        }
    });
    quickDraftAutoSaveTimer = window.setInterval(() => {
        if (!createForm?.classList.contains('d-none')) {
            persistQuickDraft();
        }
    }, quickDraftAutoSaveIntervalMs);

    const savedQuickDraft = readQuickDraft();
    if (savedQuickDraft) {
        showQuickDraftRestore(savedQuickDraft);
    }
})();
