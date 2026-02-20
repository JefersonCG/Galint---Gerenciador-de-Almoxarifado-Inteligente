"""Gera URL com token para testar JPEG no navegador."""
import requests
import sys

API_URL = "http://localhost:5000/api/mobile"
MATRICULA = "admin"
SENHA = "admin"

print("="*80)
print("🔐 GERANDO URL PARA TESTE NO NAVEGADOR")
print("="*80)

try:
    # Login
    print("\n1. Fazendo login...")
    response = requests.post(
        f"{API_URL}/login",
        json={"matricula": MATRICULA, "senha": SENHA},
        timeout=5
    )
    
    if response.status_code != 200:
        print(f"❌ Erro no login: {response.status_code}")
        print(response.text)
        sys.exit(1)
    
    data = response.json()
    token = data.get("data", {}).get("token")
    
    if not token:
        print("❌ Token não encontrado na resposta")
        sys.exit(1)
    
    print(f"✅ Token obtido: {token[:30]}...")
    
    # Gerar URLs
    print("\n" + "="*80)
    print("📋 COPIE E COLE NO NAVEGADOR:")
    print("="*80)
    
    print("\n🖼️  RELATÓRIO DIÁRIO (JPEG - Todos):")
    print(f"{API_URL}/reports/daily?format=jpeg&scope=all&token={token}")
    
    print("\n📄 RELATÓRIO DIÁRIO (PDF - Todos):")
    print(f"{API_URL}/reports/daily?format=pdf&scope=all&token={token}")
    
    print("\n📊 RELATÓRIO DIÁRIO (XLSX - Todos):")
    print(f"{API_URL}/reports/daily?format=xlsx&scope=all&token={token}")
    
    print("\n🖼️  RELATÓRIO DIÁRIO (JPEG - Materiais):")
    print(f"{API_URL}/reports/daily?format=jpeg&scope=materials&token={token}")
    
    print("\n" + "="*80)
    print("💡 DICA: O token expira em 30 dias")
    print("="*80)
    
except requests.exceptions.ConnectionError:
    print("\n❌ ERRO: Servidor não está rodando!")
    print("Execute: python app.py")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Erro: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
