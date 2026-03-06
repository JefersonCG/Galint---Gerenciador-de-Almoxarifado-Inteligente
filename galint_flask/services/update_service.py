"""Serviço de atualização automática do GALINT."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import requests

from ..paths import get_data_dir, get_version, get_executable_path, is_frozen


class UpdateService:
    """Gerencia atualizações do sistema."""
    
    # URL do servidor de updates (configure com seu domínio ou GitHub)
    UPDATE_SERVER_URL = os.environ.get(
        'GALINT_UPDATE_SERVER',
        'https://api.github.com/repos/SEU_USUARIO/galint/releases/latest'
    )
    
    @staticmethod
    def check_for_updates() -> Optional[Dict[str, Any]]:
        """
        Verifica se há atualizações disponíveis.
        
        Returns:
            dict com informações da atualização ou None se não houver
        """
        try:
            current_version = get_version()
            
            # Tenta buscar do GitHub Releases
            if 'github.com' in UpdateService.UPDATE_SERVER_URL:
                return UpdateService._check_github_releases(current_version)
            
            # Servidor customizado
            response = requests.get(
                f"{UpdateService.UPDATE_SERVER_URL}/latest.json",
                timeout=10
            )
            
            if response.status_code != 200:
                return None
            
            latest_info = response.json()
            latest_version = latest_info.get("version")
            
            # Comparar versões
            if UpdateService._is_newer_version(latest_version, current_version):
                return {
                    "version": latest_version,
                    "download_url": latest_info.get("download_url"),
                    "release_notes": latest_info.get("release_notes"),
                    "size_mb": latest_info.get("size_mb"),
                    "released_at": latest_info.get("released_at"),
                    "sha256": latest_info.get("sha256"),
                }
            
            return None
            
        except Exception as e:
            print(f"Erro ao verificar atualizações: {e}")
            return None
    
    @staticmethod
    def _check_github_releases(current_version: str) -> Optional[Dict[str, Any]]:
        """Verifica atualizações no GitHub Releases."""
        try:
            response = requests.get(UpdateService.UPDATE_SERVER_URL, timeout=10)
            if response.status_code != 200:
                return None
            
            release = response.json()
            latest_version = release.get('tag_name', '').lstrip('v')
            
            if not UpdateService._is_newer_version(latest_version, current_version):
                return None
            
            # Buscar asset .exe
            download_url = None
            asset_size = 0
            
            for asset in release.get('assets', []):
                if asset.get('name', '').endswith('.exe'):
                    download_url = asset.get('browser_download_url')
                    asset_size = asset.get('size', 0)
                    break
            
            if not download_url:
                return None
            
            return {
                'version': latest_version,
                'download_url': download_url,
                'release_notes': release.get('body', ''),
                'size_mb': round(asset_size / 1024 / 1024, 2),
                'released_at': release.get('published_at'),
                'sha256': None,  # GitHub não fornece por padrão
            }
            
        except Exception as e:
            print(f"Erro ao verificar GitHub releases: {e}")
            return None
    
    @staticmethod
    def download_update(download_url: str, expected_sha256: Optional[str] = None) -> Optional[Path]:
        """
        Baixa a atualização e verifica integridade.
        
        Args:
            download_url: URL do arquivo
            expected_sha256: Hash SHA256 esperado (opcional)
        
        Returns:
            Path do arquivo baixado ou None se falhar
        """
        try:
            # Baixar para temp
            temp_dir = Path(tempfile.gettempdir()) / "galint_update"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            update_file = temp_dir / "galint_update.exe"
            
            print("Baixando atualização...")
            response = requests.get(download_url, stream=True, timeout=300)
            
            if response.status_code != 200:
                return None
            
            # Download com progress
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(update_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Progress (opcional, pode implementar callback)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\r{percent:.1f}%", end='', flush=True)
            
            print("\nDownload concluído!")
            
            # Verificar hash SHA256 se fornecido
            if expected_sha256:
                print("Verificando integridade...")
                file_hash = UpdateService._calculate_sha256(update_file)
                
                if file_hash.lower() != expected_sha256.lower():
                    print("ERRO: Hash SHA256 não confere!")
                    update_file.unlink()
                    return None
                
                print("Integridade verificada ✓")
            
            return update_file
            
        except Exception as e:
            print(f"Erro ao baixar atualização: {e}")
            return None
    
    @staticmethod
    def install_update(update_file: Path) -> bool:
        """
        Instala a atualização (substitui o executável).
        
        IMPORTANTE: Só substitui o .exe, mantém dados em ProgramData intactos!
        
        Args:
            update_file: Path do novo executável
        
        Returns:
            True se agendou instalação com sucesso
        """
        try:
            if not is_frozen():
                print("AVISO: Atualizações automáticas só funcionam no executável!")
                return False
            
            current_exe = get_executable_path()
            backup_exe = current_exe.with_suffix('.exe.backup')
            
            # Script de atualização (será executado após fechar o app)
            update_script = f"""@echo off
echo ====================================
echo   GALINT - Instalando Atualizacao
echo ====================================
echo.

echo [1/4] Aguardando fechamento do GALINT...
timeout /t 3 /nobreak > nul

echo [2/4] Fazendo backup da versao anterior...
if exist "{backup_exe}" del "{backup_exe}"
move "{current_exe}" "{backup_exe}"

echo [3/4] Instalando nova versao...
move /Y "{update_file}" "{current_exe}"

echo [4/4] Verificando instalacao...
if exist "{current_exe}" (
    echo.
    echo ====================================
    echo   Atualizacao concluida com sucesso!
    echo ====================================
    echo.
    echo Reiniciando GALINT...
    timeout /t 2 /nobreak > nul
    start "" "{current_exe}"
) else (
    echo.
    echo ERRO: Falha na instalacao!
    echo Restaurando backup...
    move "{backup_exe}" "{current_exe}"
    echo.
    echo Backup restaurado. Reiniciando versao anterior...
    timeout /t 3 /nobreak > nul
    start "" "{current_exe}"
)

REM Autodestruir script
(goto) 2>nul & del "%~f0"
"""
            
            # Salvar script
            script_path = Path(tempfile.gettempdir()) / "galint_update.bat"
            script_path.write_text(update_script, encoding='utf-8')
            
            # Registrar atualização no histórico
            UpdateService.record_update_pending(update_file)
            
            # Executar script em processo separado
            subprocess.Popen(
                ["cmd.exe", "/c", str(script_path)],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                cwd=str(current_exe.parent)
            )
            
            # Sinalizar que app deve fechar
            return True
            
        except Exception as e:
            print(f"Erro ao instalar atualização: {e}")
            return False
    
    @staticmethod
    def _is_newer_version(new: str, current: str) -> bool:
        """
        Compara versões no formato X.Y.Z.
        
        Examples:
            _is_newer_version("1.2.1", "1.2.0") → True
            _is_newer_version("2.0.0", "1.9.9") → True
            _is_newer_version("1.2.0", "1.2.0") → False
        """
        try:
            # Remover 'v' se existir
            new = new.lstrip('v')
            current = current.lstrip('v')
            
            new_parts = [int(x) for x in new.split('.')]
            current_parts = [int(x) for x in current.split('.')]
            
            # Normalizar tamanhos
            max_len = max(len(new_parts), len(current_parts))
            new_parts.extend([0] * (max_len - len(new_parts)))
            current_parts.extend([0] * (max_len - len(current_parts)))
            
            return new_parts > current_parts
        except:
            return False
    
    @staticmethod
    def _calculate_sha256(file_path: Path) -> str:
        """Calcula hash SHA256 de um arquivo."""
        sha256_hash = hashlib.sha256()
        
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        
        return sha256_hash.hexdigest()
    
    @staticmethod
    def get_update_history() -> list[Dict[str, Any]]:
        """Retorna histórico de atualizações instaladas."""
        history_file = get_data_dir() / 'update_history.json'
        
        if not history_file.exists():
            return []
        
        try:
            return json.loads(history_file.read_text(encoding='utf-8'))
        except:
            return []
    
    @staticmethod
    def record_update(version: str, notes: str = ""):
        """Registra atualização concluída no histórico."""
        history = UpdateService.get_update_history()
        
        history.append({
            "version": version,
            "installed_at": datetime.now().isoformat(),
            "notes": notes,
            "status": "completed"
        })
        
        # Manter apenas últimas 20 atualizações
        history = history[-20:]
        
        history_file = get_data_dir() / 'update_history.json'
        history_file.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding='utf-8')
    
    @staticmethod
    def record_update_pending(update_file: Path):
        """Registra que uma atualização está pendente."""
        pending_file = get_data_dir() / 'pending_update.json'
        
        pending_file.write_text(json.dumps({
            "update_file": str(update_file),
            "scheduled_at": datetime.now().isoformat(),
        }, indent=2), encoding='utf-8')
    
    @staticmethod
    def get_pending_update() -> Optional[Dict[str, Any]]:
        """Retorna atualização pendente se houver."""
        pending_file = get_data_dir() / 'pending_update.json'
        
        if not pending_file.exists():
            return None
        
        try:
            return json.loads(pending_file.read_text(encoding='utf-8'))
        except:
            return None
    
    @staticmethod
    def clear_pending_update():
        """Limpa atualização pendente."""
        pending_file = get_data_dir() / 'pending_update.json'
        
        if pending_file.exists():
            pending_file.unlink()
    
    @staticmethod
    def get_auto_update_settings() -> Dict[str, Any]:
        """Retorna configurações de auto-update."""
        settings_file = get_data_dir() / 'auto_update_settings.json'
        
        default_settings = {
            "enabled": True,
            "check_interval_hours": 24,
            "auto_install": False,  # Se False, só notifica
            "last_check": None,
        }
        
        if not settings_file.exists():
            return default_settings
        
        try:
            settings = json.loads(settings_file.read_text(encoding='utf-8'))
            return {**default_settings, **settings}
        except:
            return default_settings
    
    @staticmethod
    def save_auto_update_settings(settings: Dict[str, Any]):
        """Salva configurações de auto-update."""
        settings_file = get_data_dir() / 'auto_update_settings.json'
        settings_file.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
    
    @staticmethod
    def should_check_for_updates() -> bool:
        """Verifica se é hora de checar atualizações."""
        settings = UpdateService.get_auto_update_settings()
        
        if not settings['enabled']:
            return False
        
        last_check = settings.get('last_check')
        
        if not last_check:
            return True
        
        try:
            last_check_dt = datetime.fromisoformat(last_check)
            hours_since = (datetime.now() - last_check_dt).total_seconds() / 3600
            
            return hours_since >= settings['check_interval_hours']
        except:
            return True
    
    @staticmethod
    def mark_check_done():
        """Marca que verificação foi feita agora."""
        settings = UpdateService.get_auto_update_settings()
        settings['last_check'] = datetime.now().isoformat()
        UpdateService.save_auto_update_settings(settings)
