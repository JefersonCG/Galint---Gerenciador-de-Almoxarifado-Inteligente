"""Serviço para gerenciar configurações da empresa e relatórios."""
from __future__ import annotations

import os
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
            'logo_width', 'logo_height', 'primeira_execucao', 'setup_completo'
        ]
        
        for campo in campos_permitidos:
            if campo in data:
                setattr(config, campo, data[campo])
        
        config.atualizado_em = datetime.utcnow()
        db.session.commit()
        
        return config
    
    @staticmethod
    def upload_logo(file) -> str:
        """Upload do logo da empresa."""
        if not file or not file.filename:
            raise ValueError("Arquivo de logo inválido")
        
        # Validar extensão
        extensoes_permitidas = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        filename = secure_filename(file.filename)
        extensao = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        if extensao not in extensoes_permitidas:
            raise ValueError(f"Extensão não permitida. Use: {', '.join(extensoes_permitidas)}")
        
        # Gerar nome único
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        novo_filename = f"logo_empresa_{timestamp}.{extensao}"
        
        # Criar diretório se não existir
        upload_folder = Path(current_app.root_path) / "static" / "uploads" / "empresa"
        upload_folder.mkdir(parents=True, exist_ok=True)
        
        # Salvar arquivo
        filepath = upload_folder / novo_filename
        file.save(str(filepath))
        
        # Retornar caminho relativo
        return f"uploads/empresa/{novo_filename}"
    
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
