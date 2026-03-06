# 🚀 GALINT - Executável Windows Multi-Empresa

## 📊 VISÃO GERAL

Transformar o GALINT em um executável Windows instalável, com personalização completa para cada cliente/empresa.

---

## ✅ VIABILIDADE: ALTA (95%)

### Componentes Necessários:
- ✅ Flask já está rodando
- ✅ Banco de dados PostgreSQL/SQLite portátil
- ✅ Sistema de templates Jinja2/Mako já implementado
- ✅ Sistema de autenticação funcionando
- ⚠️ Precisa: Configuração multi-empresa
- ⚠️ Precisa: Empacotamento PyInstaller
- ⚠️ Precisa: Interface de setup inicial

---

## 🏗️ ARQUITETURA PROPOSTA

### 1. ESTRUTURA DO EXECUTÁVEL

```
📦 galint-installer-v1.0.exe
│
├── 📂 Primeira Execução (Setup Wizard)
│   ├── Tela 1: Bem-vindo ao GALINT
│   ├── Tela 2: Dados da Empresa
│   │   ├── Nome da Empresa: [________]
│   │   ├── CNPJ: [__.__._____/____-__]
│   │   ├── Endereço: [________]
│   │   ├── Telefone: [________]
│   │   └── Email: [________]
│   │
│   ├── Tela 3: Logo da Empresa
│   │   ├── Upload de Imagem (PNG/JPG)
│   │   ├── Preview do logo
│   │   └── Ajuste de tamanho
│   │
│   ├── Tela 4: Configuração de Relatórios
│   │   ├── Cabeçalho padrão
│   │   ├── Rodapé padrão
│   │   └── Cores/Tema
│   │
│   ├── Tela 5: Usuário Administrador
│   │   ├── Nome: [________]
│   │   ├── Matrícula: [________]
│   │   ├── Senha: [********]
│   │   └── Confirmar Senha: [********]
│   │
│   └── Tela 6: Instalação
│       ├── Criando banco de dados...
│       ├── Configurando servidor...
│       ├── Importando dados padrão...
│       └── ✅ Instalação Concluída!
│
├── 📂 Uso Normal (Após Setup)
│   ├── System Tray Icon (🏭 GALINT)
│   │   ├── ▶️ Iniciar Servidor
│   │   ├── ⏸️ Parar Servidor
│   │   ├── 🌐 Abrir no Navegador
│   │   ├── ⚙️ Configurações
│   │   └── ❌ Sair
│   │
│   └── Interface Web (http://localhost:5000)
│       └── Login com logo da empresa
│
└── 📂 Arquivos de Configuração
    ├── config/empresa.json
    ├── config/relatorios.json
    ├── static/uploads/logo.png
    └── database/galint.db (ou conexão PostgreSQL)
```

---

## 📄 ARQUIVOS DE CONFIGURAÇÃO

### 1. `config/empresa.json`
```json
{
  "empresa": {
    "nome": "Indústria XYZ Ltda",
    "nome_fantasia": "XYZ Industrial",
    "cnpj": "12.345.678/0001-99",
    "endereco": {
      "rua": "Av. Industrial, 1000",
      "bairro": "Centro",
      "cidade": "São Paulo",
      "estado": "SP",
      "cep": "01000-000"
    },
    "contato": {
      "telefone": "(11) 3333-4444",
      "email": "contato@xyzindustrial.com.br",
      "site": "www.xyzindustrial.com.br"
    },
    "logo": {
      "path": "static/uploads/logo_empresa.png",
      "width": 150,
      "height": 80
    }
  },
  "sistema": {
    "versao": "1.0.0",
    "instalado_em": "2026-02-12T10:30:00",
    "primeira_execucao": false
  }
}
```

### 2. `config/relatorios.json`
```json
{
  "cabecalho": {
    "template": "{{logo}} {{nome_empresa}} - CNPJ: {{cnpj}}\n{{endereco_completo}}\nTel: {{telefone}} | Email: {{email}}",
    "altura_mm": 40,
    "mostrar_logo": true,
    "cor_texto": "#000000",
    "fonte": "Arial",
    "tamanho_fonte": 10
  },
  "rodape": {
    "template": "Relatório gerado em {{data_geracao}} às {{hora_geracao}} | Sistema GALINT v{{versao}}",
    "altura_mm": 20,
    "cor_texto": "#666666",
    "tamanho_fonte": 8
  },
  "estilo": {
    "cor_primaria": "#007bff",
    "cor_secundaria": "#6c757d",
    "fonte_principal": "Arial",
    "fonte_tabelas": "Courier New"
  }
}
```

---

## 🛠️ IMPLEMENTAÇÃO

### FASE 1: CONFIGURAÇÃO MULTI-EMPRESA (2-3 dias)

#### 1.1 Modelo de Banco de Dados
```python
# galint_flask/models.py

class EmpresaConfig(db.Model):
    __tablename__ = "empresa_config"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome_empresa: Mapped[str] = mapped_column(String(200), nullable=False)
    nome_fantasia: Mapped[str] = mapped_column(String(200), nullable=True)
    cnpj: Mapped[str] = mapped_column(String(18), nullable=True)
    
    # Endereço
    endereco_rua: Mapped[str] = mapped_column(String(255), nullable=True)
    endereco_bairro: Mapped[str] = mapped_column(String(100), nullable=True)
    endereco_cidade: Mapped[str] = mapped_column(String(100), nullable=True)
    endereco_estado: Mapped[str] = mapped_column(String(2), nullable=True)
    endereco_cep: Mapped[str] = mapped_column(String(10), nullable=True)
    
    # Contato
    telefone: Mapped[str] = mapped_column(String(20), nullable=True)
    email: Mapped[str] = mapped_column(String(100), nullable=True)
    site: Mapped[str] = mapped_column(String(100), nullable=True)
    
    # Logo
    logo_path: Mapped[str] = mapped_column(String(255), nullable=True)
    logo_width: Mapped[int] = mapped_column(Integer, default=150)
    logo_height: Mapped[int] = mapped_column(Integer, default=80)
    
    # Metadados
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RelatorioConfig(db.Model):
    __tablename__ = "relatorio_config"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Cabeçalho
    cabecalho_template: Mapped[str] = mapped_column(Text, nullable=True)
    cabecalho_altura_mm: Mapped[int] = mapped_column(Integer, default=40)
    cabecalho_mostrar_logo: Mapped[bool] = mapped_column(Boolean, default=True)
    cabecalho_cor_texto: Mapped[str] = mapped_column(String(7), default="#000000")
    cabecalho_fonte: Mapped[str] = mapped_column(String(50), default="Arial")
    cabecalho_tamanho_fonte: Mapped[int] = mapped_column(Integer, default=10)
    
    # Rodapé
    rodape_template: Mapped[str] = mapped_column(Text, nullable=True)
    rodape_altura_mm: Mapped[int] = mapped_column(Integer, default=20)
    rodape_cor_texto: Mapped[str] = mapped_column(String(7), default="#666666")
    rodape_tamanho_fonte: Mapped[int] = mapped_column(Integer, default=8)
    
    # Estilo
    cor_primaria: Mapped[str] = mapped_column(String(7), default="#007bff")
    cor_secundaria: Mapped[str] = mapped_column(String(7), default="#6c757d")
    fonte_principal: Mapped[str] = mapped_column(String(50), default="Arial")
    fonte_tabelas: Mapped[str] = mapped_column(String(50), default="Courier New")
    
    # Metadados
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

#### 1.2 Serviço de Configuração
```python
# galint_flask/services/config_service.py

class ConfigService:
    """Gerencia configurações da empresa e relatórios."""
    
    @staticmethod
    def get_empresa_config() -> EmpresaConfig:
        """Retorna configuração da empresa (cria padrão se não existir)."""
        config = EmpresaConfig.query.first()
        if not config:
            config = EmpresaConfig(
                nome_empresa="Empresa Não Configurada",
                nome_fantasia="Configure sua empresa",
            )
            db.session.add(config)
            db.session.commit()
        return config
    
    @staticmethod
    def update_empresa_config(data: dict) -> EmpresaConfig:
        """Atualiza configuração da empresa."""
        config = ConfigService.get_empresa_config()
        
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        config.atualizado_em = datetime.utcnow()
        db.session.commit()
        return config
    
    @staticmethod
    def upload_logo(file) -> str:
        """Upload do logo da empresa."""
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logo_empresa_{timestamp}.{filename.split('.')[-1]}"
        
        upload_folder = Path(current_app.root_path) / "static" / "uploads" / "empresa"
        upload_folder.mkdir(parents=True, exist_ok=True)
        
        filepath = upload_folder / filename
        file.save(filepath)
        
        return f"uploads/empresa/{filename}"
    
    @staticmethod
    def get_relatorio_config() -> RelatorioConfig:
        """Retorna configuração de relatórios."""
        config = RelatorioConfig.query.first()
        if not config:
            config = RelatorioConfig(
                cabecalho_template="{{logo}} {{nome_empresa}} - CNPJ: {{cnpj}}\n{{endereco_completo}}\nTel: {{telefone}}",
                rodape_template="Relatório gerado em {{data_geracao}} | Sistema GALINT v{{versao}}"
            )
            db.session.add(config)
            db.session.commit()
        return config
    
    @staticmethod
    def render_cabecalho(**kwargs) -> str:
        """Renderiza o cabeçalho do relatório com os dados fornecidos."""
        config_rel = ConfigService.get_relatorio_config()
        config_emp = ConfigService.get_empresa_config()
        
        context = {
            "nome_empresa": config_emp.nome_empresa,
            "cnpj": config_emp.cnpj,
            "telefone": config_emp.telefone,
            "email": config_emp.email,
            "endereco_completo": f"{config_emp.endereco_rua}, {config_emp.endereco_bairro} - {config_emp.endereco_cidade}/{config_emp.endereco_estado}",
            **kwargs
        }
        
        template = Template(config_rel.cabecalho_template)
        return template.render(**context)
```

#### 1.3 Rotas de Configuração
```python
# galint_flask/views/config.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ..services.config_service import ConfigService

bp = Blueprint("config", __name__, url_prefix="/configuracoes")

@bp.route("/empresa", methods=["GET", "POST"])
@login_required
def empresa():
    """Configuração da empresa."""
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores.", "danger")
        return redirect(url_for("main.index"))
    
    config = ConfigService.get_empresa_config()
    
    if request.method == "POST":
        data = {
            "nome_empresa": request.form.get("nome_empresa"),
            "nome_fantasia": request.form.get("nome_fantasia"),
            "cnpj": request.form.get("cnpj"),
            "endereco_rua": request.form.get("endereco_rua"),
            "endereco_bairro": request.form.get("endereco_bairro"),
            "endereco_cidade": request.form.get("endereco_cidade"),
            "endereco_estado": request.form.get("endereco_estado"),
            "endereco_cep": request.form.get("endereco_cep"),
            "telefone": request.form.get("telefone"),
            "email": request.form.get("email"),
            "site": request.form.get("site"),
        }
        
        # Upload de logo
        if "logo" in request.files:
            file = request.files["logo"]
            if file and file.filename:
                logo_path = ConfigService.upload_logo(file)
                data["logo_path"] = logo_path
        
        ConfigService.update_empresa_config(data)
        flash("Configurações da empresa atualizadas com sucesso!", "success")
        return redirect(url_for("config.empresa"))
    
    return render_template("config/empresa.html", config=config)


@bp.route("/relatorios", methods=["GET", "POST"])
@login_required
def relatorios():
    """Configuração de relatórios."""
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores.", "danger")
        return redirect(url_for("main.index"))
    
    config = ConfigService.get_relatorio_config()
    
    if request.method == "POST":
        data = {
            "cabecalho_template": request.form.get("cabecalho_template"),
            "rodape_template": request.form.get("rodape_template"),
            "cor_primaria": request.form.get("cor_primaria"),
            "cor_secundaria": request.form.get("cor_secundaria"),
        }
        
        config = ConfigService.update_relatorio_config(data)
        flash("Configurações de relatórios atualizadas!", "success")
        return redirect(url_for("config.relatorios"))
    
    return render_template("config/relatorios.html", config=config)
```

---

### FASE 2: PÁGINA DE LOGIN PERSONALIZADA (1 dia)

```html
<!-- galint_flask/templates/auth/login.html -->
{% extends "base.html" %}

{% block content %}
<div class="login-container">
    <div class="login-card">
        <!-- Logo da Empresa -->
        {% if empresa_config.logo_path %}
        <div class="logo-empresa text-center mb-4">
            <img src="{{ url_for('static', filename=empresa_config.logo_path) }}" 
                 alt="{{ empresa_config.nome_empresa }}"
                 style="max-width: {{ empresa_config.logo_width }}px; max-height: {{ empresa_config.logo_height }}px;">
        </div>
        {% endif %}
        
        <!-- Nome da Empresa -->
        <h2 class="text-center mb-4">{{ empresa_config.nome_empresa }}</h2>
        <h5 class="text-center text-muted mb-4">Sistema de Gestão de Estoque</h5>
        
        <!-- Formulário de Login -->
        <form method="POST">
            {{ form.hidden_tag() }}
            <div class="mb-3">
                {{ form.matricula.label(class="form-label") }}
                {{ form.matricula(class="form-control") }}
            </div>
            <div class="mb-3">
                {{ form.password.label(class="form-label") }}
                {{ form.password(class="form-control") }}
            </div>
            <button type="submit" class="btn btn-primary w-100">Entrar</button>
        </form>
        
        <!-- Rodapé -->
        <div class="text-center mt-4 text-muted">
            <small>GALINT v{{ versao_sistema }} | {{ empresa_config.telefone }}</small>
        </div>
    </div>
</div>
{% endblock %}
```

---

### FASE 3: EMPACOTAMENTO EXECUTÁVEL (2-3 dias)

#### 3.1 PyInstaller Spec File
```python
# galint.spec

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('galint_flask/templates', 'galint_flask/templates'),
        ('galint_flask/static', 'galint_flask/static'),
        ('config', 'config'),
    ],
    hiddenimports=[
        'flask',
        'sqlalchemy',
        'psycopg2',
        'waitress',
        'reportlab',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='GALINT',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Sem console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='galint_flask/static/img/galint-icon.ico',  # Ícone do GALINT (mesmo do APK)
)
```

#### 3.2 Script de Build
```powershell
# build_executable.ps1

Write-Host "=== GALINT - Build Executável ===" -ForegroundColor Cyan

# Limpar builds anteriores
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

# Instalar PyInstaller
pip install pyinstaller

# Build
Write-Host "Compilando executável..." -ForegroundColor Yellow
pyinstaller galint.spec --clean

# Copiar arquivos adicionais
Write-Host "Copiando arquivos de configuração..." -ForegroundColor Yellow
Copy-Item -Recurse "config" "dist/config"
Copy-Item "README.md" "dist/"
Copy-Item "LICENSE" "dist/"

Write-Host "✓ Build concluído! Executável em: dist/GALINT.exe" -ForegroundColor Green
```

---

### FASE 4: INSTALADOR/SETUP (2 dias)

Usar **Inno Setup** para criar instalador profissional:

```iss
; galint_installer.iss

[Setup]
AppName=GALINT
AppVersion=1.0.0
DefaultDirName={pf}\GALINT
DefaultGroupName=GALINT
OutputDir=installer_output
OutputBaseFilename=GALINT_Installer_v1.0.0
Compression=lzma2
SolidCompression=yes
SetupIconFile=galint_flask\static\img\icon.ico

[Files]
Source: "dist\GALINT.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\GALINT"; Filename: "{app}\GALINT.exe"
Name: "{group}\Desinstalar GALINT"; Filename: "{uninstallexe}"
Name: "{commondesktop}\GALINT"; Filename: "{app}\GALINT.exe"

[Run]
Filename: "{app}\GALINT.exe"; Description: "Executar GALINT"; Flags: postinstall nowait skipifsilent
```

---

## 📊 CRONOGRAMA DE IMPLEMENTAÇÃO

| Fase | Descrição | Tempo Estimado | Prioridade |
|------|-----------|----------------|------------|
| 1 | Configuração Multi-Empresa (Models + Services) | 2-3 dias | 🔴 Alta |
| 2 | Interface de Configuração (Views + Templates) | 2 dias | 🔴 Alta |
| 3 | Página de Login Personalizada | 1 dia | 🟡 Média |
| 4 | Editor de Cabeçalhos de Relatórios | 2 dias | 🟡 Média |
| 5 | Empacotamento PyInstaller | 2-3 dias | 🔴 Alta |
| 6 | Setup Wizard (Primeira Execução) | 3 dias | 🟡 Média |
| 7 | System Tray Application | 2 dias | 🟢 Baixa |
| 8 | Instalador Inno Setup | 1 dia | 🔴 Alta |
| 9 | Testes e Ajustes | 3 dias | 🔴 Alta |

**TOTAL: 18-21 dias úteis (3-4 semanas)**

---

## 💰 VALOR COMERCIAL

Com essa implementação, o GALINT se torna:
- ✅ Produto white-label comercializável
- ✅ Instalação simples para clientes
- ✅ Personalização completa
- ✅ Sem necessidade de conhecimento técnico do cliente
- ✅ Suporte multi-empresa

**Potencial de mercado:** Pequenas e médias indústrias, oficinas, armazéns, etc.

---

## 🎯 PRÓXIMOS PASSOS

1. **Aprovar o plano** ✋
2. **Priorizar funcionalidades** (podemos começar com MVP)
3. **Implementar Fase 1** (Configuração Multi-Empresa)
4. **Testar em ambiente real**
5. **Empacotar executável**

---

## 🤔 DECISÕES NECESSÁRIAS

1. **Banco de Dados:**
   - SQLite (mais simples, portátil) 
   - PostgreSQL (mais robusto, requer instalação)
   
2. **Licenciamento:**
   - Licença por máquina?
   - Licença por empresa?
   - Licença perpétua ou assinatura?

3. **Distribuição:**
   - Download direto?
   - Loja de aplicativos?
   - USB/CD instalável?

---

## ✅ CONCLUSÃO

**VIABILIDADE: 95% ✅**

É totalmente viável e relativamente simples de implementar. O maior trabalho é:
1. Criar a interface de configuração
2. Modificar os relatórios para usar templates personalizáveis
3. Empacotar tudo em um executável Windows

**RECOMENDAÇÃO:** 
Começar com **MVP (Minimum Viable Product)** implementando as fases 1, 2 e 5 primeiro (configuração + empacotamento básico), e depois ir adicionando recursos incrementalmente.

---

**Quer que eu comece a implementação? Por qual fase devemos começar?**
