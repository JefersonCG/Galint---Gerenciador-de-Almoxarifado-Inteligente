"""Busca visual, Fase 0 (26/11/2026): exporta os itens com foto para o teste, SÓ LENDO o banco.

Roda com o Python do GALINT (tem psycopg2):
    .venv\\Scripts\\python.exe busca_visual\\fase0_exportar_itens.py C:\\ia-visual\\fase0\\itens.json

Lê o DATABASE_URL do .env do D: com a sessão em modo somente leitura; grava codigo, descricao, categoria,
marca, unidade e o caminho completo da foto.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import psycopg2

GALINT = Path(r"D:\Jeferson dos Santos\Projetos\GALINT 08.04.2026")
STATIC = GALINT / "galint_flask" / "static"


def database_url() -> str:
    for line in (GALINT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if line.strip().startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip('"').strip("'")
            return re.sub(r"^postgresql\+\w+://", "postgresql://", url)
    raise SystemExit("DATABASE_URL não encontrado no .env do GALINT")


def main(destino: str) -> None:
    conn = psycopg2.connect(database_url())
    conn.set_session(readonly=True)
    cur = conn.cursor()
    cur.execute(
        """select codigo_item, descricao, coalesce(categoria, ''), coalesce(marca, ''), coalesce(unidade, ''), foto_path
             from itens where coalesce(trim(foto_path), '') <> '' order by codigo_item"""
    )
    itens, sem_arquivo = [], 0
    for codigo, descricao, categoria, marca, unidade, foto in cur.fetchall():
        caminho = STATIC / foto.replace("\\", "/")
        if not caminho.is_file():
            sem_arquivo += 1
            continue
        itens.append({"codigo": codigo, "descricao": descricao, "categoria": categoria, "marca": marca, "unidade": unidade, "foto": str(caminho)})
    conn.close()
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    Path(destino).write_text(json.dumps(itens, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(itens)} itens com foto exportados; {sem_arquivo} com foto apontada mas sem o arquivo.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else r"C:\ia-visual\fase0\itens.json")
