#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MIGRAÇÃO: SISTEMA DE CÓDIGO PATRIMONIAL 
========================================
Cria tabela patrimonio_ferramentas para relacionamento 1-para-muitos.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from galint_flask import create_app
from galint_flask.extensions import db

def migrate_patrimonio():
    """Executa migração do sistema patrimonial"""
    app = create_app()
    
    with app.app_context():
        try:
            print("\n" + "="*60)
            print("MIGRAÇÃO: SISTEMA PATRIMONIAL")
            print("="*60 + "\n")
            
            dialect = db.engine.dialect.name
            print(f"Banco de dados: {dialect.upper()}\n")
            
            # Verificar se tabela já existe
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            if 'patrimonio_ferramentas' in existing_tables:
                print("✓ Tabela patrimonio_ferramentas já existe!")
                print("  Nada a fazer.\n")
                return True
            
            # Criar tabela
            print("[1/2] Criando tabela patrimonio_ferramentas...")
            
            if dialect == 'sqlite':
                sql = """
                    CREATE TABLE patrimonio_ferramentas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        codigo_patrimonial VARCHAR(100) NOT NULL UNIQUE,
                        codigo_item VARCHAR(50) NOT NULL,
                        status VARCHAR(20) DEFAULT 'disponivel',
                        matricula VARCHAR(20),
                        data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        observacao TEXT,
                        FOREIGN KEY (codigo_item) REFERENCES itens(codigo_item)
                    )
                """
            else:
                # PostgreSQL
                sql = """
                    CREATE TABLE patrimonio_ferramentas (
                        id SERIAL PRIMARY KEY,
                        codigo_patrimonial VARCHAR(100) NOT NULL UNIQUE,
                        codigo_item VARCHAR(50) NOT NULL,
                        status VARCHAR(20) DEFAULT 'disponivel',
                        matricula VARCHAR(20),
                        data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        observacao TEXT,
                        FOREIGN KEY (codigo_item) REFERENCES itens(codigo_item) ON DELETE CASCADE
                    )
                """
            
            db.session.execute(db.text(sql))
            db.session.commit()
            print("   [OK] Tabela criada")
            
            # Criar índices
            print("\n[2/2] Criando índices...")
            
            indices = [
                "CREATE INDEX idx_patrimonio_codigo_item ON patrimonio_ferramentas(codigo_item)",
                "CREATE INDEX idx_patrimonio_status ON patrimonio_ferramentas(status)",
                "CREATE INDEX idx_patrimonio_matricula ON patrimonio_ferramentas(matricula)"
            ]
            
            for idx in indices:
                try:
                    db.session.execute(db.text(idx))
                except Exception as e:
                    print(f"   Aviso: {e}")
            
            db.session.commit()
            print("   [OK] Índices criados")
            
            print("\n" + "="*60)
            print("✅ MIGRAÇÃO CONCLUÍDA COM SUCESSO!")
            print("="*60 + "\n")
            
            return True
            
        except Exception as e:
            print(f"\n❌ ERRO: {e}")
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return False


if __name__ == '__main__':
    success = migrate_patrimonio()
    sys.exit(0 if success else 1)
