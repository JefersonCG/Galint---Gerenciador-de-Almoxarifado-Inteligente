"""Script para aplicar migração: adicionar campo tipo_custodia na tabela saidas."""
import sys
from pathlib import Path

# Adicionar o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from galint_flask import create_app
from galint_flask.extensions import db

def aplicar_migracao():
    """Aplica a migração para adicionar tipo_custodia."""
    app = create_app()
    
    with app.app_context():
        print("🔄 Iniciando migração: adicionar tipo_custodia...")
        
        try:
            # Ler arquivo SQL
            sql_file = Path(__file__).parent / "migrations" / "add_tipo_custodia_saidas.sql"
            
            if not sql_file.exists():
                print(f"❌ Arquivo SQL não encontrado: {sql_file}")
                return False
            
            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_commands = f.read()
            
            # Executar comandos SQL
            print("📝 Executando comandos SQL...")
            
            # Dividir por comandos (remover comentários)
            commands = []
            for line in sql_commands.split('\n'):
                line = line.strip()
                if line and not line.startswith('--'):
                    commands.append(line)
            
            sql_text = ' '.join(commands)
            
            # Executar
            db.session.execute(db.text(sql_text))
            db.session.commit()
            
            print("✅ Migração aplicada com sucesso!")
            
            # Verificar coluna
            result = db.session.execute(db.text("""
                SELECT column_name, data_type, column_default
                FROM information_schema.columns
                WHERE table_name = 'saidas' AND column_name = 'tipo_custodia'
            """))
            
            row = result.fetchone()
            if row:
                print(f"✅ Coluna criada: {row[0]} ({row[1]}) default={row[2]}")
            else:
                print("⚠️  Coluna não encontrada após migração")
            
            # Contar registros
            result = db.session.execute(db.text("SELECT COUNT(*) FROM saidas"))
            count = result.scalar()
            print(f"📊 Total de registros na tabela saidas: {count}")
            
            return True
            
        except Exception as e:
            print(f"❌ Erro ao aplicar migração: {e}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    print("=" * 60)
    print("  GALINT - Migração: Adicionar tipo_custodia")
    print("=" * 60)
    print()
    
    sucesso = aplicar_migracao()
    
    print()
    if sucesso:
        print("✅ Processo concluído com sucesso!")
    else:
        print("❌ Processo concluído com erros.")
        sys.exit(1)
