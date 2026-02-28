"""Renomeia o setor "SERVIÇOS GERAIS" para "TERCERIZADOS" no banco.

Atualiza:
- usuarios.setor
- itens.setor

Uso:
  .venv\\Scripts\\python.exe rename_setor_servicos_gerais_para_tercerizados.py
"""

from __future__ import annotations

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, Usuario

OLD = "SERVIÇOS GERAIS"
NEW = "TERCERIZADOS"


def main() -> None:
    app = create_app()

    with app.app_context():
        usuarios_qtd = Usuario.query.filter(Usuario.setor == OLD).count()
        itens_qtd = Item.query.filter(Item.setor == OLD).count()

        print("=" * 70)
        print(f"RENOMEAR SETOR: {OLD!r} -> {NEW!r}")
        print(f"Usuários afetados: {usuarios_qtd}")
        print(f"Itens afetados: {itens_qtd}")
        print("=" * 70)

        if usuarios_qtd == 0 and itens_qtd == 0:
            print("Nada a fazer.")
            return

        try:
            updated_users = 0
            updated_items = 0

            if usuarios_qtd:
                updated_users = Usuario.query.filter(Usuario.setor == OLD).update(
                    {Usuario.setor: NEW}, synchronize_session=False
                )

            if itens_qtd:
                updated_items = Item.query.filter(Item.setor == OLD).update(
                    {Item.setor: NEW}, synchronize_session=False
                )

            db.session.commit()
            print("✅ Atualização concluída.")
            print(f"- usuarios atualizados: {updated_users}")
            print(f"- itens atualizados: {updated_items}")

        except Exception as exc:
            db.session.rollback()
            print(f"❌ Erro ao atualizar: {exc}")
            raise


if __name__ == "__main__":
    main()
