"""Adiciona colunas faltantes na tabela itens."""
import psycopg2

# Conectar ao banco
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="galint_db",
    user="postgres",
    password="3384"
)

try:
    cur = conn.cursor()
    
    # Lista de colunas esperadas do modelo Item
    columns_to_check = {
        'litros_por_embalagem': 'DOUBLE PRECISION',
        'tipo_embalagem_novo': 'VARCHAR(20)',
        'unidades_por_embalagem': 'DOUBLE PRECISION',
        'estoque_embalagens': 'DOUBLE PRECISION DEFAULT 0',
        'estoque_unidades_soltas': 'DOUBLE PRECISION DEFAULT 0',
        'foto_path': 'VARCHAR(255)',
        'ultima_edicao_em': 'TIMESTAMP',
        'ultima_edicao_por': 'VARCHAR(100)',
        'voltagem': 'VARCHAR(50)',
        'amperagem': 'VARCHAR(50)',
        'local_instalacao': 'VARCHAR(255)',
    }
    
    print("=" * 60)
    print("Verificando colunas na tabela 'itens'")
    print("=" * 60)
    
    # Verificar quais colunas existem
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='itens'
    """)
    existing_columns = {row[0] for row in cur.fetchall()}
    
    print(f"\nColunas existentes: {len(existing_columns)}")
    
    # Adicionar colunas faltantes
    added_count = 0
    for col_name, col_type in columns_to_check.items():
        if col_name not in existing_columns:
            print(f"\n❌ Coluna '{col_name}' não existe. Adicionando...")
            
            try:
                sql = f"ALTER TABLE itens ADD COLUMN {col_name} {col_type}"
                cur.execute(sql)
                conn.commit()
                print(f"✅ Coluna '{col_name}' adicionada com sucesso!")
                added_count += 1
            except Exception as e:
                print(f"❌ Erro ao adicionar '{col_name}': {e}")
                conn.rollback()
        else:
            print(f"✅ Coluna '{col_name}' já existe.")
    
    # Verificar tipos de dados das colunas existentes
    print(f"\n{'='*60}")
    print("Verificando tipos de dados...")
    print(f"{'='*60}")
    
    cur.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns 
        WHERE table_name='itens' 
        AND column_name IN ('litros_por_embalagem', 'tipo_embalagem_novo', 'unidades_por_embalagem', 
                    'estoque_embalagens', 'estoque_unidades_soltas', 'foto_path',
                    'ultima_edicao_em', 'ultima_edicao_por', 'voltagem', 'amperagem',
                    'local_instalacao')
        ORDER BY column_name
    """)
    
    for row in cur.fetchall():
        col_name, data_type, is_nullable, default = row
        print(f"\n{col_name}:")
        print(f"  Tipo: {data_type}")
        print(f"  Nullable: {is_nullable}")
        print(f"  Default: {default or 'None'}")
    
    print(f"\n{'='*60}")
    print(f"Resumo: {added_count} coluna(s) adicionada(s)")
    print(f"{'='*60}")
    
    cur.close()
    
except Exception as e:
    print(f"❌ Erro geral: {e}")
    conn.rollback()
finally:
    conn.close()

print("\n✅ Script concluído!")
