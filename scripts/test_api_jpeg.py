"""Teste do endpoint JPEG via API Mobile."""
import requests
import json

# Configuração
API_URL = "http://localhost:5000/api/mobile"
MATRICULA = "admin"  # Ajuste conforme necessário
SENHA = "admin"  # Ajuste conforme necessário

def test_jpeg_endpoint():
    print("="*60)
    print("🧪 TESTE: Endpoint JPEG da API Mobile")
    print("="*60)
    
    # 1. Login para obter token
    print("\n🔐 1. Fazendo login...")
    login_response = requests.post(
        f"{API_URL}/login",
        json={"matricula": MATRICULA, "senha": SENHA},
        timeout=10
    )
    
    if login_response.status_code != 200:
        print(f"❌ Erro no login: {login_response.status_code}")
        print(login_response.text)
        return
    
    response_data = login_response.json()
    token = response_data.get("data", {}).get("token")
    if not token:
        print(f"❌ Token não encontrado na resposta:")
        print(json.dumps(response_data, indent=2))
        return
    
    print(f"✅ Token obtido: {token[:20]}...")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Testar endpoint JPEG
    print("\n📥 2. Solicitando relatório em JPEG...")
    jpeg_response = requests.get(
        f"{API_URL}/reports/daily",
        params={"format": "jpeg", "scope": "all"},
        headers=headers,
        timeout=30
    )
    
    if jpeg_response.status_code != 200:
        print(f"❌ Erro ao gerar JPEG: {jpeg_response.status_code}")
        print(jpeg_response.text)
        return
    
    # 3. Salvar arquivo
    output_file = "test_api_report.jpeg"
    with open(output_file, "wb") as f:
        f.write(jpeg_response.content)
    
    print(f"✅ JPEG recebido: {len(jpeg_response.content)} bytes")
    print(f"   Content-Type: {jpeg_response.headers.get('Content-Type')}")
    print(f"   Arquivo salvo: {output_file}")
    
    # 4. Validar imagem
    print("\n🔍 3. Validando imagem...")
    try:
        from PIL import Image
        img = Image.open(output_file)
        print(f"✅ Imagem válida:")
        print(f"   Dimensões: {img.width}x{img.height} pixels")
        print(f"   Formato: {img.format}")
        print(f"   Modo: {img.mode}")
    except Exception as e:
        print(f"❌ Erro ao validar: {e}")
        return
    
    print("\n" + "="*60)
    print("✅ TESTE CONCLUÍDO COM SUCESSO!")
    print("="*60)
    print(f"\n📱 Para testar no APK, use:")
    print(f"   URL: {API_URL}/reports/daily?format=jpeg&scope=all")
    print(f"   Header: Authorization: Bearer {{token}}")

if __name__ == "__main__":
    try:
        test_jpeg_endpoint()
    except requests.exceptions.ConnectionError:
        print("❌ Erro: Servidor não está rodando!")
        print("   Execute: python app.py")
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
