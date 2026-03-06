"""
Script para corrigir valores NULL no campo tipo_custodia da tabela saidas.
"""
import os
import psycopg2
from urllib.parse import urlparse

# Obter DATABASE_URL do ambiente (mesma lógica do config.py)
database_url = os.environ.get('GALINT_DATABASE_URI') or os.environ.get('DATABASE_URL')

if not database_url:
    print("❌ Banco de dados não configurado!")
    print("Execute: set GALINT_DATABASE_URI=postgresql://usuario:senha@host:5432/galint")
    exit(1)

# Parse URL
url = urlparse(database_url)

# Conectar ao banco
conn = psycopg2.connect(
    host=url.hostname,
    port=url.port or 5432,
    user=url.username,
    password=url.password,
    database=url.path[1:]  # Remove barra inicial
)

cur = conn.cursor()

# Verificar quantos registros têm tipo_custodia NULL
cur.execute("SELECT COUNT(*) FROM saidas WHERE tipo_custodia IS NULL")
count_null = cur.fetchone()[0]

print(f"Registros com tipo_custodia NULL: {count_null}")

if count_null > 0:
    # Atualizar para 'temporaria'
    cur.execute("UPDATE saidas SET tipo_custodia = 'temporaria' WHERE tipo_custodia IS NULL")
    conn.commit()
    print(f"✓ {count_null} registros atualizados para 'temporaria'")
else:
    print("✓ Nenhum registro com NULL encontrado")

# Verificar distribuição de tipos
cur.execute("SELECT tipo_custodia, COUNT(*) FROM saidas GROUP BY tipo_custodia")
print("\nDistribuição de tipos de custódia:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} registros")

cur.close()
conn.close()
print("\n✓ Concluído!")
