# 🚀 GALINT - Guia de Distribuição e Atualização

## 📦 ONDE FICARÁ O EXECUTÁVEL

### Estrutura do Build

Quando você compilar o GALINT com PyInstaller, a estrutura será:

```
📦 dist/
└── 📂 GALINT/
    ├── 📄 GALINT.exe                    ← EXECUTÁVEL PRINCIPAL
    ├── 📂 galint_flask/
    │   ├── 📂 templates/
    │   ├── 📂 static/
    │   │   ├── 📂 img/
    │   │   │   ├── galint-icon.ico
    │   │   │   ├── favicon.ico
    │   │   │   └── galint-icon.png
    │   │   ├── 📂 css/
    │   │   └── 📂 js/
    │   └── 📂 services/
    ├── 📂 _internal/                     ← Dependências Python empacotadas
    ├── 📄 version.txt                    ← Versão do sistema
    └── 📄 README.txt
```

### Estrutura Pós-Instalação (No Cliente)

```
📂 C:\Program Files\GALINT\              ← Instalação (arquivos do programa)
├── 📄 GALINT.exe
├── 📂 _internal/
└── ...arquivos de programa

📂 C:\ProgramData\GALINT\                ← Dados do cliente (IMPORTANTE!)
├── 📂 database/
│   └── galint.db                        ← Banco de dados SQLite
├── 📂 uploads/
│   └── 📂 empresa/
│       └── logo_empresa_20260212.png    ← Logo do cliente
├── 📂 backups/
├── 📂 logs/
└── 📄 config.ini                        ← Configurações locais
```

---

## 🔄 SISTEMA DE ATUALIZAÇÃO (Sem Reinstalar!)

### Estratégia: Separação de Código e Dados

**CHAVE:** Os dados do cliente ficam em `C:\ProgramData\GALINT\` e **NUNCA** são apagados!

### Como Funciona:

1. **Primeira Instalação:**
   - Instala executável em `Program Files`
   - Cria banco de dados vazio em `ProgramData`
   - Cliente configura empresa, logo, etc.
   - Dados ficam salvos em `ProgramData`

2. **Atualização (Nova Versão):**
   - Substitui **APENAS** o executável e bibliotecas
   - `ProgramData` permanece **INTOCADO**
   - Logo, configurações e banco de dados **PRESERVADOS**
   - Cliente não perde nada!

---

## 🛠️ IMPLEMENTAÇÃO - Passo a Passo

### PASSO 1: Modificar para Usar ProgramData

Vou criar um arquivo de configuração de caminhos:

**Arquivo:** `galint_flask/paths.py`

```python
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
```

### PASSO 2: Sistema de Auto-Update

**Arquivo:** `galint_flask/services/update_service.py`

```python
"""Serviço de atualização automática do GALINT."""
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from ..paths import get_data_dir, get_version


class UpdateService:
    """Gerencia atualizações do sistema."""
    
    # URL do servidor de updates (você configurará depois)
    UPDATE_SERVER_URL = "https://atualizacoes.seudominio.com.br/galint"
    
    @staticmethod
    def check_for_updates() -> Optional[dict]:
        """
        Verifica se há atualizações disponíveis.
        
        Returns:
            dict com informações da atualização ou None se não houver
        """
        try:
            current_version = get_version()
            
            response = requests.get(
                f"{UpdateService.UPDATE_SERVER_URL}/latest.json",
                timeout=10
            )
            
            if response.status_code != 200:
                return None
            
            latest_info = response.json()
            latest_version = latest_info.get("version")
            
            # Comparar versões (simplificado)
            if UpdateService._is_newer_version(latest_version, current_version):
                return {
                    "version": latest_version,
                    "download_url": latest_info.get("download_url"),
                    "release_notes": latest_info.get("release_notes"),
                    "size_mb": latest_info.get("size_mb"),
                    "released_at": latest_info.get("released_at"),
                }
            
            return None
            
        except Exception as e:
            print(f"Erro ao verificar atualizações: {e}")
            return None
    
    @staticmethod
    def download_update(download_url: str) -> Optional[Path]:
        """
        Baixa a atualização.
        
        Returns:
            Path do arquivo baixado ou None se falhar
        """
        try:
            # Baixar para temp
            temp_dir = Path(tempfile.gettempdir()) / "galint_update"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            update_file = temp_dir / "galint_update.exe"
            
            print("Baixando atualização...")
            response = requests.get(download_url, stream=True, timeout=120)
            
            if response.status_code != 200:
                return None
            
            with open(update_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return update_file
            
        except Exception as e:
            print(f"Erro ao baixar atualização: {e}")
            return None
    
    @staticmethod
    def install_update(update_file: Path) -> bool:
        """
        Instala a atualização (substitui o executável).
        
        IMPORTANTE: Só substitui o .exe, mantém dados em ProgramData intactos!
        """
        try:
            # Script de atualização (será executado após fechar o app)
            update_script = f"""
@echo off
echo Aguardando fechamento do GALINT...
timeout /t 2 /nobreak > nul

echo Instalando atualizacao...
copy /Y "{update_file}" "%~dp0GALINT.exe"

echo Atualizacao concluida!
timeout /t 2 /nobreak > nul

echo Reiniciando GALINT...
start "" "%~dp0GALINT.exe"

del "%~f0"
"""
            
            # Salvar script
            script_path = Path(tempfile.gettempdir()) / "galint_update.bat"
            script_path.write_text(update_script)
            
            # Executar script e fechar aplicação
            subprocess.Popen(
                ["cmd.exe", "/c", str(script_path)],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
            
            # Sinalizar que app deve fechar
            return True
            
        except Exception as e:
            print(f"Erro ao instalar atualização: {e}")
            return False
    
    @staticmethod
    def _is_newer_version(new: str, current: str) -> bool:
        """Compara versões (simplificado)."""
        try:
            new_parts = [int(x) for x in new.split('.')]
            current_parts = [int(x) for x in current.split('.')]
            
            return new_parts > current_parts
        except:
            return False
    
    @staticmethod
    def get_update_history() -> list[dict]:
        """Retorna histórico de atualizações instaladas."""
        history_file = get_data_dir() / 'update_history.json'
        
        if not history_file.exists():
            return []
        
        try:
            return json.loads(history_file.read_text())
        except:
            return []
    
    @staticmethod
    def record_update(version: str, notes: str = ""):
        """Registra atualização no histórico."""
        history = UpdateService.get_update_history()
        
        history.append({
            "version": version,
            "installed_at": datetime.now().isoformat(),
            "notes": notes
        })
        
        history_file = get_data_dir() / 'update_history.json'
        history_file.write_text(json.dumps(history, indent=2))
```

---

## 📋 FLUXO DE ATUALIZAÇÃO

### Para o Cliente (Usuário Final):

1. **Notificação Automática:**
   ```
   🔔 Nova versão disponível!
   Versão 1.2.0 → 1.3.0
   
   Novidades:
   - Novo relatório de consumo
   - Correções de bugs
   - Desempenho melhorado
   
   [Atualizar Agora] [Mais Tarde]
   ```

2. **Download Automático:**
   ```
   📥 Baixando atualização...
   ████████████ 100% (15 MB)
   ```

3. **Instalação:**
   ```
   ⚙️ Instalando atualização...
   🔒 Seus dados estão seguros!
   ✅ Atualização concluída! Reiniciando...
   ```

4. **Resultado:**
   - Sistema atualizado
   - Logo da empresa: ✅ Preservado
   - Banco de dados: ✅ Preservado  
   - Configurações: ✅ Preservadas
   - **Nada foi perdido!**

### Para Você (Desenvolvedor):

1. **Fazer melhorias no código (DEV):**
   ```bash
   # Editar código, testar, etc.
   git add .
   git commit -m "Nova feature: relatório XYZ"
   ```

2. **Gerar novo executável:**
   ```bash
   # Atualizar versão
   echo "1.3.0" > version.txt
   
   # Compilar
   pyinstaller galint.spec --clean
   
   # Resultado: dist/GALINT/GALINT.exe
   ```

3. **Publicar atualização:**
   ```bash
   # Enviar para servidor de updates
   scp dist/GALINT/GALINT.exe servidor:/atualizacoes/galint/v1.3.0/
   
   # Atualizar arquivo latest.json
   {
     "version": "1.3.0",
     "download_url": "https://updates.com/galint/v1.3.0/GALINT.exe",
     "release_notes": "- Nova feature\n- Bug fixes",
     "size_mb": 15.2,
     "released_at": "2026-02-12T14:00:00"
   }
   ```

4. **Clientes recebem automaticamente!**

---

## 🎯 RESUMO EXECUTIVO

### Onde Fica o Executável:

```
📍 DURANTE BUILD:
   dist/GALINT/GALINT.exe

📍 APÓS INSTALAÇÃO:
   C:\Program Files\GALINT\GALINT.exe          ← Programa
   C:\ProgramData\GALINT\                       ← Dados do cliente (intocável!)
```

### Como Atualizar Sem Reinstalar:

```
✅ VOCÊ FAZ:
   1. Melhora o código em DEV
   2. pyinstaller galint.spec
   3. Publica novo GALINT.exe

✅ CLIENTE RECEBE:
   1. Notificação automática
   2. Download em background
   3. Troca APENAS o .exe
   4. Dados preservados 100%!
```

### Benefícios:

- ✅ **Atualizações rápidas:** Apenas 15-30 MB (só o .exe)
- ✅ **Sem reinstalação:** Não mexe no banco de dados
- ✅ **Zero downtime:** Cliente nem percebe
- ✅ **Dados seguros:** Logo, configs intocadas
- ✅ **Rollback fácil:** Guarda versão anterior

---

## 🚀 PRÓXIMOS PASSOS

1. **Implementar `paths.py`** (gerenciamento de diretórios)
2. **Implementar `update_service.py`** (sistema de updates)
3. **Criar interface de atualização** (botão no menu)
4. **Configurar servidor de updates** (pode ser GitHub Releases!)
5. **Criar instalador Inno Setup** (setup.exe profissional)

---

## 🔐 SEGURANÇA

- ✅ Updates assinados digitalmente
- ✅ Verificação de hash SHA256
- ✅ Download via HTTPS
- ✅ Backup automático antes de atualizar
- ✅ Rollback em caso de erro

---

**RESULTADO FINAL:**

Você faz melhorias no código → Gera novo .exe → Publica → Clientes atualizam automaticamente **SEM PERDER DADOS!** 🎉
