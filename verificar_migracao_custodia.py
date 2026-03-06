"""Script para verificar se a migração tipo_custodia foi aplicada."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from galint_flask import create_app
from galint_flask.extensions import db

def verificar_migracao():
    """Verifica se a migração foi aplicada corretamente."""
    app = create_app()
    
    with app.app_context():
        print("🔍 Verificando migração tipo_custodia...")
        print()
        
        try:
            # Verificar coluna
            result = db.session.execute(db.text("""
                SELECT column_name, data_type, column_default, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'saidas' AND column_name = 'tipo_custodia'
            """))
            
            row = result.fetchone()
            if row:
                print("✅ Coluna 'tipo_custodia' encontrada:")
                print(f"   - Nome: {row[0]}")
                print(f"   - Tipo: {row[1]}")
                print(f"   - Padrão: {row[2]}")
                print(f"   - Nullable: {row[3]}")
                print()
            else:
                print("❌ Coluna 'tipo_custodia' NÃO encontrada!")
                return False
            
            # Verificar constraint
            result = db.session.execute(db.text("""
                SELECT constraint_name, constraint_type
                FROM information_schema.table_constraints
                WHERE table_name = 'saidas' AND constraint_name = 'check_tipo_custodia'
            """))
            
            row = result.fetchone()
            if row:
                print("✅ Constraint 'check_tipo_custodia' encontrada:")
                print(f"   - Nome: {row[0]}")
                print(f"   - Tipo: {row[1]}")
                print()
            else:
                print("⚠️  Constraint 'check_tipo_custodia' não encontrada")
                print()
            
            # Verificar índice
            result = db.session.execute(db.text("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'saidas' AND indexname = 'idx_saidas_tipo_custodia'
            """))
            
            row = result.fetchone()
            if row:
                print(f"✅ Índice '{row[0]}' encontrado")
                print()
            else:
                print("⚠️  Índice 'idx_saidas_tipo_custodia' não encontrado")
                print()
            
            # Contar registros por tipo
            result = db.session.execute(db.text("""
                SELECT tipo_custodia, COUNT(*) as total
                FROM saidas
                GROUP BY tipo_custodia
                ORDER BY tipo_custodia
            """))
            
            print("📊 Distribuição de registros por tipo de custódia:")
            rows = result.fetchall()
            if rows:
                for row in rows:
                    print(f"   - {row[0]}: {row[1]} registros")
            else:
                print("   Nenhum registro encontrado")
            print()
            
            # Total geral
            result = db.session.execute(db.text("SELECT COUNT(*) FROM saidas"))
            total = result.scalar()
            print(f"📊 Total de registros na tabela saidas: {total}")
            
            return True
            
        except Exception as e:
            print(f"❌ Erro ao verificar migração: {e}")
            return False

if __name__ == "__main__":
    print("=" * 70)
    print("  GALINT - Verificação: Migração tipo_custodia")
    print("=" * 70)
    print()
    
    sucesso = verificar_migracao()
    
    print()
    print("=" * 70)
    if sucesso:
        print("✅ Migração está aplicada e funcionando corretamente!")
    else:
        print("❌ Problemas encontrados na migração.")
        sys.exit(1)
    print("=" * 70)
