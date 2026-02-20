"""Script para adicionar sistema de código patrimonial/interno para ferramentas."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

from galint_flask import create_app
from galint_flask.extensions import db

def add_patrimonio_fields():
    """Adiciona campos de código patrimonial e tabela de controle."""
    app = create_app()
    
    with app.app_context():
        print("=" * 70)
        print("ADICIONANDO SISTEMA DE CÓDIGO PATRIMONIAL")
        print("=" * 70)
        print()
        
        dialect = db.engine.dialect.name
        
        try:
            # 1. Adicionar campo codigo_patrimonial na tabela itens
            print("[1/3] Adicionando campo codigo_patrimonial na tabela itens...")
            
            if dialect == "postgresql":
                sql_add_field = """
                ALTER TABLE itens 
                ADD COLUMN IF NOT EXISTS codigo_patrimonial VARCHAR(100) UNIQUE;
                """
            else:
                sql_add_field = """
                ALTER TABLE itens 
                ADD COLUMN codigo_patrimonial VARCHAR(100) UNIQUE;
                """
            
            try:
                db.session.execute(db.text(sql_add_field))
                db.session.commit()
                print("   [OK] Campo codigo_patrimonial adicionado")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print("   [AVISO] Campo codigo_patrimonial ja existe")
                    db.session.rollback()
                else:
                    raise
            
            # 2. Criar tabela de controle patrimonial (quem está usando o quê)
            print("\n[2/3] Criando tabela ferramentas_em_uso...")
            
            if dialect == "postgresql":
                sql_create_table = """
                CREATE TABLE IF NOT EXISTS ferramentas_em_uso (
                    id SERIAL PRIMARY KEY,
                    codigo_item VARCHAR NOT NULL,
                    codigo_patrimonial VARCHAR(100),
                    matricula VARCHAR NOT NULL,
                    data_retirada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    data_devolucao TIMESTAMP,
                    observacao TEXT,
                    saida_id INTEGER,
                    status VARCHAR(20) DEFAULT 'EM_USO',
                    FOREIGN KEY (codigo_item) REFERENCES itens(codigo_item) ON DELETE CASCADE,
                    FOREIGN KEY (matricula) REFERENCES usuarios(matricula) ON DELETE CASCADE,
                    FOREIGN KEY (saida_id) REFERENCES saidas(id_saida) ON DELETE SET NULL
                );
                
                CREATE INDEX IF NOT EXISTS idx_ferramentas_uso_status ON ferramentas_em_uso(status);
                CREATE INDEX IF NOT EXISTS idx_ferramentas_uso_matricula ON ferramentas_em_uso(matricula);
                CREATE INDEX IF NOT EXISTS idx_ferramentas_uso_patrimonio ON ferramentas_em_uso(codigo_patrimonial);
                """
            else:
                sql_create_table = """
                CREATE TABLE IF NOT EXISTS ferramentas_em_uso (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo_item VARCHAR NOT NULL,
                    codigo_patrimonial VARCHAR(100),
                    matricula VARCHAR NOT NULL,
                    data_retirada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    data_devolucao DATETIME,
                    observacao TEXT,
                    saida_id INTEGER,
                    status VARCHAR(20) DEFAULT 'EM_USO',
                    FOREIGN KEY (codigo_item) REFERENCES itens(codigo_item) ON DELETE CASCADE,
                    FOREIGN KEY (matricula) REFERENCES usuarios(matricula) ON DELETE CASCADE,
                    FOREIGN KEY (saida_id) REFERENCES saidas(id_saida) ON DELETE SET NULL
                );
                
                CREATE INDEX IF NOT EXISTS idx_ferramentas_uso_status ON ferramentas_em_uso(status);
                CREATE INDEX IF NOT EXISTS idx_ferramentas_uso_matricula ON ferramentas_em_uso(matricula);
                CREATE INDEX IF NOT EXISTS idx_ferramentas_uso_patrimonio ON ferramentas_em_uso(codigo_patrimonial);
                """
            
            db.session.execute(db.text(sql_create_table))
            db.session.commit()
            print("   [OK] Tabela ferramentas_em_uso criada")
            
            # 3. Criar índice no campo barcode_image_path para busca rápida
            print("\n[3/3] Adicionando indices de performance...")
            
            if dialect == "postgresql":
                sql_indexes = """
                CREATE INDEX IF NOT EXISTS idx_itens_codigo_patrimonial ON itens(codigo_patrimonial);
                CREATE INDEX IF NOT EXISTS idx_itens_numero_serie ON itens(numero_serie);
                CREATE INDEX IF NOT EXISTS idx_itens_categoria ON itens(categoria);
                """
            else:
                sql_indexes = """
                CREATE INDEX IF NOT EXISTS idx_itens_codigo_patrimonial ON itens(codigo_patrimonial);
                CREATE INDEX IF NOT EXISTS idx_itens_numero_serie ON itens(numero_serie);
                CREATE INDEX IF NOT EXISTS idx_itens_categoria ON itens(categoria);
                """
            
            db.session.execute(db.text(sql_indexes))
            db.session.commit()
            print("   [OK] Indices criados")
            
            print()
            print("=" * 70)
            print("[SUCESSO] SISTEMA DE CODIGO PATRIMONIAL INSTALADO!")
            print("=" * 70)
            print()
            print("Funcionalidades adicionadas:")
            print("  - Campo 'codigo_patrimonial' na tabela itens")
            print("  - Tabela 'ferramentas_em_uso' para controle de uso")
            print("  - Indices de performance para consultas rapidas")
            print()
            return True
            
        except Exception as e:
            print(f"\n[ERRO] Falha ao instalar sistema patrimonial: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            return False

if __name__ == '__main__':
    success = add_patrimonio_fields()
    sys.exit(0 if success else 1)
