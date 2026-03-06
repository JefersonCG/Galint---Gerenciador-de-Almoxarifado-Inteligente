"""Testa conexão PostgreSQL com diferentes senhas."""
import psycopg2

passwords = ["3384", "33840542"]
connection_params = {
    "host": "localhost",
    "port": 5432,
    "database": "galint_db",
    "user": "postgres"
}

print("Testando conexões ao PostgreSQL...")
print(f"Host: {connection_params['host']}")
print(f"Database: {connection_params['database']}")
print(f"User: {connection_params['user']}")
print("-" * 50)

for password in passwords:
    try:
        print(f"\nTestando senha: {password}")
        conn = psycopg2.connect(**connection_params, password=password)
        print(f"✅ SUCESSO! Senha '{password}' funciona!")
        conn.close()
        print(f"\nURL correta: postgresql://postgres:{password}@localhost:5432/galint_db")
        break
    except psycopg2.OperationalError as e:
        print(f"❌ Falhou com senha '{password}'")
        print(f"   Erro: {e}")
    except Exception as e:
        print(f"❌ Erro inesperado com senha '{password}': {e}")
else:
    print("\n❌ Nenhuma das senhas funcionou")
