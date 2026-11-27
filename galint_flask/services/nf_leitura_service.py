"""NF lida (PDF ou foto) → conferência → pré-cadastro (24/11/2026).

Pedido do usuário: "ao ler as NF elas iriam para o pré-cadastro; eu clicaria e abriria um formulário bem
compacto, com os nomes, datas e valores; eu editaria cada item, abriria a página de cadastro de item e lá
daria categoria, unidade básica, quantidade e valores, para ver se estão batendo com a NF". XML e
certificado A1 não estão disponíveis, então a leitura é por OCR (Tesseract) ou pelo texto do PDF
(services/nf_ocr.py).

Fluxo:
1. enviar_arquivos: guarda cada arquivo em instance/nf_leituras/AAAAMM e cria a NFLeitura "lendo". Várias
   NFs de uma vez entram numa FILA e são lidas uma de cada vez, porque o OCR pesa e o servidor é o mesmo
   do GALINT. A fila sobrevive a religar o servidor: a leitura que ficou "lendo" sem estar na fila volta
   para ela uma vez (listar_leituras); se cair de novo, vira erro.
2. processar_leitura: lê, acha o fornecedor pelo CNPJ e vê se a NF já está no GALINT (pela chave, ou pelo
   número com o mesmo fornecedor).
   - JÁ ESTÁ (pedido do usuário em 25/11/2026): a leitura vira "arquivada" e fica ligada ao documento como
     a NF física, a prova de que a nota existe em papel, para ver e imprimir em Documentos Fiscais. Não há
     conferência nem lançamento, para não duplicar a entrada.
   - VÁRIAS NFs NUM PDF SÓ (pedido do usuário em 26/11/2026: "preciso que o sistema leia o PDF inteiro mesmo sendo
     agregadas muitas outras NFs, e que divida as NFs e fiquem individuais como as outras"; caso do
     "19.11 - MERCADO LIVRE R$ 955,12.pdf", 8 NFs da AC Milan das quais só a 28498 entrou): no envio, o PDF com
     texto é separado pela chave de acesso de cada página (nf_ocr.split_pdf_by_access_key) e cada NF vira uma
     leitura com o seu pedaço do PDF; a NF que já consta fica de fora com o aviso. PDF escaneado é separado na
     leitura, depois do OCR de todas as páginas (nf_ocr.read_and_parse_nfs): a leitura fica com a 1ª NF e as
     outras viram leituras novas. O PDF é lido inteiro (até 60 páginas; eram 12).
   - REPETIDA (pedido do usuário em 26/11/2026: "o sistema não pode duplicar NF ao ler se for colocada por
     engano; tem que avisar que aquela NF já consta no sistema"): o MESMO ARQUIVO é recusado já no envio; outro
     arquivo da mesma NF (mesmo documento que já tem arquivo, ou mesmo número e fornecedor de outra leitura na
     lista) vira "duplicada": aviso em vermelho, sem guardar de novo nem abrir conferência. Até aqui a cópia
     enviada para testar (NF 28498) virava uma segunda "arquivada" na lista.
   - PODE SER UMA COMPRA JÁ LANÇADA COM OUTRO NÚMERO (cupom digitado do papel e a NFC-e em PDF):
     documentos_parecidos sugere pelo fornecedor, data e total; confirmada ("É a mesma compra"), a
     leitura vira a NF física dela (unir_a_documento), sem nova entrada no estoque.
   - NÃO ESTÁ: fica "lida", pronta para conferir, com o item do GALINT sugerido para cada linha:
   - código da linha igual ao código de um item;
   - vínculo aprendido antes (mesmo fornecedor + mesmo código de produto);
   - nome parecido (palavras em comum, marca incluída, e semelhança do texto).
3. lancar_leitura: para cada linha marcada na conferência, chama os mesmos serviços, na mesma ordem, da
   rota de NF do app (/api/mobile/documentos-fiscais):
   - linha com item novo: cria o item em PRÉ-CADASTRO (origem "nf") e liga a linha da NF a ele. O saldo
     entra quando o pré-cadastro é concluído na página do item (categoria, unidade básica, quantidade e
     valores), como já acontece com item novo vindo de NF;
   - linha ligada a item existente: registra a linha e dá entrada no estoque, como "Lançar entrada com NF".
   - linha ligada a item existente que JÁ ESTAVA NO ESTOQUE (pedido do usuário em 26/11/2026): muitas NFs
     só chegaram em PDF agora, e os produtos delas entraram antes sem NF (entrada antiga, NOTA INTERNA ou
     ajuste da conferência). A conferência mostra o saldo e essas entradas (entradas_anteriores); a
     escolhida fica ligada à linha da NF (stock_movement_id) e NÃO entra de novo: a NF fica documentada
     (financeiro e última compra) e o "Para onde foi" parte daquela entrada.
   Também registra o financeiro de cada linha e guarda o vínculo fornecedor+código → item para a próxima
   NF. Não manda aviso de item novo pelo Telegram (uma NF grande mandaria dezenas).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from flask import current_app

from ..extensions import db
from ..models import (
    DocumentoEntradaEstoque,
    DocumentoEntradaEstoqueItem,
    Entrada,
    FinanceSupplier,
    Item,
    NFItemVinculo,
    NFLeitura,
    StockMovement,
)
from ..utils.time_service import TimeService
from . import nf_ocr
from .nome_na_nf import nome_na_nf

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 25 * 1024 * 1024
# Leitura "lendo" que não está na fila deste servidor (religado no meio) volta para a fila depois deste
# tempo. Até 25/11/2026 era "20 minutos sem mudar = interrompida", o que derrubava NF parada numa fila longa.
RESUME_AFTER = timedelta(minutes=1)
RESUMED_MESSAGE = "Retomada depois de o servidor ser religado."
PROOF_STATUSES = ("lancada", "arquivada")
SUGGESTION_MIN_SCORE = 0.45
AUTO_LINK_SCORE = 0.75

_STOPWORDS = {"DE", "DA", "DO", "DAS", "DOS", "E", "COM", "PARA", "EM", "C", "P", "A", "O", "AS", "OS", "NA", "NO", "X", "UN", "UND", "PC", "PCT", "CX"}
_UNIT_TOKEN = re.compile(r"(\d+(?:[.,]\d+)?)\s+(KG|G|GR|L|LT|ML|M|MM|CM|M2|M3|W|V|A|MT|MTS|POL)\b")
_NF_UNIT_ALIASES = {"mt": "m", "mts": "m", "mtr": "m", "pr": "par", "kgs": "kg", "und.": "und", "un.": "un"}


# --------------------------------------------------------------------------------------------------
# Ligação com os itens do GALINT
# --------------------------------------------------------------------------------------------------


def _normalize(text: str | None) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(character for character in value if not unicodedata.combining(character)).upper()
    value = _UNIT_TOKEN.sub(lambda match: f"{match.group(1)}{match.group(2)}", value)  # "10 KG" -> "10KG"
    value = re.sub(r"[^A-Z0-9,./]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _tokens(text: str | None) -> set[str]:
    return {token.strip(".,/") for token in _normalize(text).split() if token.strip(".,/") and token.strip(".,/") not in _STOPWORDS}


def _token_weight(token: str) -> float:
    if re.search(r"\d", token):
        return 2.5  # medida (10KG, 2,5MM, 20A) pesa mais
    return 1.0 + min(len(token), 8) / 4.0


@dataclass
class CatalogItem:
    codigo: str
    descricao: str
    marca: str
    unidade: str
    tokens: set[str]
    norm: str
    fator_embalagem: float | None = None
    unidade_documental: str | None = None


def load_catalog() -> list[CatalogItem]:
    """Itens do GALINT para as sugestões, com a embalagem (para a prova real da conferência)."""
    from .item_lookup_service import packaging_proof_fields

    catalog = []
    for item in Item.query.all():
        text = f"{item.descricao or ''} {item.marca or ''}"
        packaging = packaging_proof_fields(item)
        catalog.append(
            CatalogItem(
                str(item.codigo_item), item.descricao or "", item.marca or "", item.unidade or "",
                _tokens(text), _normalize(item.descricao),
                packaging.get("fator_embalagem"), packaging.get("unidade_documental"),
            )
        )
    return catalog


def similarity(nf_description: str, item: CatalogItem, nf_tokens: set[str] | None = None) -> float:
    nf_tokens = nf_tokens if nf_tokens is not None else _tokens(nf_description)
    common = nf_tokens & item.tokens
    if not common or not item.tokens:
        return 0.0
    covered_item = sum(_token_weight(token) for token in common) / sum(_token_weight(token) for token in item.tokens)
    covered_nf = sum(_token_weight(token) for token in common) / max(1.0, sum(_token_weight(token) for token in nf_tokens))
    ratio = SequenceMatcher(None, _normalize(nf_description), item.norm).ratio()
    return round(0.5 * covered_item + 0.25 * covered_nf + 0.25 * ratio, 3)


def suggest_items(
    line: dict[str, Any],
    catalog: list[CatalogItem],
    *,
    linked_code: str | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Até `limit` itens do GALINT para a linha da NF, do mais provável ao menos."""
    by_code = {item.codigo: item for item in catalog}
    suggestions: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(item: CatalogItem, score: float, reason: str) -> None:
        if item.codigo in seen:
            return
        seen.add(item.codigo)
        suggestions.append({
            "codigo": item.codigo, "descricao": item.descricao, "marca": item.marca, "unidade": item.unidade,
            "fator_embalagem": item.fator_embalagem, "unidade_documental": item.unidade_documental,
            "score": score, "motivo": reason,
        })

    supplier_code = str(line.get("codigo") or "").strip()
    if linked_code and linked_code in by_code:
        add(by_code[linked_code], 1.0, "ligado antes")
    if supplier_code and supplier_code in by_code:
        add(by_code[supplier_code], 0.99, "mesmo código")
    nf_tokens = _tokens(line.get("descricao"))
    scored = []
    for item in catalog:
        if item.codigo in seen or not (nf_tokens & item.tokens):
            continue
        score = similarity(line.get("descricao") or "", item, nf_tokens)
        if score >= SUGGESTION_MIN_SCORE:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].descricao))
    for score, item in scored:
        if len(suggestions) >= limit:
            break
        add(item, score, "nome parecido")
    return suggestions[:limit]


def _supplier_by_cnpj(cnpj: str | None) -> FinanceSupplier | None:
    digits = re.sub(r"\D", "", cnpj or "")
    if len(digits) != 14:
        return None
    for supplier in FinanceSupplier.query.filter(FinanceSupplier.cnpj.isnot(None)).all():
        if re.sub(r"\D", "", supplier.cnpj or "") == digits:
            return supplier
    return None


def _existing_document(header: dict[str, Any], supplier: FinanceSupplier | None) -> DocumentoEntradaEstoque | None:
    key = re.sub(r"\D", "", header.get("chave") or "")
    if len(key) == 44:
        found = DocumentoEntradaEstoque.query.filter(DocumentoEntradaEstoque.chave_acesso == key).first()
        if found:
            return found
    number = str(header.get("numero") or "").strip()
    if number and supplier is not None:
        candidates = {number, number.zfill(6), number.zfill(9)}
        return (
            DocumentoEntradaEstoque.query.filter(DocumentoEntradaEstoque.fornecedor_id == supplier.id)
            .filter(DocumentoEntradaEstoque.numero_documento.in_(candidates))
            .first()
        )
    return None


_FILE_NUMBER = re.compile(r"(?<![A-Z])NF\W{0,3}(\d{3,9})(?!\d)", re.IGNORECASE)


def numero_do_arquivo(nome: str | None) -> str | None:
    """Número da NF escrito no nome do arquivo ("OBRAMAX NF 226340 R$ 531,37.pdf", "NF.202472", "NF4002").

    Caso de 26/11/2026: o PDF da NF 226340 não deixou ler o número nem a chave, a NF já estava no GALINT
    (documento 113) e a conferência ia lançar 7 bombonas de novo. Com o número do arquivo e o fornecedor
    pelo CNPJ, a leitura acha o documento e vira a NF física dele."""
    match = _FILE_NUMBER.search(str(nome or ""))
    return match.group(1).lstrip("0") or None if match else None


def _header_with_file_number(header: dict[str, Any], arquivo_nome: str | None) -> dict[str, Any]:
    if str(header.get("numero") or "").strip():
        return header
    numero = numero_do_arquivo(arquivo_nome)
    return {**header, "numero": numero} if numero else header


SAME_PURCHASE_DAYS = 3


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10]) if value else None
    except ValueError:
        return None


def documentos_parecidos(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Compra já lançada que pode ser esta NF sem ter a mesma chave nem o mesmo número (25/11/2026).

    Caso do usuário: cupom de balcão digitado do papel (Almedas, BMB/Obramax), sem chave e com o número
    impresso no cupom. O PDF que chega depois é a NFC-e (modelo 65) da mesma venda, com outro número:
    sem esta busca, o Ler NF lançaria a compra de novo e o estoque entraria em dobro.
    Mesma compra = mesmo fornecedor (CNPJ), documento sem chave, data até 3 dias de diferença e total
    igual (até R$ 1 ou 1%); sem o total lido, só a mesma data.
    """
    header = result.get("cabecalho") or {}
    supplier = _supplier_by_cnpj(header.get("cnpj_emitente"))
    emissao = _as_date(header.get("data_emissao"))
    if supplier is None or emissao is None:
        return []
    nf_total = header.get("valor_total") or header.get("valor_produtos")
    found = []
    for documento in DocumentoEntradaEstoque.query.filter(DocumentoEntradaEstoque.fornecedor_id == supplier.id).all():
        if len(re.sub(r"\D", "", documento.chave_acesso or "")) == 44:
            continue  # tem chave própria: se fosse esta NF, a chave teria achado
        doc_date = documento.data_emissao or documento.data_recebimento
        if doc_date is None or abs((doc_date - emissao).days) > SAME_PURCHASE_DAYS:
            continue
        doc_total = round(sum(
            float(line.valor_total) if line.valor_total is not None else float(line.valor_unitario or 0) * float(line.quantidade or 0)
            for line in documento.itens
        ), 2)
        if nf_total and doc_total:
            if abs(float(nf_total) - doc_total) > max(1.0, 0.01 * float(nf_total)):
                continue
        elif doc_date != emissao:
            continue
        found.append({
            "id": documento.id_documento,
            "tipo": documento.tipo_documento,
            "numero": documento.numero_documento,
            "data": doc_date.isoformat(),
            "total": doc_total,
        })
    return found


def unir_a_documento(reading: NFLeitura, documento_id: int, *, usuario: str | None = None) -> DocumentoEntradaEstoque:
    """O usuário confirmou que esta NF é a compra já lançada: o arquivo vira a NF física dela, sem nova
    entrada no estoque. Documento sem chave recebe a chave lida, para a próxima leitura achar sozinha."""
    if reading.status != "lida" or (load_result(reading).get("lancamento") or {}).get("linhas"):
        raise ValueError("Esta leitura não pode mais ser juntada a outro documento.")
    documento = db.session.get(DocumentoEntradaEstoque, documento_id)
    if documento is None:
        raise ValueError("Documento não encontrado.")
    result = load_result(reading)
    header = result.get("cabecalho") or {}
    chave = re.sub(r"\D", "", header.get("chave") or "")
    if len(chave) == 44 and not re.sub(r"\D", "", documento.chave_acesso or ""):
        if DocumentoEntradaEstoque.query.filter(DocumentoEntradaEstoque.chave_acesso == chave).first() is None:
            documento.chave_acesso = chave
    cnpj = re.sub(r"\D", "", header.get("cnpj_emitente") or "")
    if len(cnpj) == 14 and not documento.cnpj_emitente:
        documento.cnpj_emitente = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    result["unida_a"] = {"id": documento.id_documento, "tipo": documento.tipo_documento, "numero": documento.numero_documento, "por": usuario}
    _archive_as_proof(reading, documento.id_documento, documento.numero_documento)
    _save_result(reading, result)
    db.session.commit()
    return documento


def enrich_reading(result: dict[str, Any]) -> dict[str, Any]:
    """Acrescenta ao que o leitor achou: fornecedor do cadastro, NF já lançada e sugestões de item."""
    header = result["cabecalho"]
    supplier = _supplier_by_cnpj(header.get("cnpj_emitente"))
    if supplier is not None:
        result["fornecedor"] = {"id": supplier.id, "nome": supplier.razao_social}
        header["emitente"] = header.get("emitente") or supplier.razao_social
    existing = _existing_document(header, supplier)
    if existing is not None:
        result["ja_lancada"] = {"id": existing.id_documento, "numero": existing.numero_documento}
    else:
        result["parecidas"] = documentos_parecidos(result)
    cnpj = re.sub(r"\D", "", header.get("cnpj_emitente") or "")
    links: dict[str, str] = {}
    if cnpj:
        links = {row.codigo_fornecedor: row.codigo_item for row in NFItemVinculo.query.filter_by(cnpj_fornecedor=cnpj).all()}
    catalog = load_catalog()
    for line in result["itens"]:
        line["sugestoes"] = suggest_items(line, catalog, linked_code=links.get(str(line.get("codigo") or "").strip()))
        best = line["sugestoes"][0] if line["sugestoes"] else None
        line["acao"] = best["codigo"] if best and best["score"] >= AUTO_LINK_SCORE else "novo"
    if existing is None:
        _ligar_ao_que_ja_entrou(result, catalog)
    return result


def _so_data(valor: Any) -> date | None:
    """Data sem hora (o documento guarda data; a entrada antiga, data e hora)."""
    return valor.date() if hasattr(valor, "hour") else valor


def _entradas_com_o_numero(numero: str) -> list[dict[str, Any]]:
    """O que já entrou no estoque com este número de NF sem o documento da NF: entradas antigas (nota_fiscal escrita
    à mão) e linhas de documento manual. [{codigo, quantidade, data}]."""
    digitos = re.sub(r"\D", "", numero or "").lstrip("0")
    if len(digitos) < 3:
        return []
    achadas: list[dict[str, Any]] = []
    entradas_de_documento: set[int] = set()
    manuais = (
        db.session.query(DocumentoEntradaEstoqueItem, DocumentoEntradaEstoque)
        .join(DocumentoEntradaEstoque, DocumentoEntradaEstoqueItem.documento_id == DocumentoEntradaEstoque.id_documento)
        .filter(DocumentoEntradaEstoque.numero_documento.ilike(f"%{digitos}%"))
        .all()
    )
    for linha, documento in manuais:
        if re.sub(r"\D", "", documento.numero_documento or "").lstrip("0") != digitos:
            continue
        if linha.entrada_id:
            entradas_de_documento.add(int(linha.entrada_id))
        if (documento.tipo_documento or "").strip().lower() != "manual":
            continue
        if linha.entrada_id:
            continue  # vem da entrada antiga, logo abaixo
        achadas.append({"codigo": linha.codigo_item, "quantidade": float(linha.quantidade or 0), "data": _so_data(documento.data_recebimento or documento.criado_em)})
    for entrada in Entrada.query.filter(Entrada.nota_fiscal.ilike(f"%{digitos}%")).all():
        if re.sub(r"\D", "", entrada.nota_fiscal or "").lstrip("0") != digitos:
            continue
        documentada = entrada.id_entrada in entradas_de_documento and any(
            (doc.tipo_documento or "").strip().lower() != "manual"
            for linha, doc in manuais if linha.entrada_id == entrada.id_entrada
        )
        if documentada:
            continue  # já tem o documento da NF de verdade
        achadas.append({"codigo": entrada.codigo_item, "quantidade": float(entrada.quantidade or 0), "data": _so_data(entrada.data_entrada)})
    return [a for a in achadas if a["codigo"]]


def _ligar_ao_que_ja_entrou(result: dict[str, Any], catalog: list[CatalogItem]) -> None:
    """NF cujo material já entrou no estoque sem o arquivo da NF (27/11/2026: a NF 101456 da Obramax entrou em 21/03
    pela tela antiga de entradas, com "NF 101456" escrito, e virou o documento manual 15, sem fornecedor nem chave).
    Cada linha da NF é casada com o item dessas entradas (nome parecido, e mais ainda com a mesma quantidade): a linha
    já vem ligada a ele e a conferência marca sozinha o "Já no estoque", para não somar de novo."""
    numero = str((result.get("cabecalho") or {}).get("numero") or "")
    entradas = _entradas_com_o_numero(numero)
    if not entradas:
        return
    por_codigo = {item.codigo: item for item in catalog}
    pares = []
    for indice, linha in enumerate(result.get("itens") or []):
        tokens = _tokens(linha.get("descricao"))
        for posicao, entrada in enumerate(entradas):
            item = por_codigo.get(entrada["codigo"])
            if item is None:
                continue
            nota = similarity(linha.get("descricao") or "", item, tokens)
            mesma_quantidade = abs(float(linha.get("quantidade") or 0) - entrada["quantidade"]) < 1e-6
            if (mesma_quantidade and nota >= 0.30) or nota >= 0.45:
                pares.append((nota + (0.25 if mesma_quantidade else 0.0), indice, posicao))
    pares.sort(reverse=True)
    linhas_usadas: set[int] = set()
    entradas_usadas: set[int] = set()
    ligadas = 0
    itens = result["itens"]
    for nota, indice, posicao in pares:
        if indice in linhas_usadas or posicao in entradas_usadas:
            continue
        linhas_usadas.add(indice)
        entradas_usadas.add(posicao)
        entrada, linha, item = entradas[posicao], itens[indice], por_codigo[entradas[posicao]["codigo"]]
        quando = entrada["data"].strftime("%d/%m/%Y") if entrada.get("data") else ""
        sugestao = {
            "codigo": item.codigo, "descricao": item.descricao, "marca": item.marca, "unidade": item.unidade,
            "fator_embalagem": item.fator_embalagem, "unidade_documental": item.unidade_documental,
            "score": round(min(1.0, nota), 4), "motivo": f"entrou com a NF {numero} {quando}".strip(),
        }
        linha["sugestoes"] = [sugestao] + [s for s in (linha.get("sugestoes") or []) if s.get("codigo") != item.codigo][:2]
        linha["acao"] = item.codigo
        ligadas += 1
    datas = [e["data"] for e in entradas if e.get("data")]
    primeira = min(datas).strftime("%d/%m/%Y") if datas else ""
    result["ja_entrou_sem_arquivo"] = {"numero": numero, "itens": len(entradas), "ligadas": ligadas}
    result.setdefault("avisos", []).insert(0, (
        f"A NF {numero} já tinha entrado no estoque sem o arquivo ({len(entradas)} itens{f' em {primeira}' if primeira else ''}). "
        f"{ligadas} linha(s) foram ligadas a esses itens e o \"Já no estoque\" vem marcado: confira para não somar de novo."
    ))


# --------------------------------------------------------------------------------------------------
# Leituras: envio, processamento em segundo plano, consulta
# --------------------------------------------------------------------------------------------------


_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()
_QUEUED: set[int] = set()  # leituras na fila deste servidor (esperando ou sendo lidas)


def _executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="galint-nf-ocr")
        return _EXECUTOR


def queued_ids() -> set[int]:
    with _EXECUTOR_LOCK:
        return set(_QUEUED)


def _storage_root() -> Path:
    return Path(current_app.instance_path) / "nf_leituras"


def reading_file_path(reading: NFLeitura) -> Path:
    return Path(current_app.instance_path) / reading.arquivo_path


def load_result(reading: NFLeitura) -> dict[str, Any]:
    try:
        return json.loads(reading.resultado_json or "{}")
    except ValueError:
        return {}


def _save_result(reading: NFLeitura, result: dict[str, Any]) -> None:
    reading.resultado_json = json.dumps(result, ensure_ascii=False, default=str)


def _rotulo_da_leitura(leitura: NFLeitura) -> str:
    numero = f"NF {leitura.numero_documento}" if leitura.numero_documento else f"O arquivo {leitura.arquivo_nome}"
    quando = leitura.criado_em.strftime("%d/%m/%Y") if leitura.criado_em else ""
    return f"{numero}{f' (enviada em {quando})' if quando else ''}"


def mesmo_arquivo(data: bytes) -> NFLeitura | None:
    """Leitura (não descartada) com exatamente o mesmo arquivo: mesmo tamanho e mesmo SHA-256."""
    alvo = hashlib.sha256(data).digest()
    for leitura in NFLeitura.query.filter(NFLeitura.status != "descartada").order_by(NFLeitura.id).all():
        caminho = reading_file_path(leitura)
        try:
            if caminho.stat().st_size != len(data) or hashlib.sha256(caminho.read_bytes()).digest() != alvo:
                continue
        except OSError:
            continue
        return leitura
    return None


def aviso_de_repetida(leitura: NFLeitura) -> str:
    rotulo = _rotulo_da_leitura(leitura)
    if leitura.status in PROOF_STATUSES or leitura.status == "duplicada":
        return f"{rotulo} já consta no sistema."
    if leitura.status == "lida":
        return f"{rotulo} já está na lista, pronta para conferir."
    if leitura.status == "lendo":
        return f"{rotulo} já está na fila de leitura."
    return f"{rotulo} já está na lista (deu erro: use Ler de novo)."


def _guardar_arquivo(data: bytes, suffix: str) -> str:
    """Grava o arquivo em instance/nf_leituras/AAAAMM e devolve o caminho relativo à instance."""
    folder = _storage_root() / TimeService.now_db().strftime("%Y%m")
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / f"{uuid.uuid4().hex}{suffix}"
    stored.write_bytes(data)
    return str(stored.relative_to(Path(current_app.instance_path))).replace("\\", "/")


def _nome_da_parte(nome: str, numero: str | None, ordem: int) -> str:
    raiz, suffix = os.path.splitext(nome)
    marca = f"NF {numero}" if numero else f"parte {ordem}"
    return f"{raiz} · {marca}{suffix}"[:255]


def _documento_com_arquivo(chave: str | None) -> DocumentoEntradaEstoque | None:
    """Documento com esta chave que já tem o arquivo da NF guardado (leitura lançada ou arquivada)."""
    if not chave:
        return None
    documento = DocumentoEntradaEstoque.query.filter(DocumentoEntradaEstoque.chave_acesso == chave).first()
    if documento is None:
        return None
    guardada = NFLeitura.query.filter(NFLeitura.documento_id == documento.id_documento, NFLeitura.status.in_(PROOF_STATUSES)).first()
    return documento if guardada is not None else None


def _partes_do_pdf(name: str, data: bytes) -> list[dict[str, Any]] | None:
    if os.path.splitext(name)[1].lower() not in nf_ocr.PDF_SUFFIXES and data[:5] != b"%PDF-":
        return None
    try:
        return nf_ocr.split_pdf_by_access_key(data)
    except Exception:  # PDF estranho: segue inteiro, como sempre
        logger.exception("Falha ao separar as NFs do PDF %s", name)
        return None


def enviar_arquivos(files: list[Any], *, usuario: str | None, repetidos: list[str] | None = None) -> list[NFLeitura]:
    """Guarda os arquivos enviados e agenda a leitura de cada um. Arquivo igual a um já enviado não entra: o
    aviso vai para `repetidos` (ou vira o erro, se nenhum arquivo entrou). PDF com várias NFs vira uma leitura
    por NF; a NF que já consta (documento com arquivo guardado) fica de fora com o aviso."""
    created: list[NFLeitura] = []
    avisos: list[str] = []
    for storage in files:
        name = os.path.basename(str(getattr(storage, "filename", "") or "")).strip()
        if not name:
            continue
        suffix = os.path.splitext(name)[1].lower()
        if suffix not in nf_ocr.ACCEPTED_SUFFIXES:
            raise ValueError(f"{name}: envie PDF ou foto (JPG, PNG).")
        data = storage.read()
        if not data:
            raise ValueError(f"{name}: arquivo vazio.")
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(f"{name}: arquivo maior que 25 MB.")
        partes = _partes_do_pdf(name, data)
        if partes:
            for ordem, parte in enumerate(partes, start=1):
                numero = nf_ocr.describe_access_key(parte["chave"])["numero"] if parte["chave"] else None
                if _documento_com_arquivo(parte["chave"]) is not None:
                    avisos.append(f"NF {numero} já consta no sistema.")
                    continue
                igual = mesmo_arquivo(parte["data"])
                if igual is not None:
                    avisos.append(aviso_de_repetida(igual))
                    continue
                reading = NFLeitura(
                    arquivo_nome=_nome_da_parte(name, numero, ordem),
                    arquivo_path=_guardar_arquivo(parte["data"], ".pdf"),
                    status="lendo",
                    criado_por=usuario,
                )
                db.session.add(reading)
                created.append(reading)
            continue
        igual = mesmo_arquivo(data)
        if igual is not None:
            avisos.append(aviso_de_repetida(igual))
            continue
        reading = NFLeitura(
            arquivo_nome=name[:255],
            arquivo_path=_guardar_arquivo(data, suffix),
            status="lendo",
            criado_por=usuario,
        )
        db.session.add(reading)
        created.append(reading)
    if repetidos is not None:
        repetidos.extend(avisos)
    if not created:
        raise ValueError(" ".join(avisos) if avisos else "Escolha o PDF ou a foto da NF.")
    db.session.commit()
    for reading in created:
        agendar_leitura(reading.id)
    return created


def agendar_leitura(reading_id: int) -> None:
    app = current_app._get_current_object()
    if app.config.get("TESTING") or app.config.get("GALINT_NF_OCR_SYNC"):
        processar_leitura(reading_id)
        return
    with _EXECUTOR_LOCK:
        if reading_id in _QUEUED:
            return
        _QUEUED.add(reading_id)
    _executor().submit(_process_in_app, app, reading_id)


def _process_in_app(app, reading_id: int) -> None:
    with app.app_context():
        try:
            processar_leitura(reading_id)
        except Exception:  # pragma: no cover - registrado no log
            logger.exception("Falha ao ler a NF %s", reading_id)
        finally:
            db.session.remove()
            with _EXECUTOR_LOCK:
                _QUEUED.discard(reading_id)


def _archive_as_proof(reading: NFLeitura, documento_id: int, numero: str | None) -> None:
    """NF que já está no GALINT: o arquivo fica ligado ao documento como a NF física (ver e imprimir)."""
    reading.status = "arquivada"
    reading.documento_id = documento_id
    reading.numero_documento = (str(numero or reading.numero_documento or "")[:20]) or None
    reading.mensagem = None


def _digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _mesmo_fornecedor(a: dict[str, Any], b: dict[str, Any], leitura_a: NFLeitura, leitura_b: NFLeitura) -> bool:
    cnpj_a, cnpj_b = _digitos(a.get("cnpj_emitente")), _digitos(b.get("cnpj_emitente"))
    if len(cnpj_a) == 14 and len(cnpj_b) == 14:
        return cnpj_a == cnpj_b
    nome_a, nome_b = _normalize(leitura_a.fornecedor_nome or a.get("emitente")), _normalize(leitura_b.fornecedor_nome or b.get("emitente"))
    if nome_a and nome_b:
        return nome_a == nome_b
    total_a, total_b = leitura_a.valor_total, leitura_b.valor_total
    return total_a is not None and total_b is not None and abs(float(total_a) - float(total_b)) < 0.01


def outra_leitura_da_mesma_nf(reading: NFLeitura, header: dict[str, Any], documento_id: int | None) -> NFLeitura | None:
    """Outra leitura que já guarda esta NF: o arquivo do mesmo documento (lançada/arquivada), ou a mesma NF
    (número + fornecedor) ainda na lista para conferir."""
    if documento_id:
        guardada = (
            NFLeitura.query.filter(NFLeitura.id != reading.id, NFLeitura.documento_id == documento_id,
                                   NFLeitura.status.in_(PROOF_STATUSES))
            .order_by(NFLeitura.id)
            .first()
        )
        if guardada is not None:
            return guardada
    numero = str(header.get("numero") or "").strip()[:20]
    if not numero:
        return None
    candidatas = (
        NFLeitura.query.filter(NFLeitura.id != reading.id, NFLeitura.numero_documento == numero,
                               NFLeitura.status.in_(("lida",) + PROOF_STATUSES))
        .order_by(NFLeitura.id)
        .all()
    )
    for candidata in candidatas:
        if _mesmo_fornecedor(header, load_result(candidata).get("cabecalho") or {}, reading, candidata):
            return candidata
    return None


def _marcar_duplicada(reading: NFLeitura, original: NFLeitura, documento_id: int | None) -> None:
    reading.status = "duplicada"
    reading.documento_id = documento_id
    reading.mensagem = aviso_de_repetida(original)


def _aplicar_leitura(reading: NFLeitura, parsed: dict[str, Any], previous_launch: dict[str, Any]) -> None:
    """Resultado do leitor → leitura "lida", "arquivada" (NF já no GALINT) ou "duplicada" (NF já guardada)."""
    parsed["cabecalho"] = _header_with_file_number(parsed.get("cabecalho") or {}, reading.arquivo_nome)
    result = enrich_reading(parsed)
    if previous_launch:
        result["lancamento"] = previous_launch
    header = result["cabecalho"]
    reading.status = "lida"
    reading.fonte = result.get("fonte")
    reading.mensagem = None
    reading.numero_documento = (header.get("numero") or None) and str(header["numero"])[:20]
    reading.fornecedor_nome = (header.get("emitente") or None) and str(header["emitente"])[:200]
    reading.valor_total = header.get("valor_total") or header.get("valor_produtos")
    existing = result.get("ja_lancada")
    original = None if previous_launch.get("linhas") else outra_leitura_da_mesma_nf(reading, header, (existing or {}).get("id"))
    if original is not None:
        _marcar_duplicada(reading, original, (existing or {}).get("id"))
    elif existing and not previous_launch.get("linhas"):
        _archive_as_proof(reading, existing["id"], existing.get("numero"))
    _save_result(reading, result)


def processar_leitura(reading_id: int) -> None:
    reading = db.session.get(NFLeitura, reading_id)
    if reading is None:
        return
    # Lançamento interrompido no meio: a NF já existe por causa desta própria leitura; continua "lida".
    previous_launch = load_result(reading).get("lancamento") or {}
    try:
        data = reading_file_path(reading).read_bytes()
        nfs = nf_ocr.read_and_parse_nfs(data, reading.arquivo_nome)
        eh_pdf = data[:5] == b"%PDF-"
        if len(nfs) > 1 and eh_pdf and not previous_launch:
            # PDF escaneado com várias NFs: esta leitura fica com a 1ª e o seu pedaço do PDF; as outras viram
            # leituras novas, já lidas (sem OCR de novo), cada uma com o seu pedaço.
            nome_original = reading.arquivo_nome
            for ordem, parsed in enumerate(nfs, start=1):
                numero = (parsed.get("cabecalho") or {}).get("numero")
                destino = reading if ordem == 1 else NFLeitura(status="lendo", criado_por=reading.criado_por, arquivo_nome="", arquivo_path="")
                destino.arquivo_nome = _nome_da_parte(nome_original, str(numero) if numero else None, ordem)
                destino.arquivo_path = _guardar_arquivo(nf_ocr.pdf_pages(data, parsed["paginas_do_arquivo"]), ".pdf")
                if ordem > 1:
                    db.session.add(destino)
                    db.session.flush()
                _aplicar_leitura(destino, parsed, {})
                db.session.flush()
        else:
            _aplicar_leitura(reading, nfs[0], previous_launch)
    except nf_ocr.OcrUnavailableError as exc:
        reading.status = "erro"
        reading.mensagem = str(exc)
    except Exception as exc:
        logger.exception("Erro ao ler a NF %s (%s)", reading_id, reading.arquivo_nome)
        reading.status = "erro"
        reading.mensagem = f"Não foi possível ler o arquivo: {exc}"
    db.session.commit()


def verificar_nf_existente(reading: NFLeitura) -> dict[str, Any] | None:
    """Leitura pronta para conferir cuja NF entrou no GALINT depois (outra leitura, Documentos Fiscais,
    app): vira NF física daquele documento. Devolve o documento achado, ou None."""
    if reading.status != "lida":
        return None
    result = load_result(reading)
    if (result.get("lancamento") or {}).get("linhas"):
        return None
    header = _header_with_file_number(result.get("cabecalho") or {}, reading.arquivo_nome)
    existing = _existing_document(header, _supplier_by_cnpj(header.get("cnpj_emitente")))
    if existing is None:
        return None
    found = {"id": existing.id_documento, "numero": existing.numero_documento}
    result["ja_lancada"] = found
    original = outra_leitura_da_mesma_nf(reading, header, existing.id_documento)
    if original is not None:
        _marcar_duplicada(reading, original, existing.id_documento)
        found["duplicada"] = reading.mensagem
    else:
        _archive_as_proof(reading, existing.id_documento, existing.numero_documento)
    _save_result(reading, result)
    db.session.commit()
    return found


def _resume_interrupted_readings() -> None:
    """Leitura "lendo" fora da fila deste servidor (religado no meio): volta para a fila uma vez."""
    queued = queued_ids()
    resume_before = TimeService.now_db() - RESUME_AFTER
    interrupted = [
        reading
        for reading in NFLeitura.query.filter(NFLeitura.status == "lendo").order_by(NFLeitura.id).all()
        if reading.id not in queued and reading.atualizado_em is not None and reading.atualizado_em < resume_before
    ]
    to_queue = []
    for reading in interrupted:
        if reading.mensagem == RESUMED_MESSAGE:
            reading.status = "erro"
            reading.mensagem = "Leitura interrompida duas vezes. Clique em Ler de novo."
        else:
            reading.mensagem = RESUMED_MESSAGE
            to_queue.append(reading.id)
    if interrupted:
        db.session.commit()
    for reading_id in to_queue:
        agendar_leitura(reading_id)


def _marcar_copias_guardadas() -> None:
    """Cópias guardadas antes da regra de 26/11/2026 (2ª NF física do mesmo documento, como a cópia de teste da
    NF 28498) viram "duplicada". Fica a lançada ou, sem ela, a mais antiga; nunca mexe numa lançada."""
    provas = (
        NFLeitura.query.filter(NFLeitura.status.in_(PROOF_STATUSES), NFLeitura.documento_id.isnot(None))
        .order_by(NFLeitura.id)
        .all()
    )
    por_documento: dict[int, list[NFLeitura]] = {}
    for prova in provas:
        por_documento.setdefault(int(prova.documento_id), []).append(prova)
    mudou = False
    for lista in por_documento.values():
        if len(lista) < 2:
            continue
        original = next((prova for prova in lista if prova.status == "lancada"), lista[0])
        for prova in lista:
            if prova is not original and prova.status == "arquivada":
                _marcar_duplicada(prova, original, prova.documento_id)
                mudou = True
    if mudou:
        db.session.commit()


def listar_leituras(limit: int = 60) -> list[NFLeitura]:
    """Leituras ainda não descartadas, mais novas primeiro."""
    _resume_interrupted_readings()
    _marcar_copias_guardadas()
    return (
        NFLeitura.query.filter(NFLeitura.status != "descartada")
        .order_by(NFLeitura.criado_em.desc(), NFLeitura.id.desc())
        .limit(limit)
        .all()
    )


def reler(reading: NFLeitura) -> None:
    if reading.status in PROOF_STATUSES:
        raise ValueError("Esta NF já está no GALINT.")
    reading.status = "lendo"
    reading.mensagem = None
    db.session.commit()
    agendar_leitura(reading.id)


def descartar(reading: NFLeitura) -> None:
    if reading.status == "lancada":
        raise ValueError("Esta NF já foi lançada.")
    reading.status = "descartada"
    db.session.commit()


# --------------------------------------------------------------------------------------------------
# Lançamento no pré-cadastro
# --------------------------------------------------------------------------------------------------


def nf_unit_to_base(unit: str | None) -> str:
    from .inventory import normalize_base_item_unit

    raw = str(unit or "").strip().lower()
    return normalize_base_item_unit(_NF_UNIT_ALIASES.get(raw, raw), fallback="Unidade") or "Unidade"


def _new_item_code(supplier_code: str | None) -> str:
    from .inventory import inventory_service

    code = str(supplier_code or "").strip()
    # Código da NF que é um código de barras válido (EAN) vira o código do item; senão, código interno.
    if nf_ocr.is_valid_gtin(code) and db.session.get(Item, code) is None:
        return code
    return inventory_service.generate_unique_internal_barcode_code(prefix="2")


def _remember_link(cnpj: str, supplier_code: str, description: str, item_code: str, usuario: str | None) -> None:
    supplier_code = str(supplier_code or "").strip()[:60]
    if len(cnpj) != 14 or not supplier_code:
        return
    row = NFItemVinculo.query.filter_by(cnpj_fornecedor=cnpj, codigo_fornecedor=supplier_code).first()
    if row is None:
        row = NFItemVinculo(cnpj_fornecedor=cnpj, codigo_fornecedor=supplier_code)
        db.session.add(row)
    row.codigo_item = item_code
    row.descricao_fornecedor = (description or "")[:255] or None
    row.atualizado_por = usuario
    db.session.commit()


_UNIT_SHORT = {"quilo": "kg", "litro": "L", "metro": "m", "unidade": "un", "par": "par", "rolo": "rolo"}
_AJUSTE_REFS = {"inventario_evento", "admin_balance_override"}


def entradas_anteriores(codigo: str) -> dict[str, Any]:
    """Saldo do item e as entradas dele que nenhuma NF documenta ainda (26/11/2026).

    Pedido do usuário: "verifique quantos daquele produto temos em estoque antes de lançar a mesma
    quantidade que anteriormente já tinha sido posta". Entra na lista o que somou estoque sem NF:
    - entrada antiga (tabela entradas, de antes dos documentos fiscais);
    - linha de documento "manual" (NOTA INTERNA, sem NF);
    - ajuste para mais (conferência física, saldo corrigido pelo administrador).
    Entrada de NF ou cupom já é documentada e fica fora. Cada entrada mostra quanto ainda não foi coberto
    por NF ("disponivel"), porque uma entrada antiga grande pode ser a soma de várias compras.
    """
    codigo = str(codigo or "").strip()
    item = db.session.get(Item, codigo) if codigo else None
    if item is None:
        return {"codigo": codigo, "descricao": "", "saldo": 0.0, "unidade": "", "entradas": []}
    unidade = _UNIT_SHORT.get(str(item.unidade or "").strip().lower(), str(item.unidade or "").strip().lower())
    saldo = float(
        db.session.query(db.func.coalesce(db.func.sum(StockMovement.quantity_base), 0.0))
        .filter(StockMovement.product_id == codigo)
        .scalar()
        or 0.0
    )
    movements = (
        StockMovement.query.filter(
            StockMovement.product_id == codigo,
            StockMovement.quantity_base > 0,
            StockMovement.movement_type.in_(("entrada", "ajuste")),
        )
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .all()
    )
    rows = (
        db.session.query(DocumentoEntradaEstoqueItem, DocumentoEntradaEstoque.tipo_documento, DocumentoEntradaEstoque.numero_documento)
        .join(DocumentoEntradaEstoque, DocumentoEntradaEstoque.id_documento == DocumentoEntradaEstoqueItem.documento_id)
        .filter(DocumentoEntradaEstoqueItem.codigo_item == codigo)
        .all()
    )
    by_line = {str(row.id_documento_item): (tipo, numero) for row, tipo, numero in rows}
    covered: dict[int, float] = {}
    for row, tipo, _numero in rows:
        if tipo != "manual" and row.stock_movement_id is not None:
            covered[row.stock_movement_id] = covered.get(row.stock_movement_id, 0.0) + float(row.quantidade_base or row.quantidade or 0)
    legacy_ids = [int(m.reference_id) for m in movements if m.reference_type == "entrada" and str(m.reference_id or "").isdigit()]
    legacy_nf = {
        entrada.id_entrada: str(entrada.nota_fiscal or "").strip()
        for entrada in (Entrada.query.filter(Entrada.id_entrada.in_(legacy_ids)).all() if legacy_ids else [])
    }

    entradas = []
    for movement in movements:
        reference = movement.reference_type or ""
        if reference == "entrada_documento_item":
            tipo, numero = by_line.get(str(movement.reference_id), (None, None))
            if tipo != "manual":
                continue  # entrada de NF ou cupom: já documentada
            origem = "NOTA INTERNA" if str(numero or "").strip().upper() == "NOTA INTERNA" else f"SEM NF {numero or ''}".strip()
        elif reference == "entrada":
            nf_antiga = legacy_nf.get(int(movement.reference_id)) if str(movement.reference_id or "").isdigit() else ""
            origem = f"ENTRADA ANTIGA · NF {nf_antiga}" if nf_antiga and nf_antiga.upper() not in {"SEM NF", "NOTA INTERNA"} else "ENTRADA ANTIGA"
        elif movement.movement_type == "ajuste" and reference in _AJUSTE_REFS:
            origem = "AJUSTE"
        else:
            continue
        quantidade = float(movement.quantity_base or 0)
        disponivel = quantidade - covered.get(movement.id, 0.0)
        if disponivel <= 1e-6:
            continue
        entradas.append({
            "id": movement.id,
            "data": movement.created_at.date().isoformat() if movement.created_at else None,
            "quantidade": round(quantidade, 6),
            "disponivel": round(disponivel, 6),
            "origem": origem,
        })
    return {"codigo": codigo, "descricao": item.descricao or "", "saldo": round(saldo, 6), "unidade": unidade, "entradas": entradas}


def lancar_leitura(reading: NFLeitura, header: dict[str, Any], lines: list[dict[str, Any]], *, usuario: str | None, usuario_nome: str | None = None) -> dict[str, Any]:
    """Lança as linhas conferidas. Linhas já lançadas numa tentativa anterior são puladas."""
    from .category_catalog import DEFAULT_INVENTORY_CATEGORY_NAME, category_catalog_service
    from .finance_service import finance_service
    from .inventory import inventory_service

    if reading.status == "lancada":
        raise ValueError("Esta NF já foi lançada.")
    if reading.status == "arquivada":
        raise ValueError(f"Esta NF já está no GALINT (documento nº {reading.numero_documento}); o arquivo ficou guardado como NF física.")
    if reading.status == "duplicada":
        raise ValueError(reading.mensagem or "Esta NF já consta no sistema.")
    if reading.status != "lida":
        raise ValueError("A leitura desta NF ainda não terminou ou deu erro.")
    numero = str(header.get("numero") or "").strip()
    if not numero:
        raise ValueError("Informe o número da NF.")
    data_emissao: date | None = header.get("data_emissao")
    data_recebimento: date = header.get("data_recebimento") or date.today()
    if data_emissao is None:
        raise ValueError("Informe a data de emissão.")
    selected = [line for line in lines if line.get("incluir")]
    if not selected:
        raise ValueError("Marque ao menos um item para lançar.")
    ja_no_estoque: dict[int, StockMovement] = {}
    for line in selected:
        if not (float(line.get("quantidade") or 0) > 0):
            raise ValueError(f"Item {line['n']}: informe a quantidade.")
        if line.get("acao") != "novo":
            if not line.get("codigo_item") or db.session.get(Item, line["codigo_item"]) is None:
                raise ValueError(f"Item {line['n']}: item do GALINT não encontrado.")
            movimento_id = line.get("movimento_existente")
            if movimento_id:
                disponiveis = {row["id"] for row in entradas_anteriores(line["codigo_item"])["entradas"]}
                movimento = db.session.get(StockMovement, int(movimento_id))
                if movimento is None or movimento.id not in disponiveis:
                    raise ValueError(f"Item {line['n']}: a entrada escolhida em \"Estoque\" não está mais livre; confira de novo.")
                if any(other.id == movimento.id for other in ja_no_estoque.values()):
                    raise ValueError(f"Item {line['n']}: a mesma entrada antiga foi escolhida em duas linhas.")
                ja_no_estoque[line["n"]] = movimento
        elif not str(line.get("descricao") or "").strip():
            raise ValueError(f"Item {line['n']}: informe a descrição.")

    result = load_result(reading)
    launched: list[int] = list(result.get("lancamento", {}).get("linhas", []))
    cnpj = re.sub(r"\D", "", header.get("cnpj") or "")
    supplier = _supplier_by_cnpj(cnpj)
    existing = _existing_document({"chave": header.get("chave"), "numero": numero}, supplier)
    if existing is not None and not launched:
        raise ValueError(f"Esta NF já está no GALINT (documento nº {existing.numero_documento}).")

    chave = re.sub(r"\D", "", header.get("chave") or "") or None
    supplier_inputs = finance_service.sanitize_document_supplier_inputs(
        tipo_documento="nf",
        supplier_id=supplier.id if supplier else None,
        supplier_name=str(header.get("fornecedor") or "").strip() or (supplier.razao_social if supplier else None),
        supplier_cnpj=cnpj or None,
    )
    movimenta_estoque = finance_service.resolve_document_movimenta_estoque(data_emissao=data_emissao, data_recebimento=data_recebimento)
    categoria_padrao = category_catalog_service.resolve_name(None, fallback=DEFAULT_INVENTORY_CATEGORY_NAME, actor=usuario_nome or usuario)

    novos: list[str] = []
    existentes: list[str] = []
    documentados: list[str] = []
    warnings: list[str] = []
    documento = None
    for line in selected:
        if line["n"] in launched:
            continue
        quantidade = float(line["quantidade"])
        valor_unitario = float(line["valor_unitario"]) if line.get("valor_unitario") not in (None, "") else None
        novo = line.get("acao") == "novo"
        if novo:
            codigo = _new_item_code(line.get("codigo_fornecedor"))
            inventory_service.create_item(
                {
                    "codigo": codigo,
                    "descricao": str(line["descricao"]).strip().upper(),
                    "categoria": categoria_padrao,
                    "unidade": nf_unit_to_base(line.get("unidade_nf")),
                    "nota_fiscal": numero,
                    "marca": None,
                    "localizacao": None,
                    "quantidade": 0,
                    "pre_cadastro_pendente": True,
                    "pre_cadastro_origem": "nf",
                    "pre_cadastro_criado_em": TimeService.now_db(),
                    "pre_cadastro_finalizado_em": None,
                }
            )
        else:
            codigo = line["codigo_item"]
        item = inventory_service.get_item(codigo) or {}
        registered = finance_service.register_stock_document_entry(
            codigo_item=codigo,
            quantidade=quantidade,
            tipo_documento="nf",
            numero_documento=numero,
            data_emissao=data_emissao,
            data_recebimento=data_recebimento,
            chave_acesso=chave,
            supplier_id=supplier_inputs["supplier_id"],
            supplier_name=supplier_inputs["supplier_name"],
            supplier_cnpj=supplier_inputs["supplier_cnpj"],
            entrada_id=None,
            valor_unitario=valor_unitario,
            lote=(item.get("lote") or "") if item else None,
            data_validade=None,
            observacao=None,
            usuario_matricula=usuario,
            origem_valor="compra_nf",
            document_only=True,
            movimenta_estoque=movimenta_estoque,
        )
        document_item = registered.get("document_item")
        documento = registered.get("document") or documento
        if document_item is not None:
            # O nome da NF fica na NF; o item segue com o nome do GALINT (26/11/2026).
            document_item.descricao_nf = nome_na_nf(line.get("descricao_nf"))[:255] or None
            document_item.codigo_nf = str(line.get("codigo_fornecedor") or "").strip()[:60] or None
        anterior = ja_no_estoque.get(line["n"])
        if anterior is not None and document_item is not None and document_item.stock_movement_id is None:
            # Já estava no estoque: a linha fica ligada à entrada antiga e não soma de novo.
            quando = anterior.created_at.strftime("%d/%m/%Y") if anterior.created_at else "antes"
            document_item.stock_movement_id = anterior.id
            document_item.status_processamento = "processado"
            document_item.processado_em = TimeService.now_db()
            document_item.erro_processamento = None
            document_item.observacao = document_item.observacao or f"Já estava no estoque: entrada de {quando}."
            db.session.commit()
        if novo and documento is not None and documento.movimenta_estoque and document_item is not None:
            item_model = db.session.get(Item, codigo)
            if item_model is not None:
                item_model.pre_cadastro_pendente = True
                item_model.pre_cadastro_origem = "nf"
                item_model.pre_cadastro_documento_item_id = document_item.id_documento_item
                db.session.commit()
        if document_item is not None and documento is not None:
            try:
                finance_service.register_financial_entry(
                    codigo_item=document_item.codigo_item,
                    categoria_nome=document_item.item.categoria if document_item.item and document_item.item.categoria else "Sem categoria",
                    quantidade=float(document_item.quantidade or 0.0),
                    valor_unitario=float(document_item.valor_unitario) if document_item.valor_unitario not in (None, "") else None,
                    valor_total=float(document_item.valor_total) if document_item.valor_total not in (None, "") else None,
                    data_lancamento=documento.data_recebimento or documento.data_emissao or TimeService.now_db(),
                    fornecedor_id=documento.fornecedor_id,
                    entrada_id=document_item.entrada_id,
                    usuario_matricula=usuario,
                    origem_valor="compra_nf",
                    tipo_documento=documento.tipo_documento,
                    numero_documento=documento.numero_documento,
                    chave_acesso=documento.chave_acesso,
                    data_emissao_documento=documento.data_emissao,
                    data_recebimento_documento=documento.data_recebimento,
                    comprovacao_status="comprovado",
                    observacao=document_item.observacao or documento.observacao,
                    unidade_quantidade=document_item.unidade_quantidade,
                    quantidade_base=document_item.quantidade_base,
                    valor_unitario_base=document_item.valor_unitario_base,
                    unidade_preco=document_item.unidade_preco,
                    fator_preco_base=document_item.fator_preco_base,
                )
            except Exception as exc:
                logger.exception("Financeiro da NF lida %s, linha %s", reading.id, line["n"])
                warnings.append(f"Item {line['n']}: lançado, mas o financeiro não foi registrado ({exc}).")
            if not novo and anterior is None and documento.movimenta_estoque:
                try:
                    finance_service.process_stock_document_entries(
                        documento.id_documento,
                        usuario_matricula=usuario,
                        only_pending=True,
                        item_ids=[document_item.id_documento_item],
                    )
                except Exception as exc:
                    logger.exception("Estoque da NF lida %s, linha %s", reading.id, line["n"])
                    warnings.append(f"Item {line['n']}: lançado, mas a entrada no estoque falhou ({exc}).")
        # Última compra no item (NF, chave, datas e preço), como faz Documentos Fiscais. Até 25/11/2026 o
        # Ler NF não gravava: o cloro ficou em "compra_nf (3740)" depois de a NF 3891 ser lançada aqui.
        if document_item is not None and documento is not None:
            from .item_ultima_compra import record_item_last_purchase

            record_item_last_purchase(db.session.get(Item, codigo), documento, document_item, actor=usuario)
        _remember_link(cnpj, line.get("codigo_fornecedor") or "", line.get("descricao_nf") or line.get("descricao") or "", codigo, usuario)
        (novos if novo else documentados if anterior is not None else existentes).append(codigo)
        launched.append(line["n"])
        result["lancamento"] = {"linhas": launched}
        _save_result(reading, result)
        db.session.commit()

    for prefix in ("list_items", "list_notas_fiscais:", f"get_nota_fiscal:{numero}"):
        try:
            inventory_service.clear_runtime_cache(prefix)
        except Exception:
            pass
    for prefix in ("get_stock_value_report:", "list_stock_documents:", f"get_stock_document_by_number:{numero}"):
        try:
            finance_service.clear_runtime_cache(prefix)
        except Exception:
            pass

    if documento is None and existing is not None:
        documento = existing
    reading.status = "lancada"
    reading.documento_id = documento.id_documento if documento is not None else None
    reading.numero_documento = numero[:20]
    result["lancamento"] = {"linhas": launched, "novos": novos, "existentes": existentes, "documentados": documentados, "avisos": warnings}
    _save_result(reading, result)
    db.session.commit()
    return {"novos": novos, "existentes": existentes, "documentados": documentados, "avisos": warnings, "numero": numero, "documento": documento}
