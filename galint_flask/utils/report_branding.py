"""Helpers de padronização de cabeçalhos de relatórios.

Centraliza a obtenção do cabeçalho da empresa a partir das configurações
salvas (EmpresaConfig/RelatorioConfig).
"""

from __future__ import annotations

from ..services.config_service import ConfigService


def get_company_header_text(**kwargs) -> str:
    """Retorna o cabeçalho da empresa em texto (com quebras de linha)."""
    try:
        return (ConfigService.render_cabecalho(**kwargs) or "").strip()
    except Exception:
        # Em alguns fluxos (threads/background) pode não haver app context/db session.
        # Não deve derrubar a geração do relatório.
        return "Empresa não configurada"


def get_company_header_html(**kwargs) -> str:
    """Retorna o cabeçalho da empresa em HTML simples (com <br/>)."""
    text = get_company_header_text(**kwargs)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "<br/>".join(lines)


def get_company_header_lines(**kwargs) -> list[str]:
    """Retorna o cabeçalho da empresa como lista de linhas (para XLSX)."""
    text = get_company_header_text(**kwargs)
    return [line.strip() for line in text.splitlines() if line.strip()]
