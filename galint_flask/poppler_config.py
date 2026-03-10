"""Configuração automática do Poppler para conversão PDF→JPEG."""
import os
import shutil
import sys
from pathlib import Path

def configure_poppler_path():
    """Adiciona o poppler ao PATH se necessário (Windows)."""
    if sys.platform != "win32":
        return  # Linux/Mac já tem poppler no sistema

    # Se já está disponível no PATH, não há nada a configurar.
    if shutil.which("pdfinfo") and shutil.which("pdftoppm"):
        return
    
    # Caminho padrão do poppler instalado
    poppler_paths: list[Path | str] = [
        r"C:\poppler\poppler-23.11.0\Library\bin",
        r"C:\poppler\Library\bin",
        Path(__file__).parent.parent / ".poppler" / "Library" / "bin",
    ]

    # Instalação via winget (oschwartz10612.Poppler)
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        winget_root = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
        if winget_root.exists():
            poppler_paths.extend(list(winget_root.glob("oschwartz10612.Poppler_*/*/Library/bin")))
    
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
    
    # Última tentativa: poppler pode estar em qualquer lugar do PATH, mesmo sem ambos utilitários.
    if shutil.which("pdfinfo"):
        return

    print("⚠️  Poppler não encontrado. Instale de:")
    print("   https://github.com/oschwartz10612/poppler-windows/releases")

# Configurar automaticamente ao importar
configure_poppler_path()
