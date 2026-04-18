"""Serviço para gerenciar configurações da empresa e relatórios."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import current_app
from jinja2 import Template
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import EmpresaConfig, RelatorioConfig


class ConfigService:
    """Gerencia configurações da empresa e relatórios."""

    EMPRESA_UPLOAD_DIR = Path("uploads") / "empresa"
    LOGIN_BRANDING_CONFIG_FILENAME = "login_branding.json"
    DEFAULT_LOGIN_BACKGROUND_PATH = "logo/logo.png"
    DEFAULT_LOGIN_CARD_IMAGE_PATH = "logo/icone-galint.png"
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    
    # Templates padrão
    CABECALHO_PADRAO = """{{nome_empresa}}
{% if cnpj %}CNPJ: {{cnpj}}{% endif %}
{{endereco_completo}}
{% if telefone %}Tel: {{telefone}}{% endif %}{% if email %} | {{email}}{% endif %}"""
    
    RODAPE_PADRAO = """Relatório gerado em {{data_geracao}} às {{hora_geracao}} | Sistema GALINT v{{versao}} | Página {{pagina}}"""
    
    @staticmethod
    def is_primeira_execucao() -> bool:
        """Verifica se é a primeira execução do sistema."""
        config = EmpresaConfig.query.first()
        return config is None or config.primeira_execucao
    
    @staticmethod
    def get_empresa_config() -> EmpresaConfig:
        """Retorna configuração da empresa (cria padrão se não existir)."""
        config = EmpresaConfig.query.first()
        
        if not config:
            config = EmpresaConfig(
                nome_empresa="Sistema não configurado",
                nome_fantasia="Configure sua empresa",
                primeira_execucao=True,
                setup_completo=False,
                versao_instalada="1.0.0"
            )
            db.session.add(config)
            db.session.commit()
        
        return config
    
    @staticmethod
    def update_empresa_config(data: dict[str, Any]) -> EmpresaConfig:
        """Atualiza configuração da empresa."""
        config = ConfigService.get_empresa_config()
        
        # Atualizar campos
        campos_permitidos = [
            'nome_empresa', 'nome_fantasia', 'cnpj',
            'endereco_rua', 'endereco_numero', 'endereco_complemento',
            'endereco_bairro', 'endereco_cidade', 'endereco_estado', 'endereco_cep',
            'telefone', 'telefone_secundario', 'email', 'site',
            'logo_path', 'logo_width', 'logo_height', 'primeira_execucao', 'setup_completo'
        ]
        
        for campo in campos_permitidos:
            if campo in data:
                setattr(config, campo, data[campo])
        
        config.atualizado_em = datetime.utcnow()
        db.session.commit()
        
        return config
    
    @staticmethod
    def _save_empresa_image(file, *, prefix: str) -> str:
        """Salva uma imagem da empresa em static/uploads/empresa."""
        if not file or not file.filename:
            raise ValueError("Arquivo de imagem inválido")

        filename = secure_filename(file.filename)
        extensao = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

        if extensao not in ConfigService.ALLOWED_IMAGE_EXTENSIONS:
            allowed = ', '.join(sorted(ConfigService.ALLOWED_IMAGE_EXTENSIONS))
            raise ValueError(f"Extensão não permitida. Use: {allowed}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        novo_filename = f"{prefix}_{timestamp}.{extensao}"

        upload_folder = Path(current_app.root_path) / "static" / ConfigService.EMPRESA_UPLOAD_DIR
        upload_folder.mkdir(parents=True, exist_ok=True)

        filepath = upload_folder / novo_filename
        file.save(str(filepath))

        return str(ConfigService.EMPRESA_UPLOAD_DIR / novo_filename).replace('\\', '/')

    @staticmethod
    def upload_logo(file) -> str:
        """Upload do logo da empresa."""
        return ConfigService._save_empresa_image(file, prefix="logo_empresa")

    @staticmethod
    def upload_login_background(file) -> str:
        """Upload da imagem de fundo da página de login."""
        return ConfigService._save_empresa_image(file, prefix="login_background")

    @staticmethod
    def upload_login_card_image(file) -> str:
        """Upload da imagem exibida no card da página de login."""
        return ConfigService._save_empresa_image(file, prefix="login_card")

    @staticmethod
    def _branding_config_dir() -> Path:
        config_dir = Path(current_app.instance_path) / "branding"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    @staticmethod
    def _branding_config_path() -> Path:
        return ConfigService._branding_config_dir() / ConfigService.LOGIN_BRANDING_CONFIG_FILENAME

    @staticmethod
    def _delete_uploaded_empresa_asset(asset_path: str | None) -> bool:
        if not asset_path:
            return False

        normalized = str(asset_path).replace('\\', '/').strip().lstrip('/')
        expected_prefix = str(ConfigService.EMPRESA_UPLOAD_DIR).replace('\\', '/') + '/'
        if not normalized.startswith(expected_prefix):
            return False

        file_path = Path(current_app.root_path) / "static" / normalized
        try:
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
                return True
        except OSError as exc:
            current_app.logger.warning("Não foi possível remover asset antigo de branding %s: %s", normalized, exc)
        return False

    @staticmethod
    def get_login_branding_config() -> dict[str, Any]:
        """Retorna a configuração visual da página de login."""
        config = {
            "login_background_path": ConfigService.DEFAULT_LOGIN_BACKGROUND_PATH,
            "login_card_image_path": None,
        }

        config_path = ConfigService._branding_config_path()
        if not config_path.exists():
            return config

        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            current_app.logger.warning("Não foi possível ler branding do login em %s: %s", config_path, exc)
            return config

        if isinstance(payload, dict):
            for key in ("login_background_path", "login_card_image_path"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    config[key] = value.strip().replace('\\', '/')
                elif value in (None, ""):
                    config[key] = None if key == "login_card_image_path" else ConfigService.DEFAULT_LOGIN_BACKGROUND_PATH

        return config

    @staticmethod
    def update_login_branding_config(data: dict[str, Any]) -> dict[str, Any]:
        """Atualiza e persiste a configuração visual da página de login."""
        config = ConfigService.get_login_branding_config()
        previous_config = dict(config)
        allowed_keys = {"login_background_path", "login_card_image_path"}

        for key, value in data.items():
            if key not in allowed_keys:
                continue
            normalized = str(value).strip().replace('\\', '/') if value not in (None, "") else None
            if key == "login_background_path":
                config[key] = normalized or ConfigService.DEFAULT_LOGIN_BACKGROUND_PATH
            else:
                config[key] = normalized

            old_value = previous_config.get(key)
            new_value = config.get(key)
            if old_value and old_value != new_value:
                ConfigService._delete_uploaded_empresa_asset(old_value)

        config_path = ConfigService._branding_config_path()
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        return config

    @staticmethod
    def clear_login_branding_asset(config_key: str) -> dict[str, Any]:
        """Remove um asset configurado do login e volta para o fallback."""
        if config_key not in {"login_background_path", "login_card_image_path"}:
            raise ValueError("Chave de branding inválida")

        current_config = ConfigService.get_login_branding_config()
        ConfigService._delete_uploaded_empresa_asset(current_config.get(config_key))

        fallback_value = None
        if config_key == "login_background_path":
            fallback_value = ConfigService.DEFAULT_LOGIN_BACKGROUND_PATH

        return ConfigService.update_login_branding_config({config_key: fallback_value})
    
    @staticmethod
    def set_logo(logo_path: str) -> EmpresaConfig:
        """Define o logo da empresa."""
        config = ConfigService.get_empresa_config()
        config.logo_path = logo_path
        config.atualizado_em = datetime.utcnow()
        db.session.commit()
        
        return config
    
    @staticmethod
    def get_relatorio_config() -> RelatorioConfig:
        """Retorna configuração de relatórios."""
        config = RelatorioConfig.query.first()
        
        if not config:
            config = RelatorioConfig(
                cabecalho_template=ConfigService.CABECALHO_PADRAO,
                rodape_template=ConfigService.RODAPE_PADRAO
            )
            db.session.add(config)
            db.session.commit()
        
        return config
    
    @staticmethod
    def update_relatorio_config(data: dict[str, Any]) -> RelatorioConfig:
        """Atualiza configuração de relatórios."""
        config = ConfigService.get_relatorio_config()
        
        # Atualizar campos
        campos_permitidos = [
            'cabecalho_template', 'cabecalho_altura_mm', 'cabecalho_mostrar_logo',
            'cabecalho_cor_texto', 'cabecalho_fonte', 'cabecalho_tamanho_fonte',
            'rodape_template', 'rodape_altura_mm', 'rodape_cor_texto',
            'rodape_tamanho_fonte', 'rodape_mostrar_data', 'rodape_mostrar_pagina',
            'cor_primaria', 'cor_secundaria', 'cor_sucesso', 'cor_perigo', 'cor_aviso',
            'fonte_principal', 'fonte_tabelas'
        ]
        
        for campo in campos_permitidos:
            if campo in data:
                setattr(config, campo, data[campo])
        
        config.atualizado_em = datetime.utcnow()
        db.session.commit()
        
        return config
    
    @staticmethod
    def render_cabecalho(**kwargs) -> str:
        """Renderiza o cabeçalho do relatório com os dados fornecidos."""
        config_rel = ConfigService.get_relatorio_config()
        config_emp = ConfigService.get_empresa_config()
        
        # Preparar contexto
        context = {
            "nome_empresa": config_emp.nome_empresa,
            "nome_fantasia": config_emp.nome_fantasia,
            "cnpj": config_emp.cnpj,
            "telefone": config_emp.telefone,
            "telefone_secundario": config_emp.telefone_secundario,
            "email": config_emp.email,
            "site": config_emp.site,
            "endereco_completo": config_emp.get_endereco_completo(),
            **kwargs  # Permite passar variáveis adicionais
        }
        
        # Renderizar template
        template = Template(config_rel.cabecalho_template or ConfigService.CABECALHO_PADRAO)
        return template.render(**context)
    
    @staticmethod
    def render_rodape(**kwargs) -> str:
        """Renderiza o rodapé do relatório com os dados fornecidos."""
        config_rel = ConfigService.get_relatorio_config()
        
        # Preparar contexto padrão
        now = datetime.now()
        context = {
            "data_geracao": now.strftime("%d/%m/%Y"),
            "hora_geracao": now.strftime("%H:%M:%S"),
            "versao": "1.0.0",  # TODO: Pegar da configuração
            "pagina": kwargs.get("pagina", "1"),
            **kwargs
        }
        
        # Renderizar template
        template = Template(config_rel.rodape_template or ConfigService.RODAPE_PADRAO)
        return template.render(**context)
    
    @staticmethod
    def marcar_setup_completo() -> None:
        """Marca o setup inicial como completo."""
        config = ConfigService.get_empresa_config()
        config.primeira_execucao = False
        config.setup_completo = True
        config.atualizado_em = datetime.utcnow()
        db.session.commit()
    
    @staticmethod
    def resetar_para_primeira_execucao() -> None:
        """Reseta o sistema para primeira execução (útil para testes)."""
        config = ConfigService.get_empresa_config()
        config.primeira_execucao = True
        config.setup_completo = False
        db.session.commit()


# Instância global
config_service = ConfigService()
