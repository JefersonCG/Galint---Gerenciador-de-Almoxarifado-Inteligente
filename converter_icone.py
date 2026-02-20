"""
Converte o ícone do GALINT mobile (PNG) para formato ICO (Windows).
"""
from PIL import Image
import sys

def convert_icon():
    try:
        # Abrir PNG original
        img = Image.open("galint_flask/static/img/galint-icon.png")
        
        # Criar versões em múltiplos tamanhos (padrão Windows)
        icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        
        # Salvar como ICO
        img.save(
            "galint_flask/static/img/galint-icon.ico",
            format='ICO',
            sizes=icon_sizes
        )
        
        print("✅ Ícone convertido com sucesso!")
        print("   PNG: galint_flask/static/img/galint-icon.png")
        print("   ICO: galint_flask/static/img/galint-icon.ico")
        
    except Exception as e:
        print(f"❌ Erro ao converter ícone: {e}")
        sys.exit(1)

if __name__ == "__main__":
    convert_icon()
