"""Padroniza itens líquidos de 5L para a embalagem Bombona."""

from __future__ import annotations

import re

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item


FIVE_LITER_PATTERN = re.compile(r"\b5\s*(l|lt|lts|litro|litros)\b", re.IGNORECASE)
NORMALIZED_LITER_UNITS = {"l", "lt", "lts", "litro", "litros", "unidade", "unidades", "galao", "galão", "galoes", "galões"}


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _is_five_liter_candidate(item: Item) -> bool:
    descricao = _normalize(item.descricao)
    litros = float(item.litros_por_embalagem or 0)
    tipo = _normalize(item.tipo_embalagem_novo)
    unidade = _normalize(item.unidade)

    is_5l = litros == 5.0 or bool(FIVE_LITER_PATTERN.search(descricao))
    if not is_5l:
        return False

    return tipo in {"", "litro", "lata", "balde", "bombona"} or unidade in NORMALIZED_LITER_UNITS


def aplicar_migracao() -> dict[str, object]:
    app = create_app()
    atualizados: list[dict[str, object]] = []

    with app.app_context():
        itens = Item.query.order_by(Item.codigo_item.asc()).all()
        for item in itens:
            if not _is_five_liter_candidate(item):
                continue

            alterado = False
            unidade_original = item.unidade
            tipo_original = item.tipo_embalagem_novo

            if item.tipo_embalagem_novo != "bombona":
                item.tipo_embalagem_novo = "bombona"
                alterado = True

            if float(item.litros_por_embalagem or 0) != 5.0:
                item.litros_por_embalagem = 5.0
                alterado = True

            if float(item.unidades_por_embalagem or 0) != 5.0:
                item.unidades_por_embalagem = 5.0
                alterado = True

            if _normalize(item.unidade) in NORMALIZED_LITER_UNITS and item.unidade != "Litro":
                item.unidade = "Litro"
                alterado = True

            if item.grandeza_referencia not in (None, ""):
                item.grandeza_referencia = None
                alterado = True

            if alterado:
                atualizados.append(
                    {
                        "codigo": item.codigo_item,
                        "descricao": item.descricao,
                        "unidade_antes": unidade_original,
                        "tipo_antes": tipo_original,
                        "unidade_depois": item.unidade,
                        "tipo_depois": item.tipo_embalagem_novo,
                    }
                )

        if atualizados:
            db.session.commit()
        else:
            db.session.rollback()

    return {"updated": len(atualizados), "items": atualizados}


if __name__ == "__main__":
    resultado = aplicar_migracao()
    print(resultado)