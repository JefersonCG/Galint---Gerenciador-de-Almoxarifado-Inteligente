from pathlib import Path

content = """<!doctype html>
<html lang="pt-BR">

<head>
    <meta charset="utf-8">
    <title>{% block title %}GALINT{% endblock %}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/qss_like.css') }}">
</head>

<body class="layout-shell">
    <header class="topbar shadow-sm">
        <div class="d-flex align-items-center gap-2">
            <button class="btn btn-sm btn-outline-light rounded-circle" id="sidebar-toggle" aria-label="Alternar menu">
                <i class="bi bi-list"></i>
            </button>
            <div class="topbar-brand">
                <span class="brand-title">GALINT</span>
                <small class="text-muted">Sistema pensado para almoxarifado</small>
            </div>
        </div>
        <div class="topbar-actions d-flex align-items-center gap-3">
            {% if current_user.is_authenticated %}
            <span class="text-light">{{ current_user.nome }}</span>
            <form method="post" action="{{ url_for('auth.logout') }}">
                <button class="btn btn-sm btn-outline-light" type="submit">Sair</button>
            </form>
            {% else %}
            <a class="btn btn-sm btn-outline-light" href="{{ url_for('auth.login_form') }}">Entrar</a>
            {% endif %}
        </div>
    </header>
    <div class="app-body">
        <aside id="sidebar-column" class="sidebar-column">
            {% include 'sidebar_layout.html' %}
        </aside>
        <section class="content-panel">
            <div class="page-header">
                {% block page_header %}{% endblock %}
            </div>
            {% with flashes = get_flashed_messages(with_categories=True) %}
            {% if flashes %}
            {% for category, message in flashes %}
            <div class="alert alert-{{ category }} mb-3">{{ message }}</div>
            {% endfor %}
            {% endif %}
            {% endwith %}
            {% block content %}{% endblock %}
        </section>
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
</body>

</html>
"""
Path("c:/Users/LUIS/Desktop/Cond. Sublime Almoxarife/GALINT FLASK/galint_flask/templates/base.html").write_text(content, encoding="utf-8")
