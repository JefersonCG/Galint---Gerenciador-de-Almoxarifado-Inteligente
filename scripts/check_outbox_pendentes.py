import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from galint_flask import create_app
from galint_flask.models import TelegramOutbox, Saida

print("Iniciando checagem do outbox...")
app = create_app()

with app.app_context():
    pendentes = (
        TelegramOutbox.query
        .filter(TelegramOutbox.saida_id.isnot(None))
        .filter(TelegramOutbox.status.in_(["pending", "failed", "dead"]))
        .order_by(TelegramOutbox.created_at.desc())
        .all()
    )

    print(f"Total pendentes/failed/dead (saídas): {len(pendentes)}")
    for out in pendentes[:50]:
        saida = Saida.query.get(out.saida_id) if out.saida_id else None
        codigo = getattr(saida, "codigo_item", None)
        quantidade = getattr(saida, "quantidade", None)
        data_saida = getattr(saida, "data_saida", None)
        print(
            "outbox_id={} status={} saida_id={} codigo={} qtd={} data={} erro={}".format(
                out.id,
                out.status,
                out.saida_id,
                codigo,
                quantidade,
                data_saida,
                out.last_error,
            )
        )
