"""
Script para aplicar a migração da tabela equipamentos_reparo.

Execute este script para criar a tabela equipamentos_reparo no banco de dados.
"""
import os
import sys

# Adicionar o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from galint_flask import create_app
from galint_flask.extensions import db


def aplicar_migracao():
    """Aplica a migração para criar a tabela equipamentos_reparo."""
    app = create_app()
    
    with app.app_context():
        # Ler o arquivo SQL de migração
        migration_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "migrations",
            "add_equipamentos_reparo.sql"
        )
        
        if not os.path.exists(migration_path):
            print(f"❌ Arquivo de migração não encontrado: {migration_path}")
            return False
        
        with open(migration_path, 'r', encoding='utf-8') as f:
            sql = f.read()
        
        try:
            # Executar SQL
            db.session.execute(db.text(sql))
            db.session.commit()
            print("✅ Migração aplicada com sucesso!")
            print("   Tabela 'equipamentos_reparo' criada.")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"❌ Erro ao aplicar migração: {e}")
            return False


if __name__ == "__main__":
    print("=" * 60)
    print("MIGRAÇÃO: Criar tabela equipamentos_reparo")
    print("=" * 60)
    sucesso = aplicar_migracao()
    sys.exit(0 if sucesso else 1)
