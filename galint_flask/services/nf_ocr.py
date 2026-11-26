"""Leitura de NF (DANFE) por OCR com o Tesseract, ou pelo texto do próprio PDF (24/11/2026).

Pedido do usuário: "vamos colocar o Tesseract em ponto operacional... XML e certificado A1 aqui vai ser
difícil conseguir, então a prioridade é o OCR". A NF em PDF ou foto vira cabeçalho (chave, número,
série, CNPJ, fornecedor, datas, totais) e linhas de itens (código do fornecedor, descrição, NCM, CFOP,
unidade, quantidade, valor unitário e total) para conferência no GALINT.

Como lê:
- PDF com texto (gerado pelo sistema do fornecedor): usa o texto do próprio PDF, sem OCR (exato).
- PDF escaneado, foto (JPG/PNG/WEBP) ou PDF sem texto legível: desenha a página a 300 dpi e passa no
  Tesseract (português, tessdata_best), girando antes se a página estiver deitada.
- Itens da NF-e: cada linha de item tem NCM (8 dígitos) seguido de CFOP; o resto da linha (unidade,
  quantidade, valores) é lido a partir daí, e a conta quantidade x unitário = total decide entre as
  leituras possíveis de cada número. Linha que não fecha a conta sai marcada para conferir.
- Cupom (NFC-e), sem NCM: só entra a linha cuja conta fecha.
- A chave de acesso só é aceita com o dígito verificador certo; dela saem CNPJ, número, série e modelo.

Este módulo não usa banco de dados: recebe bytes e devolve um dicionário. A conferência, a ligação com
os itens do GALINT e o lançamento ficam em nf_leitura_service.py.

O Tesseract é procurado em GALINT_TESSERACT_CMD, no PATH, em %LOCALAPPDATA%\\Programs\\Tesseract-OCR
(onde foi posto neste servidor, extraído do instalador oficial da UB Mannheim, sem precisar de
administrador) e em Arquivos de Programas.
"""
from __future__ import annotations

import csv
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from statistics import median
from typing import Any, Iterable

# PDF sem texto é desenhado a 400 dpi: com 300, a letra de 6,5 pt do DANFE trocava dígitos no código do
# produto ("A-778" lido "A-T7T8"); com 400, sai certo, por cerca de 1 s a mais por página.
OCR_DPI = 400
MAX_RENDER_WIDTH = 3300  # A4 em 400 dpi
# 26/11/2026: era 12. PDF com várias NFs juntas (8 da AC Milan num arquivo só) precisa ser lido inteiro.
MAX_PAGES = 60
TESSERACT_TIMEOUT_SECONDS = 240

PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
ACCEPTED_SUFFIXES = PDF_SUFFIXES | IMAGE_SUFFIXES

# Códigos IBGE das UFs (dois primeiros dígitos da chave de acesso).
UF_CODES = {
    "11", "12", "13", "14", "15", "16", "17", "21", "22", "23", "24", "25", "26", "27", "28", "29",
    "31", "32", "33", "35", "41", "42", "43", "50", "51", "52", "53",
}
MODEL_LABELS = {"55": "NF-e", "65": "NFC-e"}

# Rótulos que encerram a tabela de itens do DANFE.
TABLE_STOP_LABELS = (
    "DADOS ADICIONAIS",
    "CALCULO DO ISSQN",
    "INFORMACOES COMPLEMENTARES",
    "RESERVADO AO FISCO",
)
# Letras que o OCR costuma trocar por dígitos dentro de números.
_DIGIT_FIXES = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "i": "1", "S": "5", "s": "5", "B": "8", "Z": "2"})
# Sujeira nas pontas do que o OCR lê junto da borda das células ('2,0000, «1,0000, |579,80).
_EDGE_JUNK = "\"'`´‘’“”«»|[](){}<>:;!_~^*°ºª•·—–"


class OcrUnavailableError(RuntimeError):
    """Tesseract ou leitor de PDF ausente no servidor."""


# --------------------------------------------------------------------------------------------------
# Palavras com posição na página (vindas do Tesseract ou do texto do PDF)
# --------------------------------------------------------------------------------------------------


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 100.0

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return max(1.0, self.y1 - self.y0)


@dataclass
class Line:
    words: list[Word]
    page: int
    page_width: float = 1.0

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def norm(self) -> str:
        return normalize_text(self.text)

    @property
    def yc(self) -> float:
        return sum(word.yc for word in self.words) / max(1, len(self.words))

    @property
    def height(self) -> float:
        return median([word.height for word in self.words]) if self.words else 1.0


@dataclass
class PageText:
    lines: list[Line]
    source: str  # "texto_pdf" ou "ocr"
    width: float
    height: float
    confidence: float | None = None


@dataclass
class ReadResult:
    pages: list[PageText] = field(default_factory=list)
    seconds: float = 0.0


def normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", text.upper()).strip()


# --------------------------------------------------------------------------------------------------
# Tesseract
# --------------------------------------------------------------------------------------------------


def find_tesseract() -> tuple[str, str] | None:
    """Devolve (tesseract.exe, pasta tessdata) ou None."""
    candidates: list[str] = []
    configured = os.environ.get("GALINT_TESSERACT_CMD")
    if configured:
        candidates.append(configured)
    on_path = shutil.which("tesseract")
    if on_path:
        candidates.append(on_path)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(os.path.join(local_app_data, "Programs", "Tesseract-OCR", "tesseract.exe"))
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            candidates.append(os.path.join(base, "Tesseract-OCR", "tesseract.exe"))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            tessdata = os.environ.get("GALINT_TESSDATA_DIR") or os.path.join(os.path.dirname(candidate), "tessdata")
            return candidate, tessdata
    return None


def ocr_status() -> dict[str, Any]:
    """Situação do OCR neste servidor (mostrada na página de leitura de NF)."""
    found = find_tesseract()
    try:
        import pypdfium2  # noqa: F401

        pdf_ok = True
    except Exception:
        pdf_ok = False
    if not found:
        return {"ok": False, "pdf": pdf_ok, "message": "Tesseract não encontrado neste servidor."}
    exe, tessdata = found
    has_por = os.path.isfile(os.path.join(tessdata, "por.traineddata"))
    return {
        "ok": True,
        "pdf": pdf_ok,
        "tesseract": exe,
        "idioma": "por" if has_por else "eng",
        "message": "" if has_por else "Sem o português no Tesseract: lendo em inglês.",
    }


def _run_tesseract(args: list[str]) -> str:
    found = find_tesseract()
    if not found:
        raise OcrUnavailableError("Tesseract não encontrado neste servidor.")
    exe, tessdata = found
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
    completed = subprocess.run(
        [exe, *args[:2], "--tessdata-dir", tessdata, *args[2:]],
        capture_output=True,
        timeout=TESSERACT_TIMEOUT_SECONDS,
        creationflags=creationflags,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(f"Tesseract falhou: {detail[-1] if detail else completed.returncode}")
    return completed.stdout.decode("utf-8", "replace")


def _language() -> str:
    found = find_tesseract()
    if found and os.path.isfile(os.path.join(found[1], "por.traineddata")):
        return "por"
    return "eng"


def _prepare_image(image):
    from PIL import ImageOps

    image = ImageOps.exif_transpose(image)
    if image.mode not in ("L", "RGB"):
        image = image.convert("RGB")
    image = image.convert("L")
    # Foto pequena (menos de 2.000 px de largura): amplia para o equivalente a uma A4 em 400 dpi, onde a
    # letra de 6,5 pt do DANFE fica legível. Scan de 300 dpi (2.480 px) fica como veio: ampliado, piorava.
    if image.width < 2000:
        scale = MAX_RENDER_WIDTH / float(image.width)
        image = image.resize((int(image.width * scale), int(image.height * scale)))
    return ImageOps.autocontrast(image, cutoff=1)


def _detect_rotation(image_path: str) -> int:
    """Graus que a página precisa girar (sentido horário) para ficar em pé, pelo OSD do Tesseract."""
    try:
        output = _run_tesseract([image_path, "stdout", "--psm", "0", "-l", "osd"])
    except Exception:
        return 0
    rotate = re.search(r"Rotate:\s*(\d+)", output)
    confidence = re.search(r"Orientation confidence:\s*([\d.]+)", output)
    if not rotate or not confidence or float(confidence.group(1)) < 1.5:
        return 0
    value = int(rotate.group(1)) % 360
    return value if value in (90, 180, 270) else 0


def remove_table_lines(image):
    """Apaga as bordas da tabela do DANFE (traços verticais e horizontais longos) antes do OCR.

    Na NF real da ACQUA ILHA PISCINA (23/11/2026), lida como foto, o Tesseract tomava as bordas das
    células por "|" e "]" e engolia CSOSN, CFOP, unidade e total: nenhum item saía. Sem as bordas, sai.
    Traço vertical com mais de 0,12 pol. e horizontal com mais de 0,5 pol., todo escuro, vira branco
    (letra de DANFE não chega a isso). Sem numpy, devolve a imagem como veio.
    """
    try:
        import numpy as np
    except Exception:  # pragma: no cover
        return image
    from PIL import Image

    pixels = np.asarray(image)
    dark = pixels < 170
    dpi = max(150.0, image.width / 8.27)  # largura de uma A4

    def covered_by_long_runs(mask, length: int):
        height = mask.shape[0]
        if length >= height:
            return np.zeros_like(mask)
        sums = np.vstack([np.zeros((1, mask.shape[1]), dtype=np.int32), np.cumsum(mask, axis=0, dtype=np.int32)])
        full = (sums[length:] - sums[:-length]) == length
        full_sums = np.vstack([np.zeros((1, mask.shape[1]), dtype=np.int32), np.cumsum(full, axis=0, dtype=np.int32)])
        rows = np.arange(height)
        low = np.clip(rows - length + 1, 0, full.shape[0])
        high = np.clip(rows + 1, 0, full.shape[0])
        return (full_sums[high] - full_sums[low]) > 0

    lines = covered_by_long_runs(dark, int(dpi * 0.12)) | covered_by_long_runs(dark.T, int(dpi * 0.5)).T
    cleaned = pixels.copy()
    cleaned[lines] = 255
    return Image.fromarray(cleaned)


def _tesseract_lines(image, page_index: int, psm: int) -> tuple[list[Line], float | None]:
    with tempfile.TemporaryDirectory(prefix="galint-ocr-") as tmp:
        path = os.path.join(tmp, "pagina.png")
        image.save(path)
        tsv = _run_tesseract([path, "stdout", "-l", _language(), "--psm", str(psm), "-c", "preserve_interword_spaces=1", "tsv"])
    lines, confidence = _lines_from_tsv(tsv, page_index, float(image.width))
    if psm != 6:
        # Nos modos de texto esparso o Tesseract não monta linhas de tabela: monta pela altura.
        lines = group_words_into_lines([word for line in lines for word in line.words], page_index, float(image.width))
    return lines, confidence


def _items_match_products_total(parsed: dict[str, Any]) -> bool:
    reference = parsed["cabecalho"].get("valor_produtos")
    total = sum(float(item["valor_total"] or 0) for item in parsed["itens"])
    return bool(reference) and abs(total - float(reference)) <= 0.05


def _page_score(parsed: dict[str, Any]) -> float:
    header = parsed["cabecalho"]
    items = parsed["itens"]
    return (
        10 * sum(1 for item in items if item["confere"])
        + 3 * len(items)
        + 15 * _items_match_products_total(parsed)
        + 5 * bool(header["chave"])
        + 2 * bool(header["emitente"])
        + bool(header["data_emissao"])
        + bool(header["valor_total"])
    )


def _attempt_is_complete(parsed: dict[str, Any]) -> bool:
    """Todos os itens fecham a conta, a chave foi lida e (se a nota mostra) a soma bate com os produtos."""
    items = parsed["itens"]
    if not items or not all(item["confere"] for item in items) or not parsed["cabecalho"]["chave"]:
        return False
    return _items_match_products_total(parsed) or not parsed["cabecalho"].get("valor_produtos")


# Tentativas de OCR, na ordem; para na 1ª completa (_attempt_is_complete) e fica com a de maior pontuação.
# Medido em 24/11/2026: sem bordas + psm 6 leu a NF da ACQUA (foto) mas perdeu 1 de 6 itens no DANFE
# de exemplo; sem bordas + psm 11 leu os dois; com bordas + psm 6 leu o exemplo e não a ACQUA.
OCR_ATTEMPTS = (("sem_bordas", 6), ("sem_bordas", 11), ("original", 6))


def ocr_image(image, page_index: int = 0) -> PageText:
    """Passa uma imagem no Tesseract e devolve as linhas com a posição de cada palavra."""
    image = _prepare_image(image)
    with tempfile.TemporaryDirectory(prefix="galint-ocr-") as tmp:
        path = os.path.join(tmp, "pagina.png")
        image.save(path)
        rotation = _detect_rotation(path)
    if rotation:
        image = image.rotate(-rotation, expand=True)
    without_lines = remove_table_lines(image)
    best: tuple[float, PageText] | None = None
    for variant, psm in OCR_ATTEMPTS:
        source = without_lines if variant == "sem_bordas" else image
        lines, confidence = _tesseract_lines(source, page_index, psm)
        page = PageText(lines=lines, source="ocr", width=float(image.width), height=float(image.height), confidence=confidence)
        parsed = parse_danfe([page])
        score = _page_score(parsed)
        if best is None or score > best[0]:
            best = (score, page)
        if _attempt_is_complete(parsed):
            break
    return best[1]


def _lines_from_tsv(tsv: str, page_index: int, page_width: float) -> tuple[list[Line], float | None]:
    grouped: dict[tuple[int, int, int], list[Word]] = {}
    order: list[tuple[int, int, int]] = []
    confidences: list[float] = []
    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    for row in reader:
        text = (row.get("text") or "").strip()
        if row.get("level") != "5" or not text:
            continue
        try:
            left, top = float(row["left"]), float(row["top"])
            width, height = float(row["width"]), float(row["height"])
            conf = float(row.get("conf") or 0)
        except (TypeError, ValueError, KeyError):
            continue
        key = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(Word(text, left, top, left + width, top + height, conf))
        if conf >= 0:
            confidences.append(conf)
    lines = [Line(sorted(grouped[key], key=lambda word: word.x0), page_index, page_width) for key in order]
    lines.sort(key=lambda line: line.yc)
    return lines, (sum(confidences) / len(confidences)) if confidences else None


# --------------------------------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------------------------------


def _pdfium():
    try:
        import pypdfium2 as pdfium
    except Exception as exc:  # pragma: no cover - depende da instalação
        raise OcrUnavailableError("Leitor de PDF (pypdfium2) não instalado neste servidor.") from exc
    return pdfium


def _text_layer_words(page, page_height: float) -> list[Word]:
    pdfium = _pdfium()
    textpage = page.get_textpage()
    try:
        count = textpage.count_chars()
        words: list[Word] = []
        current: list[tuple[str, tuple[float, float, float, float]]] = []

        def flush() -> None:
            if not current:
                return
            text = "".join(character for character, _ in current)
            x0 = min(box[0] for _, box in current)
            x1 = max(box[2] for _, box in current)
            top = max(box[3] for _, box in current)
            bottom = min(box[1] for _, box in current)
            words.append(Word(text, x0, page_height - top, x1, page_height - bottom))
            current.clear()

        for index in range(count):
            code = pdfium.raw.FPDFText_GetUnicode(textpage.raw, index)
            character = chr(code) if code else ""
            if not character or character.isspace() or ord(character) < 32:
                flush()
                continue
            # Caixa "larga" (da fonte): todas as letras da linha têm a mesma altura e letras vizinhas
            # da mesma palavra se encostam; com a caixa justa, "100" virava "1 00" e a vírgula
            # descia para outra linha.
            box = textpage.get_charbox(index, loose=True)
            if box[2] - box[0] <= 0 and box[3] - box[1] <= 0:
                continue
            if current:
                previous = current[-1][1]
                height = max(1.0, previous[3] - previous[1], box[3] - box[1])
                same_line = abs(((box[1] + box[3]) / 2) - ((previous[1] + previous[3]) / 2)) < height * 0.5
                gap = box[0] - previous[2]
                if not same_line or gap > height * 0.25 or gap < -height:
                    flush()
            current.append((character, box))
        flush()
        return words
    finally:
        textpage.close()


def group_words_into_lines(words: list[Word], page_index: int, page_width: float) -> list[Line]:
    if not words:
        return []
    typical_height = median([word.height for word in words])
    lines: list[Line] = []
    for word in sorted(words, key=lambda item: (item.yc, item.x0)):
        if lines and abs(word.yc - lines[-1].yc) <= typical_height * 0.5:
            lines[-1].words.append(word)
        else:
            lines.append(Line([word], page_index, page_width))
    for line in lines:
        line.words.sort(key=lambda item: item.x0)
    return lines


def _text_layer_is_readable(lines: list[Line]) -> bool:
    text = normalize_text(" ".join(line.text for line in lines))
    if len(re.sub(r"[^A-Z0-9]", "", text)) < 150:
        return False
    keywords = ("DANFE", "NOTA FISCAL", "CNPJ", "VALOR", "CHAVE", "EMISSAO", "PRODUTO")
    return sum(1 for keyword in keywords if keyword in text) >= 3


def read_pdf(data: bytes) -> ReadResult:
    pdfium = _pdfium()
    started = time.monotonic()
    result = ReadResult()
    document = pdfium.PdfDocument(data)
    try:
        for index in range(min(len(document), MAX_PAGES)):
            page = document[index]
            try:
                width, height = page.get_size()
                lines = group_words_into_lines(_text_layer_words(page, height), index, width)
                if _text_layer_is_readable(lines):
                    result.pages.append(PageText(lines=lines, source="texto_pdf", width=width, height=height))
                    continue
                # 400 dpi numa A4; página de tamanho fora do comum é limitada à mesma largura em pixels.
                scale = min(OCR_DPI / 72, MAX_RENDER_WIDTH / max(1.0, width))
                image = page.render(scale=scale, grayscale=True).to_pil()
                result.pages.append(ocr_image(image, index))
            finally:
                page.close()
    finally:
        document.close()
    result.seconds = time.monotonic() - started
    return result


MAX_SPLIT_PAGES = 80


def split_pdf_by_access_key(data: bytes) -> list[dict[str, Any]] | None:
    """PDF com VÁRIAS NFs (uma por página ou por grupo de páginas) → uma parte por chave de acesso.

    Caso de 26/11/2026: "19.11 - MERCADO LIVRE R$ 955,12.pdf" juntava 8 NFs da AC Milan (28494 a 28501, 1 fardo de
    bambu cada); o Ler NF lia o PDF como uma NF só e lançou só a primeira página (28498). Só usa o texto do PDF (sem
    OCR): página sem chave legível fica junto da anterior (continuação da mesma NF). Devolve None quando há menos
    de duas chaves (o PDF segue inteiro, como sempre); senão [{"chave", "paginas", "data"}] na ordem do arquivo.
    """
    pdfium = _pdfium()
    document = pdfium.PdfDocument(data)
    try:
        total = min(len(document), MAX_SPLIT_PAGES)
        if total < 2:
            return None
        groups: list[dict[str, Any]] = []
        for index in range(total):
            page = document[index]
            try:
                width, height = page.get_size()
                lines = group_words_into_lines(_text_layer_words(page, height), index, width)
            finally:
                page.close()
            key = find_access_key(lines) if lines else None
            if groups and (key is None or key == groups[-1]["chave"]):
                groups[-1]["paginas"].append(index)
            else:
                groups.append({"chave": key, "paginas": [index]})
        if len([group for group in groups if group["chave"]]) < 2:
            return None
        for group in groups:
            part = pdfium.PdfDocument.new()
            try:
                part.import_pages(document, pages=group["paginas"])
                buffer = io.BytesIO()
                part.save(buffer)
                group["data"] = buffer.getvalue()
            finally:
                part.close()
        return groups
    finally:
        document.close()


def read_image(data: bytes) -> ReadResult:
    from PIL import Image

    started = time.monotonic()
    image = Image.open(io.BytesIO(data))
    pages: list[PageText] = []
    frame = 0
    while True:
        pages.append(ocr_image(image.copy(), frame))
        frame += 1
        if frame >= MAX_PAGES:
            break
        try:
            image.seek(frame)
        except EOFError:
            break
    return ReadResult(pages=pages, seconds=time.monotonic() - started)


def read_file(data: bytes, filename: str) -> ReadResult:
    suffix = os.path.splitext(filename or "")[1].lower()
    if suffix in PDF_SUFFIXES or data[:5] == b"%PDF-":
        return read_pdf(data)
    if suffix in IMAGE_SUFFIXES or not suffix:
        return read_image(data)
    raise ValueError("Envie a NF em PDF ou foto (JPG, PNG).")


# --------------------------------------------------------------------------------------------------
# Números, datas e chave de acesso
# --------------------------------------------------------------------------------------------------


def clean_token(token: str) -> str:
    return str(token or "").strip().strip(_EDGE_JUNK).strip()


def fix_digits(token: str) -> str:
    """Corrige letras lidas no lugar de dígitos, só em token que já é quase todo número."""
    token = clean_token(token)
    digits = sum(character.isdigit() for character in token)
    if digits == 0 or digits < len(re.sub(r"[.,/\-]", "", token)) / 2:
        return token
    return token.translate(_DIGIT_FIXES)


def number_candidates(token: str) -> list[float]:
    """Leituras possíveis de um número escrito à brasileira (ou à americana) no DANFE."""
    text = fix_digits(token.strip()).strip(".,")
    if not re.fullmatch(r"\d[\d.,]*", text):
        return []
    try:
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                return [float(text.replace(".", "").replace(",", "."))]
            return [float(text.replace(",", ""))]
        if "," in text:
            parts = text.split(",")
            if len(parts) == 2:
                return [float(text.replace(",", "."))]
            return [float(text.replace(",", ""))]
        if "." in text:
            parts = text.split(".")
            if len(parts) == 2:
                as_decimal = float(text)
                if len(parts[1]) == 3:
                    return [as_decimal, float(text.replace(".", ""))]
                return [as_decimal]
            return [float(text.replace(".", ""))]
        return [float(text)]
    except ValueError:
        return []


def parse_number(token: str | None) -> float | None:
    candidates = number_candidates(token or "")
    return candidates[0] if candidates else None


_DATE_RE = re.compile(r"(?<!\d)(\d{2})[/.\-](\d{2})[/.\-](\d{4})(?!\d)")


def parse_date(text: str | None) -> date | None:
    match = _DATE_RE.search(fix_digits(text or "") if text else "")
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def access_key_check_digit(first43: str) -> int:
    total = 0
    weight = 2
    for digit in reversed(first43):
        total += int(digit) * weight
        weight = 2 if weight == 9 else weight + 1
    remainder = total % 11
    return 0 if remainder in (0, 1) else 11 - remainder


def is_valid_access_key(key: str) -> bool:
    if not re.fullmatch(r"\d{44}", key or ""):
        return False
    if key[:2] not in UF_CODES or not 1 <= int(key[4:6]) <= 12:
        return False
    return access_key_check_digit(key[:43]) == int(key[43])


def describe_access_key(key: str) -> dict[str, Any]:
    return {
        "chave": key,
        "uf": key[:2],
        "ano_mes": f"20{key[2:4]}-{key[4:6]}",
        "cnpj_emitente": key[6:20],
        "modelo": key[20:22],
        "modelo_label": MODEL_LABELS.get(key[20:22], key[20:22]),
        "serie": str(int(key[22:25])),
        "numero": str(int(key[25:34])),
    }


def find_access_key(lines: list[Line]) -> str | None:
    texts = [line.text for line in lines]
    candidates = texts + [f"{texts[i]} {texts[i + 1]}" for i in range(len(texts) - 1)]
    for text in candidates:
        digits = "".join(re.sub(r"\D", "", fix_digits(token)) for token in text.split() if sum(c.isdigit() for c in token) >= 2)
        if len(digits) < 44:
            continue
        for start in range(0, len(digits) - 43):
            window = digits[start:start + 44]
            if is_valid_access_key(window):
                return window
    return None


def is_valid_gtin(code: str | None) -> bool:
    """EAN-8, EAN-13 ou GTIN-14 com dígito verificador certo (código de barras do produto)."""
    text = str(code or "").strip()
    if not re.fullmatch(r"\d{8}|\d{12,14}", text) or set(text) == {"0"}:
        return False
    body, check = text[:-1], int(text[-1])
    total = sum(int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


# --------------------------------------------------------------------------------------------------
# Interpretação do DANFE
# --------------------------------------------------------------------------------------------------


def _find_label(lines: list[Line], *labels: str) -> tuple[int, float] | None:
    """Índice da linha e posição x (centro) do primeiro rótulo encontrado."""
    for index, line in enumerate(lines):
        norm = line.norm
        for label in labels:
            position = norm.find(label)
            if position < 0:
                continue
            # posição x aproximada: palavra onde o rótulo começa
            consumed = 0
            for word in line.words:
                consumed += len(normalize_text(word.text)) + 1
                if consumed > position:
                    label_words = len(label.split())
                    start = line.words.index(word)
                    span = line.words[start:start + label_words]
                    return index, (span[0].x0 + span[-1].x1) / 2
    return None


def _value_near(lines: list[Line], label: tuple[int, float] | None, kind: str, *, same_line_first: bool = True) -> Any:
    """Valor (data ou dinheiro) logo abaixo do rótulo, na mesma coluna; ou na mesma linha, à direita."""
    if not label:
        return None
    index, x_center = label
    line = lines[index]
    width = line.page_width or 1.0

    def pick(words: Iterable[Word], max_distance: float) -> Any:
        best = None
        for word in words:
            value = parse_date(word.text) if kind == "date" else (parse_number(word.text) if re.search(r"\d[.,]\d{2}$", fix_digits(word.text)) else None)
            if value is None:
                continue
            distance = abs(word.xc - x_center)
            if distance <= max_distance and (best is None or distance < best[0]):
                best = (distance, value)
        return best[1] if best else None

    if same_line_first:
        right = [word for word in line.words if word.x0 > x_center]
        found = pick(right, width * 0.3)
        if found is not None:
            return found
    for offset in (1, 2, 3):
        if index + offset >= len(lines) or lines[index + offset].page != line.page:
            break
        found = pick(lines[index + offset].words, width * 0.18)
        if found is not None:
            return found
    return None


def _supplier_name(lines: list[Line]) -> str | None:
    joined = " ".join(line.text for line in lines[:40])
    match = re.search(r"RECEBEMOS\s+DE\s+(.+?)\s+OS\s+PRODUTOS", joined, flags=re.IGNORECASE)
    if match:
        name = re.sub(r"\s+", " ", match.group(1)).strip(" -:")
        if 3 <= len(name) <= 120:
            return name
    return None


def _first_cnpj(lines: list[Line]) -> str | None:
    for line in lines:
        match = re.search(r"\d{2}[.\s]?\d{3}[.\s]?\d{3}\s?/\s?\d{4}\s?-\s?\d{2}", fix_digits(line.text))
        if match:
            return re.sub(r"\D", "", match.group(0))
    return None


def _item_from_tokens(tokens: list[str]) -> dict[str, Any] | None:
    """Linha de item da NF-e: código, descrição, NCM, [CST], CFOP, unidade, quantidade, unitário, total."""
    fixed = [fix_digits(token) for token in tokens]
    ncm_index = None
    cfop_index = None
    for index in range(1, len(fixed)):
        candidate = re.sub(r"[.\s]", "", fixed[index])
        if not re.fullmatch(r"\d{8}", candidate):
            continue
        for offset in (1, 2, 3):
            # CFOP com ou sem ponto: "5102" ou "5.102" (NF da ACQUA ILHA PISCINA, 23/11/2026).
            if index + offset < len(fixed) and re.fullmatch(r"[1-7]\.?\d{3}", fixed[index + offset]):
                ncm_index, cfop_index = index, index + offset
                break
        if ncm_index is not None:
            break
    if ncm_index is None:
        return None
    rest = tokens[cfop_index + 1:]
    unit_index = next((i for i, token in enumerate(rest[:3]) if re.search(r"[A-Za-zÀ-ú]", token) and len(token) <= 8), None)
    numbers_from = (unit_index + 1) if unit_index is not None else 0
    after_unit = rest[numbers_from:numbers_from + 8]
    quantity, unit_price, total, fits = None, None, None, False
    for variant in _number_variants(after_unit):
        numeric = [token for token in variant if number_candidates(token)][:6]
        if len(numeric) < 3:
            continue
        candidate = _best_fit(numeric)
        if quantity is None or (candidate[3] and not fits):
            quantity, unit_price, total, fits = candidate
        if fits:
            break
    if quantity is None:
        return None
    return {
        "codigo": tokens[0].strip(),
        "descricao": " ".join(tokens[1:ncm_index]).strip(),
        "ncm": re.sub(r"\D", "", fixed[ncm_index]),
        "cfop": fixed[cfop_index].replace(".", ""),
        "unidade": rest[unit_index].strip(".").upper() if unit_index is not None else "",
        "quantidade": quantity,
        "valor_unitario": unit_price,
        "valor_total": total,
        "confere": fits,
    }


def _number_variants(tokens: list[str]) -> list[list[str]]:
    """Leituras alternativas de números que o OCR partiu ou sujou, na ordem em que são tentadas.

    1) como veio, só trocando ",." e ".," por "," ("3,.0000");
    2) juntando o pedaço que começa com separador ao anterior ("289" ",9000" -> "289,9000");
    3) juntando dois blocos só de dígitos quando o 2º tem 2 ou 4 casas ("459" "9000" -> "459,9000").
    Quem decide se a variante vale é a conta quantidade x unitário = total (_best_fit).
    """
    base = [re.sub(r"[,.]{2,}", ",", clean_token(token)) for token in tokens]
    joined: list[str] = []
    for token in base:
        if joined and re.fullmatch(r"[,.]\d{2,4}", token) and re.fullmatch(r"\d[\d.]*", joined[-1]):
            joined[-1] = joined[-1] + token
        else:
            joined.append(token)
    glued: list[str] = []
    for token in joined:
        if glued and re.fullmatch(r"\d{2}|\d{4}", token) and re.fullmatch(r"\d{1,6}", glued[-1]):
            glued[-1] = f"{glued[-1]},{token}"
        else:
            glued.append(token)
    variants = [base]
    for variant in (joined, glued):
        if variant not in variants:
            variants.append(variant)
    return variants


def _best_fit(numeric: list[str]) -> tuple[float | None, float | None, float | None, bool]:
    """Escolhe quantidade, unitário e total (e as leituras de cada número) pela conta q x u = t."""
    best = None
    for total_position in (2, 3):
        if total_position >= len(numeric):
            continue
        for quantity in number_candidates(numeric[0]):
            for unit_price in number_candidates(numeric[1]):
                for total in number_candidates(numeric[total_position]):
                    error = abs(quantity * unit_price - total)
                    score = error / max(total, 0.01)
                    if best is None or score < best[0]:
                        best = (score, quantity, unit_price, total)
    if best is None:
        return None, None, None, False
    score, quantity, unit_price, total = best
    return quantity, unit_price, total, _closes(quantity, unit_price, total)


def _closes(quantity: float, unit_price: float, total: float) -> bool:
    """quantidade x unitário = total, aceitando só o arredondamento do unitário (meio centavo por unidade).

    Com 0,5% do total, "1 x 459 = 459,90" passava por certo e o número partido pelo OCR ("459 9000")
    não era remendado.
    """
    return abs(quantity * unit_price - total) <= max(0.02, quantity * 0.005 + 0.01)


def _receipt_item_from_tokens(tokens: list[str]) -> dict[str, Any] | None:
    """Cupom (NFC-e) e layouts sem NCM: só aceita a linha em que quantidade x unitário = total."""
    numeric_tail: list[str] = []
    unit = ""
    stop = len(tokens)  # o que vem antes de stop é código + descrição
    for index in range(len(tokens) - 1, -1, -1):
        token = tokens[index]
        if number_candidates(token) and len(numeric_tail) < 3:
            numeric_tail.insert(0, token)
        elif len(numeric_tail) in (1, 2) and token.upper() in {"X", "*"}:
            pass
        elif len(numeric_tail) == 2 and re.fullmatch(r"[A-Za-z]{1,4}\d?", token) and not unit:
            unit = token.upper()
        else:
            break
        stop = index
        if len(numeric_tail) == 3:
            break
    if len(numeric_tail) != 3:
        return None
    quantity, unit_price, total, fits = _best_fit(numeric_tail)
    if not fits or not total:
        return None
    head = [token for token in tokens[:stop] if token.upper() not in {"X", "*"}]
    if head and re.fullmatch(r"\d{1,3}", head[0]):
        head = head[1:]  # número do item no cupom
    codigo = head[0] if head and re.fullmatch(r"[\dA-Za-z\-.]{3,20}", head[0]) and any(c.isdigit() for c in head[0]) else ""
    descricao = " ".join(head[1:] if codigo else head).strip()
    if len(re.sub(r"[^A-Za-zÀ-ú]", "", descricao)) < 3:
        return None
    return {
        "codigo": codigo,
        "descricao": descricao,
        "ncm": "",
        "cfop": "",
        "unidade": unit,
        "quantidade": quantity,
        "valor_unitario": unit_price,
        "valor_total": total,
        "confere": True,
    }


def _is_table_header(norm: str) -> bool:
    return "DESCRI" in norm and any(label in norm for label in ("NCM", "CFOP", "QUANT", "QTD", "UNIT", "V.UNIT"))


def _parse_items(lines: list[Line]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    last_item_line: Line | None = None
    continuation_count = 0
    for line in lines:
        norm = line.norm
        if _is_table_header(norm) or any(label in norm for label in TABLE_STOP_LABELS):
            last_item_line = None
            continue
        words = [word for word in line.words if clean_token(word.text)]
        if not words:
            continue
        item = _item_from_tokens([clean_token(word.text) for word in words])
        if item:
            desc_words = words[1:1 + len(item["descricao"].split())] if item["descricao"] else []
            item["_desc_x0"] = desc_words[0].x0 if desc_words else (words[1].x0 if len(words) > 1 else words[0].x0)
            item["pagina"] = line.page + 1
            items.append(item)
            last_item_line = line
            continuation_count = 0
            continue
        # Continuação da descrição: logo abaixo do item, começando na coluna da descrição.
        if items and last_item_line is not None and continuation_count < 2 and line.page == last_item_line.page:
            width = line.page_width or 1.0
            close_below = 0 < line.yc - last_item_line.yc <= last_item_line.height * 3.2 * (continuation_count + 1)
            aligned = abs(words[0].x0 - items[-1]["_desc_x0"]) <= width * 0.05
            has_letters = len(re.sub(r"[^A-Za-zÀ-ú]", "", line.text)) >= 3
            if close_below and aligned and has_letters:
                items[-1]["descricao"] = f"{items[-1]['descricao']} {' '.join(clean_token(word.text) for word in words)}".strip()
                continuation_count += 1
                continue
    if not items:
        for line in lines:
            item = _receipt_item_from_tokens([word.text for word in line.words])
            if item:
                item["pagina"] = line.page + 1
                items.append(item)
    for number, item in enumerate(items, start=1):
        item.pop("_desc_x0", None)
        item["n"] = number
        item["descricao"] = re.sub(r"\s+", " ", item["descricao"]).strip()
    return items


def parse_danfe(pages: list[PageText]) -> dict[str, Any]:
    """Transforma as linhas lidas em cabeçalho e itens da NF."""
    lines = [line for page in pages for line in page.lines]
    first_page = [line for line in lines if line.page == 0] or lines
    warnings: list[str] = []

    key = find_access_key(lines)
    header: dict[str, Any] = {
        "chave": key,
        "numero": None,
        "serie": None,
        "modelo": None,
        "cnpj_emitente": None,
        "emitente": _supplier_name(first_page),
        "data_emissao": None,
        "data_saida": None,
        "valor_produtos": None,
        "valor_total": None,
    }
    if key:
        described = describe_access_key(key)
        header.update(
            numero=described["numero"],
            serie=described["serie"],
            modelo=described["modelo_label"],
            cnpj_emitente=described["cnpj_emitente"],
        )
    else:
        warnings.append("Chave de acesso não lida: confira número, série e CNPJ.")
        joined = " ".join(line.text for line in first_page)
        number = re.search(r"N[º°o0]\s*\.?\s*:?\s*(\d{1,3}(?:\.\d{3}){1,3}|\d{3,9})", joined)
        if number:
            header["numero"] = str(int(re.sub(r"\D", "", number.group(1))))
        series = re.search(r"S[ÉE]RIE\s*:?\s*(\d{1,3})", joined, flags=re.IGNORECASE)
        if series:
            header["serie"] = str(int(series.group(1)))
        header["cnpj_emitente"] = _first_cnpj(first_page)

    emission = _value_near(first_page, _find_label(first_page, "DATA DA EMISSAO", "DATA DE EMISSAO", "EMISSAO"), "date")
    if emission is None:
        emission = next((parse_date(line.text) for line in first_page if parse_date(line.text)), None)
    header["data_emissao"] = emission.isoformat() if emission else None
    exit_date = _value_near(first_page, _find_label(first_page, "DATA DA SAIDA", "DATA DE SAIDA", "SAIDA/ENTRADA", "ENTRADA / SAIDA", "ENTRADA/SAIDA"), "date")
    header["data_saida"] = exit_date.isoformat() if exit_date else None
    header["valor_produtos"] = _value_near(lines, _find_label(lines, "VALOR TOTAL DOS PRODUTOS", "V. TOTAL PRODUTOS", "TOTAL DOS PRODUTOS"), "money")
    header["valor_total"] = _value_near(lines, _find_label(lines, "VALOR TOTAL DA NOTA", "V. TOTAL DA NOTA", "VALOR TOTAL DA NF", "VALOR A PAGAR"), "money")
    for key in ("valor_produtos", "valor_total"):
        if not header[key]:
            header[key] = None  # "0,00" de célula vizinha (foto torta) não é total de nota

    items = _parse_items(lines)
    if not items:
        warnings.append("Nenhum item lido: confira se a página dos produtos está nítida.")
    else:
        to_check = sum(1 for item in items if not item["confere"])
        if to_check:
            warnings.append(f"{to_check} item(ns) com quantidade x valor que não fecha: conferir.")
        total_items = round(sum(float(item["valor_total"] or 0) for item in items), 2)
        reference = header["valor_produtos"]
        if reference and abs(total_items - float(reference)) > 0.05:
            warnings.append(f"Soma dos itens (R$ {total_items:.2f}) diferente do total dos produtos (R$ {float(reference):.2f}).")
    return {"cabecalho": header, "itens": items, "avisos": warnings}


def _parse_pages(pages: list[PageText], seconds: float) -> dict[str, Any]:
    parsed = parse_danfe(pages)
    sources = {page.source for page in pages}
    confidences = [page.confidence for page in pages if page.confidence is not None]
    parsed.update(
        fonte="ocr" if "ocr" in sources else "texto_pdf",
        paginas=len(pages),
        segundos=round(seconds, 1),
        confianca_ocr=round(sum(confidences) / len(confidences), 1) if confidences else None,
        texto="\n".join(line.text for page in pages for line in page.lines)[:60000],
    )
    return parsed


def read_and_parse(data: bytes, filename: str) -> dict[str, Any]:
    """Lê o arquivo e devolve cabeçalho, itens, avisos, fonte (texto do PDF ou OCR) e o texto lido."""
    result = read_file(data, filename)
    return _parse_pages(result.pages, result.seconds)


def page_groups_by_access_key(pages: list[PageText]) -> list[list[int]] | None:
    """Páginas agrupadas por chave de acesso (a página sem chave legível fica com a anterior). None com menos de
    duas chaves: o arquivo é uma NF só."""
    groups: list[tuple[str | None, list[int]]] = []
    for index, page in enumerate(pages):
        key = find_access_key(page.lines) if page.lines else None
        if groups and (key is None or key == groups[-1][0]):
            groups[-1][1].append(index)
        else:
            groups.append((key, [index]))
    if len([key for key, _ in groups if key]) < 2:
        return None
    return [indices for _, indices in groups]


def read_and_parse_nfs(data: bytes, filename: str) -> list[dict[str, Any]]:
    """Como read_and_parse, mas uma NF por chave de acesso (26/11/2026: PDF escaneado com várias NFs juntas, que a
    separação pelo texto no envio não pega). Cada uma traz "paginas_do_arquivo" (índices das páginas)."""
    result = read_file(data, filename)
    groups = page_groups_by_access_key(result.pages) if len(result.pages) > 1 else None
    if not groups:
        parsed = _parse_pages(result.pages, result.seconds)
        parsed["paginas_do_arquivo"] = list(range(len(result.pages)))
        return [parsed]
    share = result.seconds / max(1, len(groups))
    nfs = []
    for indices in groups:
        parsed = _parse_pages([result.pages[i] for i in indices], share)
        parsed["paginas_do_arquivo"] = indices
        nfs.append(parsed)
    return nfs


def pdf_pages(data: bytes, indices: list[int]) -> bytes:
    """Novo PDF só com as páginas pedidas (para guardar cada NF de um PDF que juntava várias)."""
    pdfium = _pdfium()
    document = pdfium.PdfDocument(data)
    part = pdfium.PdfDocument.new()
    try:
        part.import_pages(document, pages=list(indices))
        buffer = io.BytesIO()
        part.save(buffer)
        return buffer.getvalue()
    finally:
        part.close()
        document.close()
