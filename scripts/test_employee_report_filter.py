"""Validação rápida do filtro de PDF por aba (materiais/ferramentas).

Roda a função de rota (bypass login_required) em um request_context e imprime:
- status_code
- mimetype
- tamanho do PDF

Uso:
  .venv\Scripts\python.exe scripts\test_employee_report_filter.py
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from app import app
    from galint_flask.views.tool_custody import download_employee_report

    with app.app_context():
        from galint_flask.models import Usuario

        usuario = Usuario.query.first()
        if not usuario:
            print("Sem usuários na base para testar.")
            return 2

        matricula = usuario.matricula
        print("Matricula de teste:", matricula)

        for aba in ("all", "materiais", "ferramentas"):
            url = f"/controle-ferramentas/api/funcionario/{matricula}/relatorio.pdf?aba={aba}"
            with app.test_request_context(url):
                resp = download_employee_report.__wrapped__(matricula)
                try:
                    resp.direct_passthrough = False
                except Exception:
                    pass
                data = resp.get_data()
                print(aba, resp.status_code, resp.mimetype, len(data))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
