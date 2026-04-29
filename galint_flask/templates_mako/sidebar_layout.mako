<div class="sidebar-wrapper">
    <div class="sidebar-brand px-3 py-4 text-uppercase text-light">
        <strong>GALINT</strong>
        <small class="text-white-50 d-block">Gestão de Almoxarifado</small>
    </div>
    <div class="sidebar-scroll">
        <%
            p = request.path

            def optional_url(endpoint):
                try:
                    return url_for(endpoint)
                except Exception:
                    return None

            saidas_hub_url = optional_url('movements.saidas_hub') or url_for('movements.index')
            saida_fracionada_url = optional_url('movements.saida_fracionada_page')
            central_kits_url = optional_url('central_kits.index')
            tool_custody_url = optional_url('tool_custody.index')
            reparo_url = optional_url('reparo.listar_reparos')
            valor_estoque_url = optional_url('inventory.valor_estoque')
            consumo_painel_url = optional_url('inventory.consumption_dashboard')
            analytics_url = optional_url('analytics.index')
            fornecedores_url = optional_url('config.fornecedores')
            admin_stock_adjust_url = optional_url('config.estoque_ajuste_admin')
            central_operacoes_url = optional_url('operations.central_operations')
            lojas_lab_url = optional_url('inventory.lojas_lab')
            projection_url = optional_url('inventory.purchase_projection_page')
            nf_url = url_for('nf.nf_index') if config.get('FEATURE_NOTAS_ENABLED', True) else None
            users_list_url = optional_url('users.list_users')
            mobile_panel_url = '/mobile-panel' if getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'is_admin', False) and config.get('FEATURE_MOBILE_PANEL_ENABLED', False) else None
            config_root_url = optional_url('pages.config')
            empresa_url = optional_url('config.empresa')
            relatorios_config_url = optional_url('config.relatorios')
            updates_url = optional_url('updates.index')
            rede_url = optional_url('pages.config_rede')
            telegram_url = optional_url('telegram_config.index')
            notificacoes_url = optional_url('config.notificacoes')
            backup_url = optional_url('pages.config_backup')
            restore_backup_url = optional_url('pages.restore_backup')
            conversionengine_url = optional_url('pages.config_conversionengine')

            lancamentos_active = (
                p.startswith(saidas_hub_url)
                or p.startswith(url_for('movements.index'))
                or p.startswith(url_for('movements.saida_page'))
                or (saida_fracionada_url and p.startswith(saida_fracionada_url))
                or p.startswith(url_for('movements.entrada_page'))
            )
            estoque_active = (
                (p.startswith('/itens') and not (projection_url and p.startswith(projection_url)))
                or p.startswith('/estoque')
                or (central_operacoes_url and p.startswith(central_operacoes_url))
                or (consumo_painel_url and p.startswith(consumo_painel_url))
            )
            suprimentos_active = (
                (valor_estoque_url and p.startswith(valor_estoque_url))
                or (fornecedores_url and p.startswith(fornecedores_url))
                or (admin_stock_adjust_url and p.startswith(admin_stock_adjust_url))
                or (lojas_lab_url and p.startswith(lojas_lab_url))
                or (nf_url and p.startswith(nf_url))
                or (projection_url and p.startswith(projection_url))
            )
            ferramentas_active = (central_kits_url and p.startswith(central_kits_url)) or (tool_custody_url and p.startswith(tool_custody_url)) or (reparo_url and p.startswith(reparo_url))
            configuracoes_active = (
                (config_root_url and p.startswith(config_root_url))
                or
                (empresa_url and p.startswith(empresa_url))
                or (relatorios_config_url and p.startswith(relatorios_config_url))
                or (updates_url and p.startswith(updates_url))
                or (rede_url and p.startswith(rede_url))
                or (telegram_url and p.startswith(telegram_url))
                or (notificacoes_url and p.startswith(notificacoes_url))
                or (backup_url and p.startswith(backup_url))
                or (restore_backup_url and p.startswith(restore_backup_url))
                or (conversionengine_url and p.startswith(conversionengine_url))
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
                <a class="sidebar-link ps-4 ${'active' if p.startswith(saidas_hub_url) or p == url_for('movements.index') else ''}"
                    href="${saidas_hub_url}">
                    <i class="bi bi-box-arrow-up-right"></i>
                    <span>Registro de Saídas</span>
                </a>
            </div>
            <button
                class="sidebar-link d-flex justify-content-between align-items-center border-0 bg-transparent text-start w-100 ${'active' if estoque_active else 'collapsed'}"
                type="button" data-bs-toggle="collapse" data-bs-target="#estoqueMenu"
                aria-expanded="${'true' if estoque_active else 'false'}">
                <span>
                    <i class="bi bi-boxes"></i>
                    <span>Estoque</span>
                </span>
                <i class="bi bi-chevron-down small"></i>
            </button>
            <div id="estoqueMenu" class="collapse ${'show' if estoque_active else ''}">
                <a class="sidebar-link ps-4 ${'active' if p.startswith(url_for('inventory.list_items')) else ''}"
                    href="${url_for('inventory.list_items')}">
                    <i class="bi bi-card-list"></i>
                    <span>Itens Cadastrados</span>
                </a>
                % if consumo_painel_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(consumo_painel_url) else ''}"
                    href="${consumo_painel_url}">
                    <i class="bi bi-geo-alt"></i>
                    <span>Painel de Consumo</span>
                </a>
                % endif
                % if central_operacoes_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(central_operacoes_url) else ''}"
                    href="${central_operacoes_url}">
                    <i class="bi bi-activity"></i>
                    <span>Central de Operações</span>
                </a>
                % endif
            </div>

            <button
                class="sidebar-link d-flex justify-content-between align-items-center border-0 bg-transparent text-start w-100 ${'active' if suprimentos_active else 'collapsed'}"
                type="button" data-bs-toggle="collapse" data-bs-target="#suprimentosMenu"
                aria-expanded="${'true' if suprimentos_active else 'false'}">
                <span>
                    <i class="bi bi-briefcase-fill"></i>
                    <span>Gestão de Suprimentos</span>
                </span>
                <i class="bi bi-chevron-down small"></i>
            </button>
            <div id="suprimentosMenu" class="collapse ${'show' if suprimentos_active else ''}">
                % if valor_estoque_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(valor_estoque_url) else ''}"
                    href="${valor_estoque_url}">
                    <i class="bi bi-cash-stack"></i>
                    <span>Financeiro</span>
                </a>
                % endif
                % if fornecedores_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(fornecedores_url) else ''}"
                    href="${fornecedores_url}">
                    <i class="bi bi-building-add"></i>
                    <span>Cadastrar fornecedor</span>
                </a>
                % endif
                % if getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'is_admin', False) and admin_stock_adjust_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(admin_stock_adjust_url) else ''}"
                    href="${admin_stock_adjust_url}">
                    <i class="bi bi-shield-lock"></i>
                    <span>Ajuste Administrativo</span>
                </a>
                % endif
                % if lojas_lab_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(lojas_lab_url) else ''}"
                    href="${lojas_lab_url}">
                    <i class="bi bi-shop"></i>
                    <span>Laboratório de Lojas</span>
                </a>
                % endif
                % if nf_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(nf_url) else ''}"
                    href="${nf_url}">
                    <i class="bi bi-receipt"></i>
                    <span>Documentos Fiscais</span>
                </a>
                % endif
                % if projection_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(projection_url) else ''}"
                    href="${projection_url}">
                    <i class="bi bi-graph-up-arrow"></i>
                    <span>Projeção de Compras</span>
                </a>
                % endif
            </div>

            <button
                class="sidebar-link d-flex justify-content-between align-items-center border-0 bg-transparent text-start w-100 ${'active' if ferramentas_active else 'collapsed'}"
                type="button" data-bs-toggle="collapse" data-bs-target="#ferramentasMenu"
                aria-expanded="${'true' if ferramentas_active else 'false'}">
                <span>
                    <i class="bi bi-tools"></i>
                    <span>Ferramentas</span>
                </span>
                <i class="bi bi-chevron-down small"></i>
            </button>
            <div id="ferramentasMenu" class="collapse ${'show' if ferramentas_active else ''}">
                % if central_kits_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(central_kits_url) else ''}"
                    href="${central_kits_url}">
                    <i class="bi bi-briefcase-fill"></i>
                    <span>Central de Kits</span>
                </a>
                % endif
                % if tool_custody_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(tool_custody_url) else ''}"
                    href="${tool_custody_url}">
                    <i class="bi bi-search"></i>
                    <span>Auditar Ferramentas</span>
                </a>
                % endif
                % if reparo_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(reparo_url) else ''}"
                    href="${reparo_url}">
                    <i class="bi bi-wrench-adjustable"></i>
                    <span>Em reparo...</span>
                </a>
                % endif
            </div>

            % if analytics_url and current_user.is_authenticated and getattr(current_user, 'is_admin', False):
            <a class="sidebar-link ${'active' if p.startswith(analytics_url) else ''}"
                href="${analytics_url}">
                <i class="bi bi-bar-chart-line"></i>
                <span>Central Analítica</span>
            </a>
            % endif
            % if current_user.is_authenticated and current_user.is_admin:
                <a class="sidebar-link ${'active' if users_list_url and p.startswith(users_list_url) else ''}"
                    href="${users_list_url}">
                    <i class="bi bi-people-fill"></i>
                    <span>Usuários</span>
                </a>
                % if mobile_panel_url:
                <a class="sidebar-link ${'active' if p.startswith('/mobile-panel') else ''}"
                    href="${mobile_panel_url}">
                    <i class="bi bi-phone-fill"></i>
                    <span>Painel Mobile</span>
                </a>
                % endif
                <div class="sidebar-divider"></div>

                <button
                    class="sidebar-link d-flex justify-content-between align-items-center border-0 bg-transparent text-start w-100 ${'active' if configuracoes_active else 'collapsed'}"
                    type="button" data-bs-toggle="collapse" data-bs-target="#configuracoesMenu"
                    aria-expanded="${'true' if configuracoes_active else 'false'}">
                    <span>
                        <i class="bi bi-gear-fill"></i>
                        <span>Configurações</span>
                    </span>
                    <i class="bi bi-chevron-down small"></i>
                </button>
                <div id="configuracoesMenu" class="collapse ${'show' if configuracoes_active else ''}">
                    % if empresa_url:
                    <a class="sidebar-link ps-4 ${'active' if p.startswith(empresa_url) else ''}"
                        href="${empresa_url}">
                        <i class="bi bi-building"></i>
                        <span>Empresa</span>
                    </a>
                    % endif
                    % if relatorios_config_url:
                    <a class="sidebar-link ps-4 ${'active' if p.startswith(relatorios_config_url) else ''}"
                        href="${relatorios_config_url}">
                        <i class="bi bi-file-earmark-text"></i>
                        <span>Relatórios</span>
                    </a>
                    % endif
                    % if updates_url:
                    <a class="sidebar-link ps-4 ${'active' if p.startswith(updates_url) else ''}"
                        href="${updates_url}">
                        <i class="bi bi-arrow-clockwise"></i>
                        <span>Atualizações</span>
                    </a>
                    % endif
                    % if rede_url:
                    <a class="sidebar-link ps-4 ${'active' if p.startswith(rede_url) else ''}"
                        href="${rede_url}">
                        <i class="bi bi-wifi"></i>
                        <span>Rede</span>
                    </a>
                    % endif
                    % if telegram_url:
                    <a class="sidebar-link ps-4 ${'active' if p.startswith(telegram_url) else ''}"
                        href="${telegram_url}">
                        <i class="bi bi-telegram"></i>
                        <span>Telegram</span>
                    </a>
                    % endif
                    % if notificacoes_url:
                    <a class="sidebar-link ps-4 ${'active' if p.startswith(notificacoes_url) else ''}"
                        href="${notificacoes_url}">
                        <i class="bi bi-broadcast-pin"></i>
                        <span>Notificações</span>
                    </a>
                    % endif
                    % if backup_url:
                    <a class="sidebar-link ps-4 ${'active' if p.startswith(backup_url) or (restore_backup_url and p.startswith(restore_backup_url)) else ''}"
                        href="${backup_url}">
                        <i class="bi bi-database"></i>
                        <span>Backup</span>
                    </a>
                    % endif
                    % if conversionengine_url:
                    <a class="sidebar-link ps-4 ${'active' if p.startswith(conversionengine_url) else ''}"
                        href="${conversionengine_url}">
                        <i class="bi bi-cpu"></i>
                        <span>ConversionEngine</span>
                    </a>
                    % endif
                </div>
            % endif
            % if current_user.is_authenticated:
            <div class="sidebar-link d-flex align-items-center justify-content-between" style="cursor: default;">
                <span>
                    <i class="bi bi-robot"></i>
                    <span>Assistente</span>
                </span>
                <div class="form-check form-switch m-0">
                    <input class="form-check-input" type="checkbox" id="assistant-toggle" aria-label="Alternar assistente">
                </div>
            </div>
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
