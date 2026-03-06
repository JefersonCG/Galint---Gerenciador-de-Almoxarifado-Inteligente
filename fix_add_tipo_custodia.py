"""Adiciona coluna tipo_custodia se não existir."""
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
    
    # Verificar se a coluna existe
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='saidas' AND column_name='tipo_custodia'
    """)
    
    if cur.fetchone() is None:
        print("❌ Coluna 'tipo_custodia' não existe. Adicionando...")
        
        # Adicionar a coluna
        cur.execute("""
            ALTER TABLE saidas 
            ADD COLUMN tipo_custodia VARCHAR(20) DEFAULT 'temporaria'
        """)
        
        # Atualizar valores NULL (se houver)
        cur.execute("""
            UPDATE saidas 
            SET tipo_custodia = 'temporaria' 
            WHERE tipo_custodia IS NULL
        """)
        
        conn.commit()
        print("✅ Coluna 'tipo_custodia' adicionada com sucesso!")
    else:
        print("✅ Coluna 'tipo_custodia' já existe.")
        
        # Verificar se há valores NULL
        cur.execute("SELECT COUNT(*) FROM saidas WHERE tipo_custodia IS NULL")
        null_count = cur.fetchone()[0]
        
        if null_count > 0:
            print(f"⚠️  Encontrados {null_count} registros com tipo_custodia NULL. Corrigindo...")
            cur.execute("""
                UPDATE saidas 
                SET tipo_custodia = 'temporaria' 
                WHERE tipo_custodia IS NULL
            """)
            conn.commit()
            print("✅ Valores NULL corrigidos!")
        else:
            print("✅ Não há valores NULL em tipo_custodia.")
    
    cur.close()
    
except Exception as e:
    print(f"❌ Erro: {e}")
    conn.rollback()
finally:
    conn.close()
