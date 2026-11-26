"""Lado do GALINT do "Será que temos!?" (busca visual, 26/11/2026).

O serviço de visão (busca_visual/servico.py) roda à parte, no ambiente C:\\ia-visual\\venv, só em 127.0.0.1. Aqui:
- escrever_catalogo(): as fotos de cada item (cadastro + referências confirmadas) em instance/busca_visual/catalogo.json,
  que o serviço lê para manter o índice;
- garantir_ligado(): o serviço não fica ligado o tempo todo (os modelos ocupam ~1,2 GB num PC de 8 GB). A primeira
  busca o liga, em prioridade baixa; ele se desliga sozinho depois de 20 minutos sem uso;
- guardar_consulta() / consultar() / confirmar(): a foto do app, a busca e a foto confirmada virando referência.

Nos testes (TESTING) o serviço nunca é ligado.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from flask import current_app
from PIL import Image, ImageOps

from ..extensions import db
from ..models import BuscaVisualReferencia, Item

PORTA = 5077
PYTHON_PADRAO = r"C:\ia-visual\venv\Scripts\python.exe"
LADO_MAXIMO = 1024
CATALOGO_VALE_S = 120
CONSULTA_VALE_S = 2 * 24 * 3600
_ID = re.compile(r"^[0-9a-f]{32}$")

_trava_inicio = threading.Lock()
_iniciado_em = 0.0


class BuscaVisualIndisponivel(RuntimeError):
    pass


def pasta() -> Path:
    destino = Path(current_app.instance_path) / "busca_visual"
    (destino / "consultas").mkdir(parents=True, exist_ok=True)
    (destino / "referencias").mkdir(parents=True, exist_ok=True)
    return destino


def _python() -> Path:
    return Path(os.environ.get("GALINT_BUSCA_VISUAL_PYTHON") or current_app.config.get("BUSCA_VISUAL_PYTHON") or PYTHON_PADRAO)


def _script() -> Path:
    return Path(current_app.root_path).parent / "busca_visual" / "servico.py"


def disponivel() -> bool:
    if current_app.config.get("TESTING"):
        return bool(current_app.config.get("BUSCA_VISUAL_TESTE"))
    return _python().is_file() and _script().is_file()


def _chamar(metodo: str, caminho: str, corpo: dict | None = None, timeout: float = 30.0) -> tuple[int, dict] | None:
    """(status, json) do serviço, ou None se ele não estiver ouvindo."""
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    pedido = urlrequest.Request(f"http://127.0.0.1:{PORTA}{caminho}", data=dados, method=metodo,
                                headers={"Content-Type": "application/json"})
    try:
        with urlrequest.urlopen(pedido, timeout=timeout) as resposta:
            return resposta.status, json.loads(resposta.read().decode("utf-8") or "{}")
    except urlerror.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read().decode("utf-8") or "{}")
        except ValueError:
            return erro.code, {}
    except (urlerror.URLError, OSError, ValueError):
        return None


def iniciar() -> None:
    """Liga o serviço (uma vez a cada 2 minutos, no máximo), separado do GALINT e em prioridade baixa."""
    global _iniciado_em
    if current_app.config.get("TESTING"):
        return
    with _trava_inicio:
        if time.monotonic() - _iniciado_em < 120:
            return
        _iniciado_em = time.monotonic()
        dados = pasta()
        registro = open(dados / "servico.log", "ab")  # noqa: SIM115 — fica com o processo filho
        opcoes = 0
        if os.name == "nt":
            opcoes = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.BELOW_NORMAL_PRIORITY_CLASS
        subprocess.Popen(
            [str(_python()), str(_script()), "--dados", str(dados), "--porta", str(PORTA)],
            cwd=str(_script().parent),
            stdout=registro,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=opcoes,
            close_fds=True,
        )
        registro.close()
        current_app.logger.info("Será que temos!?: serviço de busca visual ligado.")


def garantir_ligado() -> dict | None:
    """Saúde do serviço; None (e manda ligar) se ele não estiver no ar."""
    resposta = _chamar("GET", "/saude", timeout=2)
    if resposta is None:
        iniciar()
        return None
    return resposta[1]


def escrever_catalogo(forcar: bool = False) -> None:
    """Fotos de cada item para o índice: a do cadastro e as confirmadas no app."""
    destino = pasta() / "catalogo.json"
    if not forcar and destino.is_file() and time.time() - destino.stat().st_mtime < CATALOGO_VALE_S:
        return
    estaticos = Path(current_app.static_folder or "")
    fotos: list[dict[str, str]] = []
    linhas = (
        db.session.query(Item.codigo_item, Item.foto_path)
        .filter(Item.foto_path.isnot(None), Item.foto_path != "")
        .filter(Item.pre_cadastro_pendente.isnot(True))
        .all()
    )
    for codigo, foto in linhas:
        arquivo = estaticos / str(foto).replace("\\", "/")
        if arquivo.is_file():
            fotos.append({"codigo": codigo, "arquivo": str(arquivo), "origem": "cadastro"})
    codigos_validos = {row[0] for row in db.session.query(Item.codigo_item).all()}
    for referencia in BuscaVisualReferencia.query.all():
        arquivo = pasta() / referencia.arquivo
        if referencia.codigo_item in codigos_validos and arquivo.is_file():
            fotos.append({"codigo": referencia.codigo_item, "arquivo": str(arquivo), "origem": "referencia"})
    temporario = destino.with_suffix(".tmp")
    temporario.write_text(json.dumps({"gerado_em": time.time(), "fotos": fotos}, ensure_ascii=False), encoding="utf-8")
    os.replace(temporario, destino)


def _limpar_consultas_velhas(consultas: Path) -> None:
    limite = time.time() - CONSULTA_VALE_S
    for arquivo in consultas.glob("*.jpg"):
        try:
            if arquivo.stat().st_mtime < limite:
                arquivo.unlink()
        except OSError:
            pass


def guardar_consulta(arquivo_enviado) -> str:
    """Grava a foto do app como JPEG de até 1024 px. Devolve o número da consulta."""
    try:
        imagem = ImageOps.exif_transpose(Image.open(arquivo_enviado.stream))
        imagem.load()
    except Exception as erro:
        raise ValueError("Foto inválida.") from erro
    imagem = imagem.convert("RGB")
    imagem.thumbnail((LADO_MAXIMO, LADO_MAXIMO), Image.Resampling.LANCZOS)
    consultas = pasta() / "consultas"
    _limpar_consultas_velhas(consultas)
    consulta = uuid.uuid4().hex
    imagem.save(consultas / f"{consulta}.jpg", format="JPEG", quality=88)
    return consulta


def _arquivo_da_consulta(consulta: str) -> Path:
    if not _ID.match(str(consulta or "")):
        raise ValueError("Consulta inválida.")
    arquivo = pasta() / "consultas" / f"{consulta}.jpg"
    if not arquivo.is_file():
        raise ValueError("Esta foto já não está mais no servidor. Tire outra.")
    return arquivo


def consultar(consulta: str, quantos: int = 5) -> dict[str, Any]:
    """{"pronto": False} enquanto o serviço liga; {"pronto": True, "resultados": [...]} quando responde."""
    arquivo = _arquivo_da_consulta(consulta)
    if not disponivel():
        raise BuscaVisualIndisponivel("O Será que temos!? não está instalado neste servidor.")
    escrever_catalogo()
    resposta = _chamar("POST", "/buscar", {"arquivo": str(arquivo), "quantos": quantos}, timeout=60)
    if resposta is None:
        iniciar()
        return {"pronto": False}
    status, corpo = resposta
    if status == 503:
        if corpo.get("erro"):
            raise BuscaVisualIndisponivel("A busca visual não conseguiu carregar os modelos.")
        return {"pronto": False}
    if status != 200:
        raise BuscaVisualIndisponivel(corpo.get("erro") or "A busca visual não respondeu.")
    return {"pronto": True, "resultados": list(corpo.get("resultados") or []), "ms": corpo.get("ms")}


def confirmar(consulta: str, codigo: str, *, matricula: str | None) -> None:
    """A foto da consulta vira referência do item escolhido (e o índice a recebe na próxima sincronização)."""
    arquivo = _arquivo_da_consulta(consulta)
    if db.session.get(Item, codigo) is None:
        raise ValueError("Item não encontrado.")
    relativo = f"referencias/{consulta}.jpg"
    if BuscaVisualReferencia.query.filter_by(arquivo=relativo).first() is not None:
        return
    shutil.copy2(arquivo, pasta() / relativo)
    db.session.add(BuscaVisualReferencia(codigo_item=codigo, arquivo=relativo, criado_por=matricula))
    db.session.commit()
    escrever_catalogo(forcar=True)
    if not current_app.config.get("TESTING"):
        _chamar("POST", "/sincronizar", {}, timeout=2)
