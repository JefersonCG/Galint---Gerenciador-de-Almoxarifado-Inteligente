"""Versões do app Android publicadas pelo próprio GALINT (atualização sozinha, como no Pipocas).

Pedido do usuário em 23/11/2026: "será possível essa atualização subir sozinha para o APK? Igual ao
do Pipocas?". Até aqui cada versão nova era instalada à mão, celular por celular (em 23/11 os
aparelhos estavam espalhados entre a 1.2.2 e a 2.2.3), e a atualização pelo ar (EAS Update) depende
de uma conta Expo que este servidor não usa.

Publicar uma versão = pôr o APK em instance/apks/ com o nome GALINT-<versão>-codigo<código>[-<rótulo>].apk
(o mesmo nome que sai de galint-mobile/build-output). Um .txt com o mesmo nome, se existir, vira a
nota da versão. O app pergunta /api/mobile/app/atualizacao, baixa /api/mobile/app/apk/<código> e
abre o instalador do Android.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from flask import current_app

APK_NAME = re.compile(r"^GALINT-(?P<name>\d+(?:\.\d+)*)-codigo(?P<code>\d+)(?:-[\w.-]+)?\.apk$", re.IGNORECASE)
_SHA_CACHE: dict[tuple[str, float, int], str] = {}


def releases_dir() -> Path:
    return Path(current_app.instance_path) / "apks"


def _sha256(path: Path) -> str:
    stat = path.stat()
    key = (str(path), stat.st_mtime, stat.st_size)
    if key not in _SHA_CACHE:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        _SHA_CACHE[key] = digest.hexdigest()
    return _SHA_CACHE[key]


def list_releases() -> list[dict[str, Any]]:
    folder = releases_dir()
    if not folder.is_dir():
        return []
    releases = []
    for path in folder.iterdir():
        match = APK_NAME.match(path.name)
        if not match or not path.is_file():
            continue
        notes_file = path.with_suffix(".txt")
        releases.append({
            "version_name": match.group("name"),
            "version_code": int(match.group("code")),
            "file": path,
            "tamanho": path.stat().st_size,
            "notas": notes_file.read_text(encoding="utf-8").strip() if notes_file.is_file() else "",
        })
    return sorted(releases, key=lambda release: release["version_code"], reverse=True)


def latest_release() -> dict[str, Any] | None:
    releases = list_releases()
    if not releases:
        return None
    latest = dict(releases[0])
    latest["sha256"] = _sha256(latest["file"])
    return latest


def release_file(version_code: int) -> Path | None:
    for release in list_releases():
        if release["version_code"] == version_code:
            return release["file"]
    return None
