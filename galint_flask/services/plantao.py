"""Plantão de quem usa o app (27/11/2026).

Pedido do usuário: "agora todos eles [supervisão e zeladoria] são plantonista 12 por 36, pegam de 07h às 19h; sempre
que encerrar essa carga horária o sistema deslogará o usuário, para ninguém usar o usuário dele".

Cada usuário pode ter `plantao_inicio` e `plantao_fim` ("07:00" e "19:00"; vazio = sem plantão). O login pelo app só
passa dentro do plantão (com 30 minutos de folga antes do início, para quem chega cedo), o token vence no fim dele e
todo pedido do app depois do fim é recusado. Plantão que vira a noite ("19:00" às "07:00") também vale.
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import Any

FOLGA_ANTES = timedelta(minutes=30)
_HORA = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def normalizar_hora(valor: Any) -> str | None:
    """'7:00', '07:00', '7h' → '07:00'; vazio ou inválido → None."""
    texto = str(valor or "").strip().lower().replace("h", ":").rstrip(":")
    if not texto:
        return None
    if texto.isdigit():
        texto = f"{texto}:00"
    achado = _HORA.match(texto)
    if not achado:
        return None
    return f"{int(achado.group(1)):02d}:{achado.group(2)}"


def _hora(valor: str) -> time:
    horas, minutos = valor.split(":")
    return time(int(horas), int(minutos))


def tem_plantao(usuario: Any) -> bool:
    return bool(normalizar_hora(getattr(usuario, "plantao_inicio", None)) and normalizar_hora(getattr(usuario, "plantao_fim", None)))


def janela(inicio: Any, fim: Any, agora: datetime) -> tuple[datetime, datetime] | None:
    """O plantão em que `agora` (hora local) está, como (começo, fim); None fora dele ou sem plantão."""
    hora_inicio = normalizar_hora(inicio)
    hora_fim = normalizar_hora(fim)
    if not hora_inicio or not hora_fim:
        return None
    duracao = datetime.combine(agora.date(), _hora(hora_fim)) - datetime.combine(agora.date(), _hora(hora_inicio))
    if duracao <= timedelta(0):
        duracao += timedelta(days=1)  # vira a noite (19:00 às 07:00) ou 24 h
    for dias_atras in (0, 1):
        comeco = datetime.combine(agora.date() - timedelta(days=dias_atras), _hora(hora_inicio), tzinfo=agora.tzinfo)
        if comeco - FOLGA_ANTES <= agora < comeco + duracao:
            return comeco, comeco + duracao
    return None


def janela_do_usuario(usuario: Any, agora: datetime) -> tuple[datetime, datetime] | None:
    return janela(getattr(usuario, "plantao_inicio", None), getattr(usuario, "plantao_fim", None), agora)


def fora_do_plantao(usuario: Any, agora: datetime) -> bool:
    """Tem plantão e `agora` está fora dele (sem plantão: nunca)."""
    return tem_plantao(usuario) and janela_do_usuario(usuario, agora) is None


def rotulo(usuario: Any) -> str:
    """'07h às 19h' (ou '07h30 às 19h')."""
    def curto(valor: str) -> str:
        horas, minutos = valor.split(":")
        return f"{horas}h" if minutos == "00" else f"{horas}h{minutos}"

    inicio = normalizar_hora(getattr(usuario, "plantao_inicio", None))
    fim = normalizar_hora(getattr(usuario, "plantao_fim", None))
    return f"{curto(inicio)} às {curto(fim)}" if inicio and fim else ""
