"""Adiciona coluna foto_path na tabela itens para armazenar caminho da foto do item.

Executar:
    python scripts/add_foto_path_to_itens.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Adicionar raiz ao path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from app import app
    from galint_flask.extensions import db

    with app.app_context():
        print("🔄 Adicionando coluna 'foto_path' na tabela 'itens'...")

        try:
            # Adicionar coluna
            db.session.execute(db.text("""
                ALTER TABLE itens 
                ADD COLUMN IF NOT EXISTS foto_path VARCHAR(255);
            """))
            db.session.commit()

            print("✅ Coluna 'foto_path' adicionada com sucesso!")
            print("   - Todos os itens começam com foto_path = NULL (sem foto)")
            print("   - Use o formulário de edição para adicionar fotos aos itens")
            return 0

        except Exception as e:
            db.session.rollback()
            print(f"❌ Erro ao adicionar coluna: {e}")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
