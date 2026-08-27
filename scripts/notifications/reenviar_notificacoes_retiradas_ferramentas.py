r"""Reenvia (reenfileira) notificações de Telegram para retiradas de ferramentas.

Útil quando retiradas foram registradas antes da implementação de notificação.

Uso:
  .\.venv\Scripts\python.exe reenviar_notificacoes_retiradas_ferramentas.py
  .\.venv\Scripts\python.exe reenviar_notificacoes_retiradas_ferramentas.py --hours 48

Observação:
- Usa idempotency_key, então não deve duplicar mensagens já enfileiradas.
- Requer Telegram habilitado (polling/outbox).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import RetiradaFerramenta
from galint_flask.services.ferramentas import ferramentas_service


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24, help="Janela de horas para buscar retiradas")
    args = parser.parse_args()

    since = datetime.utcnow() - timedelta(hours=max(1, int(args.hours)))

    app = create_app()
    with app.app_context():
        retiradas = (
            db.session.query(RetiradaFerramenta)
            .filter(RetiradaFerramenta.data_retirada >= since)
            .order_by(RetiradaFerramenta.data_retirada.asc())
            .all()
        )

        print(f"Retiradas encontradas desde {since.isoformat()}Z: {len(retiradas)}")

        ok = 0
        falhas = 0
        for r in retiradas:
            try:
                # Método interno do service — OK para uso operacional/diagnóstico.
                ferramentas_service._notificar_retirada_telegram(r)  # type: ignore[attr-defined]
                ok += 1
            except Exception as e:
                falhas += 1
                print(f"Falha ao notificar retirada id={r.id}: {e}")

        print(f"Concluído. Processadas={len(retiradas)} OK={ok} Falhas={falhas}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
