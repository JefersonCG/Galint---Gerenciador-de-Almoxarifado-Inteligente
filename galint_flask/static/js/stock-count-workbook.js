// Botão "Conferência física": escolhe as categorias e baixa a planilha A4 só com elas.
(function () {
    function initialize() {
        const modalElement = document.getElementById('stockCountWorkbookModal');
        if (!modalElement || !window.bootstrap) {
            return;
        }

        const categoriesUrl = modalElement.dataset.categoriesUrl;
        const downloadUrl = modalElement.dataset.downloadUrl;
        const list = document.getElementById('stockCountWorkbookCategories');
        const summary = document.getElementById('stockCountWorkbookSummary');
        const feedback = document.getElementById('stockCountWorkbookFeedback');
        const submitButton = document.getElementById('stockCountWorkbookSubmit');
        const selectAllButton = document.getElementById('stockCountWorkbookSelectAll');
        const clearButton = document.getElementById('stockCountWorkbookClear');
        const modal = window.bootstrap.Modal.getOrCreateInstance(modalElement);
        const submitLabel = submitButton.innerHTML;
        let categories = [];
        let generating = false;

        function setFeedback(message, tone) {
            feedback.textContent = message || '';
            feedback.className = message ? `small alert alert-${tone || 'danger'} py-2` : 'small';
        }

        function plural(count, singular, pluralWord) {
            return `${count.toLocaleString('pt-BR')} ${count === 1 ? singular : pluralWord}`;
        }

        function checkboxes() {
            return Array.from(list.querySelectorAll('input[type="checkbox"]'));
        }

        function selectedNames() {
            return checkboxes().filter((input) => input.checked).map((input) => input.value);
        }

        function refreshSummary() {
            const boxes = checkboxes();
            const chosen = boxes.filter((input) => input.checked);
            boxes.forEach((input) => {
                input.closest('.stock-count-category')?.classList.toggle('is-checked', input.checked);
            });
            const totalItems = chosen.reduce((sum, input) => sum + Number(input.dataset.total || 0), 0);
            if (!boxes.length) {
                summary.textContent = 'Nenhuma categoria com itens.';
            } else if (!chosen.length) {
                summary.textContent = 'Marque uma ou mais categorias.';
            } else if (chosen.length === boxes.length) {
                summary.textContent = `Todas as categorias · ${plural(totalItems, 'item', 'itens')}`;
            } else {
                summary.textContent = `${plural(chosen.length, 'categoria', 'categorias')} · ${plural(totalItems, 'item', 'itens')}`;
            }
            submitButton.disabled = generating || !chosen.length;
        }

        function renderCategories(previouslyChosen) {
            list.replaceChildren();
            categories.forEach((category) => {
                const label = document.createElement('label');
                label.className = 'stock-count-category';
                const color = String(category.color || '');
                if (/^#[0-9a-f]{3,8}$/i.test(color)) {
                    label.style.setProperty('--category-color', color);
                }

                const input = document.createElement('input');
                input.type = 'checkbox';
                input.className = 'form-check-input';
                input.value = category.nome;
                input.dataset.total = String(category.total || 0);
                input.checked = previouslyChosen.has(category.nome);
                input.addEventListener('change', refreshSummary);

                const icon = document.createElement('span');
                icon.className = 'stock-count-category-icon';
                icon.setAttribute('aria-hidden', 'true');
                icon.textContent = category.icon || '';

                const name = document.createElement('span');
                name.className = 'stock-count-category-name';
                name.textContent = category.nome;

                const total = document.createElement('span');
                total.className = 'stock-count-category-total';
                total.textContent = plural(Number(category.total || 0), 'item', 'itens');

                label.append(input, icon, name, total);
                list.append(label);
            });
            refreshSummary();
        }

        async function authFetch(url, options) {
            const requestOptions = { credentials: 'same-origin', ...options };
            return window.galintFetchWithAuth
                ? window.galintFetchWithAuth(url, requestOptions, 'Sua sessão expirou. Faça login novamente.')
                : window.fetch(url, requestOptions);
        }

        async function loadCategories() {
            const previouslyChosen = new Set(selectedNames());
            setFeedback('', null);
            summary.textContent = 'Carregando categorias...';
            submitButton.disabled = true;
            try {
                const response = await authFetch(categoriesUrl, { headers: { Accept: 'application/json' } });
                const payload = await response.json();
                if (!response.ok || !payload?.success) {
                    throw new Error(payload?.message || 'Não foi possível carregar as categorias.');
                }
                categories = Array.isArray(payload.categories) ? payload.categories : [];
                renderCategories(previouslyChosen);
            } catch (error) {
                summary.textContent = '';
                setFeedback(error?.message || 'Não foi possível carregar as categorias.', 'danger');
            }
        }

        function filenameFrom(response) {
            const header = response.headers.get('Content-Disposition') || '';
            const encoded = header.match(/filename\*=UTF-8''([^;]+)/i);
            if (encoded) {
                try {
                    return decodeURIComponent(encoded[1]);
                } catch {
                    // segue para o nome simples
                }
            }
            const plain = header.match(/filename="?([^";]+)"?/i);
            return plain ? plain[1] : 'conferencia_estoque.xlsx';
        }

        async function generate() {
            const chosen = selectedNames();
            if (!chosen.length || generating) {
                return;
            }
            const url = new URL(downloadUrl, window.location.origin);
            // Todas marcadas = planilha completa, sem filtro (pega também categoria nova criada agora).
            if (chosen.length < checkboxes().length) {
                chosen.forEach((name) => url.searchParams.append('categoria', name));
            }

            generating = true;
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Gerando planilha...';
            setFeedback('', null);
            try {
                const response = await authFetch(url.toString(), {});
                const contentType = response.headers.get('Content-Type') || '';
                if (!response.ok || contentType.includes('application/json') || contentType.includes('text/html')) {
                    let message = 'Não foi possível gerar a planilha.';
                    if (contentType.includes('application/json')) {
                        const payload = await response.json().catch(() => null);
                        message = payload?.message || message;
                    }
                    throw new Error(message);
                }
                const blob = await response.blob();
                const objectUrl = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = objectUrl;
                link.download = filenameFrom(response);
                document.body.append(link);
                link.click();
                link.remove();
                window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
                setFeedback('Planilha gerada. Confira a pasta de downloads.', 'success');
                window.setTimeout(() => modal.hide(), 1200);
            } catch (error) {
                setFeedback(error?.message || 'Não foi possível gerar a planilha.', 'danger');
            } finally {
                generating = false;
                submitButton.innerHTML = submitLabel;
                refreshSummary();
            }
        }

        selectAllButton.addEventListener('click', () => {
            checkboxes().forEach((input) => {
                input.checked = true;
            });
            refreshSummary();
        });
        clearButton.addEventListener('click', () => {
            checkboxes().forEach((input) => {
                input.checked = false;
            });
            refreshSummary();
        });
        submitButton.addEventListener('click', generate);
        modalElement.addEventListener('show.bs.modal', loadCategories);
        modalElement.addEventListener('hidden.bs.modal', () => setFeedback('', null));
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize, { once: true });
    } else {
        initialize();
    }
})();
