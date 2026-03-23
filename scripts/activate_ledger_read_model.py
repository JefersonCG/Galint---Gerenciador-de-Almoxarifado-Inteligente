from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from galint_flask.services.ledger_cutover import ledger_cutover_service


def _parse_args(argv: list[str]) -> tuple[list[str], bool, bool, bool]:
    product_ids: list[str] = []
    allow_explainable = False
    force = False
    dry_run = False

    for arg in argv:
        normalized = (arg or "").strip()
        if not normalized:
            continue
        if normalized == "--allow-explainable":
            allow_explainable = True
            continue
        if normalized == "--force":
            force = True
            continue
        if normalized == "--dry-run":
            dry_run = True
            continue
        product_ids.append(normalized)

    return product_ids, allow_explainable, force, dry_run


def main() -> None:
    product_ids, allow_explainable, force, dry_run = _parse_args(sys.argv[1:])
    if not product_ids:
        raise SystemExit(
            "Informe ao menos um product_id. Flags disponíveis: --allow-explainable --force --dry-run"
        )

    app = create_app()
    with app.app_context():
        decisions = ledger_cutover_service.activate_batch(
            product_ids,
            allow_explainable=allow_explainable,
            force=force,
            dry_run=dry_run,
        )
        print("ATIVACAO DE LEITURA LEDGER")
        for decision in decisions:
            status = "ATIVADO" if decision.activated else "BLOQUEADO"
            print(
                f"- {decision.product_id} | {status} | {decision.classification} | "
                f"legado={decision.legacy_balance:g} | ledger={decision.ledger_balance:g} | "
                f"cache={decision.stock_balance:g} | {decision.reason}"
            )


if __name__ == "__main__":
    main()
