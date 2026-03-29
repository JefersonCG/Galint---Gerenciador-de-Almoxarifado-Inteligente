<!doctype html>
<html lang="pt-BR">

<head>
    <meta charset="utf-8">
    <title><%block name="title">GALINT</%block></title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#08111f">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css">
    <link rel="stylesheet" href="${url_for('static', filename='css/qss_like.css')}">
    <link rel="stylesheet" href="${url_for('static', filename='css/galint-modern.css')}">
    <%block name="extra_css"></%block>
</head>

<body class="layout-shell galint-app<%block name='body_class'></%block>">
    <header class="topbar shadow-sm">
        <div class="galint-topbar-inner">
            <div class="galint-topbar-brand">
                <button class="galint-sidebar-toggle" id="sidebar-toggle" aria-label="Alternar menu">
                    <i class="bi bi-list"></i>
                </button>
                <div class="galint-topbar-copy">
                    <span class="galint-topbar-title">GALINT</span>
                    <small class="galint-topbar-subtitle">Centro operacional de almoxarifado, rastreabilidade e governança.</small>
                </div>
            </div>
            <div class="galint-topbar-actions">
                % if current_user.is_authenticated:
                    <span class="galint-topbar-user"><i class="bi bi-person-badge"></i> ${current_user.nome}</span>
                    <form method="post" action="${url_for('auth.logout')}">
                        <button class="galint-topbar-ghost-btn" type="submit">Sair</button>
                    </form>
                % else:
                    <a class="galint-topbar-action-btn" href="${url_for('auth.login_form')}">Entrar</a>
                % endif
            </div>
        </div>
    </header>
    <div class="app-body">
        <div class="galint-content-shell">
            <aside id="sidebar-column" class="sidebar-column">
                <%include file="sidebar_layout.mako"/>
            </aside>
            <main class="content-panel">
                <div class="galint-page-frame">
                    <div class="galint-page-header-slot">
                        <%block name="page_header"></%block>
                    </div>
                    <%
                        flashes = get_flashed_messages(with_categories=True)
                    %>
                    % if flashes:
                        % for category, message in flashes:
                            <div class="alert alert-${category} mb-3">${message}</div>
                        % endfor
                    % endif
                    <%block name="content"></%block>
                </div>
            </main>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        document.addEventListener('DOMContentLoaded', function () {
            const toggle = document.getElementById('sidebar-toggle');
            const sidebar = document.getElementById('sidebar-column');
            toggle?.addEventListener('click', () => {
                sidebar?.classList.toggle('collapsed');
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
    <%block name="scripts"></%block>
</body>

</html>
