from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from galint_flask.services.ledger_cutover import ledger_cutover_service


def main() -> None:
    allow_explainable = "--allow-explainable" in sys.argv[1:]
    dry_run = "--dry-run" in sys.argv[1:]

    app = create_app()
    with app.app_context():
        eligible = ledger_cutover_service.eligible_products(
            allow_explainable=allow_explainable,
        )
        product_ids = [result.product_id for result in eligible]
        decisions = ledger_cutover_service.activate_batch(
            product_ids,
            allow_explainable=allow_explainable,
            dry_run=dry_run,
        )
        activated = sum(1 for decision in decisions if decision.activated)
        blocked = len(decisions) - activated
        print("ATIVACAO EM LOTE DO READ MODEL")
        print(f"Produtos elegiveis: {len(product_ids)}")
        print(f"Produtos ativados: {activated}")
        print(f"Produtos bloqueados: {blocked}")
        for decision in decisions:
            status = "ATIVADO" if decision.activated else "BLOQUEADO"
            print(
                f"- {decision.product_id} | {status} | {decision.classification} | "
                f"legado={decision.legacy_balance:g} | ledger={decision.ledger_balance:g} | "
                f"cache={decision.stock_balance:g} | {decision.reason}"
            )


if __name__ == "__main__":
    main()