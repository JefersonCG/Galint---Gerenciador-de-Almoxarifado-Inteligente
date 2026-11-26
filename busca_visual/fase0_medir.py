"""Busca visual, Fase 0 (26/11/2026): mede DINOv2 + OpenCLIP nas fotos reais do GALINT, sem mexer em produção.

Pedido do usuário: avaliar "DINOv2 + OpenCLIP" para identificar material pela foto do celular. Antes de construir
o serviço, esta fase responde: quanto tempo e memória isso custa no PC do almoxarifado (i5-6500, 8 GB, sem placa
de vídeo NVIDIA), e quanto acerta.

Roda no ambiente separado C:\\ia-visual\\venv (torch, transformers, open_clip), em prioridade baixa, um modelo
por vez, para não atrapalhar o GALINT:
    C:\\ia-visual\\venv\\Scripts\\python.exe busca_visual\\fase0_medir.py

Entrada: C:\\ia-visual\\fase0\\itens.json (fase0_exportar_itens.py). Fotos reais opcionais em
C:\\ia-visual\\fotos_teste: o nome do arquivo começa pelo código do item ("7891234567895.jpg",
"7891234567895_2.jpg"), ou a foto fica numa pasta com o código do item.

O que mede:
1. Tempo por foto e memória de cada modelo.
2. Acerto em fotos "de celular" simuladas a partir da foto de catálogo (fundo, giro, luz, desfoque, JPEG).
   É otimista: a foto de origem é a mesma do índice. O número que vale é o das fotos reais (item 5).
3. Itens diferentes com fotos quase iguais: risco de confusão e candidatos a cadastro duplicado.
4. Busca por texto em português com o CLIP (descrição do item → foto do item).
5. Acerto nas fotos reais, quando houver.

Saída em C:\\ia-visual\\fase0: relatorio.json, parecidos.csv, vetores (dino.npy, clip.npy, codigos.json).
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import gc
import io
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

LADO = 224
DINO_NOME = "facebook/dinov2-base"  # ViT-B/14: 224 px = 16 x 16 blocos; CLS com 768 números
CLIP_NOME, CLIP_PESOS = "ViT-B-32", "laion2b_s34b_b79k"  # 512 números para imagem e texto
EXTENSOES = {".jpg", ".jpeg", ".png", ".webp"}


# --------------------------------------------------------------------------------------------------
# Processo: prioridade baixa e memória (Windows)
# --------------------------------------------------------------------------------------------------


class _Memoria(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def baixa_prioridade() -> None:
    if sys.platform != "win32":
        return
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL_PRIORITY_CLASS


def memoria_mb() -> dict[str, int] | None:
    if sys.platform != "win32":
        return None
    kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Memoria), ctypes.c_ulong]
    info = _Memoria()
    info.cb = ctypes.sizeof(_Memoria)
    psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(info), info.cb)
    return {"agora": round(info.WorkingSetSize / 2**20), "pico": round(info.PeakWorkingSetSize / 2**20)}


# --------------------------------------------------------------------------------------------------
# Imagem: EXIF, fundo branco no lugar da transparência, quadrado sem cortar o objeto
# --------------------------------------------------------------------------------------------------


def abrir(origem) -> Image.Image:
    imagem = ImageOps.exif_transpose(Image.open(origem))
    if imagem.mode in ("RGBA", "LA") or (imagem.mode == "P" and "transparency" in imagem.info):
        imagem = imagem.convert("RGBA")
        fundo = Image.new("RGB", imagem.size, "white")
        fundo.paste(imagem, mask=imagem.getchannel("A"))
        return fundo
    return imagem.convert("RGB")


def quadrado(imagem: Image.Image) -> Image.Image:
    """Reduz e completa com branco até 224 x 224. O corte central dos modelos cortaria o objeto fora do meio."""
    return ImageOps.pad(imagem, (LADO, LADO), method=Image.Resampling.BICUBIC, color=(255, 255, 255))


def foto_de_celular(imagem: Image.Image, rng: np.random.Generator) -> Image.Image:
    """Simula a foto tirada no almoxarifado a partir da foto de catálogo: o objeto, sem o fundo branco, num fundo
    cinza com textura, de 45% a 80% do quadro, girado até 12°, com luz, contraste e cor variando, um pouco
    desfocado e salvo em JPEG 70 a 800 px (o que o app mandaria)."""
    lado = 800
    cor = rng.integers(80, 200, size=3)
    ruido = rng.normal(0, 16, (lado, lado, 3)) + cor
    cena = Image.fromarray(np.clip(ruido, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2))
    escala = rng.uniform(0.45, 0.80) * lado / max(imagem.size)
    objeto = imagem.resize((max(1, int(imagem.width * escala)), max(1, int(imagem.height * escala))), Image.Resampling.BICUBIC)
    pixels = np.asarray(objeto)
    mascara = Image.fromarray(((pixels.min(axis=2) < 236) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))
    objeto = objeto.convert("RGBA")
    objeto.putalpha(mascara)
    objeto = objeto.rotate(float(rng.uniform(-12, 12)), resample=Image.Resampling.BICUBIC, expand=True)
    x = int(rng.integers(0, max(1, lado - objeto.width)))
    y = int(rng.integers(0, max(1, lado - objeto.height)))
    cena.paste(objeto, (x, y), objeto)
    cena = ImageEnhance.Brightness(cena).enhance(float(rng.uniform(0.7, 1.2)))
    cena = ImageEnhance.Contrast(cena).enhance(float(rng.uniform(0.8, 1.2)))
    cena = ImageEnhance.Color(cena).enhance(float(rng.uniform(0.8, 1.2)))
    cena = cena.filter(ImageFilter.GaussianBlur(float(rng.uniform(0, 1.2))))
    saida = io.BytesIO()
    cena.save(saida, format="JPEG", quality=70)
    saida.seek(0)
    return Image.open(saida).convert("RGB")


# --------------------------------------------------------------------------------------------------
# Modelos
# --------------------------------------------------------------------------------------------------


class Dino:
    def __init__(self) -> None:
        from transformers import AutoImageProcessor, AutoModel

        processador = AutoImageProcessor.from_pretrained(DINO_NOME)
        self.media = torch.tensor(processador.image_mean, dtype=torch.float32).view(3, 1, 1)
        self.desvio = torch.tensor(processador.image_std, dtype=torch.float32).view(3, 1, 1)
        self.modelo = AutoModel.from_pretrained(DINO_NOME).eval()

    @torch.inference_mode()
    def vetores(self, imagens: list[Image.Image]) -> np.ndarray:
        lote = torch.stack([
            (torch.from_numpy(np.asarray(quadrado(imagem), dtype=np.float32) / 255.0).permute(2, 0, 1) - self.media) / self.desvio
            for imagem in imagens
        ])
        saida = self.modelo(pixel_values=lote).pooler_output  # CLS normalizado pela última camada: (lote, 768)
        assert saida.shape[-1] == 768, saida.shape
        return torch.nn.functional.normalize(saida, dim=-1).numpy().astype(np.float32)


class Clip:
    def __init__(self) -> None:
        import open_clip

        self.modelo, _, self.preparo = open_clip.create_model_and_transforms(CLIP_NOME, pretrained=CLIP_PESOS)
        self.modelo.eval()
        self.tokenizador = open_clip.get_tokenizer(CLIP_NOME)

    @torch.inference_mode()
    def vetores(self, imagens: list[Image.Image]) -> np.ndarray:
        lote = torch.stack([self.preparo(quadrado(imagem)) for imagem in imagens])
        saida = self.modelo.encode_image(lote)
        assert saida.shape[-1] == 512, saida.shape
        return torch.nn.functional.normalize(saida, dim=-1).numpy().astype(np.float32)

    @torch.inference_mode()
    def textos(self, frases: list[str]) -> np.ndarray:
        saida = self.modelo.encode_text(self.tokenizador(frases))
        return torch.nn.functional.normalize(saida, dim=-1).numpy().astype(np.float32)


# --------------------------------------------------------------------------------------------------
# Contas
# --------------------------------------------------------------------------------------------------


def em_lotes(funcao, imagens: list[Image.Image], tamanho: int = 8) -> np.ndarray:
    return np.concatenate([funcao(imagens[i:i + tamanho]) for i in range(0, len(imagens), tamanho)])


def tempo_por_foto(funcao, imagens: list[Image.Image]) -> float:
    funcao(imagens[:1])  # aquece
    tempos = []
    for imagem in imagens:
        inicio = time.perf_counter()
        funcao([imagem])
        tempos.append((time.perf_counter() - inicio) * 1000)
    return round(statistics.median(tempos))


def acerto(semelhanca: np.ndarray, certos: list[int]) -> dict:
    """semelhanca: (consultas, itens). Acerto no 1º e entre os 3 e 5 primeiros; nota do certo e do melhor errado."""
    ordem = np.argsort(-semelhanca, axis=1)
    posicoes = [int(np.where(ordem[i] == certo)[0][0]) for i, certo in enumerate(certos)]
    nota_certo = [float(semelhanca[i, certo]) for i, certo in enumerate(certos)]
    melhor_errado = []
    for i, certo in enumerate(certos):
        linha = semelhanca[i].copy()
        linha[certo] = -9
        melhor_errado.append(float(linha.max()))
    topo = [float(semelhanca[i, ordem[i, 0]]) for i in range(len(certos))]
    acertou = [p == 0 for p in posicoes]
    return {
        "consultas": len(certos),
        "top1": round(sum(acertou) / len(certos), 3),
        "top3": round(sum(p < 3 for p in posicoes) / len(certos), 3),
        "top5": round(sum(p < 5 for p in posicoes) / len(certos), 3),
        "nota_certo_mediana": round(statistics.median(nota_certo), 3),
        "nota_melhor_errado_mediana": round(statistics.median(melhor_errado), 3),
        "limiar_95": limiar_para_precisao(topo, acertou, 0.95),
    }


def limiar_para_precisao(notas: list[float], acertou: list[bool], alvo: float) -> dict | None:
    """Menor nota a partir da qual o 1º colocado acerta em pelo menos `alvo` das vezes, e quantas consultas passam."""
    pares = sorted(zip(notas, acertou), reverse=True)
    melhor = None
    certos = 0
    for indice, (nota, ok) in enumerate(pares, start=1):
        certos += ok
        if certos / indice >= alvo:
            melhor = {"limiar": round(nota, 3), "cobertura": round(indice / len(pares), 3)}
    return melhor


def codigo_da_foto(arquivo: Path, raiz: Path) -> str:
    if arquivo.parent != raiz:
        return arquivo.parent.name.strip()
    return arquivo.stem.split("_")[0].strip()


# --------------------------------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pasta", default=r"C:\ia-visual\fase0")
    parser.add_argument("--fotos-teste", default=r"C:\ia-visual\fotos_teste")
    parser.add_argument("--consultas", type=int, default=200, help="fotos de celular simuladas")
    parser.add_argument("--nucleos", type=int, default=2, help="núcleos do processador para o torch")
    args = parser.parse_args()

    baixa_prioridade()
    torch.set_num_threads(args.nucleos)
    pasta = Path(args.pasta)
    itens = json.loads((pasta / "itens.json").read_text(encoding="utf-8"))
    relatorio: dict = {"itens": len(itens), "nucleos": args.nucleos, "memoria_inicio_mb": memoria_mb()}
    print(f"{len(itens)} itens; {args.nucleos} núcleos; memória {relatorio['memoria_inicio_mb']}", flush=True)

    # Na memória fica só o quadrado de 224 px de cada foto (~150 KB); a foto inteira de 985 itens passaria de 2 GB.
    catalogo, validos = [], []
    for item in itens:
        try:
            catalogo.append(quadrado(abrir(item["foto"])))
            validos.append(item)
        except Exception as exc:  # foto corrompida: fica fora do teste
            print(f"foto ilegível {item['codigo']}: {exc}", flush=True)
    itens = validos
    codigos = [item["codigo"] for item in itens]
    rng = np.random.default_rng(7)
    amostra = sorted(rng.choice(len(itens), size=min(args.consultas, len(itens)), replace=False).tolist())
    simuladas = []
    for posicao, i in enumerate(amostra):
        original = abrir(itens[i]["foto"])
        original.thumbnail((1000, 1000))
        cena = foto_de_celular(original, rng)
        if posicao == 0:
            cena.save(pasta / "exemplo_foto_simulada.jpg", quality=85)
        simuladas.append(quadrado(cena))

    reais, certos_reais = [], []
    raiz = Path(args.fotos_teste)
    if raiz.is_dir():
        indice = {codigo: i for i, codigo in enumerate(codigos)}
        for arquivo in sorted(raiz.rglob("*")):
            if arquivo.suffix.lower() in EXTENSOES and codigo_da_foto(arquivo, raiz) in indice:
                reais.append(quadrado(abrir(arquivo)))
                certos_reais.append(indice[codigo_da_foto(arquivo, raiz)])
    relatorio["fotos_reais"] = len(reais)

    vetores = {}
    for nome, Modelo in (("dino", Dino), ("clip", Clip)):
        inicio = time.perf_counter()
        modelo = Modelo()
        carga = round(time.perf_counter() - inicio, 1)
        memoria_modelo = memoria_mb()
        inicio = time.perf_counter()
        indice_vetores = em_lotes(modelo.vetores, catalogo)
        indexar = round(time.perf_counter() - inicio, 1)
        consultas = em_lotes(modelo.vetores, simuladas)
        consultas_reais = em_lotes(modelo.vetores, reais) if reais else None
        relatorio[nome] = {
            "carregar_s": carga,
            "memoria_com_modelo_mb": memoria_modelo,
            "indexar_todas_s": indexar,
            "ms_por_foto": tempo_por_foto(modelo.vetores, simuladas[:12]),
            "dimensao": int(indice_vetores.shape[1]),
        }
        if nome == "clip":
            frases = [itens[i]["descricao"] for i in amostra]
            textos = modelo.textos(frases)
            relatorio["clip_texto_pt"] = acerto(textos @ indice_vetores.T, amostra)
        vetores[nome] = (indice_vetores, consultas, consultas_reais)
        np.save(pasta / f"{nome}.npy", indice_vetores)
        print(f"{nome}: {relatorio[nome]}", flush=True)
        del modelo
        gc.collect()
    relatorio["memoria_pico_mb"] = memoria_mb()
    (pasta / "codigos.json").write_text(json.dumps(codigos), encoding="utf-8")

    dino_indice, dino_consultas, dino_reais = vetores["dino"]
    clip_indice, clip_consultas, clip_reais = vetores["clip"]
    sem_dino = dino_consultas @ dino_indice.T
    sem_clip = clip_consultas @ clip_indice.T
    relatorio["simuladas"] = {
        "dino": acerto(sem_dino, amostra),
        "clip": acerto(sem_clip, amostra),
        "juntos": acerto((sem_dino + sem_clip) / 2, amostra),  # = vetor de 1280 concatenado e normalizado
    }
    if reais:
        sr_dino, sr_clip = dino_reais @ dino_indice.T, clip_reais @ clip_indice.T
        relatorio["reais"] = {
            "dino": acerto(sr_dino, certos_reais),
            "clip": acerto(sr_clip, certos_reais),
            "juntos": acerto((sr_dino + sr_clip) / 2, certos_reais),
        }

    # Itens diferentes com fotos quase iguais (mesma foto para dois tamanhos, cadastro duplicado, peças gêmeas).
    entre_itens = dino_indice @ dino_indice.T
    np.fill_diagonal(entre_itens, -1)
    pares = []
    for i, j in zip(*np.where(np.triu(entre_itens, 1) >= 0.90)):
        pares.append((float(entre_itens[i, j]), float(clip_indice[i] @ clip_indice[j]), itens[i], itens[j]))
    pares.sort(key=lambda par: -par[0])
    with (pasta / "parecidos.csv").open("w", encoding="utf-8-sig", newline="") as arquivo:
        escrita = csv.writer(arquivo, delimiter=";")
        escrita.writerow(["dino", "clip", "codigo_a", "item_a", "codigo_b", "item_b"])
        for nota_dino, nota_clip, a, b in pares:
            escrita.writerow([f"{nota_dino:.3f}".replace(".", ","), f"{nota_clip:.3f}".replace(".", ","), a["codigo"], a["descricao"], b["codigo"], b["descricao"]])
    relatorio["pares_quase_iguais_090"] = len(pares)
    relatorio["pares_exemplos"] = [
        {"dino": round(d, 3), "a": f"{a['codigo']} {a['descricao']}", "b": f"{b['codigo']} {b['descricao']}"} for d, _c, a, b in pares[:15]
    ]

    (pasta / "relatorio.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(relatorio, ensure_ascii=False, indent=1), flush=True)


if __name__ == "__main__":
    main()
