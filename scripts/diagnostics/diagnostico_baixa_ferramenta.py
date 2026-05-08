"""Diagnóstico de baixa de ferramenta (custódia x estoque).

Mostra, para cada código informado:
- últimas saídas (Saida)
- custódia aberta (RetiradaFerramenta)
- evidências de devolução após a saída (InventarioEvento / Entrada legada sem NF)

Uso:
  .venv\\Scripts\\python.exe diagnostico_baixa_ferramenta.py 0280 0291
  .venv\\Scripts\\python.exe diagnostico_baixa_ferramenta.py 0280 --matricula 84155
"""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any, cast

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Entrada, InventarioEvento, Item, RetiradaFerramenta, Saida, Usuario


RETURN_TYPES = (
    "devolucao_ferramenta",
    "devolucao_material",
    "quebra_ferramenta",
    "reparo_ferramenta",
)


def _fmt_dt(value: datetime | None) -> str:
    if not value:
        return "-"
    return value.strftime("%d/%m/%Y %H:%M")


def _print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def diagnose_code(codigo_item: str, matricula: str | None) -> None:
    _print_header(f"CÓDIGO {codigo_item} (matricula filtro={matricula or 'N/A'})")

    item = cast(Any, Item.query.filter(Item.codigo_item == codigo_item).first())
    if item:
        print(
            "Item: "
            f"{getattr(item, 'codigo_item', '-') } | {getattr(item, 'descricao', '-') } | "
            f"categoria={getattr(item, 'categoria', '-') } | setor={getattr(item, 'setor', '-') }"
        )
    else:
        print("Item: (não encontrado em itens.codigo_item)")

    q = db.session.query(Saida).filter(Saida.codigo_item == codigo_item)
    if matricula:
        q = q.filter(Saida.matricula == matricula)

    saidas = q.order_by(Saida.data_saida.desc()).limit(10).all()
    if not saidas:
        print("Saídas: nenhuma encontrada")
        return

    print(f"Saídas (últimas {len(saidas)}):")
    for saida in saidas:
        usuario = Usuario.query.get(saida.matricula) if saida.matricula else None
        usuario_label = f"{usuario.nome} ({usuario.matricula})" if usuario else (saida.matricula or "-")

        print("-" * 80)
        print(
            f"Saida id={saida.id_saida} | data={_fmt_dt(saida.data_saida)} | qtd={saida.quantidade} | usuario={usuario_label}"
        )
        print(f"  local={saida.local_servico or '-'}")
        print(f"  obs={saida.observacao or '-'}")

        retirada = cast(
            Any,
            RetiradaFerramenta.query.filter(
                RetiradaFerramenta.codigo_item == saida.codigo_item,
                RetiradaFerramenta.matricula == saida.matricula,
                RetiradaFerramenta.status.in_(["em_uso", "atrasada", "para_reparo", "devolvida"]),
                RetiradaFerramenta.data_retirada >= saida.data_saida,
            )
            .order_by(RetiradaFerramenta.data_retirada.desc())
            .first()
        )

        if retirada:
            print(
                "  Custódia: "
                f"retirada_id={getattr(retirada, 'id', '-')} | "
                f"status={getattr(retirada, 'status', '-')} | "
                f"retirada_em={_fmt_dt(getattr(retirada, 'data_retirada', None))} | "
                f"devolvida_em={_fmt_dt(getattr(retirada, 'data_devolucao', None))}"
            )
        else:
            print("  Custódia: (nenhum registro encontrado a partir desta saída)")

        eventos = (
            db.session.query(InventarioEvento)
            .filter(
                InventarioEvento.codigo_item == saida.codigo_item,
                InventarioEvento.matricula == saida.matricula,
                InventarioEvento.data_evento >= saida.data_saida,
            )
            .order_by(InventarioEvento.data_evento.asc())
            .all()
        )

        eventos_retorno = [e for e in eventos if (e.tipo or "").strip() in RETURN_TYPES]
        if eventos_retorno:
            print(f"  Eventos retorno ({len(eventos_retorno)}):")
            for e in eventos_retorno:
                print(
                    f"    - id={e.id_evento} | tipo={e.tipo} | qtd={e.quantidade} | data={_fmt_dt(e.data_evento)} | desc={e.descricao or '-'}"
                )
        else:
            print("  Eventos retorno: nenhum")

        entrada_legado = (
            db.session.query(Entrada)
            .filter(
                Entrada.codigo_item == saida.codigo_item,
                Entrada.matricula == saida.matricula,
                Entrada.nota_fiscal.is_(None),
                Entrada.data_entrada >= saida.data_saida,
            )
            .order_by(Entrada.data_entrada.asc())
            .first()
        )
        if entrada_legado:
            obs = getattr(entrada_legado, "observacao", None) or getattr(entrada_legado, "observacao_entrada", None)
            print(
                f"  Entrada legada: id={entrada_legado.id_entrada} | qtd={entrada_legado.quantidade} | data={_fmt_dt(entrada_legado.data_entrada)} | obs={obs or '-'}"
            )
        else:
            print("  Entrada legada: nenhuma")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("codigos", nargs="+", help="Código(s) do item (itens.codigo_item)")
    parser.add_argument("--matricula", help="Filtra pela matrícula (opcional)")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        for codigo in args.codigos:
            diagnose_code(codigo.strip(), (args.matricula or "").strip() or None)


if __name__ == "__main__":
    main()
