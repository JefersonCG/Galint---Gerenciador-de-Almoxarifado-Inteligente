"""Script para aplicar migração: adicionar contexto operacional estruturado na tabela saidas."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from galint_flask import create_app
from galint_flask.extensions import db


def aplicar_migracao():
    """Adiciona atividade_operacional, ordem_servico e centro_custo em saidas."""
    app = create_app()

    with app.app_context():
        print("=" * 60)
        print("  GALINT - Migração: Contexto operacional em saídas")
        print("=" * 60)

        statements = [
            "ALTER TABLE saidas ADD COLUMN IF NOT EXISTS atividade_operacional VARCHAR(64)",
            "ALTER TABLE saidas ADD COLUMN IF NOT EXISTS ordem_servico VARCHAR(120)",
            "ALTER TABLE saidas ADD COLUMN IF NOT EXISTS centro_custo VARCHAR(120)",
        ]

        try:
            for statement in statements:
                print(f"[EXEC] {statement}")
                db.session.execute(db.text(statement))

            db.session.commit()
            print("[OK] Migracao aplicada com sucesso!")

            result = db.session.execute(
                db.text(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = 'saidas'
                      AND column_name IN ('atividade_operacional', 'ordem_servico', 'centro_custo')
                    ORDER BY column_name
                    """
                )
            )
            rows = result.fetchall()
            for row in rows:
                print(f"[OK] Coluna disponivel: {row[0]} ({row[1]})")

            return True
        except Exception as exc:
            print(f"[ERRO] Erro ao aplicar migracao: {exc}")
            db.session.rollback()
            return False


if __name__ == "__main__":
    success = aplicar_migracao()
    if not success:
        sys.exit(1)