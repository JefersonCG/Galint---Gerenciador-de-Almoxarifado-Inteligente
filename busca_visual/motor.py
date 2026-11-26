"""Motor do "Será que temos!?" (26/11/2026): foto → dois vetores (DINOv2 768 + OpenCLIP 512).

Mesmo preparo da Fase 0 (fase0_medir.py), que mediu 87% de acerto em 1º lugar e 97% entre os 3 primeiros com os
dois modelos juntos: EXIF desvirado, transparência em fundo branco, foto completada com branco até virar quadrado
de 224 px (sem o corte central dos modelos, que cortaria o objeto fora do meio).

Roda só no ambiente C:\\ia-visual\\venv (torch, transformers, open_clip). O GALINT não importa este arquivo.
"""
from __future__ import annotations

import ctypes
import sys

import numpy as np
from PIL import Image, ImageOps

LADO = 224
DINO_NOME = "facebook/dinov2-base"
CLIP_NOME, CLIP_PESOS = "ViT-B-32", "laion2b_s34b_b79k"


def baixa_prioridade() -> None:
    """Windows: prioridade abaixo do normal, para o GALINT (waitress) e o PC não sentirem."""
    if sys.platform != "win32":
        return
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL_PRIORITY_CLASS


def abrir(origem) -> Image.Image:
    imagem = ImageOps.exif_transpose(Image.open(origem))
    if imagem.mode in ("RGBA", "LA") or (imagem.mode == "P" and "transparency" in imagem.info):
        imagem = imagem.convert("RGBA")
        fundo = Image.new("RGB", imagem.size, "white")
        fundo.paste(imagem, mask=imagem.getchannel("A"))
        return fundo
    return imagem.convert("RGB")


def quadrado(imagem: Image.Image) -> Image.Image:
    return ImageOps.pad(imagem, (LADO, LADO), method=Image.Resampling.BICUBIC, color=(255, 255, 255))


class Modelos:
    """Os dois modelos carregados uma vez. vetores() devolve (dino, clip), cada linha normalizada."""

    def __init__(self, threads: int = 2) -> None:
        import open_clip
        import torch
        from transformers import AutoImageProcessor, AutoModel

        torch.set_num_threads(max(1, int(threads)))
        self._torch = torch
        processador = AutoImageProcessor.from_pretrained(DINO_NOME)
        self._media = torch.tensor(processador.image_mean, dtype=torch.float32).view(3, 1, 1)
        self._desvio = torch.tensor(processador.image_std, dtype=torch.float32).view(3, 1, 1)
        self._dino = AutoModel.from_pretrained(DINO_NOME).eval()
        self._clip, _, self._preparo = open_clip.create_model_and_transforms(CLIP_NOME, pretrained=CLIP_PESOS)
        self._clip.eval()

    def vetores(self, imagens: list[Image.Image]) -> tuple[np.ndarray, np.ndarray]:
        torch = self._torch
        quadrados = [quadrado(imagem) for imagem in imagens]
        with torch.inference_mode():
            lote_dino = torch.stack([
                (torch.from_numpy(np.asarray(q, dtype=np.float32) / 255.0).permute(2, 0, 1) - self._media) / self._desvio
                for q in quadrados
            ])
            dino = self._dino(pixel_values=lote_dino).pooler_output
            clip = self._clip.encode_image(torch.stack([self._preparo(q) for q in quadrados]))
            dino = torch.nn.functional.normalize(dino, dim=-1).numpy().astype(np.float32)
            clip = torch.nn.functional.normalize(clip, dim=-1).numpy().astype(np.float32)
        assert dino.shape[-1] == 768 and clip.shape[-1] == 512, (dino.shape, clip.shape)
        return dino, clip
