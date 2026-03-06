"""Verifica qual DATABASE_URI está sendo usada."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Simular o carregamento do .env como o Flask faz
cwd = Path.cwd()
candidates = [cwd.parent.parent / ".env", cwd.parent / ".env", cwd / ".env"]

print("Procurando arquivos .env:")
for p in candidates:
    if p.exists():
        print(f"  ✅ {p}")
        load_dotenv(p, override=True)
    else:
        print(f"  ❌ {p} (não existe)")

load_dotenv(override=True)

print("\nVariáveis de ambiente após carregar .env:")
print(f"GALINT_DATABASE_URI: {os.environ.get('GALINT_DATABASE_URI', 'NÃO DEFINIDA')}")
print(f"DATABASE_URL: {os.environ.get('DATABASE_URL', 'NÃO DEFINIDA')}")

# Verificar o conteúdo do arquivo .env local
env_local = cwd / ".env"
if env_local.exists():
    print(f"\nConteúdo do {env_local}:")
    with open(env_local, 'r', encoding='utf-8') as f:
        for line in f:
            if 'DATABASE' in line or 'POSTGRES' in line:
                print(f"  {line.rstrip()}")
