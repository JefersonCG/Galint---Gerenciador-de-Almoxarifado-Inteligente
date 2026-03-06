# 📱 Sugestão: Menu "Painel Mobile"

## 🎯 Objetivo

Adicionar um novo menu chamado **"Painel Mobile"** no sidebar da aplicação Flask para acessar o painel de controle de dispositivos móveis, versões APK e feature flags.

---

## 📍 Onde Adicionar

### Arquivo: `galint_flask/templates/sidebar.html`

**Localização sugerida:** Entre o menu "Usuários" e o separador `<hr>`, na seção de menus administrativos.

---

## 💻 Código Sugerido

```html
<!-- ADICIONAR APÓS O MENU "Usuários" (linha ~34) -->

{% if current_user.is_authenticated and current_user.is_admin %}
<a class="nav-link text-light {% if p.startswith(url_for('mobile_panel.dashboard')) %}active{% endif %}"
    href="{{ url_for('mobile_panel.dashboard') }}">
    <i class="bi bi-phone-fill me-2"></i> Painel Mobile
</a>
{% endif %}

<hr class="sidebar-sep" />
```

---

## 🎨 Preview Visual

```
┌─────────────────────────────┐
│ GALINT                      │
│ Almoxarifado                │
├─────────────────────────────┤
│ 🏠 Estoque                  │
│ 📦 Lançamentos              │
│ 🧾 Lançamento NF            │
│ 📋 Cadastro de Itens        │
│ 👥 Usuários                 │
│ 📱 Painel Mobile       ← NOVO│
├─────────────────────────────┤
│ ⚙️ Configurações             │
│ ℹ️ Sobre                     │
└─────────────────────────────┘
```

---

## 🔧 Implementação Completa

### 1. Atualizar Sidebar

**Arquivo:** `galint_flask/templates/sidebar.html`

```html
<div class="d-flex flex-column vh-100 text-light" style="background:#2b2f33;">
    <div class="p-3 border-bottom" style="background:#23272b;">
        <h5 class="mb-0">GALINT</h5>
        <small class="text-muted">Almoxarifado</small>
    </div>
    <nav class="nav flex-column p-2 sidebar-nav" aria-label="Main menu">
        {% set p = request.path %}
        <a class="nav-link text-light {% if p.startswith(url_for('dashboard.index')) %}active{% endif %}"
            href="{{ url_for('dashboard.index') }}">
            <i class="bi bi-house-door-fill me-2"></i> Estoque
        </a>
        {% if current_user.is_authenticated and (current_user.is_admin or current_user.is_standard) %}
        <a class="nav-link text-light {% if p.startswith(url_for('movements.index')) %}active{% endif %}"
            href="{{ url_for('movements.index') }}">
            <i class="bi bi-box-seam me-2"></i> Lançamentos
        </a>
        {% endif %}
        {% if config.get('FEATURE_NOTAS_ENABLED', True) %}
        <a class="nav-link text-light {% if p.startswith(url_for('nf.nf_index')) %}active{% endif %}"
            href="{{ url_for('nf.nf_index') }}">
            <i class="bi bi-receipt me-2"></i> Lançamento NF
        </a>
        {% endif %}
        <a class="nav-link text-light {% if p.startswith(url_for('inventory.list_items')) %}active{% endif %}"
            href="{{ url_for('inventory.list_items') }}">
            <i class="bi bi-card-list me-2"></i> Cadastro de Itens
        </a>
        {% if current_user.is_authenticated and current_user.is_admin %}
        <a class="nav-link text-light {% if p.startswith(url_for('users.list_users')) %}active{% endif %}"
            href="{{ url_for('users.list_users') }}">
            <i class="bi bi-people-fill me-2"></i> Usuários
        </a>
        <!-- ↓↓↓ NOVO MENU PAINEL MOBILE ↓↓↓ -->
        <a class="nav-link text-light {% if p.startswith(url_for('mobile_panel.dashboard')) %}active{% endif %}"
            href="{{ url_for('mobile_panel.dashboard') }}">
            <i class="bi bi-phone-fill me-2"></i> Painel Mobile
        </a>
        <!-- ↑↑↑ FIM DO NOVO MENU ↑↑↑ -->
        {% endif %}
        <hr class="sidebar-sep" />
        <a class="nav-link text-light {% if p == url_for('pages.config') %}active{% endif %}"
            href="{{ url_for('pages.config') }}">
            <i class="bi bi-gear-fill me-2"></i> Configurações
        </a>
        <a class="nav-link text-light {% if p == url_for('pages.sobre') %}active{% endif %}"
            href="{{ url_for('pages.sobre') }}">
            <i class="bi bi-info-circle me-2"></i> Sobre
        </a>
    </nav>
    <div class="mt-auto p-3 sidebar-footer">
        <small class="text-muted">Usuário: {% if current_user.is_authenticated %}{{ current_user.nome }}{% else
            %}Visitante{% endif %}</small>
    </div>
</div>
```

---

### 2. Criar Blueprint Flask

**Arquivo:** `galint_flask/views/mobile_panel.py` (a criar)

```python
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from functools import wraps

bp = Blueprint('mobile_panel', __name__, url_prefix='/mobile-panel')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({'error': 'Acesso negado. Apenas administradores.'}), 403
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/')
@login_required
@admin_required
def dashboard():
    """Dashboard principal do Painel Mobile"""
    return render_template('mobile_panel/dashboard.html')

@bp.route('/devices')
@login_required
@admin_required
def devices():
    """Lista de dispositivos"""
    return render_template('mobile_panel/devices.html')

@bp.route('/versions')
@login_required
@admin_required
def versions():
    """Controle de versões APK"""
    return render_template('mobile_panel/versions.html')

@bp.route('/features')
@login_required
@admin_required
def features():
    """Gerenciamento de feature flags"""
    return render_template('mobile_panel/features.html')

@bp.route('/audit')
@login_required
@admin_required
def audit():
    """Logs de auditoria"""
    return render_template('mobile_panel/audit.html')
```

---

### 3. Registrar Blueprint

**Arquivo:** `galint_flask/__init__.py`

```python
# ... imports existentes ...

def create_app():
    app = Flask(__name__)
    # ... configurações existentes ...
    
    # Registrar blueprints existentes
    from galint_flask.views import dashboard, movements, inventory, users, pages, nf
    # ... outros blueprints ...
    
    # ↓↓↓ ADICIONAR NOVO BLUEPRINT ↓↓↓
    from galint_flask.views import mobile_panel
    app.register_blueprint(mobile_panel.bp)
    # ↑↑↑ FIM DO NOVO BLUEPRINT ↑↑↑
    
    return app
```

---

### 4. Criar Template Inicial

**Arquivo:** `galint_flask/templates/mobile_panel/dashboard.html` (a criar)

```html
{% extends "base.html" %}

{% block title %}Painel Mobile - GALINT{% endblock %}

{% block content %}
<div class="container-fluid py-4">
    <h2 class="mb-4">
        <i class="bi bi-phone-fill me-2"></i>
        Painel de Controle Mobile
    </h2>

    <!-- Cards de Status -->
    <div class="row g-4 mb-4">
        <div class="col-md-3">
            <div class="card bg-success text-white">
                <div class="card-body">
                    <h5 class="card-title">Dispositivos Online</h5>
                    <h2 class="mb-0">42</h2>
                    <small>Últimos 5 minutos</small>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card bg-warning text-dark">
                <div class="card-body">
                    <h5 class="card-title">Dispositivos Offline</h5>
                    <h2 class="mb-0">3</h2>
                    <small>Sem heartbeat > 5min</small>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card bg-danger text-white">
                <div class="card-body">
                    <h5 class="card-title">Bloqueados</h5>
                    <h2 class="mb-0">1</h2>
                    <small>Administrativamente</small>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card bg-info text-white">
                <div class="card-body">
                    <h5 class="card-title">Versão Atual</h5>
                    <h2 class="mb-0">1.2.0</h2>
                    <small>35 dispositivos</small>
                </div>
            </div>
        </div>
    </div>

    <!-- Botões de Ação -->
    <div class="d-flex gap-2 mb-4">
        <a href="{{ url_for('mobile_panel.devices') }}" class="btn btn-primary">
            <i class="bi bi-list-ul me-2"></i>
            Ver Todos os Dispositivos
        </a>
        <a href="{{ url_for('mobile_panel.versions') }}" class="btn btn-secondary">
            <i class="bi bi-tag me-2"></i>
            Gerenciar Versões
        </a>
        <a href="{{ url_for('mobile_panel.features') }}" class="btn btn-secondary">
            <i class="bi bi-toggle-on me-2"></i>
            Feature Flags
        </a>
        <a href="{{ url_for('mobile_panel.audit') }}" class="btn btn-secondary">
            <i class="bi bi-journal-text me-2"></i>
            Logs de Auditoria
        </a>
    </div>

    <!-- Placeholder para implementação futura -->
    <div class="alert alert-info">
        <i class="bi bi-info-circle me-2"></i>
        <strong>Em Desenvolvimento:</strong> Este painel está em fase de implementação.
        Os dados apresentados são simulados para fins de visualização.
    </div>
</div>
{% endblock %}
```

---

## 🎯 Checklist de Implementação

- [ ] Atualizar `sidebar.html` com novo menu
- [ ] Criar blueprint `mobile_panel.py`
- [ ] Registrar blueprint em `__init__.py`
- [ ] Criar pasta `templates/mobile_panel/`
- [ ] Criar template `dashboard.html`
- [ ] Testar acesso (apenas admins devem ver)
- [ ] Implementar endpoints da API (PARTE 2)
- [ ] Criar modelos SQLAlchemy (conforme PAINEL_WEB_MOBILE.md)
- [ ] Implementar telas de devices, versions, features, audit

---

## 🔐 Segurança

✅ **Acesso Restrito:**
- Menu visível apenas para `current_user.is_admin`
- Todas as rotas protegidas com `@admin_required`
- Sessão Flask validada por `@login_required`

✅ **Isolamento:**
- Blueprint separado (`/mobile-panel/*`)
- Templates isolados na pasta `mobile_panel/`
- Não afeta funcionalidades existentes

---

## 📊 Estrutura de Pastas Resultante

```
galint_flask/
├── views/
│   ├── mobile_panel.py          ← NOVO blueprint
│   ├── dashboard.py             (existente)
│   ├── movements.py             (existente)
│   └── ...
├── templates/
│   ├── mobile_panel/            ← NOVA pasta
│   │   ├── dashboard.html       (dashboard principal)
│   │   ├── devices.html         (lista dispositivos)
│   │   ├── versions.html        (controle versões)
│   │   ├── features.html        (feature flags)
│   │   └── audit.html           (logs)
│   ├── sidebar.html             (atualizado)
│   └── ...
```

---

## ⚡ Próximos Passos (Após Aprovação)

1. **Fase 1 - Menu Básico** (1-2 horas)
   - Adicionar menu no sidebar
   - Criar blueprint vazio
   - Criar template placeholder

2. **Fase 2 - Models SQLAlchemy** (3-4 horas)
   - Implementar 6 tabelas conforme PAINEL_WEB_MOBILE.md
   - Criar migration Alembic
   - Testar models

3. **Fase 3 - API Endpoints** (4-6 horas)
   - Implementar endpoints mobile (/login, /heartbeat)
   - Implementar endpoints admin (/devices, /versions)
   - Criar decorators de segurança

4. **Fase 4 - UI Completa** (6-8 horas)
   - Dashboard com cards reais
   - Lista de dispositivos (DataTables)
   - Modals de bloqueio/logout
   - Timeline de audit

---

## ✅ Aguardando Aval para Implementação

**Você autoriza a implementação deste menu?**

- [ ] Sim, pode adicionar o menu "Painel Mobile"
- [ ] Sim, e já implementar o blueprint básico
- [ ] Sim, e já criar os models SQLAlchemy
- [ ] Não, fazer ajustes primeiro

