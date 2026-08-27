r"""Aplica sincronização conservadora do estoque de embalagens a partir do saldo legado.

Quando usar:
- Itens com `tipo_embalagem_novo` configurado e `unidades_por_embalagem > 0`
- Mas `estoque_embalagens`/`estoque_unidades_soltas` estão zerados ou menores do que o legado,
  causando "Saldo insuficiente" ao retirar unidades.

Regras de segurança (definidas em `EmbalagemService.tentar_sincronizar_estoque_de_legacy`):
- Só sincroniza quando o saldo legado parece inteiro (típico de entradas em caixas/pacotes)
- Só aumenta `estoque_embalagens` (não diminui)
- Evita mexer quando há unidades soltas (sinal de retirada em unidades já em andamento)

Uso:
  .\.venv\Scripts\python.exe aplicar_sync_embalagens_legacy.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    sys.path.insert(0, os.getcwd())

    from app import app
    from galint_flask.extensions import db
    from galint_flask.models import Item
    from galint_flask.services.embalagem_service import EmbalagemService

    alterados: list[tuple[str, float, float, float, float, float]] = []

    with app.app_context():
        itens = Item.query.order_by(Item.codigo_item).all()
        for item in itens:
            if not EmbalagemService.tem_embalagem(item):
                continue

            emb_before = float(item.estoque_embalagens or 0)
            soltas_before = float(item.estoque_unidades_soltas or 0)

            try:
                changed = EmbalagemService.tentar_sincronizar_estoque_de_legacy(item)
            except Exception:
                changed = False

            if not changed:
                continue

            emb_after = float(item.estoque_embalagens or 0)
            soltas_after = float(item.estoque_unidades_soltas or 0)
            try:
                legacy = float(item.get_saldo_atual() or 0)
            except Exception:
                legacy = 0.0

            alterados.append(
                (
                    item.codigo_item,
                    legacy,
                    emb_before,
                    soltas_before,
                    emb_after,
                    soltas_after,
                )
            )

        if alterados:
            db.session.commit()

    print(f"Itens sincronizados: {len(alterados)}")
    for codigo, legacy, emb_b, sol_b, emb_a, sol_a in alterados:
        print(
            f"{codigo}: legacy={legacy:g} | novo {emb_b:g} emb + {sol_b:g} soltas -> {emb_a:g} emb + {sol_a:g} soltas"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
