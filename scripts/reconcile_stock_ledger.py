"""Relatório de reconciliação entre saldo legado e saldo do ledger."""
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
from galint_flask.services.inventory_engine import inventory_engine


def main() -> int:
    app = create_app()
    with app.app_context():
        divergencias = inventory_engine.reconcile_with_legacy()
        resumo = {
            "total_divergencias": len(divergencias),
            "divergencias": divergencias,
        }

        output_dir = Path("instance")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "stock_ledger_reconciliation.json"
        output_path.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")

        print(json.dumps({
            "total_divergencias": len(divergencias),
            "arquivo": str(output_path),
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())