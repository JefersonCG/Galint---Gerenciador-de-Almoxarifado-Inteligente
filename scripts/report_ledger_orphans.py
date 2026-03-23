from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import not_

from app import create_app
from galint_flask.extensions import db
from galint_flask.models import Entrada, InventarioEvento, Item, Saida
from scripts.ledger_maintenance_utils import build_report_path, persist_execution_report


def _collect_orphans() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    entradas = (
        db.session.query(Entrada)
        .filter(not_(Entrada.codigo_item.in_(db.session.query(Item.codigo_item))))
        .order_by(Entrada.data_entrada.asc(), Entrada.id_entrada.asc())
        .all()
    )
    for row in entradas:
        rows.append(
            {
                "origem": "entrada",
                "id_referencia": row.id_entrada,
                "codigo_item": row.codigo_item,
                "quantidade": float(row.quantidade or 0.0),
                "data": row.data_entrada.isoformat() if row.data_entrada else "",
                "descricao": row.observacao or row.nota_fiscal or "",
            }
        )

    saidas = (
        db.session.query(Saida)
        .filter(not_(Saida.codigo_item.in_(db.session.query(Item.codigo_item))))
        .order_by(Saida.data_saida.asc(), Saida.id_saida.asc())
        .all()
    )
    for row in saidas:
        rows.append(
            {
                "origem": "saida",
                "id_referencia": row.id_saida,
                "codigo_item": row.codigo_item,
                "quantidade": float(row.quantidade or 0.0),
                "data": row.data_saida.isoformat() if row.data_saida else "",
                "descricao": row.observacao or row.local_servico or "",
            }
        )

    eventos = (
        db.session.query(InventarioEvento)
        .filter(not_(InventarioEvento.codigo_item.in_(db.session.query(Item.codigo_item))))
        .order_by(InventarioEvento.data_evento.asc(), InventarioEvento.id_evento.asc())
        .all()
    )
    for row in eventos:
        rows.append(
            {
                "origem": f"inventario_evento:{row.tipo or ''}",
                "id_referencia": row.id_evento,
                "codigo_item": row.codigo_item,
                "quantidade": float(row.quantidade or 0.0),
                "data": row.data_evento.isoformat() if row.data_evento else "",
                "descricao": row.descricao or "",
            }
        )

    return rows


def main() -> None:
    app = create_app()
    with app.app_context():
        rows = _collect_orphans()
        reports_dir = ROOT / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        output_file = reports_dir / "ledger_orphan_movements.csv"
        with output_file.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["origem", "id_referencia", "codigo_item", "quantidade", "data", "descricao"],
            )
            writer.writeheader()
            writer.writerows(rows)

        lines = [
            "RELATORIO DE MOVIMENTOS ORFAOS",
            f"Total de registros: {len(rows)}",
            f"Arquivo CSV: {output_file}",
        ]
        for row in rows[:20]:
            lines.append(
                f"- {row['origem']} | ref={row['id_referencia']} | codigo={row['codigo_item']} | "
                f"qtd={row['quantidade']} | data={row['data']} | {row['descricao']}"
            )
        lines.append("")
        report_path = build_report_path(ROOT, "ledger_orphans")
        lines.append(f"Relatorio salvo em: {report_path}")
        persist_execution_report(report_path, lines)

        for line in lines:
            print(line)


if __name__ == "__main__":
    main()