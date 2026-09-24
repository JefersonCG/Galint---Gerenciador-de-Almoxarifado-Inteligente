"""Regressoes do padrao unico de data/hora do GALINT.

Defeito que originou: cada parte do sistema gravava a hora de um jeito
(`datetime.utcnow()`, `datetime.now()`, `datetime.now(timezone.utc)` e
`func.now()`), entao o mesmo lancamento aparecia com 3 horas de diferenca entre
tabelas (saida 09:42 x movimento de estoque 12:42) e a tela exibia 06:42 para
uma saida registrada as 09:42.

Convencao fixada: o banco guarda hora de Sao Paulo sem tzinfo e toda escrita
passa por TimeService.now_db().
"""

from __future__ import annotations

import ast
import os
import pathlib
import re
from datetime import datetime, timedelta, timezone

os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")

from galint_flask.utils.time_service import TimeService, get_local_tz

RAIZ = pathlib.Path(__file__).parent / "galint_flask"

# Arquivos que legitimamente trabalham em UTC: sessao web, backups, logs tecnicos
# em SQLite e integracoes externas gravam ISO com fuso explicito.
ARQUIVOS_FORA_DA_CONVENCAO = {
    "galint_flask/__init__.py",
    "galint_flask/services/auth.py",
    "galint_flask/services/backup.py",
    "galint_flask/services/backup_restore_jobs.py",
    "galint_flask/services/admin_stock_audit_sqlite.py",
    "galint_flask/services/nf_deletion_audit_sqlite.py",
    "galint_flask/services/user_deletion_archive_sqlite.py",
    "galint_flask/services/user_deletion_archive.py",
    "galint_flask/services/update_service.py",
    "galint_flask/services/mirror_state_service.py",
    "galint_flask/services/conversion_engine.py",
    "galint_flask/services/scheduler_service.py",
    "galint_flask/utils/time_service.py",
}


def _arquivos_python() -> list[pathlib.Path]:
    return [
        caminho
        for caminho in RAIZ.rglob("*.py")
        if "__pycache__" not in caminho.as_posix()
        and caminho.as_posix().split("GALINT 08.04.2026/")[-1] not in ARQUIVOS_FORA_DA_CONVENCAO
        and "/".join(caminho.as_posix().split("/")[-3:]) not in ARQUIVOS_FORA_DA_CONVENCAO
    ]


def _relativo(caminho: pathlib.Path) -> str:
    return "galint_flask/" + caminho.relative_to(RAIZ).as_posix()


def test_now_db_devolve_hora_local_sem_tzinfo() -> None:
    agora = TimeService.now_db()

    assert agora.tzinfo is None
    assert abs((agora - datetime.now()).total_seconds()) < 90


def test_hora_gravada_e_hora_exibida_sao_iguais() -> None:
    gravado = datetime(2026, 9, 24, 9, 42, 3)

    assert TimeService.format_local(gravado) == "24/09/2026 09:42"


def test_datetime_do_banco_vira_utc_correto_para_api() -> None:
    gravado = datetime(2026, 9, 24, 9, 42, 3)

    assert TimeService.isoformat_utc(gravado) == "2026-09-24T12:42:03Z"


def test_datetime_com_fuso_continua_sendo_convertido() -> None:
    com_fuso = datetime(2026, 9, 24, 12, 42, 3, tzinfo=timezone.utc)

    assert TimeService.format_local(com_fuso) == "24/09/2026 09:42"
    assert TimeService.as_db_naive(com_fuso) == datetime(2026, 9, 24, 9, 42, 3)


def test_as_db_naive_preserva_datetime_ja_no_padrao() -> None:
    gravado = datetime(2026, 9, 24, 9, 42, 3)

    assert TimeService.as_db_naive(gravado) is gravado
    assert TimeService.as_db_naive(None) is None


def test_expediente_usa_a_hora_local_do_registro() -> None:
    dentro = datetime(2026, 9, 24, 9, 42, 3)
    fora = datetime(2026, 9, 24, 18, 5, 0)

    assert TimeService.is_within_business_hours(dentro) is True
    assert TimeService.is_within_business_hours(fora) is False
    assert TimeService.get_business_day_tag(fora) == "APÓS O EXPEDIENTE"


def test_ida_e_volta_entre_banco_e_fuso_nao_desloca_a_hora() -> None:
    gravado = TimeService.now_db()
    convertido = TimeService.as_db_naive(TimeService.to_local(gravado))

    assert convertido == gravado
    assert TimeService.to_utc(gravado) - timedelta(hours=3) == gravado.replace(tzinfo=timezone.utc)


def test_nenhum_arquivo_de_negocio_usa_utcnow() -> None:
    infratores = [
        _relativo(caminho)
        for caminho in _arquivos_python()
        if "datetime.utcnow()" in caminho.read_text(encoding="utf-8-sig")
    ]

    assert infratores == [], f"use TimeService.now_db() nestes arquivos: {infratores}"


def test_nenhum_modelo_usa_default_de_hora_fora_do_timeservice() -> None:
    fonte = (RAIZ / "models.py").read_text(encoding="utf-8-sig")

    # server_default=func.now() continua valendo como rede de seguranca no DDL:
    # o default da aplicacao e que precisa ser o TimeService.
    assert re.search(r"(?<!server_)default=func\.now\(\)", fonte) is None
    assert "onupdate=func.now()" not in fonte
    assert "default=datetime.utcnow" not in fonte
    assert "datetime.now()" not in fonte


def test_arquivos_alterados_continuam_com_sintaxe_valida() -> None:
    for caminho in _arquivos_python():
        ast.parse(caminho.read_text(encoding="utf-8-sig"), filename=str(caminho))


def test_fuso_do_projeto_e_sao_paulo() -> None:
    assert str(get_local_tz()) in {"America/Sao_Paulo", "UTC"}


def test_fonte_de_hora_sem_fuso_e_lida_como_utc() -> None:
    """timeapi.io responde `2026-09-24T14:40:00` (UTC, sem fuso).

    Antes, `.astimezone()` sobre esse valor sem fuso fazia o Python assumir o
    fuso da maquina: o relogio do sistema inteiro adiantava 3 horas sempre que
    essa fonte era usada, de forma intermitente.
    """
    from galint_flask.utils.time_service import _parse_iso_utc

    referencia = datetime(2026, 9, 24, 14, 40, tzinfo=timezone.utc)

    assert _parse_iso_utc("2026-09-24T14:40:00") == referencia
    assert _parse_iso_utc("2026-09-24T14:40:00Z") == referencia
    assert _parse_iso_utc("2026-09-24T11:40:00-03:00") == referencia
    assert _parse_iso_utc("") is None
    assert _parse_iso_utc("isso nao e data") is None


def test_sincronizacao_recusa_correcao_absurda() -> None:
    """Uma fonte que peca 3 horas de ajuste esta errada, nao o relogio do servidor."""
    from galint_flask.utils.time_service import NetworkTimeResult

    offset_original = TimeService._offset_seconds
    ultima_falha = TimeService._last_failure_monotonic
    ultima_sync = TimeService._last_sync_monotonic
    try:
        TimeService._offset_seconds = 0.0
        TimeService._last_failure_monotonic = 0.0
        TimeService._last_sync_monotonic = 0.0

        adiantada = datetime.now(timezone.utc) + timedelta(hours=3)
        TimeService._sync_from_network = classmethod(  # type: ignore[method-assign]
            lambda cls: NetworkTimeResult(utc_datetime=adiantada, source="fonte-de-teste")
        )
        TimeService.sync()

        assert TimeService._offset_seconds == 0.0, "correcao de 3 horas deveria ter sido recusada"
    finally:
        del TimeService._sync_from_network  # type: ignore[attr-defined]
        TimeService._offset_seconds = offset_original
        TimeService._last_failure_monotonic = ultima_falha
        TimeService._last_sync_monotonic = ultima_sync


def test_sincronizacao_aceita_ajuste_pequeno() -> None:
    from galint_flask.utils.time_service import NetworkTimeResult

    offset_original = TimeService._offset_seconds
    ultima_falha = TimeService._last_failure_monotonic
    ultima_sync = TimeService._last_sync_monotonic
    try:
        TimeService._offset_seconds = 0.0
        TimeService._last_failure_monotonic = 0.0
        TimeService._last_sync_monotonic = 0.0

        proxima = datetime.now(timezone.utc) + timedelta(seconds=12)
        TimeService._sync_from_network = classmethod(  # type: ignore[method-assign]
            lambda cls: NetworkTimeResult(utc_datetime=proxima, source="fonte-de-teste")
        )
        TimeService.sync()

        assert 8 <= TimeService._offset_seconds <= 16
    finally:
        del TimeService._sync_from_network  # type: ignore[attr-defined]
        TimeService._offset_seconds = offset_original
        TimeService._last_failure_monotonic = ultima_falha
        TimeService._last_sync_monotonic = ultima_sync


def test_fuso_do_projeto_nunca_cai_para_utc() -> None:
    """Sem o banco de fusos (tzdata), o fallback anterior era UTC — e o sistema

    passaria a gravar tudo 3 horas adiantado sem ninguem perceber.
    """
    agora = TimeService.now_local()
    deslocamento = agora.utcoffset()

    assert deslocamento is not None
    assert deslocamento == timedelta(hours=-3), f"fuso resolvido: {agora.tzinfo} ({deslocamento})"
