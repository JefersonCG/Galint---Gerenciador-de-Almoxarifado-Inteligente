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

            saidas_fracionadas_url = optional_url('movements.saidas_fracionadas_page')
            saidas_hub_url = optional_url('movements.saidas_hub') or url_for('movements.index')
            saida_fracionada_url = optional_url('movements.saida_fracionada_page')
            ferramentas_retirar_url = optional_url('ferramentas.retirar_page')
            ferramentas_painel_url = optional_url('ferramentas.painel')
            tool_custody_url = optional_url('tool_custody.index')
            reparo_url = optional_url('reparo.listar_reparos')
            valor_estoque_url = optional_url('inventory.valor_estoque')
            fornecedores_url = optional_url('config.fornecedores')
            central_operacoes_url = optional_url('operations.central_operations')
            reports_index_url = optional_url('reports.index')
            percentual_movimentos_url = optional_url('reports.percentual_movimentos')
            mobile_panel_url = '/mobile-panel' if getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'is_admin', False) else None
            empresa_url = optional_url('config.empresa')
            relatorios_config_url = optional_url('config.relatorios')
            updates_url = optional_url('updates.index')
            rede_url = optional_url('pages.config_rede')
            telegram_url = optional_url('telegram_config.index')
            backup_url = optional_url('pages.config_backup')
            restore_backup_url = optional_url('pages.restore_backup')

            lancamentos_active = (
                p.startswith(saidas_hub_url)
                or p.startswith(url_for('movements.index'))
                or p.startswith(url_for('movements.saida_page'))
                or (saida_fracionada_url and p.startswith(saida_fracionada_url))
                or p.startswith(url_for('movements.entrada_page'))
                or (ferramentas_retirar_url and p.startswith(ferramentas_retirar_url))
                or (saidas_fracionadas_url and p.startswith(saidas_fracionadas_url))
            )
            estoque_active = (
                p.startswith('/itens')
                or p.startswith('/nf')
                or (central_operacoes_url and p.startswith(central_operacoes_url))
                or (fornecedores_url and p.startswith(fornecedores_url))
            )
            ferramentas_active = (tool_custody_url and p.startswith(tool_custody_url)) or (reparo_url and p.startswith(reparo_url)) or (ferramentas_painel_url and p.startswith(ferramentas_painel_url)) or (ferramentas_retirar_url and p.startswith(ferramentas_retirar_url))
            configuracoes_active = (
                (empresa_url and p.startswith(empresa_url))
                or (relatorios_config_url and p.startswith(relatorios_config_url))
                or (updates_url and p.startswith(updates_url))
                or (rede_url and p.startswith(rede_url))
                or (telegram_url and p.startswith(telegram_url))
                or (backup_url and p.startswith(backup_url))
                or (restore_backup_url and p.startswith(restore_backup_url))
            )
        %>
        <nav class="sidebar-menu">
            <a class="sidebar-link ${'active' if p == url_for('dashboard.index') else ''}" href="${url_for('dashboard.index')}">
                <i class="bi bi-speedometer2"></i>
                <span>Dashboard</span>
            </a>
            <button
                class="sidebar-link d-flex justify-content-between align-items-center border-0 bg-transparent text-start w-100"
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
                <a class="sidebar-link ps-4 ${'active' if p.startswith(url_for('movements.entrada_page')) else ''}"
                    href="${url_for('movements.entrada_page')}">
                    <i class="bi bi-arrow-return-left"></i>
                    <span>Registro de Devolução</span>
                </a>
                % if saidas_fracionadas_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(saidas_fracionadas_url) else ''}"
                    href="${saidas_fracionadas_url}">
                    <i class="bi bi-droplet-half"></i>
                    <span>Saídas Fracionadas</span>
                </a>
                % endif
            </div>
            <button
                class="sidebar-link d-flex justify-content-between align-items-center border-0 bg-transparent text-start w-100"
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
                % if valor_estoque_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(valor_estoque_url) else ''}"
                    href="${valor_estoque_url}">
                    <i class="bi bi-cash-stack"></i>
                    <span>Financeiro</span>
                </a>
                % endif
                % if central_operacoes_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(central_operacoes_url) else ''}"
                    href="${central_operacoes_url}">
                    <i class="bi bi-activity"></i>
                    <span>Central de Operações</span>
                </a>
                % endif
                % if fornecedores_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(fornecedores_url) else ''}"
                    href="${fornecedores_url}">
                    <i class="bi bi-building-add"></i>
                    <span>Cadastrar fornecedor</span>
                </a>
                % endif
                % if optional_url('inventory.lojas_lab'):
                <a class="sidebar-link ps-4 ${'active' if p.startswith(optional_url('inventory.lojas_lab')) else ''}"
                    href="${optional_url('inventory.lojas_lab')}">
                    <i class="bi bi-shop"></i>
                    <span>Laboratório de Lojas</span>
                </a>
                % endif
                <a class="sidebar-link ps-4 ${'active' if p.startswith(url_for('nf.nf_index')) else ''}"
                    href="${url_for('nf.nf_index')}">
                    <i class="bi bi-receipt"></i>
                    <span>Documentos Fiscais</span>
                </a>
            </div>

            <button
                class="sidebar-link d-flex justify-content-between align-items-center border-0 bg-transparent text-start w-100"
                type="button" data-bs-toggle="collapse" data-bs-target="#ferramentasMenu"
                aria-expanded="${'true' if ferramentas_active else 'false'}">
                <span>
                    <i class="bi bi-tools"></i>
                    <span>Ferramentas</span>
                </span>
                <i class="bi bi-chevron-down small"></i>
            </button>
            <div id="ferramentasMenu" class="collapse ${'show' if ferramentas_active else ''}">
                % if ferramentas_retirar_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(ferramentas_retirar_url) else ''}"
                    href="${ferramentas_retirar_url}">
                    <i class="bi bi-box-arrow-up-right"></i>
                    <span>Retirar Ferramenta</span>
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
                % if ferramentas_painel_url:
                <a class="sidebar-link ps-4 ${'active' if p.startswith(ferramentas_painel_url) else ''}"
                    href="${ferramentas_painel_url}">
                    <i class="bi bi-grid"></i>
                    <span>Painel Ferramentas</span>
                </a>
                % endif
            </div>

            % if reports_index_url:
            <a class="sidebar-link ${'active' if p.startswith(reports_index_url) else ''}"
                href="${reports_index_url}">
                <i class="bi bi-file-earmark-bar-graph"></i>
                <span>Relatórios Gerais</span>
            </a>
            % endif
            % if percentual_movimentos_url:
            <a class="sidebar-link ${'active' if p.startswith(percentual_movimentos_url) else ''}"
                href="${percentual_movimentos_url}">
                <i class="bi bi-pie-chart"></i>
                <span>Percentual Movimentos</span>
            </a>
            % endif
            % if current_user.is_authenticated and current_user.is_admin:
                <a class="sidebar-link ${'active' if p.startswith(url_for('users.list_users')) else ''}"
                    href="${url_for('users.list_users')}">
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
                    class="sidebar-link d-flex justify-content-between align-items-center border-0 bg-transparent text-start w-100"
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
                    % if backup_url:
                    <a class="sidebar-link ps-4 ${'active' if p.startswith(backup_url) or (restore_backup_url and p.startswith(restore_backup_url)) else ''}"
                        href="${backup_url}">
                        <i class="bi bi-database"></i>
                        <span>Backup</span>
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
