"""Servidor HTTPS usando Werkzeug adhoc SSL."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from galint_flask import create_app

app = create_app()

if __name__ == "__main__":
    print("="*60)
    print("🔒 SERVIDOR HTTPS (adhoc SSL)")
    print("="*60)
    print("🚀 Iniciando servidor HTTPS...")
    print(f"   URL: https://127.0.0.1:5443")
    print(f"   URL: https://10.0.0.245:5443")
    print("\n⚠️  Usando certificado adhoc (temporário)")
    print("Pressione Ctrl+C para parar.\n")
    
    try:
        # Usar adhoc SSL (gera certificado temporário automaticamente)
        app.run(
            host="0.0.0.0",
            port=5443,
            debug=False,
            ssl_context='adhoc',
            use_reloader=False,
            threaded=True
        )
    except ImportError as e:
        print("\n❌ ERRO: pyOpenSSL não instalado!")
        print("Execute: pip install pyOpenSSL")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
