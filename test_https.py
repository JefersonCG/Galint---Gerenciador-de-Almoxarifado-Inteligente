"""Teste simples de servidor HTTPS Flask."""
import os
import sys

# Adicionar o diretório ao path
sys.path.insert(0, os.path.dirname(__file__))

from galint_flask import create_app

app = create_app()

if __name__ == "__main__":
    cert_path = os.path.join(os.path.dirname(__file__), 'certs', 'cert.pem')
    key_path = os.path.join(os.path.dirname(__file__), 'certs', 'key.pem')
    
    print("="*60)
    print("🔒 TESTE SERVIDOR HTTPS")
    print("="*60)
    print(f"Certificado: {cert_path}")
    print(f"Existe? {os.path.exists(cert_path)}")
    print(f"Chave: {key_path}")
    print(f"Existe? {os.path.exists(key_path)}")
    print("="*60)
    
    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        print("❌ Certificados não encontrados!")
        print("Execute: python generate_cert_python.py")
        sys.exit(1)
    
    try:
        print("\n🚀 Iniciando servidor HTTPS...")
        print(f"   URL: https://127.0.0.1:5443")
        print(f"   URL: https://10.0.0.245:5443")
        print("\nPressione Ctrl+C para parar.\n")
        
        app.run(
            host="0.0.0.0",
            port=5443,
            debug=False,
            ssl_context=(cert_path, key_path),
            use_reloader=False,
            threaded=True
        )
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
