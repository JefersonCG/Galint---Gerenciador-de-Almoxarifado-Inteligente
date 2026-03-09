<div class="sidebar-wrapper">
    <div class="sidebar-brand px-3 py-4 text-uppercase text-light">
        <strong>GALINT</strong>
        <small class="text-white-50 d-block">Gestão de Almoxarifado</small>
    </div>
    <div class="sidebar-scroll">
        <%
            p = request.path
            lancamentos_active = (
                p.startswith(url_for('movements.index'))
                or p.startswith(url_for('movements.saida_page'))
                or p.startswith(url_for('movements.saida_fracionada_page'))
                or p.startswith(url_for('movements.entrada_page'))
                or p.startswith(url_for('ferramentas.retirar_page'))
            )
        %>
        <nav class="sidebar-menu">
            <a class="sidebar-link ${'active' if p == url_for('dashboard.index') else ''}" href="${url_for('dashboard.index')}">
                <i class="bi bi-speedometer2"></i>
                <span>Dashboard</span>
            </a>
            <button
                class="sidebar-link d-flex justify-content-between align-items-center border-0 bg-transparent text-start w-100 ${'active' if lancamentos_active else 'collapsed'}"
                type="button" data-bs-toggle="collapse" data-bs-target="#lancamentosMenu"
                aria-expanded="${'true' if lancamentos_active else 'false'}">
                <span>
                    <i class="bi bi-box-seam"></i>
                    <span>Lançamentos</span>
                </span>
                <i class="bi bi-chevron-down small"></i>
            </button>
            <div id="lancamentosMenu" class="collapse ${'show' if lancamentos_active else ''}">
                <a class="sidebar-link ps-4 ${'active' if p == url_for('movements.index') else ''}"
                    href="${url_for('movements.index')}">
                    <i class="bi bi-box-arrow-up-right"></i>
                    <span>Registro de Saídas</span>
                </a>
                <a class="sidebar-link ps-4 ${'active' if p.startswith(url_for('movements.entrada_page')) else ''}"
                    href="${url_for('movements.entrada_page')}">
                    <i class="bi bi-arrow-return-left"></i>
                    <span>Registro de Devolução</span>
                </a>
            </div>
            <a class="sidebar-link ${'active' if p.startswith(url_for('inventory.list_items')) else ''}"
                href="${url_for('inventory.list_items')}">
                <i class="bi bi-boxes"></i>
                <span>Estoque</span>
            </a>
            <%
                try:
                    reparo_url = url_for('reparo.listar_reparos')
                    has_reparo = True
                except:
                    has_reparo = False
            %>
            % if has_reparo:
            <a class="sidebar-link ${'active' if p.startswith(reparo_url) else ''}"
                href="${reparo_url}">
                <i class="bi bi-tools"></i>
                <span>Equipamentos em Reparo</span>
            </a>
            % endif
            <a class="sidebar-link ${'active' if p.startswith(url_for('nf.nf_index')) else ''}"
                href="${url_for('nf.nf_index')}">
                <i class="bi bi-receipt"></i>
                <span>Notas Fiscais</span>
            </a>
            % if current_user.is_authenticated and current_user.is_admin:
                <a class="sidebar-link ${'active' if p.startswith(url_for('users.list_users')) else ''}"
                    href="${url_for('users.list_users')}">
                    <i class="bi bi-people-fill"></i>
                    <span>Usuários</span>
                </a>
                <div class="sidebar-divider"></div>
                <a class="sidebar-link ${'active' if p == url_for('pages.config') else ''}"
                    href="${url_for('pages.config')}">Configurações</a>
            % endif
            <div class="sidebar-divider"></div>
            <a class="sidebar-link ${'active' if p == url_for('pages.sobre') else ''}"
                href="${url_for('pages.sobre')}">Sobre</a>
        </nav>
    </div>
    <div class="sidebar-footer px-3 py-3">
        <small class="text-muted">Usuário: ${current_user.nome if current_user.is_authenticated else 'Visitante'}</small>
    </div>
</div>
