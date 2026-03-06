<%inherit file="/base.mako"/>
<%!
    def fmt_num(value):
        if value is None:
            return "-"
        try:
            return f"{float(value):.4f}".rstrip("0").rstrip(".")
        except Exception:
            return str(value)

    def fmt_dt(value):
        if not value:
            return "-"
        try:
            return value.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return str(value)
%>

<%block name="title">Saídas Fracionadas</%block>

<%block name="extra_css">
<style>
    .page-header {
        background: linear-gradient(120deg, #2563eb 0%, #3b82f6 100%);
        color: white;
        padding: 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 20px rgba(37, 99, 235, 0.4);
    }
    
    .page-header h2 {
        margin: 0;
        font-weight: 700;
        font-size: 1.75rem;
    }
    
    .page-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.95;
        font-size: 0.95rem;
    }
</style>
</%block>

<%block name="content">
    <div class="container-fluid">
        <div class="page-header">
            <h2><i class="bi bi-droplet-half me-2"></i>Saídas Fracionadas</h2>
            <p>Histórico de retiradas fracionadas (líquidos) por fração da embalagem</p>
        </div>

        <div class="card shadow-sm">
            <div class="card-body">
                % if not saidas:
                    <div class="text-center text-muted py-5">Nenhuma saída fracionada registrada.</div>
                % else:
                    <div class="table-responsive">
                        <table class="table table-hover align-middle">
                            <thead class="table-light">
                                <tr>
                                    <th>Data</th>
                                    <th>Item</th>
                                    <th>Fração</th>
                                    <th>Embalagem</th>
                                    <th>Litros</th>
                                    <th>Quilos</th>
                                    <th>Retirado por</th>
                                    <th>Observação</th>
                                </tr>
                            </thead>
                            <tbody>
                                % for s in saidas:
                                    <tr>
                                        <td>${fmt_dt(s.get('data'))}</td>
                                        <td>
                                            <div class="fw-semibold">${s.get('descricao') or s.get('codigo') or '-'}</div>
                                            <div class="text-muted small">Código: ${s.get('codigo') or '-'}</div>
                                        </td>
                                        <td>
                                            % if s.get('fracao_numerador') and s.get('fracao_denominador'):
                                                ${s.get('fracao_numerador')}/${s.get('fracao_denominador')}
                                            % else:
                                                -
                                            % endif
                                        </td>
                                        <td>${fmt_num(s.get('quantidade_total_embalagem'))}</td>
                                        <td>${fmt_num(s.get('quantidade_retirada_em_litros'))}</td>
                                        <td>${fmt_num(s.get('quantidade_retirada_em_quilos'))}</td>
                                        <td>
                                            <div>${s.get('usuario') or '-'}</div>
                                            <div class="text-muted small">Mat: ${s.get('matricula') or '-'}</div>
                                        </td>
                                        <td>${s.get('observacao') or '-'}</td>
                                    </tr>
                                % endfor
                            </tbody>
                        </table>
                    </div>
                % endif
            </div>
        </div>
    </div>
</%block>
