"""Gerenciamento de caminhos para executável portátil."""
import os
import sys
from pathlib import Path


def get_app_root() -> Path:
    """Retorna o diretório raiz da aplicação."""
    if getattr(sys, 'frozen', False):
        # Executável PyInstaller
        return Path(sys._MEIPASS)
    else:
        # Desenvolvimento
        return Path(__file__).parent.parent


def get_data_dir() -> Path:
    """Retorna o diretório de dados do usuário."""
    if getattr(sys, 'frozen', False):
        # Executável: usar ProgramData (Windows) ou equivalente
        if os.name == 'nt':  # Windows
            data_dir = Path(os.environ.get('PROGRAMDATA', 'C:\\ProgramData')) / 'GALINT'
        else:  # Linux/Mac
            data_dir = Path.home() / '.galint'
    else:
        # Desenvolvimento: usar diretório local
        data_dir = get_app_root() / 'data'
    
    # Criar diretório se não existir
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_database_path() -> Path:
    """Retorna o caminho do banco de dados."""
    db_dir = get_data_dir() / 'database'
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / 'galint.db'


def get_uploads_dir() -> Path:
    """Retorna o diretório de uploads."""
    uploads_dir = get_data_dir() / 'uploads'
    uploads_dir.mkdir(parents=True, exist_ok=True)
    return uploads_dir


def get_backups_dir() -> Path:
    """Retorna o diretório de backups."""
    backups_dir = get_data_dir() / 'backups'
    backups_dir.mkdir(parents=True, exist_ok=True)
    return backups_dir


def get_logs_dir() -> Path:
    """Retorna o diretório de logs."""
    logs_dir = get_data_dir() / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_version() -> str:
    """Retorna a versão atual do sistema."""
    version_file = get_app_root() / 'version.txt'
    if version_file.exists():
        return version_file.read_text().strip()
    return "1.0.0"


def is_frozen() -> bool:
    """Retorna True se está rodando como executável."""
    return getattr(sys, 'frozen', False)


def get_executable_path() -> Path:
    """Retorna o caminho do executável atual."""
    if is_frozen():
        return Path(sys.executable)
    else:
        return Path(__file__).parent.parent / 'app.py'
