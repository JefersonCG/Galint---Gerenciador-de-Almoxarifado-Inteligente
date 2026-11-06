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
    <script src="${url_for('static', filename='js/galint-core.js')}?v=20260924"></script>
    <%block name="extra_css"></%block>
</head>

<body class="layout-shell<%block name='body_class'></%block>">
    <header class="topbar shadow-sm">
        % if current_user.is_authenticated:
        <form class="topbar-item-search" id="topbar-item-search" role="search"
            data-suggestions-url="${url_for('reports.general_search_suggestions_api')}"
            data-report-url-template="${url_for('reports.item_consumption_api', codigo_item='__CODIGO__')}">
            <label class="visually-hidden" for="topbar-item-query">Pesquisar material ou ferramenta</label>
            <i class="bi bi-search" aria-hidden="true"></i>
            <input id="topbar-item-query" class="form-control" type="search" placeholder="Pesquisar material ou ferramenta" autocomplete="off" aria-controls="topbar-item-suggestions" aria-expanded="false">
            <div class="topbar-item-suggestions d-none" id="topbar-item-suggestions" role="listbox"></div>
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
    % if current_user.is_authenticated:
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
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    % if current_user.is_authenticated:
    <script src="${url_for('static', filename='js/consumption-search.js')}?v=20261106"></script>
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
