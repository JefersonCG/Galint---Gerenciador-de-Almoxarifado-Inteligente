"""Script para adicionar colunas numero_serie e modelo à tabela itens"""
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from galint_flask import create_app
from galint_flask.extensions import db

app = create_app()

def main():
    with app.app_context():
        print("Adicionando colunas numero_serie e modelo...")
        
        try:
            # Verificar se colunas já existem
            result = db.session.execute(db.text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='itens' 
                AND column_name IN ('numero_serie', 'modelo')
            """))
            existing = [row[0] for row in result]
            
            if 'numero_serie' in existing and 'modelo' in existing:
                print("Colunas ja existem!")
                return
            
            if 'numero_serie' not in existing:
                print("Adicionando coluna numero_serie...")
                db.session.execute(db.text("""
                    ALTER TABLE itens ADD COLUMN numero_serie VARCHAR
                """))
            
            if 'modelo' not in existing:
                print("Adicionando coluna modelo...")
                db.session.execute(db.text("""
                    ALTER TABLE itens ADD COLUMN modelo VARCHAR
                """))
            
            db.session.commit()
            print("Colunas adicionadas com sucesso!")
            
        except Exception as e:
            print(f"Erro: {e}")
            db.session.rollback()

if __name__ == "__main__":
    main()
