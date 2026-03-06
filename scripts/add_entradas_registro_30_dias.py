"""Script para adicionar tabela de controle de ciclos de 30 dias de entradas."""
import os
import sys

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Desabilitar serviços em background
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import EntradaRegistro30Dias
from datetime import datetime

def add_entradas_registro_30_dias_table():
    """Adiciona a tabela entradas_registro_30_dias ao banco."""
    app = create_app()
    
    with app.app_context():
        print("🔧 Criando tabela entradas_registro_30_dias...")
        
        # SQL para criar a tabela
        dialect = db.engine.dialect.name
        if dialect == "postgresql":
            sql_create = """
            CREATE TABLE IF NOT EXISTS entradas_registro_30_dias (
                id SERIAL PRIMARY KEY,
                data_inicio TIMESTAMP NOT NULL,
                data_fim TIMESTAMP,
                pdf_gerado BOOLEAN DEFAULT FALSE,
                pdf_caminho TEXT,
                pdf_nome_arquivo TEXT,
                data_geracao_pdf TIMESTAMP,
                ativo BOOLEAN DEFAULT TRUE,
                data_criacao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        else:
            sql_create = """
            CREATE TABLE IF NOT EXISTS entradas_registro_30_dias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_inicio DATETIME NOT NULL,
                data_fim DATETIME,
                pdf_gerado INTEGER DEFAULT 0,
                pdf_caminho TEXT,
                pdf_nome_arquivo TEXT,
                data_geracao_pdf DATETIME,
                ativo INTEGER DEFAULT 1,
                data_criacao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        
        try:
            # Cria a tabela
            db.session.execute(db.text(sql_create))
            db.session.commit()
            print("✅ Tabela 'entradas_registro_30_dias' criada com sucesso!")
            
            # Verifica se já existe um ciclo ativo
            existing_cycle = db.session.query(EntradaRegistro30Dias).filter(EntradaRegistro30Dias.ativo.is_(True)).first()
            
            if not existing_cycle:
                # Cria ciclo inicial
                new_cycle = EntradaRegistro30Dias(
                    data_inicio=datetime.utcnow(),
                    ativo=True
                )
                db.session.add(new_cycle)
                db.session.commit()
                print(f"✅ Ciclo inicial criado (ID: {new_cycle.id})")
            else:
                print(f"ℹ️  Ciclo ativo já existe (ID: {existing_cycle.id})")
                
        except Exception as e:
            db.session.rollback()
            print(f"❌ Erro ao criar tabela: {e}")
            return False
        
        return True

if __name__ == '__main__':
    success = add_entradas_registro_30_dias_table()
    sys.exit(0 if success else 1)
