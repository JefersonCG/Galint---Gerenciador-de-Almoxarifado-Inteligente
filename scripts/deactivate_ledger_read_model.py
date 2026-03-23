from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from galint_flask.services.ledger_cutover import ledger_cutover_service


def main() -> None:
    product_ids = [arg.strip() for arg in sys.argv[1:] if arg.strip()]
    if not product_ids:
        raise SystemExit("Informe ao menos um product_id para reverter a leitura")

    app = create_app()
    with app.app_context():
        print("REVERSAO DE LEITURA LEDGER")
        for product_id in product_ids:
            decision = ledger_cutover_service.deactivate_product(product_id)
            print(
                f"- {decision.product_id} | LEGADO | {decision.classification} | "
                f"legado={decision.legacy_balance:g} | ledger={decision.ledger_balance:g} | "
                f"cache={decision.stock_balance:g} | {decision.reason}"
            )


if __name__ == "__main__":
    main()
