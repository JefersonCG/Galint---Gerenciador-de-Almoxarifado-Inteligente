"""Diagnóstico: itens com embalagem com estoque novo incoerente vs saldo legado.

Uso:
  .\.venv\Scripts\python.exe check_embalagens_inconsistentes.py

Motivação:
- Itens antigos podem ter saldo legado (entradas/saídas) registrado como "embalagens",
  enquanto o novo sistema usa `Item.estoque_embalagens` e `Item.estoque_unidades_soltas`.
- Quando o estoque novo está baixo (ex.: 3 unidades), mas o legado sugere 1 caixa,
  saídas em unidades podem falhar com "Saldo insuficiente".

Este script lista candidatos para revisão/migração.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    # Garante que o diretório do projeto esteja no sys.path
    sys.path.insert(0, os.getcwd())

    from app import app
    from galint_flask.models import Item
    from galint_flask.services.embalagem_service import EmbalagemService

    with app.app_context():
        rows: list[tuple[float, str, str, float, float, float, float, float]] = []

        for item in Item.query.all():
            if not EmbalagemService.tem_embalagem(item):
                continue

            unidades_por = float(item.unidades_por_embalagem or 0)
            if unidades_por <= 0:
                continue

            try:
                novo_total = float(EmbalagemService.calcular_estoque_total(item) or 0)
            except Exception:
                novo_total = 0.0

            try:
                legacy = float(item.get_saldo_atual() or 0)
            except Exception:
                legacy = 0.0

            legacy_int = int(round(legacy))
            legacy_is_int = abs(legacy - legacy_int) < 1e-6
            legacy_units = float(legacy_int) * unidades_por if legacy_is_int else 0.0

            # Heurística: legado parece representar embalagens (inteiro positivo)
            # e implica mais unidades do que o estoque novo mostra.
            if legacy_is_int and legacy_int > 0 and legacy_units > novo_total and novo_total <= unidades_por:
                diff = legacy_units - novo_total
                rows.append(
                    (
                        diff,
                        item.codigo_item,
                        (item.descricao or ""),
                        legacy,
                        float(item.estoque_embalagens or 0),
                        float(item.estoque_unidades_soltas or 0),
                        unidades_por,
                        novo_total,
                    )
                )

        rows.sort(reverse=True)
        print(f"Candidatos: {len(rows)}")
        for diff, codigo, desc, legacy, emb, soltas, up, novo_total in rows[:50]:
            desc_short = desc.replace("\n", " ").strip()[:80]
            print(
                f"{codigo} | legacy={legacy:g} emb | up={up:g} | novo_emb={emb:g} novo_soltas={soltas:g} "
                f"novo_total={novo_total:g} | diff={diff:g} | {desc_short}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
