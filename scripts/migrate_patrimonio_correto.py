#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MIGRAÇÃO: SISTEMA DE CÓDIGO PATRIMONIAL CORRETO
================================================
Remove codigo_patrimonial da tabela itens e cria tabela patrimonio_ferramentas
com relacionamento 1-para-muitos correto.

Arquitetura:
- 1 Item pode ter MÚLTIPLOS códigos patrimoniais
- Cada código patrimonial = 1 unidade física da ferramenta
- Exemplo: 20 furadeiras Bosch = 20 códigos patrimoniais (PAT-001 a PAT-020)
"""

import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from galint_flask import create_app
from galint_flask.extensions import db

def migrate_patrimonio_sistema():
    """
    Executa migração do sistema patrimonial
    """
    app = create_app()
    
    with app.app_context():
        try:
            print("\n" + "="*80)
            print("MIGRAÇÃO: SISTEMA PATRIMONIAL CORRETO (1-para-muitos)")
            print("="*80 + "\n")
            
            # Detecta o dialeto do banco
            dialect = db.engine.dialect.name
            print(f"🔍 Banco de dados detectado: {dialect.upper()}\n")
            
            # ============================================================
            # PASSO 1: Backup de dados existentes (se houver)
            # ============================================================
            print("[1/4] Verificando dados existentes no campo codigo_patrimonial...")
            
            # Verifica se existe o campo codigo_patrimonial
            inspector = db.inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('itens')]
            
            dados_backup = []
            if 'codigo_patrimonial' in columns:
                result = db.session.execute(db.text("""
                    SELECT codigo_item, codigo_patrimonial 
                    FROM itens 
                    WHERE codigo_patrimonial IS NOT NULL
                """))
                dados_backup = result.fetchall()
                
                if dados_backup:
                    print(f"   ⚠️  Encontrados {len(dados_backup)} itens com código patrimonial")
                    print("   📋 Esses dados serão migrados para a nova tabela")
                else:
                    print("   ✓ Nenhum dado existente no campo codigo_patrimonial")
            else:
                print("   ℹ️  Campo codigo_patrimonial não existe ainda")
            
            # ============================================================
            # PASSO 2: Remover campo codigo_patrimonial da tabela itens
            # ============================================================
            print("\n[2/4] Removendo campo codigo_patrimonial da tabela itens...")
            
            if 'codigo_patrimonial' in columns:
                # Remove índice primeiro (se existir)
                if dialect == 'postgresql':
                    try:
                        db.session.execute(db.text("""
                            DROP INDEX IF EXISTS idx_itens_codigo_patrimonial;
                        """))
                        print("   ✓ Índice idx_itens_codigo_patrimonial removido")
                    except Exception as e:
                        print(f"   ⚠️  Aviso ao remover índice: {e}")
                
                # Remove coluna
                if dialect == 'postgresql':
                    db.session.execute(db.text("""
                        ALTER TABLE itens DROP COLUMN IF EXISTS codigo_patrimonial;
                    """))
                elif dialect == 'sqlite':
                    # SQLite não suporta DROP COLUMN diretamente
                    # Precisamos recriar a tabela (complexo, vamos apenas avisar)
                    print("   ⚠️  SQLite detectado: campo será mantido mas não usado")
                    print("   ℹ️  Para remover completamente, faça backup/restore do banco")
                else:
                    db.session.execute(db.text("""
                        ALTER TABLE itens DROP COLUMN codigo_patrimonial;
                    """))
                
                db.session.commit()
                print("   [OK] Campo codigo_patrimonial removido/desabilitado")
            else:
                print("   ℹ️  Campo não existia, nada a remover")
            
            # ============================================================
            # PASSO 3: Criar tabela patrimonio_ferramentas
            # ============================================================
            print("\n[3/4] Criando tabela patrimonio_ferramentas...")
            
            # Verificar se tabela já existe
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            if 'patrimonio_ferramentas' in existing_tables:
                print("   ℹ️  Tabela patrimonio_ferramentas já existe")
            else:
                if dialect == 'sqlite':
                    db.session.execute(db.text("""
                        CREATE TABLE IF NOT EXISTS patrimonio_ferramentas (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            codigo_patrimonial VARCHAR(100) NOT NULL UNIQUE,
                            codigo_item VARCHAR(50) NOT NULL,
                            status VARCHAR(20) DEFAULT 'disponivel',
                            matricula VARCHAR(20),
                            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            observacao TEXT,
                            FOREIGN KEY (codigo_item) REFERENCES itens(codigo_item),
                            CHECK (status IN ('disponivel', 'em_uso', 'manutencao', 'baixado'))
                        )
                    """))
                else:
                    # PostgreSQL
                    db.session.execute(db.text("""
                        CREATE TABLE IF NOT EXISTS patrimonio_ferramentas (
                            id SERIAL PRIMARY KEY,
                            codigo_patrimonial VARCHAR(100) NOT NULL UNIQUE,
                            codigo_item VARCHAR(50) NOT NULL,
                            status VARCHAR(20) DEFAULT 'disponivel',
                            matricula VARCHAR(20),
                            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            observacao TEXT,
                            FOREIGN KEY (codigo_item) REFERENCES itens(codigo_item) ON DELETE CASCADE,
                            CHECK (status IN ('disponivel', 'em_uso', 'manutencao', 'baixado'))
                        )
                    """))
                
                db.session.commit()
                print("   [OK] Tabela patrimonio_ferramentas criada")
            
            # ============================================================
            # PASSO 4: Criar índices de performance
            # ============================================================
            print("\n[4/4] Criando índices de performance...")
            
            indices = [
                "CREATE INDEX IF NOT EXISTS idx_patrimonio_codigo_item ON patrimonio_ferramentas(codigo_item)",
                "CREATE INDEX IF NOT EXISTS idx_patrimonio_status ON patrimonio_ferramentas(status)",
                "CREATE INDEX IF NOT EXISTS idx_patrimonio_matricula ON patrimonio_ferramentas(matricula)",
                "CREATE INDEX IF NOT EXISTS idx_patrimonio_codigo ON patrimonio_ferramentas(codigo_patrimonial)"
            ]
            
            for idx in indices:
                db.session.execute(db.text(idx))
            
            db.session.commit()
            print("   [OK] Índices criados")
            
            # ============================================================
            # MIGRAR DADOS ANTIGOS (se houver)
            # ============================================================
            if dados_backup:
                print("\n[MIGRAÇÃO] Transferindo dados antigos para nova estrutura...")
                
                for codigo_item, codigo_pat in dados_backup:
                    db.session.execute(db.text("""
                        INSERT INTO patrimonio_ferramentas 
                        (codigo_patrimonial, codigo_item, status)
                        VALUES (:cod_pat, :cod_item, 'disponivel')
                    """), {
                        'cod_pat': codigo_pat,
                        'cod_item': codigo_item
                    })
                
                db.session.commit()
                print(f"   [OK] {len(dados_backup)} códigos patrimoniais migrados")
            
            # ============================================================
            # RESUMO FINAL
            # ============================================================
            print("\n" + "="*80)
            print("✅ MIGRAÇÃO CONCLUÍDA COM SUCESSO!")
            print("="*80)
            print("\nNOVA ESTRUTURA:")
            print("  • Tabela: patrimonio_ferramentas")
            print("  • Relacionamento: 1 item → MÚLTIPLOS códigos patrimoniais")
            print("  • Status: disponivel | em_uso | manutencao | baixado")
            print("\nEXEMPLO DE USO:")
            print("  20 furadeiras Bosch (mesmo código) = 20 códigos patrimoniais")
            print("  PAT-001, PAT-002, ..., PAT-020")
            print("\nPRÓXIMOS PASSOS:")
            print("  1. Atualizar models.py (adicionar modelo PatrimonioFerramenta)")
            print("  2. Criar serviço de gestão patrimonial")
            print("  3. Atualizar interfaces (cadastro e saída)")
            print("="*80 + "\n")
            
        except Exception as e:
            print(f"\n❌ ERRO durante migração: {e}")
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return False
    
    return True


if __name__ == '__main__':
    success = migrate_patrimonio_sistema()
    sys.exit(0 if success else 1)
