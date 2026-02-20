"""Script para adicionar coluna active_session_id na tabela usuarios."""
import sys
import os

# Adicionar o diretório raiz ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from galint_flask import create_app
from galint_flask.extensions import db

def add_active_session_column():
    app = create_app()
    with app.app_context():
        try:
            # Verificar se a coluna já existe
            result = db.session.execute(db.text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='usuarios' AND column_name='active_session_id'
            """))
            
            if result.fetchone():
                print("✓ Coluna active_session_id já existe na tabela usuarios")
                return
            
            # Adicionar a coluna
            db.session.execute(db.text("""
                ALTER TABLE usuarios 
                ADD COLUMN active_session_id VARCHAR
            """))
            db.session.commit()
            print("✓ Coluna active_session_id adicionada com sucesso à tabela usuarios")
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Erro ao adicionar coluna: {e}")
            raise

if __name__ == '__main__':
    add_active_session_column()
