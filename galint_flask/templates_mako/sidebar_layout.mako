<div class="sidebar-wrapper">
    <div class="sidebar-brand px-3 py-3 text-uppercase text-light">
        <div class="sidebar-brand-heading">
            <button class="btn btn-sm btn-outline-light rounded-circle" id="sidebar-toggle" aria-label="Recolher menu" aria-expanded="true" title="Recolher/abrir menu">
                <i class="bi bi-list"></i>
            </button>
            <div>
                <strong class="sidebar-brand-title">${system_name}</strong>
                <small class="text-white-50 d-block">Gestão de Almoxarifado</small>
            </div>
        </div>
    </div>
    <div class="sidebar-scroll">
        <% sidebar = build_sidebar_navigation() %>
        <nav class="sidebar-menu">
            % for entry in sidebar['entries']:
                % if entry['type'] == 'divider':
                <div class="sidebar-divider"></div>
                % elif entry['type'] == 'group':
                <button
                    class="sidebar-link d-flex justify-content-between align-items-center border-0 bg-transparent text-start w-100 ${'active' if entry['active'] else 'collapsed'}"
                    type="button" data-bs-toggle="collapse" data-bs-target="#${entry['collapse_id']}"
                    aria-expanded="${'true' if entry['active'] else 'false'}">
                    <span>
                        <i class="bi ${entry['icon']}"></i>
                        <span>${entry['label']}</span>
                    </span>
                    <i class="bi bi-chevron-down small"></i>
                </button>
                <div id="${entry['collapse_id']}" class="collapse ${'show' if entry['active'] else ''}">
                    % for child in entry['children']:
                    <a class="sidebar-link ps-4 ${'active' if child['active'] else ''}" href="${child['href']}">
                        <i class="bi ${child['icon']}"></i>
                        <span>${child['label']}</span>
                    </a>
                    % endfor
                </div>
                % elif entry['type'] == 'toggle':
                <div class="sidebar-link d-flex align-items-center justify-content-between" style="cursor: default;">
                    <span>
                        <i class="bi ${entry['icon']}"></i>
                        <span>${entry['label']}</span>
                    </span>
                    <div class="form-check form-switch m-0">
                        <input class="form-check-input" type="checkbox" id="${entry['input_id']}" aria-label="Alternar assistente">
                    </div>
                </div>
                % else:
                <a class="sidebar-link ${'active' if entry['active'] else ''}" href="${entry['href']}">
                    % if entry['icon']:
                    <i class="bi ${entry['icon']}"></i>
                    % endif
                    <span>${entry['label']}</span>
                </a>
                % endif
            % endfor
        </nav>
    </div>
    <div class="sidebar-footer px-3 py-3">
        <small class="text-muted">Usuário: ${sidebar['footer_user_label']}</small>
    </div>
</div>
