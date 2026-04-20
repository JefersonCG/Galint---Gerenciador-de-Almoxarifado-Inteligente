(function () {
    function escapeHtml(value) {
        var div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    }

    function buildUrl(url, params) {
        var target = new URL(url, window.location.origin);
        Object.keys(params || {}).forEach(function (key) {
            var value = params[key];
            if (value === undefined || value === null || value === '') {
                return;
            }
            target.searchParams.set(key, value);
        });
        return target.toString();
    }

    async function fetchWithSession(url, options, authMessage) {
        if (typeof window.galintFetchWithAuth === 'function') {
            return window.galintFetchWithAuth(url, options, authMessage || 'Sua sessao expirou. Faca login novamente.');
        }

        var response = await fetch(url, Object.assign({
            credentials: 'same-origin',
            cache: 'no-cache'
        }, options || {}));

        if (response.status === 401) {
            var authPayload = await response.clone().json().catch(function () { return {}; });
            var authError = new Error(authPayload.message || authMessage || 'Sua sessao expirou. Faca login novamente.');
            authError.isAuthRedirect = true;
            throw authError;
        }

        if (response.redirected && /login/i.test(response.url || '')) {
            window.location.href = response.url;
            var redirectError = new Error(authMessage || 'Sua sessao expirou. Faca login novamente.');
            redirectError.isAuthRedirect = true;
            throw redirectError;
        }

        return response;
    }

    function normaliseIdentifier(value) {
        return String(value || '').trim().toLowerCase();
    }

    function getToneClass(tone) {
        if (tone === 'success') {
            return 'alert-success';
        }
        if (tone === 'danger') {
            return 'alert-danger';
        }
        if (tone === 'warning') {
            return 'alert-warning';
        }
        return 'alert-secondary';
    }

    function renderPreviewChips(values) {
        var list = Array.isArray(values) ? values : [];
        if (!list.length) {
            return '';
        }
        return '<div class="express-return-preview-chips">' + list.map(function (value) {
            return '<span class="express-return-chip">' + escapeHtml(value) + '</span>';
        }).join('') + '</div>';
    }

    function init(config) {
        var modalEl = document.getElementById(config.modalId);
        if (!modalEl || !window.bootstrap) {
            return null;
        }

        var openButton = document.getElementById(config.openButtonId);
        var modal = typeof window.bootstrap.Modal.getOrCreateInstance === 'function'
            ? window.bootstrap.Modal.getOrCreateInstance(modalEl)
            : new window.bootstrap.Modal(modalEl);
        var statusEl = modalEl.querySelector('[data-express-return-role="status"]');
        var collaboratorsEl = modalEl.querySelector('[data-express-return-role="collaborators"]');
        var itemsEl = modalEl.querySelector('[data-express-return-role="items"]');
        var detailEl = modalEl.querySelector('[data-express-return-role="detail"]');
        var submitButton = modalEl.querySelector('[data-express-return-role="submit"]');
        if (!statusEl || !collaboratorsEl || !itemsEl || !detailEl || !submitButton) {
            return null;
        }

        var state = {
            collaborators: [],
            selectedCollaborator: null,
            items: [],
            selectedItem: null,
            collaboratorsRequestId: 0,
            itemsRequestId: 0,
        };

        function getCollaboratorIdentity(collaborator) {
            return String(collaborator && (collaborator.matricula || collaborator.id || '') || '');
        }

        function getItemIdentity(item) {
            if (typeof config.getItemIdentity === 'function') {
                return String(config.getItemIdentity(item) || '');
            }
            return String(item && (item.saida_id || item.id || item.codigo || '') || '');
        }

        function revealStatus() {
            if (!statusEl || typeof statusEl.scrollIntoView !== 'function') {
                return;
            }
            try {
                statusEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            } catch (_error) {
                statusEl.scrollIntoView();
            }
        }

        function setStatus(message, tone, options) {
            statusEl.textContent = message || 'Sem informações no momento.';
            statusEl.className = 'alert express-return-status ' + getToneClass(tone);
            if (options && options.reveal) {
                revealStatus();
            }
        }

        function renderCollaborators() {
            if (!state.collaborators.length) {
                collaboratorsEl.innerHTML = '<div class="express-return-empty">' + escapeHtml((config.messages && config.messages.noCollaborators) || 'Nenhum colaborador encontrado.') + '</div>';
                return;
            }

            var activeId = getCollaboratorIdentity(state.selectedCollaborator);
            collaboratorsEl.innerHTML = state.collaborators.map(function (collaborator, index) {
                var collaboratorId = getCollaboratorIdentity(collaborator);
                var activeClass = collaboratorId && collaboratorId === activeId ? ' is-active' : '';
                var previewItems = renderPreviewChips(collaborator.preview_items || []);
                return '' +
                    '<button type="button" class="express-return-collaborator' + activeClass + '" data-collaborator-index="' + index + '">' +
                        '<div class="express-return-item-title">' + escapeHtml(collaborator.nome || collaborator.label || collaborator.matricula || 'Colaborador') + '</div>' +
                        '<div class="express-return-item-meta">' +
                            '<span class="express-return-item-code">Matrícula: ' + escapeHtml(collaborator.matricula || '-') + '</span>' +
                            '<span class="express-return-chip is-highlight">' + escapeHtml(String(collaborator.total_items || 0)) + ' item(ns)</span>' +
                            (collaborator.ultima_saida_label ? '<span>Última saída: ' + escapeHtml(collaborator.ultima_saida_label) + '</span>' : '') +
                        '</div>' +
                        ((collaborator.local_servico || collaborator.latest_label)
                            ? '<div class="express-return-item-meta">' +
                                (collaborator.local_servico ? '<span>Local: ' + escapeHtml(collaborator.local_servico) + '</span>' : '') +
                                (collaborator.latest_label ? '<span>' + escapeHtml(collaborator.latest_label) + '</span>' : '') +
                            '</div>'
                            : '') +
                        previewItems +
                    '</button>';
            }).join('');

            collaboratorsEl.querySelectorAll('[data-collaborator-index]').forEach(function (buttonEl) {
                buttonEl.addEventListener('click', function () {
                    var index = parseInt(buttonEl.getAttribute('data-collaborator-index') || '-1', 10);
                    if (!Number.isFinite(index) || index < 0 || !state.collaborators[index]) {
                        return;
                    }
                    state.selectedCollaborator = state.collaborators[index];
                    renderCollaborators();
                    loadItems(state.selectedCollaborator);
                });
            });
        }

        function renderItems() {
            if (!state.selectedCollaborator) {
                itemsEl.innerHTML = '<div class="express-return-empty">' + escapeHtml((config.messages && config.messages.selectCollaboratorFirst) || 'Selecione um colaborador acima.') + '</div>';
                return;
            }
            if (!state.items.length) {
                itemsEl.innerHTML = '<div class="express-return-empty">' + escapeHtml((config.messages && config.messages.noItems) || 'Nenhum item disponível para devolução.') + '</div>';
                return;
            }

            var activeId = getItemIdentity(state.selectedItem);
            itemsEl.innerHTML = state.items.map(function (item, index) {
                var itemId = getItemIdentity(item);
                var activeClass = itemId && itemId === activeId ? ' is-active' : '';
                var innerHtml = typeof config.renderItemButtonContent === 'function'
                    ? config.renderItemButtonContent(item, state.selectedCollaborator, escapeHtml)
                    : '<div class="express-return-item-title">' + escapeHtml(item.descricao || item.codigo || 'Item') + '</div>';
                return '<button type="button" class="express-return-item' + activeClass + '" data-item-index="' + index + '">' + innerHtml + '</button>';
            }).join('');

            itemsEl.querySelectorAll('[data-item-index]').forEach(function (buttonEl) {
                buttonEl.addEventListener('click', function () {
                    var index = parseInt(buttonEl.getAttribute('data-item-index') || '-1', 10);
                    if (!Number.isFinite(index) || index < 0 || !state.items[index]) {
                        return;
                    }
                    state.selectedItem = state.items[index];
                    renderItems();
                    renderDetail();
                    setStatus((config.messages && config.messages.readyToSubmit) || 'Revise os dados e confirme a devolução.', 'success');
                });
            });
        }

        function renderDetail() {
            if (!state.selectedItem) {
                detailEl.className = 'express-return-detail is-empty';
                detailEl.innerHTML = '<strong>' + escapeHtml((config.messages && config.messages.emptyDetailTitle) || 'Nenhum item selecionado.') + '</strong>' +
                    '<div class="express-return-hint">' + escapeHtml((config.messages && config.messages.emptyDetailHint) || 'Escolha um item da lista acima para liberar a devolução.') + '</div>';
                submitButton.disabled = true;
                submitButton.textContent = (config.messages && config.messages.submitButton) || 'Fazer devolução';
                return;
            }

            detailEl.className = 'express-return-detail';
            detailEl.innerHTML = typeof config.renderDetail === 'function'
                ? config.renderDetail({
                    item: state.selectedItem,
                    collaborator: state.selectedCollaborator,
                    modalEl: modalEl,
                    escapeHtml: escapeHtml,
                })
                : '<div class="express-return-detail-title">' + escapeHtml(state.selectedItem.descricao || state.selectedItem.codigo || 'Item') + '</div>';
            submitButton.disabled = false;
            submitButton.textContent = (config.messages && config.messages.submitButton) || 'Fazer devolução';
        }

        async function loadCollaborators(options) {
            var requestId = ++state.collaboratorsRequestId;
            state.collaborators = [];
            state.selectedCollaborator = null;
            state.items = [];
            state.selectedItem = null;
            collaboratorsEl.innerHTML = '<div class="express-return-empty">' + escapeHtml((config.messages && config.messages.loadingCollaborators) || 'Carregando colaboradores...') + '</div>';
            renderItems();
            renderDetail();

            try {
                var collaboratorsUrl = typeof config.buildCollaboratorsUrl === 'function' ? config.buildCollaboratorsUrl() : config.collaboratorsUrl;
                var response = await fetchWithSession(collaboratorsUrl, {
                    headers: { 'Accept': 'application/json' }
                }, config.authMessageLoad);
                var data = await response.json().catch(function () { return {}; });
                if (!response.ok || !data || data.success === false) {
                    throw new Error((data && (data.error || data.message)) || 'Não foi possível carregar os colaboradores da devolução expressa.');
                }
                if (requestId !== state.collaboratorsRequestId) {
                    return;
                }

                state.collaborators = Array.isArray(data.collaborators) ? data.collaborators : [];
                var preferredIdentifier = options && options.preferredIdentifier ? options.preferredIdentifier : '';
                if (!preferredIdentifier && typeof config.getInitialCollaboratorIdentifier === 'function') {
                    preferredIdentifier = config.getInitialCollaboratorIdentifier();
                }
                var normalizedPreferred = normaliseIdentifier(preferredIdentifier);
                if (normalizedPreferred) {
                    state.selectedCollaborator = state.collaborators.find(function (collaborator) {
                        var values = [collaborator.matricula, collaborator.nome, collaborator.label];
                        return values.some(function (value) {
                            var normalizedValue = normaliseIdentifier(value);
                            return normalizedValue === normalizedPreferred || normalizedValue.indexOf(normalizedPreferred) > -1;
                        });
                    }) || null;
                }

                renderCollaborators();

                if (state.selectedCollaborator) {
                    await loadItems(state.selectedCollaborator, { silent: true });
                    if (!(options && options.silent)) {
                        setStatus((config.messages && config.messages.selectItem) || 'Escolha o item para concluir a devolução expressa.', 'success');
                    }
                    return;
                }

                if (!(options && options.silent)) {
                    setStatus(
                        data.message || (state.collaborators.length
                            ? ((config.messages && config.messages.selectCollaborator) || 'Escolha o colaborador para carregar os itens.')
                            : ((config.messages && config.messages.noCollaborators) || 'Nenhum colaborador elegível foi encontrado.')),
                        data.window_open === false ? 'warning' : 'info'
                    );
                }
            } catch (error) {
                if (error && error.isAuthRedirect) {
                    return;
                }
                if (requestId !== state.collaboratorsRequestId) {
                    return;
                }
                state.collaborators = [];
                renderCollaborators();
                renderItems();
                renderDetail();
                setStatus(error.message || 'Falha ao carregar os colaboradores da devolução expressa.', 'danger');
            }
        }

        async function loadItems(collaborator, options) {
            if (!collaborator) {
                return;
            }

            var requestId = ++state.itemsRequestId;
            state.selectedCollaborator = collaborator;
            state.items = [];
            state.selectedItem = null;
            renderCollaborators();
            itemsEl.innerHTML = '<div class="express-return-empty">' + escapeHtml((config.messages && config.messages.loadingItems) || 'Carregando itens...') + '</div>';
            renderDetail();

            try {
                var itemsUrl = typeof config.buildItemsUrl === 'function' ? config.buildItemsUrl(collaborator) : config.itemsUrl;
                var response = await fetchWithSession(itemsUrl, {
                    headers: { 'Accept': 'application/json' }
                }, config.authMessageLoad);
                var data = await response.json().catch(function () { return {}; });
                if (!response.ok || !data || data.success === false) {
                    throw new Error((data && (data.error || data.message)) || 'Não foi possível carregar os itens da devolução expressa.');
                }
                if (requestId !== state.itemsRequestId) {
                    return;
                }

                state.items = Array.isArray(data.items) ? data.items : [];
                if (Array.isArray(state.items) && state.items.length === 1) {
                    state.selectedItem = state.items[0];
                }
                renderItems();
                renderDetail();

                if (!(options && options.silent)) {
                    setStatus(
                        data.message || (state.items.length
                            ? ((config.messages && config.messages.selectItem) || 'Escolha o item para concluir a devolução expressa.')
                            : ((config.messages && config.messages.noItems) || 'Nenhum item disponível para este colaborador.')),
                        state.items.length ? 'success' : 'info'
                    );
                }
            } catch (error) {
                if (error && error.isAuthRedirect) {
                    return;
                }
                if (requestId !== state.itemsRequestId) {
                    return;
                }
                state.items = [];
                state.selectedItem = null;
                renderItems();
                renderDetail();
                setStatus(error.message || 'Falha ao carregar os itens da devolução expressa.', 'danger');
            }
        }

        async function submitReturn() {
            if (!state.selectedCollaborator) {
                setStatus((config.messages && config.messages.selectCollaborator) || 'Escolha o colaborador antes de devolver.', 'warning', { reveal: true });
                return;
            }
            if (!state.selectedItem) {
                setStatus((config.messages && config.messages.selectItem) || 'Escolha o item antes de devolver.', 'warning', { reveal: true });
                return;
            }

            var request;
            submitButton.disabled = true;
            submitButton.textContent = (config.messages && config.messages.submitBusy) || 'Devolvendo...';

            try {
                request = config.buildSubmitRequest({
                    collaborator: state.selectedCollaborator,
                    item: state.selectedItem,
                    modalEl: modalEl,
                });
            } catch (error) {
                setStatus(error.message || 'Não foi possível preparar a devolução.', 'warning', { reveal: true });
                submitButton.disabled = !state.selectedItem;
                submitButton.textContent = (config.messages && config.messages.submitButton) || 'Fazer devolução';
                return;
            }

            if (!request || !request.url) {
                setStatus('Configuração inválida da devolução expressa.', 'danger', { reveal: true });
                submitButton.disabled = !state.selectedItem;
                submitButton.textContent = (config.messages && config.messages.submitButton) || 'Fazer devolução';
                return;
            }

            try {
                var response = await fetchWithSession(request.url, request.options || {}, request.authMessage || config.authMessageSubmit);
                var data = await response.json().catch(function () { return {}; });
                if (!response.ok || !data || data.success === false) {
                    throw new Error((data && (data.error || data.message)) || 'Falha ao registrar a devolução expressa.');
                }

                await loadCollaborators({
                    preferredIdentifier: getCollaboratorIdentity(state.selectedCollaborator),
                    silent: true,
                });
                setStatus(data.message || ((config.messages && config.messages.submitSuccess) || 'Devolução registrada com sucesso.'), 'success', { reveal: true });
            } catch (error) {
                if (error && error.isAuthRedirect) {
                    return;
                }
                setStatus(error.message || ((config.messages && config.messages.submitError) || 'Falha ao registrar a devolução expressa.'), 'danger', { reveal: true });
            } finally {
                submitButton.disabled = !state.selectedItem;
                submitButton.textContent = (config.messages && config.messages.submitButton) || 'Fazer devolução';
            }
        }

        function resetState() {
            state.collaborators = [];
            state.selectedCollaborator = null;
            state.items = [];
            state.selectedItem = null;
            renderCollaborators();
            renderItems();
            renderDetail();
            setStatus((config.messages && config.messages.initialStatus) || 'Abra o painel para carregar os colaboradores com devolução pendente.', 'info');
        }

        if (openButton && config.bindOpenButton !== false) {
            openButton.addEventListener('click', function () {
                modal.show();
            });
        }

        modalEl.addEventListener('shown.bs.modal', function () {
            loadCollaborators();
        });
        modalEl.addEventListener('hidden.bs.modal', resetState);
        submitButton.addEventListener('click', submitReturn);

        resetState();

        return {
            open: function () {
                modal.show();
            },
            reload: function () {
                return loadCollaborators();
            },
        };
    }

    window.GalintExpressReturnModal = {
        init: init,
        buildUrl: buildUrl,
        escapeHtml: escapeHtml,
    };
}());