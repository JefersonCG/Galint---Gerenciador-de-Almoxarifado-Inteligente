from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from galint_flask.models import StockBalance
from galint_flask.services.ledger_backfill import ledger_backfill_service
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
        summary = ledger_backfill_service.backfill()
        reconciliation_results = ledger_reconciliation_service.reconcile_all()
        reconciliation_summary = _summarize_results(reconciliation_results)
        read_model_ready = (
            StockBalance.query
            .filter(StockBalance.read_model_ready.is_(True))
            .count()
        )
        read_model_pending = (
            StockBalance.query
            .filter(StockBalance.read_model_ready.is_(False))
            .count()
        )
        critical_results = [
            result for result in reconciliation_results
            if result.classification == "divergencia_critica"
        ]
        lines = [
            "BACKFILL LEDGER CONCLUIDO",
            f"Entradas processadas: {summary.processed_entries}",
            f"Saidas processadas: {summary.processed_exits}",
            f"Eventos processados: {summary.processed_events}",
            f"Registros ignorados por já existirem: {summary.skipped_existing}",
            f"Registros ignorados por item ausente: {summary.skipped_missing_product}",
            f"Saldos reconstruidos: {summary.balances_rebuilt}",
            f"Read models preservados: {summary.read_models_preserved}",
            f"Read models desativados por divergencia: {summary.read_models_not_preserved}",
            "",
            "RECONCILIACAO APOS BACKFILL",
            f"Total de produtos: {reconciliation_summary['total']}",
            f"Divergencia zero: {reconciliation_summary['divergencia_zero']}",
            f"Divergencia explicavel: {reconciliation_summary['divergencia_explicavel']}",
            f"Divergencia critica: {reconciliation_summary['divergencia_critica']}",
            "",
            "ESTADO DO READ MODEL",
            f"Produtos com leitura ledger ativa: {read_model_ready}",
            f"Produtos pendentes em legado: {read_model_pending}",
        ]

        if critical_results:
            lines.append("")
            lines.append("PRODUTOS COM DIVERGENCIA CRITICA")
            for result in critical_results:
                lines.append(
                    f"- {result.product_id} | {result.description} | "
                    f"legado={result.legacy_balance:g} | ledger={result.ledger_balance:g} | cache={result.stock_balance:g}"
                )

        exit_code = resolve_exit_code(
            has_critical_divergence=bool(reconciliation_summary["divergencia_critica"]),
            has_orphans=bool(summary.skipped_missing_product),
        )
        lines.append("")
        report_path = build_report_path(ROOT, "ledger_backfill")
        lines.append(f"Relatorio salvo em: {report_path}")
        lines.append(f"Codigo de saida previsto: {exit_code}")
        persist_execution_report(report_path, lines)

        for line in lines:
            print(line)

        if exit_code:
            raise SystemExit(exit_code)


if __name__ == "__main__":
    main()