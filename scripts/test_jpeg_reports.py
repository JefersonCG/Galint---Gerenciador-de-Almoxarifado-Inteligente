"""Teste rápido para validar conversão PDF → JPEG dos relatórios."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from galint_flask import create_app
from galint_flask.services.telegram_service import TelegramService

def test_jpeg_conversion():
    print("="*60)
    print("🧪 TESTE: Conversão PDF → JPEG de Relatórios")
    print("="*60)
    
    app = create_app()
    with app.app_context():
        reports_dir = Path("instance") / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        # Teste 1: Gerar PDF do relatório diário
        print("\n📄 1. Gerando PDF do relatório diário...")
        pdf_path = reports_dir / "test_daily_report.pdf"
        try:
            TelegramService.generate_saidas_dia_pdf(str(pdf_path), scope="all")
            print(f"✅ PDF gerado: {pdf_path.stat().st_size} bytes")
        except Exception as e:
            print(f"❌ Erro ao gerar PDF: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # Teste 2: Converter PDF para JPEG
        print("\n🖼️  2. Convertendo PDF → JPEG...")
        jpeg_path = reports_dir / "test_daily_report.jpeg"
        try:
            from galint_flask.views.api_mobile import _convert_pdf_to_jpeg
            _convert_pdf_to_jpeg(str(pdf_path), str(jpeg_path), dpi=200)
            print(f"✅ JPEG gerado: {jpeg_path.stat().st_size} bytes")
            print(f"   Localização: {jpeg_path.absolute()}")
        except ImportError as e:
            print(f"❌ Dependências faltando: {e}")
            print("\n📦 Para instalar:")
            print("   pip install pdf2image pillow")
            print("\n🪟 Windows também precisa de poppler:")
            print("   https://github.com/oschwartz10612/poppler-windows/releases")
            return
        except Exception as e:
            print(f"❌ Erro ao converter: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # Teste 3: Validar imagem
        print("\n🔍 3. Validando imagem JPEG...")
        try:
            from PIL import Image
            img = Image.open(jpeg_path)
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
        print(f"\n📁 Arquivos gerados em: {reports_dir.absolute()}")
        print("   - test_daily_report.pdf")
        print("   - test_daily_report.jpeg")

if __name__ == "__main__":
    test_jpeg_conversion()
