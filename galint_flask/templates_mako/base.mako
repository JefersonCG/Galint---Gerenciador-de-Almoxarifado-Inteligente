<!doctype html>
<html lang="pt-BR">

<head>
    <meta charset="utf-8">
    <title><%block name="title">${system_name}</%block></title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css">
    <link rel="stylesheet" href="${url_for('static', filename='css/galint-tokens.css')}?v=20260924">
    <link rel="stylesheet" href="${url_for('static', filename='css/qss_like.css')}?v=20261106">
    <link rel="stylesheet" href="${url_for('static', filename='css/consumption-search.css')}?v=20261106">
    <link rel="stylesheet" href="${url_for('static', filename='css/stock-count-modal.css')}?v=20261119-categorias">
    <script src="${url_for('static', filename='js/galint-core.js')}?v=20260924"></script>
    <%block name="extra_css"></%block>
</head>

<body class="layout-shell<%block name='body_class'></%block>">
    <header class="topbar shadow-sm">
        % if current_user.is_authenticated and ((endpoint_exists('reports.general_search_suggestions_api') and endpoint_exists('reports.item_consumption_api') and endpoint_exists('reports.item_consumption_pdf')) or endpoint_exists('inventory.stock_count_item_lookup')):
        <form class="topbar-item-search" id="topbar-item-search" role="search"
            data-item-search-available="${'true' if endpoint_exists('reports.general_search_suggestions_api') and endpoint_exists('reports.item_consumption_api') and endpoint_exists('reports.item_consumption_pdf') else 'false'}"
            % if endpoint_exists('reports.general_search_suggestions_api') and endpoint_exists('reports.item_consumption_api') and endpoint_exists('reports.item_consumption_pdf'):
            data-suggestions-url="${url_for('reports.general_search_suggestions_api')}"
            % endif
            % if endpoint_exists('reports.general_search_suggestions_api') and endpoint_exists('reports.item_consumption_api') and endpoint_exists('reports.item_consumption_pdf'):
            data-report-url-template="${url_for('reports.item_consumption_api', codigo_item='__CODIGO__')}"
            % endif
            % if endpoint_exists('inventory.stock_count_item_lookup'):
            data-stock-count-lookup-url="${url_for('inventory.stock_count_item_lookup')}"
            data-stock-count-adjust-url-template="${url_for('inventory.stock_count_item_adjust', codigo='__CODIGO__')}"
            % endif
            >
            <label class="visually-hidden" for="topbar-item-query">Pesquisar material, ferramenta, código de barras, NF ou chave de acesso</label>
            <i class="bi bi-search" aria-hidden="true"></i>
            <input id="topbar-item-query" class="form-control" type="search" placeholder="Material, código de barras, nº NF ou chave de acesso" autocomplete="off" aria-controls="topbar-item-suggestions" aria-expanded="false">
            <div class="topbar-item-suggestions d-none" id="topbar-item-suggestions" role="listbox"></div>
        </form>
        % elif current_user.is_authenticated and (endpoint_exists('nf.buscar_documento_modal') or endpoint_exists('inventory.stock_count_item_lookup')):
        <form class="topbar-item-search" id="topbar-item-search" role="search" data-item-search-available="false"
            % if endpoint_exists('inventory.stock_count_item_lookup'):
            data-stock-count-lookup-url="${url_for('inventory.stock_count_item_lookup')}"
            data-stock-count-adjust-url-template="${url_for('inventory.stock_count_item_adjust', codigo='__CODIGO__')}"
            % endif
            >
            <label class="visually-hidden" for="topbar-item-query">Pesquisar código de barras, nota fiscal ou chave de acesso</label>
            <i class="bi bi-search" aria-hidden="true"></i>
            <input id="topbar-item-query" class="form-control" type="search" placeholder="Código de barras, nº NF ou chave de acesso" autocomplete="off" aria-controls="topbar-item-suggestions" aria-expanded="false">
            <div class="topbar-item-suggestions d-none" id="topbar-item-suggestions" role="listbox"></div>
        </form>
        % endif
        % if current_user.is_authenticated and endpoint_exists('inventory.stock_count_workbook') and endpoint_exists('inventory.stock_count_categories'):
        <a class="btn btn-sm btn-outline-light text-nowrap" href="${url_for('inventory.stock_count_workbook')}" role="button" data-bs-toggle="modal" data-bs-target="#stockCountWorkbookModal" title="Escolher as categorias e gerar a planilha A4 de conferência física">
            <i class="bi bi-clipboard2-check me-1" aria-hidden="true"></i> Conferência física
        </a>
        % endif
        % if current_user.is_authenticated and endpoint_exists('nf.buscar_documento_modal'):
        <form class="topbar-nf-search d-none" data-search-url="${url_for('nf.buscar_documento_modal')}" role="search" aria-label="Buscar nota fiscal">
            <input id="topbar-nf-query" type="hidden" name="nota">
            <button type="submit" tabindex="-1" aria-hidden="true"></button>
        </form>
        % endif
        <div class="topbar-actions d-flex align-items-center gap-3">
            % if current_user.is_authenticated:
                <span class="text-light">${current_user.nome}</span>
                <form method="post" action="${url_for('auth.logout')}">
                    <button class="btn btn-sm btn-outline-light" type="submit">Sair</button>
                </form>
            % else:
                <a class="btn btn-sm btn-outline-light" href="${url_for('auth.login_form')}">Entrar</a>
            % endif
        </div>
    </header>
    <div class="app-body">
        <aside id="sidebar-column" class="sidebar-column">
            <%include file="sidebar_layout.mako"/>
        </aside>
        <section class="content-panel">
            <div class="page-header"><%block name="page_header"></%block></div>
            <%
                flashes = get_flashed_messages(with_categories=True)
            %>
            % if flashes:
                % for category, message in flashes:
                    <div class="alert alert-${category} mb-3">${message}</div>
                % endfor
            % endif
            <%block name="content"></%block>
        </section>
    </div>
    % if current_user.is_authenticated and endpoint_exists('reports.item_consumption_api') and endpoint_exists('reports.item_consumption_pdf'):
    <div class="modal fade" id="itemConsumptionModal" tabindex="-1" aria-labelledby="itemConsumptionModalTitle" aria-hidden="true">
        <div class="modal-dialog modal-xl modal-dialog-scrollable">
            <div class="modal-content consumption-modal-content">
                <div class="modal-header">
                    <div>
                        <span class="consumption-modal-kicker"><i class="bi bi-graph-up-arrow"></i> Análise de consumo</span>
                        <h2 class="modal-title fs-5" id="itemConsumptionModalTitle">Material ou ferramenta</h2>
                        <div class="small text-muted" id="itemConsumptionSubtitle"></div>
                    </div>
                    <label class="visually-hidden" for="itemConsumptionPeriod">Período de comparação</label>
                    <select class="form-select form-select-sm consumption-period-select" id="itemConsumptionPeriod" aria-label="Período de comparação">
                        <option value="7d">7 dias</option>
                        <option value="30d">30 dias</option>
                        <option value="month">Mês atual</option>
                        <option value="3m">3 meses</option>
                        <option value="6m">6 meses</option>
                        <option value="12m">12 meses</option>
                    </select>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Fechar"></button>
                </div>
                <div class="modal-body" id="itemConsumptionContent" aria-live="polite">
                    <div class="consumption-loading"><span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Calculando consumo...</div>
                </div>
            </div>
        </div>
    </div>
    % endif
    % if current_user.is_authenticated and endpoint_exists('nf.buscar_documento_modal'):
    <div class="modal fade" id="nfSearchModal" tabindex="-1" aria-labelledby="nfSearchModalTitle" aria-hidden="true">
        <div class="modal-dialog modal-lg modal-dialog-scrollable">
            <div class="modal-content nf-search-modal-content">
                <div class="modal-header">
                    <div>
                        <h2 class="modal-title fs-5" id="nfSearchModalTitle">Nota fiscal</h2>
                        <div class="small text-muted" id="nfSearchModalSubtitle"></div>
                    </div>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Fechar"></button>
                </div>
                <div class="modal-body">
                    <div id="nfSearchModalFeedback" class="small" role="status" aria-live="polite"></div>
                    <div id="nfSearchModalContent" class="d-none"></div>
                </div>
            </div>
        </div>
    </div>
    % endif
    % if current_user.is_authenticated and endpoint_exists('inventory.stock_count_item_lookup') and endpoint_exists('inventory.stock_count_item_adjust'):
    <div class="modal fade" id="stockCountModal" tabindex="-1" aria-labelledby="stockCountModalTitle" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content stock-count-modal-content">
                <div class="modal-header">
                    <div>
                        <h2 class="modal-title fs-5" id="stockCountModalTitle">Contagem física</h2>
                        <div class="small text-muted" id="stockCountItemCode"></div>
                    </div>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Fechar"></button>
                </div>
                <div class="modal-body">
                    <div id="stockCountFeedback" class="small" role="status" aria-live="polite"></div>
                    <section id="stockCountItemDetails" class="d-none">
                        <div class="stock-count-item">
                            <div class="stock-count-photo is-empty" id="stockCountPhotoBox">
                                <a class="stock-count-photo-link d-none" id="stockCountPhotoLink" href="#" target="_blank" rel="noopener" title="Abrir a foto em tamanho maior">
                                    <img id="stockCountPhoto" alt="">
                                </a>
                                <i class="bi bi-image" id="stockCountPhotoEmptyIcon" aria-hidden="true"></i>
                                <span id="stockCountPhotoEmptyText">Sem foto</span>
                            </div>
                            <div class="stock-count-item-info">
                                <h3 class="stock-count-item-name" id="stockCountItemDescription"></h3>
                                <div class="stock-count-balance">
                                    <span class="stock-count-balance-label">No sistema</span>
                                    <strong id="stockCountSystemBalance"></strong>
                                </div>
                            </div>
                        </div>
                        <div id="stockCountPendingWarning" class="alert alert-warning py-2 d-none">Este item ainda está pendente de cadastro e não pode ter o estoque ajustado.</div>
                        <form id="stockCountForm">
                            <div id="stockCountDirectGroup">
                                <label class="form-label" for="stockCountDirectValue">Quantidade física (<span data-stock-unit></span>)</label>
                                <input class="form-control form-control-lg" id="stockCountDirectValue" type="number" min="0" step="any" required inputmode="decimal">
                            </div>
                            <div id="stockCountPackageGroup" class="d-none">
                                <p class="small text-secondary mb-2" id="stockCountPackageHint"></p>
                                <label class="form-label" for="stockCountPackageValue">Embalagens fechadas</label>
                                <input class="form-control mb-3" id="stockCountPackageValue" type="number" min="0" step="1" inputmode="numeric">
                                <label class="form-label" for="stockCountInternalValue">Quantidade solta (<span data-stock-unit></span>)</label>
                                <input class="form-control" id="stockCountInternalValue" type="number" min="0" step="any" inputmode="decimal">
                            </div>
                            <div class="d-flex justify-content-end gap-2 mt-4">
                                <button class="btn btn-outline-light" type="button" data-bs-dismiss="modal">Cancelar</button>
                                <button class="btn btn-primary" type="submit" id="stockCountSubmit">Aplicar contagem</button>
                            </div>
                        </form>
                    </section>
                </div>
            </div>
        </div>
    </div>
    % endif
    % if current_user.is_authenticated and endpoint_exists('inventory.stock_count_workbook') and endpoint_exists('inventory.stock_count_categories'):
    <div class="modal fade" id="stockCountWorkbookModal" tabindex="-1" aria-labelledby="stockCountWorkbookModalTitle" aria-hidden="true"
        data-categories-url="${url_for('inventory.stock_count_categories')}"
        data-download-url="${url_for('inventory.stock_count_workbook')}">
        <div class="modal-dialog modal-dialog-centered modal-dialog-scrollable">
            <div class="modal-content stock-count-modal-content">
                <div class="modal-header">
                    <div>
                        <h2 class="modal-title fs-5" id="stockCountWorkbookModalTitle">Conferência física</h2>
                        <div class="small text-muted">Escolha as categorias que vão para a planilha A4.</div>
                    </div>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Fechar"></button>
                </div>
                <div class="modal-body">
                    <div id="stockCountWorkbookFeedback" class="small" role="status" aria-live="polite"></div>
                    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
                        <span class="small text-muted" id="stockCountWorkbookSummary">Carregando categorias...</span>
                        <div class="d-flex gap-2">
                            <button type="button" class="btn btn-sm btn-outline-light" id="stockCountWorkbookSelectAll">Marcar todas</button>
                            <button type="button" class="btn btn-sm btn-outline-light" id="stockCountWorkbookClear">Limpar</button>
                        </div>
                    </div>
                    <div class="stock-count-category-list" id="stockCountWorkbookCategories" role="group" aria-label="Categorias"></div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-outline-light" type="button" data-bs-dismiss="modal">Cancelar</button>
                    <button class="btn btn-primary" type="button" id="stockCountWorkbookSubmit" disabled>
                        <i class="bi bi-file-earmark-spreadsheet me-1" aria-hidden="true"></i> Gerar planilha
                    </button>
                </div>
            </div>
        </div>
    </div>
    % endif
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    % if current_user.is_authenticated and (endpoint_exists('reports.general_search_suggestions_api') or endpoint_exists('inventory.stock_count_item_lookup')):
    <script src="${url_for('static', filename='js/consumption-search.js')}?v=20261119-stock-count"></script>
    % endif
    % if current_user.is_authenticated and endpoint_exists('nf.buscar_documento_modal'):
    <script src="${url_for('static', filename='js/nf-search-modal.js')}?v=20261105"></script>
    % endif
    % if current_user.is_authenticated and endpoint_exists('inventory.stock_count_item_lookup'):
    <script src="${url_for('static', filename='js/stock-count-modal.js')}?v=20261119-foto"></script>
    % endif
    % if current_user.is_authenticated and endpoint_exists('inventory.stock_count_workbook') and endpoint_exists('inventory.stock_count_categories'):
    <script src="${url_for('static', filename='js/stock-count-workbook.js')}?v=20261119"></script>
    % endif
    <script>
        document.addEventListener('DOMContentLoaded', function () {
            const toggle = document.getElementById('sidebar-toggle');
            const sidebar = document.getElementById('sidebar-column');
            toggle?.addEventListener('click', () => {
                if (!sidebar) {
                    return;
                }
                const isCollapsed = sidebar.classList.toggle('collapsed');
                toggle.setAttribute('aria-expanded', String(!isCollapsed));
                toggle.setAttribute('aria-label', isCollapsed ? 'Abrir menu' : 'Recolher menu');
            });

            document.querySelectorAll('[data-sidebar-target]').forEach((toggleBtn) => {
                const target = document.querySelector(toggleBtn.getAttribute('data-sidebar-target') || '');
                toggleBtn.addEventListener('click', () => {
                    target?.classList.toggle('open');
                    const icon = toggleBtn.querySelector('i');
                    if (icon) {
                        icon.classList.toggle('rotate-90');
                    }
                });
            });
        });
    </script>
    <script>
        window.galintNativeFetch = window.galintNativeFetch || window.fetch.bind(window);

        window.galintShouldInspectFetch = function (input) {
            const rawUrl = typeof input === 'string'
                ? input
                : (input && typeof input.url === 'string' ? input.url : '');

            if (!rawUrl) {
                return true;
            }

            try {
                const resolved = new URL(rawUrl, window.location.origin);
                return resolved.origin === window.location.origin;
            } catch (error) {
                return !/^https?:\/\//i.test(rawUrl);
            }
        };

        window.galintRedirectToLogin = function (loginUrl, message) {
            if (window.__galintAuthRedirecting) {
                return;
            }
            window.__galintAuthRedirecting = true;
            if (message) {
                try {
                    window.alert(message);
                } catch (error) {
                }
            }
            const fallbackLoginUrl = '${url_for("auth.login_form")}' + '?next=' + encodeURIComponent(window.location.pathname + window.location.search);
            window.location.href = loginUrl || fallbackLoginUrl;
        };

        window.galintEnsureAuthenticatedResponse = async function (response, fallbackMessage) {
            const defaultMessage = fallbackMessage || 'Sua sessão expirou. Faça login novamente.';
            const defaultLoginUrl = '${url_for("auth.login_form")}' + '?next=' + encodeURIComponent(window.location.pathname + window.location.search);

            if (response.redirected && response.url && response.url.includes('/auth/login')) {
                window.galintRedirectToLogin(response.url, defaultMessage);
                const redirectError = new Error(defaultMessage);
                redirectError.isAuthRedirect = true;
                throw redirectError;
            }

            if (response.status === 401 || response.status === 403) {
                let loginUrl = defaultLoginUrl;
                let message = defaultMessage;
                const contentType = String(response.headers.get('content-type') || '').toLowerCase();
                if (contentType.includes('application/json')) {
                    try {
                        const payload = await response.clone().json();
                        if (payload && typeof payload.login_url === 'string' && payload.login_url.trim()) {
                            loginUrl = payload.login_url;
                        }
                        if (payload && typeof payload.message === 'string' && payload.message.trim()) {
                            message = payload.message;
                        }
                    } catch (error) {
                    }
                }
                window.galintRedirectToLogin(loginUrl, message);
                const authError = new Error(message);
                authError.isAuthRedirect = true;
                throw authError;
            }

            return response;
        };

        window.galintFetchWithAuth = async function (url, options, fallbackMessage) {
            const requestOptions = Object.assign({ credentials: 'same-origin' }, options || {});
            const response = await window.galintNativeFetch(url, requestOptions);
            return window.galintEnsureAuthenticatedResponse(response, fallbackMessage);
        };

        if (!window.__galintFetchWrapped) {
            window.__galintFetchWrapped = true;
            window.fetch = function (input, init) {
                const requestOptions = Object.assign({ credentials: 'same-origin' }, init || {});
                return window.galintNativeFetch(input, requestOptions).then(function (response) {
                    if (!window.galintShouldInspectFetch(input)) {
                        return response;
                    }
                    return window.galintEnsureAuthenticatedResponse(response);
                });
            };
        }
    </script>
    % if current_user.is_authenticated:
    <script>
        window.galintSessionConfig = {
            keepaliveUrl: '${url_for("auth.session_activity")}',
            loginUrl: '${url_for("auth.login_form")}?next=' + encodeURIComponent(window.location.pathname + window.location.search),
            throttleMs: 5 * 60 * 1000,
        };
    </script>
    <script src="${url_for('static', filename='js/session-activity.js')}"></script>
    % endif
    <%block name="scripts"></%block>
</body>

</html>
