"""Gera URL com token para testar JPEG no navegador."""
import requests
import sys

API_URL = "http://localhost:5000/api/mobile"

print("="*80)
print("GERANDO URL PARA TESTE NO NAVEGADOR")
print("="*80)

try:
    # Login
    print("\nFazendo login...")
    response = requests.post(
        f"{API_URL}/login",
        json={"matricula": "admin", "senha": "admin"},
        timeout=5
    )
    
    if response.status_code != 200:
        print(f"ERRO no login: {response.status_code}")
        sys.exit(1)
    
    token = response.json().get("data", {}).get("token")
    
    if not token:
        print("ERRO: Token nao encontrado")
        sys.exit(1)
    
    print(f"Token obtido com sucesso!")
    
    # Gerar URL
    print("\n" + "="*80)
    print("COPIE A URL ABAIXO E COLE NO NAVEGADOR:")
    print("="*80)
    print(f"\n{API_URL}/reports/daily?format=jpeg&scope=all&token={token}\n")
    print("="*80)
    
except Exception as e:
    print(f"\nERRO: {e}")
    sys.exit(1)
