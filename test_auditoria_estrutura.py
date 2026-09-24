"""Guardas de estrutura levantadas na auditoria de 24/09/2026.

Defeitos que originaram:
- Templates legados (form_old, form_tabs, sidebar_clean, movements/saida.html,
  telegram_service.py.bak_modelo3...) ficavam no repositorio depois de
  substituidos, e alguem acabava editando a copia errada.
- Utilitarios iguais (escapeHtml, normalizeAutocompleteText, formatCurrencyBR)
  estavam copiados em mais de dez telas, cada copia com um comportamento
  ligeiramente diferente para valor nulo.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess

import pytest

os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

RAIZ = pathlib.Path(__file__).parent / "galint_flask"
TEMPLATES = RAIZ / "templates"
TEMPLATES_MAKO = RAIZ / "templates_mako"

# Telas ativas que passaram a usar o utilitario central.
TELAS_CENTRALIZADAS = (
    TEMPLATES_MAKO / "movements" / "saida.mako",
    TEMPLATES_MAKO / "movements" / "saida_fracionada.mako",
    TEMPLATES_MAKO / "ferramentas" / "retirar.mako",
    TEMPLATES / "movements" / "entrada.html",
)


def _arquivos_python() -> list[pathlib.Path]:
    return [p for p in RAIZ.rglob("*.py") if "__pycache__" not in p.as_posix()]


def test_toda_rota_aponta_para_um_template_que_existe() -> None:
    quebradas: list[str] = []
    for caminho in _arquivos_python():
        fonte = caminho.read_text(encoding="utf-8-sig", errors="ignore")
        for achado in re.finditer(r"render_template\(\s*[\"']([^\"']+\.html)[\"']", fonte):
            if not (TEMPLATES / achado.group(1)).exists():
                quebradas.append(f"{caminho.name} -> templates/{achado.group(1)}")
        for achado in re.finditer(r"render_mako_template\(\s*[\"']([^\"']+\.mako)[\"']", fonte):
            if not (TEMPLATES_MAKO / achado.group(1)).exists():
                quebradas.append(f"{caminho.name} -> templates_mako/{achado.group(1)}")

    assert quebradas == [], f"templates referenciados que nao existem: {quebradas}"


def test_repositorio_versionado_sem_copias_de_backup() -> None:
    """Só olha o que está versionado: cópias locais nao rastreadas sao do operador."""
    saida = subprocess.run(
        ["git", "ls-files", "galint_flask"],
        cwd=pathlib.Path(__file__).parent,
        capture_output=True,
        text=True,
        check=False,
    )
    if saida.returncode != 0:
        pytest.skip("git indisponivel neste ambiente")

    # config_backup.html e a tela de backups do sistema, nao uma copia.
    telas_legitimas = {"galint_flask/templates/config_backup.html"}
    suspeitos = [
        linha
        for linha in saida.stdout.splitlines()
        if linha not in telas_legitimas
        and re.search(r"(\.bak(_\w+)?$|_old\.\w+$|\.orig$|_backup\.(html|py|js)$|\bcopy\b)", linha)
    ]

    assert suspeitos == [], f"copias de backup nao devem ser versionadas: {suspeitos}"


def test_utilitario_central_existe_e_exporta_as_funcoes_esperadas() -> None:
    core = (RAIZ / "static" / "js" / "galint-core.js").read_text(encoding="utf-8")

    for funcao in (
        "escapeHtml",
        "normalizeText",
        "formatCurrencyBR",
        "formatNumberBR",
        "formatDateTimeBR",
        "focusWithoutScroll",
    ):
        assert f"{funcao}: {funcao}" in core, f"GalintCore deveria exportar {funcao}"


def test_layouts_base_carregam_o_utilitario_central() -> None:
    base_jinja = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    base_mako = (TEMPLATES_MAKO / "base.mako").read_text(encoding="utf-8")

    assert "js/galint-core.js" in base_jinja
    assert "js/galint-core.js" in base_mako


def test_telas_de_movimentacao_nao_reimplementam_os_utilitarios() -> None:
    reimplementacoes: list[str] = []
    for caminho in TELAS_CENTRALIZADAS:
        fonte = caminho.read_text(encoding="utf-8")
        for funcao in ("escapeHtml", "normalizeAutocompleteText", "formatCurrencyBR"):
            achado = re.search(
                r"function\s+" + funcao + r"\s*\([^)]*\)\s*\{(?P<corpo>[^}]*)\}",
                fonte,
                re.S,
            )
            if achado and "GalintCore" not in achado.group("corpo"):
                reimplementacoes.append(f"{caminho.name}:{funcao}")

    assert reimplementacoes == [], f"devem delegar ao GalintCore: {reimplementacoes}"


def test_tela_de_saida_nao_usa_onclick_inline_na_lista() -> None:
    fonte = (TEMPLATES_MAKO / "movements" / "saida.mako").read_text(encoding="utf-8")

    # Os botoes da lista passaram a usar data-item-action + listener delegado;
    # onclick inline voltava a quebrar o foco e o scroll da pagina.
    assert "onclick=\"adjustQueuedItemQuantity(" not in fonte
    assert "onclick=\"removeItem(" not in fonte
    assert 'data-item-action="qty"' in fonte
    assert 'data-item-action="remove"' in fonte


def test_foco_da_tela_de_saida_nao_arrasta_a_pagina() -> None:
    fonte = (TEMPLATES_MAKO / "movements" / "saida.mako").read_text(encoding="utf-8")

    assert "preventScroll: true" in fonte
    assert "restoreQuantityButtonFocus" in fonte
