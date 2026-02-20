#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Altera o código (EAN) de um item com segurança.

Uso:
  .\.venv\Scripts\python.exe scripts/change_item_code.py 7890983086224 7890988603224

A estratégia:
1) cria um novo Item com o novo código (copia os dados do antigo)
2) atualiza todas as tabelas filhas para o novo código
3) remove o item antigo
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, Entrada, Saida, InventarioEvento, MaterialInventario


def change_code(old_code: str, new_code: str) -> bool:
    os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
    os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
    app = create_app()
    with app.app_context():
        try:
            old_code = (old_code or "").strip()
            new_code = (new_code or "").strip()
            if not old_code or not new_code:
                print("ERRO: códigos inválidos.")
                return False
            if old_code == new_code:
                print("ERRO: códigos são iguais.")
                return False

            old_item = db.session.get(Item, old_code)
            if not old_item:
                print(f"ERRO: item {old_code} não encontrado.")
                return False
            if db.session.get(Item, new_code):
                print(f"ERRO: já existe item com código {new_code}.")
                return False

            # cria novo item copiando campos
            new_item = Item(
                codigo_item=new_code,
                descricao=old_item.descricao,
                unidade=old_item.unidade,
                localizacao=old_item.localizacao,
                setor=old_item.setor,
                estoque_minimo=old_item.estoque_minimo,
                nota_fiscal=old_item.nota_fiscal,
                categoria=old_item.categoria,
                marca=old_item.marca,
                numero_serie=old_item.numero_serie,
                modelo=old_item.modelo,
                data_entrada=old_item.data_entrada,
                lote=old_item.lote,
                data_fabricacao=old_item.data_fabricacao,
                data_validade=old_item.data_validade,
                tipo_embalagem=old_item.tipo_embalagem,
                grandeza_referencia=old_item.grandeza_referencia,
                densidade=old_item.densidade,
                litros_por_embalagem=old_item.litros_por_embalagem,
                barcode_image_path=old_item.barcode_image_path,
            )
            db.session.add(new_item)
            db.session.flush()

            # atualiza tabelas filhas
            Entrada.query.filter_by(codigo_item=old_code).update({"codigo_item": new_code})
            Saida.query.filter_by(codigo_item=old_code).update({"codigo_item": new_code})
            InventarioEvento.query.filter_by(codigo_item=old_code).update({"codigo_item": new_code})
            MaterialInventario.query.filter_by(codigo_item=old_code).update({"codigo_item": new_code})

            # remove item antigo
            db.session.delete(old_item)
            db.session.commit()

            print("OK: código alterado com sucesso.")
            print(f"{old_code} -> {new_code}")
            return True
        except Exception as exc:
            db.session.rollback()
            print(f"ERRO: {exc}")
            return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python scripts/change_item_code.py <codigo_antigo> <codigo_novo>")
        sys.exit(1)
    ok = change_code(sys.argv[1], sys.argv[2])
    sys.exit(0 if ok else 1)
