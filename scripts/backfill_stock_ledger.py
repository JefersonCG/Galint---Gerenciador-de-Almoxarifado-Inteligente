"""Backfill do ledger de estoque a partir do modelo legado."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import StockBalance, StockMovement
from galint_flask.services.inventory_engine import inventory_engine


def main() -> int:
    app = create_app()
    with app.app_context():
        print("[ledger] iniciando backfill do estoque")

        if StockMovement.query.count() > 0:
            print("[ledger] stock_movements já possui registros; o backfill é idempotente e fará apenas os faltantes")

        counts = inventory_engine.backfill_legacy_rows()
        saldos = inventory_engine.rebuild_stock_balance()
        db.session.commit()

        payload = {
            "movimentos_processados": counts,
            "itens_com_saldo": len(saldos),
            "linhas_stock_balance": StockBalance.query.count(),
            "linhas_stock_movement": StockMovement.query.count(),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())