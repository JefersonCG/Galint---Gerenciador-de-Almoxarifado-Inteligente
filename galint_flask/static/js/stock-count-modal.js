(function () {
    function initialize() {
        const searchForm = document.getElementById('topbar-item-search');
        const modalElement = document.getElementById('stockCountModal');
        const form = document.getElementById('stockCountForm');
        const feedback = document.getElementById('stockCountFeedback');
        const details = document.getElementById('stockCountItemDetails');
        if (!searchForm?.dataset.stockCountLookupUrl || !modalElement || !form || !window.bootstrap) {
            return;
        }

        const modal = window.bootstrap.Modal.getOrCreateInstance(modalElement);
        const searchInput = document.getElementById('topbar-item-query');
        const directGroup = document.getElementById('stockCountDirectGroup');
        const packageGroup = document.getElementById('stockCountPackageGroup');
        const directInput = document.getElementById('stockCountDirectValue');
        const packageInput = document.getElementById('stockCountPackageValue');
        const internalInput = document.getElementById('stockCountInternalValue');
        const submitButton = document.getElementById('stockCountSubmit');
        const photoBox = document.getElementById('stockCountPhotoBox');
        const photoLink = document.getElementById('stockCountPhotoLink');
        const photo = document.getElementById('stockCountPhoto');
        const photoEmptyIcon = document.getElementById('stockCountPhotoEmptyIcon');
        const photoEmptyText = document.getElementById('stockCountPhotoEmptyText');
        let selectedItem = null;
        let requestVersion = 0;

        function setFeedback(message, isError) {
            if (!feedback) {
                return;
            }
            feedback.textContent = message || '';
            feedback.className = message ? `small alert alert-${isError ? 'danger' : 'success'} py-2` : 'small';
        }

        function setUnit(unit) {
            modalElement.querySelectorAll('[data-stock-unit]').forEach((element) => {
                element.textContent = unit || 'un';
            });
        }

        function showPhotoPlaceholder() {
            if (!photoBox) {
                return;
            }
            photoBox.classList.add('is-empty');
            photoLink?.classList.add('d-none');
            photoLink?.removeAttribute('href');
            photo?.removeAttribute('src');
            photoEmptyIcon?.classList.remove('d-none');
            photoEmptyText?.classList.remove('d-none');
        }

        function renderPhoto(item) {
            const url = String(item.foto_url || '').trim();
            if (!url || !photoBox || !photo || !photoLink) {
                showPhotoPlaceholder();
                return;
            }
            photoBox.classList.remove('is-empty');
            photoLink.classList.remove('d-none');
            photoLink.href = url;
            photo.alt = item.descricao ? `Foto de ${item.descricao}` : 'Foto do item';
            photo.src = url;
            photoEmptyIcon?.classList.add('d-none');
            photoEmptyText?.classList.add('d-none');
        }

        // Arquivo da foto apagado ou corrompido: volta para "Sem foto" em vez do ícone quebrado.
        photo?.addEventListener('error', () => {
            if (photo.getAttribute('src')) {
                showPhotoPlaceholder();
            }
        });

        function renderItem(item) {
            selectedItem = item;
            document.getElementById('stockCountItemCode').textContent = `Código: ${item.codigo}`;
            document.getElementById('stockCountItemDescription').textContent = item.descricao || 'Item';
            renderPhoto(item);
            document.getElementById('stockCountSystemBalance').textContent = item.saldo_display || `${item.saldo} ${item.unidade || 'un'}`;

            const input = item.input || {};
            const packaged = Boolean(input.supports_packaging);
            const pending = Boolean(item.pre_cadastro_pendente);
            setUnit(input.internal_unit_display || item.unidade || 'un');
            directGroup.classList.toggle('d-none', packaged);
            packageGroup.classList.toggle('d-none', !packaged);
            directInput.disabled = packaged || pending;
            packageInput.disabled = !packaged || pending;
            internalInput.disabled = !packaged || pending;
            directInput.required = !packaged && !pending;
            packageInput.required = packaged && !pending;
            internalInput.required = packaged && !pending;
            directInput.step = input.internal_allow_decimal ? 'any' : '1';
            internalInput.step = input.internal_allow_decimal ? 'any' : '1';
            directInput.value = '';
            packageInput.value = '';
            internalInput.value = '';

            document.getElementById('stockCountPackageHint').textContent =
                input.package_content_display || 'Informe embalagens fechadas e quantidade solta.';
            document.getElementById('stockCountPendingWarning').classList.toggle('d-none', !pending);
            submitButton.disabled = pending;
            details.classList.remove('d-none');
            setFeedback('', false);
            window.setTimeout(() => {
                (packaged ? packageInput : directInput).focus();
            }, 120);
        }

        async function fetchJson(url, options) {
            const requestOptions = {
                credentials: 'same-origin',
                ...options,
                headers: { Accept: 'application/json', ...(options?.headers || {}) },
            };
            const response = window.galintFetchWithAuth
                ? await window.galintFetchWithAuth(
                    url,
                    requestOptions,
                    'Não foi possível acessar a contagem de estoque.'
                )
                : await window.fetch(url, requestOptions);
            let payload;
            try {
                payload = await response.json();
            } catch {
                throw new Error('O servidor retornou uma resposta inválida.');
            }
            return { response, payload };
        }

        window.galintTryOpenStockCountModal = async function (rawCode) {
            const code = String(rawCode || '').trim();
            if (!code) {
                return false;
            }

            const version = ++requestVersion;
            selectedItem = null;
            const lookupUrl = new URL(searchForm.dataset.stockCountLookupUrl, window.location.origin);
            lookupUrl.searchParams.set('codigo', code);
            let result;
            try {
                result = await fetchJson(lookupUrl.toString());
            } catch (error) {
                if (version !== requestVersion) {
                    return true;
                }
                details.classList.add('d-none');
                setFeedback(error?.message || 'Falha ao localizar o item.', true);
                modal.show();
                return true;
            }

            if (version !== requestVersion) {
                return true;
            }
            if (result.response.status === 404) {
                return false;
            }
            if (!result.response.ok || !result.payload?.success) {
                details.classList.add('d-none');
                setFeedback(result.payload?.message || 'Não foi possível localizar o item.', true);
                modal.show();
                return true;
            }

            renderItem(result.payload.item || {});
            if (searchInput) {
                searchInput.value = '';
            }
            modal.show();
            return true;
        };

        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            if (!selectedItem || submitButton.disabled) {
                return;
            }

            const input = selectedItem.input || {};
            const packaged = Boolean(input.supports_packaging);
            const mode = packaged ? 'packages_plus_internal' : 'direct';
            if (!form.reportValidity()) {
                return;
            }

            const data = packaged
                ? {
                    mode,
                    package_quantity: packageInput.value,
                    internal_quantity: internalInput.value,
                }
                : { mode, quantity: directInput.value };
            const confirmQuantity = packaged
                ? `${packageInput.value} ${input.package_plural || 'embalagens'} + ${internalInput.value} ${input.internal_unit_display || 'un'}`
                : `${directInput.value} ${input.internal_unit_display || 'un'}`;
            if (!window.confirm(`Confirmar contagem física de ${confirmQuantity} para "${selectedItem.descricao}"?`)) {
                return;
            }

            const template = searchForm.dataset.stockCountAdjustUrlTemplate || '';
            const url = template.replace('__CODIGO__', encodeURIComponent(selectedItem.codigo));
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Salvando';
            setFeedback('', false);
            try {
                const { response, payload } = await fetchJson(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data),
                });
                if (!response.ok || !payload?.success) {
                    throw new Error(payload?.message || 'Não foi possível salvar o ajuste.');
                }
                setFeedback(payload.changed ? 'Contagem aplicada e registrada.' : 'O saldo já estava igual à contagem.', false);
                window.setTimeout(() => {
                    modal.hide();
                    if (searchInput) {
                        searchInput.value = '';
                        searchInput.focus();
                    }
                }, 700);
            } catch (error) {
                setFeedback(error?.message || 'Falha ao salvar o ajuste de estoque.', true);
            } finally {
                submitButton.disabled = Boolean(selectedItem?.pre_cadastro_pendente);
                submitButton.textContent = 'Aplicar contagem';
            }
        });

        modalElement.addEventListener('hidden.bs.modal', () => {
            selectedItem = null;
            form.reset();
            details.classList.add('d-none');
            showPhotoPlaceholder();
            setFeedback('', false);
            if (searchInput) {
                searchInput.value = '';
                searchInput.focus();
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize, { once: true });
    } else {
        initialize();
    }
})();
