from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from galint_flask.services.ledger_reconciliation import ledger_reconciliation_service
from scripts.ledger_maintenance_utils import build_report_path, persist_execution_report, resolve_exit_code


def _summarize_results(results: list[object]) -> dict[str, int]:
    summary = {
        "total": len(results),
        "divergencia_zero": 0,
        "divergencia_explicavel": 0,
        "divergencia_critica": 0,
    }
    for result in results:
        summary[result.classification] += 1
    return summary


def main() -> None:
    app = create_app()
    with app.app_context():
        results = ledger_reconciliation_service.reconcile_all()
        summary = _summarize_results(results)
        critical_results = [
            result for result in results
            if result.classification == "divergencia_critica"
        ]
        lines = [
            "RECONCILIACAO LEDGER",
            f"Total de produtos: {summary['total']}",
            f"Divergencia zero: {summary['divergencia_zero']}",
            f"Divergencia explicavel: {summary['divergencia_explicavel']}",
            f"Divergencia critica: {summary['divergencia_critica']}",
            "",
            "PRODUTOS COM DIVERGENCIA CRITICA",
        ]
        for result in critical_results:
            lines.append(
                f"- {result.product_id} | {result.description} | "
                f"legado={result.legacy_balance:g} | ledger={result.ledger_balance:g} | cache={result.stock_balance:g}"
            )

        exit_code = resolve_exit_code(
            has_critical_divergence=bool(summary["divergencia_critica"]),
            has_orphans=False,
        )
        lines.append("")
        report_path = build_report_path(ROOT, "ledger_reconcile")
        lines.append(f"Relatorio salvo em: {report_path}")
        lines.append(f"Codigo de saida previsto: {exit_code}")
        persist_execution_report(report_path, lines)

        for line in lines:
            print(line)

        if exit_code:
            raise SystemExit(exit_code)


if __name__ == "__main__":
    main()