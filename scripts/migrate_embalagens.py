"""
Migration: Adiciona campos para sistema de embalagens.

Adiciona:
- tipo_embalagem: lata, rolo, pacote, caixa, litro, balde, nenhum
- unidades_por_embalagem: quantas unidades tem em cada embalagem
- estoque_embalagens: quantidade de embalagens fechadas
- estoque_unidades_soltas: unidades de embalagem aberta
"""
import sys
from pathlib import Path

# Adiciona diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from galint_flask import create_app
from galint_flask.extensions import db

def migrate():
    app = create_app()
    
    with app.app_context():
        engine = db.engine
        
        # Verifica se as colunas já existem
        inspector = db.inspect(engine)
        existing_columns = [col['name'] for col in inspector.get_columns('itens')]
        
        with engine.begin() as conn:
            # Adiciona tipo_embalagem_novo
            if 'tipo_embalagem_novo' not in existing_columns:
                print("Adicionando coluna tipo_embalagem_novo...")
                conn.execute(db.text("""
                    ALTER TABLE itens 
                    ADD COLUMN tipo_embalagem_novo VARCHAR(20)
                """))
                print("✓ Coluna tipo_embalagem_novo adicionada")
            
            # Adiciona unidades_por_embalagem
            if 'unidades_por_embalagem' not in existing_columns:
                print("Adicionando coluna unidades_por_embalagem...")
                conn.execute(db.text("""
                    ALTER TABLE itens 
                    ADD COLUMN unidades_por_embalagem DECIMAL(15,3)
                """))
                print("✓ Coluna unidades_por_embalagem adicionada")
            
            # Adiciona estoque_embalagens
            if 'estoque_embalagens' not in existing_columns:
                print("Adicionando coluna estoque_embalagens...")
                conn.execute(db.text("""
                    ALTER TABLE itens 
                    ADD COLUMN estoque_embalagens DECIMAL(15,3) DEFAULT 0
                """))
                print("✓ Coluna estoque_embalagens adicionada")
            
            # Adiciona estoque_unidades_soltas
            if 'estoque_unidades_soltas' not in existing_columns:
                print("Adicionando coluna estoque_unidades_soltas...")
                conn.execute(db.text("""
                    ALTER TABLE itens 
                    ADD COLUMN estoque_unidades_soltas DECIMAL(15,3) DEFAULT 0
                """))
                print("✓ Coluna estoque_unidades_soltas adicionada")
        
        print("\n✅ Migration concluída com sucesso!")
        print("\n📝 Próximos passos:")
        print("1. Reiniciar o servidor Flask")
        print("2. Configurar tipo de embalagem nos itens desejados")
        print("3. Sistema automaticamente gerenciará embalagens vs unidades")

if __name__ == "__main__":
    migrate()
