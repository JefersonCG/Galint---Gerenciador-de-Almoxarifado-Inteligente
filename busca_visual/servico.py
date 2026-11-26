"""Serviço do "Será que temos!?" (busca visual, 26/11/2026).

Pedido do usuário: "vamos implantar!" o DINOv2 + OpenCLIP depois da Fase 0 (87% em 1º lugar, 97% entre os 3
primeiros, com os dois juntos). Decisões da avaliação, seguidas aqui:
- só vetores por código de item (várias fotos por item); o estoque continua só no GALINT;
- sem pgvector: com mil e poucas fotos a busca exata em memória leva milissegundos;
- ouve só em 127.0.0.1; o app fala com o GALINT pelo token de sempre, e o GALINT fala com este serviço;
- resposta é lista curta para a pessoa escolher (a Fase 0 mostrou que limiar fixo não serve);
- a foto confirmada pela pessoa vira nova referência do item.

Memória: os dois modelos ocupam ~1,2 GB e o PC tem 8 GB. Por isso o serviço não fica ligado o tempo todo: o
GALINT o liga na primeira busca (services/busca_visual.py), e ele se desliga sozinho depois de N minutos sem uso.
Roda em prioridade abaixo do normal e com 2 núcleos.

Pasta de dados (instance/busca_visual do GALINT):
- catalogo.json   escrito pelo GALINT: as fotos de cada item (cadastro e referências confirmadas);
- indice.json/.npz escrito aqui: os vetores, refeitos só para foto nova ou mudada;
- consultas/      fotos enviadas pelo app (lidas aqui pelo caminho).

Uso:
    C:\\ia-visual\\venv\\Scripts\\python.exe busca_visual\\servico.py --dados <instance>\\busca_visual
    ... --indexar   (só monta o índice e sai)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

PORTA_PADRAO = 5077
LOTE = 8


def _agora() -> str:
    return time.strftime("%d/%m/%Y %H:%M:%S")


def _log(texto: str) -> None:
    print(f"[{_agora()}] {texto}", flush=True)


def assinatura(arquivo: str) -> str | None:
    try:
        info = os.stat(arquivo)
    except OSError:
        return None
    return f"{info.st_mtime_ns}-{info.st_size}"


class Indice:
    """Vetores das fotos dos itens, guardados em indice.json (quem é quem) + indice.npz (os números)."""

    def __init__(self, pasta: Path) -> None:
        self.pasta = Path(pasta)
        self.trava = threading.Lock()
        self.entradas: list[dict] = []
        self.dino = np.zeros((0, 768), dtype=np.float32)
        self.clip = np.zeros((0, 512), dtype=np.float32)
        self._carregar()

    def _carregar(self) -> None:
        lista, numeros = self.pasta / "indice.json", self.pasta / "indice.npz"
        if not lista.is_file() or not numeros.is_file():
            return
        try:
            entradas = json.loads(lista.read_text(encoding="utf-8"))
            with np.load(numeros) as dados:
                dino, clip = dados["dino"].astype(np.float32), dados["clip"].astype(np.float32)
        except Exception as erro:  # índice estragado: refaz do zero
            _log(f"Índice ilegível, refazendo: {erro}")
            return
        if len(entradas) == len(dino) == len(clip):
            self.entradas, self.dino, self.clip = entradas, dino, clip

    def salvar(self) -> None:
        with self.trava:
            entradas, dino, clip = list(self.entradas), self.dino.copy(), self.clip.copy()
        self.pasta.mkdir(parents=True, exist_ok=True)
        temporario_npz = self.pasta / "indice.tmp.npz"
        np.savez(temporario_npz, dino=dino.astype(np.float16), clip=clip.astype(np.float16))
        os.replace(temporario_npz, self.pasta / "indice.npz")
        temporario_json = self.pasta / "indice.tmp.json"
        temporario_json.write_text(json.dumps(entradas, ensure_ascii=False), encoding="utf-8")
        os.replace(temporario_json, self.pasta / "indice.json")

    def podar(self, catalogo: list[dict]) -> list[dict]:
        """Tira do índice o que saiu do catálogo ou mudou; devolve as fotos que faltam vetorizar."""
        desejadas = {}
        for foto in catalogo:
            codigo, arquivo = str(foto.get("codigo") or ""), str(foto.get("arquivo") or "")
            if codigo and arquivo:
                desejadas[(codigo, arquivo)] = str(foto.get("origem") or "cadastro")
        with self.trava:
            manter = []
            vistas = set()
            for posicao, entrada in enumerate(self.entradas):
                chave = (entrada["codigo"], entrada["arquivo"])
                if chave in desejadas and chave not in vistas and entrada.get("assinatura") == assinatura(entrada["arquivo"]):
                    manter.append(posicao)
                    vistas.add(chave)
            self.entradas = [self.entradas[p] for p in manter]
            self.dino, self.clip = self.dino[manter], self.clip[manter]
        faltam = []
        for (codigo, arquivo), origem in desejadas.items():
            if (codigo, arquivo) in vistas:
                continue
            marca = assinatura(arquivo)
            if marca:
                faltam.append({"codigo": codigo, "arquivo": arquivo, "origem": origem, "assinatura": marca})
        return faltam

    def acrescentar(self, entradas: list[dict], dino: np.ndarray, clip: np.ndarray) -> None:
        with self.trava:
            self.entradas.extend(entradas)
            self.dino = np.concatenate([self.dino, dino.astype(np.float32)])
            self.clip = np.concatenate([self.clip, clip.astype(np.float32)])

    def buscar(self, dino: np.ndarray, clip: np.ndarray, quantos: int = 5) -> list[dict]:
        """Nota de cada foto = média das duas semelhanças (como na Fase 0); a do item é a da melhor foto."""
        with self.trava:
            if not self.entradas:
                return []
            nota_dino = self.dino @ dino.reshape(-1)
            nota_clip = self.clip @ clip.reshape(-1)
            codigos = [entrada["codigo"] for entrada in self.entradas]
        notas = (nota_dino + nota_clip) / 2
        melhor: dict[str, int] = {}
        for posicao in np.argsort(-notas):
            codigo = codigos[posicao]
            if codigo not in melhor:
                melhor[codigo] = int(posicao)
                if len(melhor) >= quantos:
                    break
        return [
            {
                "codigo": codigo,
                "nota": round(float(notas[p]), 4),
                "dino": round(float(nota_dino[p]), 4),
                "clip": round(float(nota_clip[p]), 4),
            }
            for codigo, p in melhor.items()
        ]

    def resumo(self) -> dict:
        with self.trava:
            return {"fotos": len(self.entradas), "itens": len({e["codigo"] for e in self.entradas})}


class Servico:
    def __init__(self, dados: Path, threads: int) -> None:
        self.dados = Path(dados)
        self.consultas = (self.dados / "consultas").resolve()
        self.indice = Indice(self.dados)
        self.threads = threads
        self.modelos = None
        self.trava_modelos = threading.Lock()
        self.ultimo_uso = time.monotonic()
        self.sincronizando = False
        self.faltam = 0
        self.catalogo_visto: int | None = None
        self.erro: str | None = None

    # ---------- modelos e índice ----------
    def carregar_modelos(self) -> None:
        from motor import Modelos

        inicio = time.monotonic()
        try:
            self.modelos = Modelos(threads=self.threads)
        except Exception as erro:  # sem modelos não há o que servir
            self.erro = f"Falha ao carregar os modelos: {erro}"
            _log(self.erro)
            return
        _log(f"Modelos prontos em {time.monotonic() - inicio:.0f} s.")

    def _ler_catalogo(self) -> list[dict] | None:
        caminho = self.dados / "catalogo.json"
        try:
            marca = caminho.stat().st_mtime_ns
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        self.catalogo_visto = marca
        return list(dados.get("fotos") or [])

    def catalogo_mudou(self) -> bool:
        try:
            return (self.dados / "catalogo.json").stat().st_mtime_ns != self.catalogo_visto
        except OSError:
            return False

    def sincronizar(self) -> None:
        # O vigia de ociosidade não desliga enquanto isto roda; ao terminar, o relógio do "sem uso" recomeça.
        """Deixa o índice igual ao catálogo: tira o que saiu, vetoriza o que entrou ou mudou."""
        from motor import abrir

        if self.sincronizando or self.modelos is None:
            return
        self.sincronizando = True
        try:
            catalogo = self._ler_catalogo()
            if catalogo is None:
                return
            faltam = self.indice.podar(catalogo)
            self.faltam = len(faltam)
            if faltam:
                _log(f"Sincronizando: {len(faltam)} foto(s) para vetorizar.")
            feitos = 0
            for inicio in range(0, len(faltam), LOTE):
                parte, imagens = [], []
                for foto in faltam[inicio:inicio + LOTE]:
                    try:
                        imagens.append(abrir(foto["arquivo"]))
                        parte.append(foto)
                    except Exception as erro:
                        _log(f"Foto ilegível ({foto['codigo']}): {erro}")
                if parte:
                    with self.trava_modelos:
                        dino, clip = self.modelos.vetores(imagens)
                    self.indice.acrescentar(parte, dino, clip)
                feitos += len(faltam[inicio:inicio + LOTE])
                self.faltam = len(faltam) - feitos
                if feitos % 64 == 0:
                    self.indice.salvar()
            self.indice.salvar()
            if faltam:
                _log(f"Índice pronto: {self.indice.resumo()}.")
        finally:
            self.faltam = 0
            self.ultimo_uso = time.monotonic()
            self.sincronizando = False

    def sincronizar_em_segundo_plano(self) -> None:
        if not self.sincronizando:
            threading.Thread(target=self.sincronizar, name="sincronizar", daemon=True).start()

    # ---------- consulta ----------
    def buscar(self, arquivo: str, quantos: int) -> dict:
        from motor import abrir

        caminho = Path(arquivo).resolve()
        if self.consultas not in caminho.parents or not caminho.is_file():
            raise ValueError("Foto da consulta fora da pasta de consultas.")
        inicio = time.monotonic()
        imagem = abrir(caminho)
        with self.trava_modelos:
            dino, clip = self.modelos.vetores([imagem])
        resultados = self.indice.buscar(dino[0], clip[0], quantos=quantos)
        return {"pronto": True, "resultados": resultados, "ms": round((time.monotonic() - inicio) * 1000)}

    def saude(self) -> dict:
        return {
            "pronto": self.modelos is not None,
            "erro": self.erro,
            "sincronizando": self.sincronizando,
            "faltam": self.faltam,
            **self.indice.resumo(),
        }


def _handler(servico: Servico):
    class Pedido(BaseHTTPRequestHandler):
        def log_message(self, formato, *args):  # o log do http.server polui o servico.log
            return

        def _responder(self, status: int, corpo: dict) -> None:
            dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def _corpo(self) -> dict:
            tamanho = int(self.headers.get("Content-Length") or 0)
            if not tamanho:
                return {}
            try:
                return json.loads(self.rfile.read(min(tamanho, 65536)).decode("utf-8"))
            except ValueError:
                return {}

        def do_GET(self):
            if self.path.rstrip("/") == "/saude":
                self._responder(200, servico.saude())
            else:
                self._responder(404, {"erro": "não existe"})

        def do_POST(self):
            caminho = self.path.rstrip("/")
            corpo = self._corpo()
            servico.ultimo_uso = time.monotonic()
            if caminho == "/sincronizar":
                servico.sincronizar_em_segundo_plano()
                self._responder(202, {"ok": True})
                return
            if caminho != "/buscar":
                self._responder(404, {"erro": "não existe"})
                return
            if servico.modelos is None:
                self._responder(503, {"pronto": False, "erro": servico.erro})
                return
            if servico.catalogo_mudou():
                servico.sincronizar_em_segundo_plano()
            try:
                quantos = max(1, min(10, int(corpo.get("quantos") or 5)))
                self._responder(200, servico.buscar(str(corpo.get("arquivo") or ""), quantos))
            except ValueError as erro:
                self._responder(400, {"erro": str(erro)})
            except Exception as erro:  # foto estragada etc.: responde em vez de derrubar
                _log(f"Falha na busca: {erro}")
                self._responder(500, {"erro": "Não foi possível ler a foto."})

    return Pedido


def _vigiar_ocioso(servico: Servico, servidor: ThreadingHTTPServer, minutos: float) -> None:
    while True:
        time.sleep(30)
        if servico.sincronizando:
            continue
        if time.monotonic() - servico.ultimo_uso > minutos * 60:
            _log(f"{minutos:.0f} min sem uso: desligando para liberar a memória.")
            servico.indice.salvar()
            servidor.shutdown()
            os._exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Será que temos!? — busca visual do GALINT")
    parser.add_argument("--dados", required=True, help="pasta instance/busca_visual do GALINT")
    parser.add_argument("--porta", type=int, default=PORTA_PADRAO)
    parser.add_argument("--ocioso", type=float, default=20.0, help="minutos sem uso até desligar")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--indexar", action="store_true", help="só monta o índice e sai")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from motor import baixa_prioridade

    baixa_prioridade()
    servico = Servico(Path(args.dados), threads=args.threads)

    if args.indexar:
        servico.carregar_modelos()
        servico.sincronizar()
        _log(f"Índice: {servico.indice.resumo()}")
        return

    try:
        servidor = ThreadingHTTPServer(("127.0.0.1", args.porta), _handler(servico))
    except OSError:
        _log(f"Porta {args.porta} ocupada: já há um serviço rodando.")
        return
    servidor.daemon_threads = True
    _log(f"Ouvindo em 127.0.0.1:{args.porta} (dados em {args.dados}).")

    def preparar():
        servico.carregar_modelos()
        servico.ultimo_uso = time.monotonic()
        servico.sincronizar()

    threading.Thread(target=preparar, name="preparar", daemon=True).start()
    threading.Thread(target=_vigiar_ocioso, args=(servico, servidor, args.ocioso), name="ocioso", daemon=True).start()
    servidor.serve_forever()


if __name__ == "__main__":
    main()
