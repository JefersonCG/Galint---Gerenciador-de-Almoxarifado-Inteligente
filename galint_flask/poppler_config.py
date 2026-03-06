"""Configuração automática do Poppler para conversão PDF→JPEG."""
import os
import sys
from pathlib import Path

def configure_poppler_path():
    """Adiciona o poppler ao PATH se necessário (Windows)."""
    if sys.platform != "win32":
        return  # Linux/Mac já tem poppler no sistema
    
    # Caminho padrão do poppler instalado
    poppler_paths = [
        r"C:\poppler\poppler-23.07.0\Library\bin",
        r"C:\poppler\poppler-23.11.0\Library\bin",
        r"C:\poppler\Library\bin",
        Path(__file__).parent.parent / ".poppler" / "Library" / "bin",
    ]
    
    # Verificar se poppler já está no PATH
    for path in poppler_paths:
        path_str = str(path)
        if os.path.exists(path_str):
            pdfinfo_exe = os.path.join(path_str, "pdfinfo.exe")
            if os.path.isfile(pdfinfo_exe):
                # Adicionar ao PATH da sessão atual
                if path_str not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = path_str + os.pathsep + os.environ["PATH"]
                    print(f"✅ Poppler configurado: {path_str}")
                return
    
    print("⚠️  Poppler não encontrado. Instale de:")
    print("   https://github.com/oschwartz10612/poppler-windows/releases")

# Configurar automaticamente ao importar
configure_poppler_path()
