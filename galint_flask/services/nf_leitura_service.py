"""NF lida (PDF ou foto) → conferência → pré-cadastro (24/11/2026).

Pedido do usuário: "ao ler as NF elas iriam para o pré-cadastro; eu clicaria e abriria um formulário bem
compacto, com os nomes, datas e valores; eu editaria cada item, abriria a página de cadastro de item e lá
daria categoria, unidade básica, quantidade e valores, para ver se estão batendo com a NF". XML e
certificado A1 não estão disponíveis, então a leitura é por OCR (Tesseract) ou pelo texto do PDF
(services/nf_ocr.py).

Fluxo:
1. enviar_arquivos: guarda cada arquivo em instance/nf_leituras/AAAAMM e cria a NFLeitura "lendo".
2. processar_leitura (em segundo plano, uma de cada vez, porque o OCR pesa): lê, acha o fornecedor pelo
   CNPJ, avisa se a NF já está no GALINT e sugere o item do GALINT para cada linha:
   - código da linha igual ao código de um item;
   - vínculo aprendido antes (mesmo fornecedor + mesmo código de produto);
   - nome parecido (palavras em comum, marca incluída, e semelhança do texto).
3. lancar_leitura: para cada linha marcada na conferência, chama os mesmos serviços, na mesma ordem, da
   rota de NF do app (/api/mobile/documentos-fiscais):
   - linha com item novo: cria o item em PRÉ-CADASTRO (origem "nf") e liga a linha da NF a ele. O saldo
     entra quando o pré-cadastro é concluído na página do item (categoria, unidade básica, quantidade e
     valores), como já acontece com item novo vindo de NF;
   - linha ligada a item existente: registra a linha e dá entrada no estoque, como "Lançar entrada com NF".
   Também registra o financeiro de cada linha e guarda o vínculo fornecedor+código → item para a próxima
   NF. Não manda aviso de item novo pelo Telegram (uma NF grande mandaria dezenas).
"""
from __future__ import annotations

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
from ..models import DocumentoEntradaEstoque, FinanceSupplier, Item, NFItemVinculo, NFLeitura
from ..utils.time_service import TimeService
from . import nf_ocr

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 25 * 1024 * 1024
STALE_READING = timedelta(minutes=20)
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
    cnpj = re.sub(r"\D", "", header.get("cnpj_emitente") or "")
    links: dict[str, str] = {}
    if cnpj:
        links = {row.codigo_fornecedor: row.codigo_item for row in NFItemVinculo.query.filter_by(cnpj_fornecedor=cnpj).all()}
    catalog = load_catalog()
    for line in result["itens"]:
        line["sugestoes"] = suggest_items(line, catalog, linked_code=links.get(str(line.get("codigo") or "").strip()))
        best = line["sugestoes"][0] if line["sugestoes"] else None
        line["acao"] = best["codigo"] if best and best["score"] >= AUTO_LINK_SCORE else "novo"
    return result


# --------------------------------------------------------------------------------------------------
# Leituras: envio, processamento em segundo plano, consulta
# --------------------------------------------------------------------------------------------------


_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()


def _executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="galint-nf-ocr")
        return _EXECUTOR


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


def enviar_arquivos(files: list[Any], *, usuario: str | None) -> list[NFLeitura]:
    """Guarda os arquivos enviados e agenda a leitura de cada um."""
    created: list[NFLeitura] = []
    folder = _storage_root() / TimeService.now_db().strftime("%Y%m")
    folder.mkdir(parents=True, exist_ok=True)
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
        stored = f"{uuid.uuid4().hex}{suffix}"
        (folder / stored).write_bytes(data)
        reading = NFLeitura(
            arquivo_nome=name[:255],
            arquivo_path=str((folder / stored).relative_to(Path(current_app.instance_path))).replace("\\", "/"),
            status="lendo",
            criado_por=usuario,
        )
        db.session.add(reading)
        created.append(reading)
    if not created:
        raise ValueError("Escolha o PDF ou a foto da NF.")
    db.session.commit()
    for reading in created:
        agendar_leitura(reading.id)
    return created


def agendar_leitura(reading_id: int) -> None:
    app = current_app._get_current_object()
    if app.config.get("TESTING") or app.config.get("GALINT_NF_OCR_SYNC"):
        processar_leitura(reading_id)
        return
    _executor().submit(_process_in_app, app, reading_id)


def _process_in_app(app, reading_id: int) -> None:
    with app.app_context():
        try:
            processar_leitura(reading_id)
        except Exception:  # pragma: no cover - registrado no log
            logger.exception("Falha ao ler a NF %s", reading_id)
        finally:
            db.session.remove()


def processar_leitura(reading_id: int) -> None:
    reading = db.session.get(NFLeitura, reading_id)
    if reading is None:
        return
    try:
        data = reading_file_path(reading).read_bytes()
        result = enrich_reading(nf_ocr.read_and_parse(data, reading.arquivo_nome))
        header = result["cabecalho"]
        reading.status = "lida"
        reading.fonte = result.get("fonte")
        reading.mensagem = None
        reading.numero_documento = (header.get("numero") or None) and str(header["numero"])[:20]
        reading.fornecedor_nome = (header.get("emitente") or None) and str(header["emitente"])[:200]
        reading.valor_total = header.get("valor_total") or header.get("valor_produtos")
        _save_result(reading, result)
    except nf_ocr.OcrUnavailableError as exc:
        reading.status = "erro"
        reading.mensagem = str(exc)
    except Exception as exc:
        logger.exception("Erro ao ler a NF %s (%s)", reading_id, reading.arquivo_nome)
        reading.status = "erro"
        reading.mensagem = f"Não foi possível ler o arquivo: {exc}"
    db.session.commit()


def listar_leituras(limit: int = 60) -> list[NFLeitura]:
    """Leituras ainda não descartadas, mais novas primeiro. Leitura parada (servidor religado) vira erro."""
    stale_before = TimeService.now_db() - STALE_READING
    stale = NFLeitura.query.filter(NFLeitura.status == "lendo", NFLeitura.atualizado_em < stale_before).all()
    for reading in stale:
        reading.status = "erro"
        reading.mensagem = "Leitura interrompida (o servidor foi religado). Clique em Ler de novo."
    if stale:
        db.session.commit()
    return (
        NFLeitura.query.filter(NFLeitura.status != "descartada")
        .order_by(NFLeitura.criado_em.desc(), NFLeitura.id.desc())
        .limit(limit)
        .all()
    )


def reler(reading: NFLeitura) -> None:
    if reading.status == "lancada":
        raise ValueError("Esta NF já foi lançada.")
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


def lancar_leitura(reading: NFLeitura, header: dict[str, Any], lines: list[dict[str, Any]], *, usuario: str | None, usuario_nome: str | None = None) -> dict[str, Any]:
    """Lança as linhas conferidas. Linhas já lançadas numa tentativa anterior são puladas."""
    from .category_catalog import DEFAULT_INVENTORY_CATEGORY_NAME, category_catalog_service
    from .finance_service import finance_service
    from .inventory import inventory_service

    if reading.status == "lancada":
        raise ValueError("Esta NF já foi lançada.")
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
    for line in selected:
        if not (float(line.get("quantidade") or 0) > 0):
            raise ValueError(f"Item {line['n']}: informe a quantidade.")
        if line.get("acao") != "novo":
            if not line.get("codigo_item") or db.session.get(Item, line["codigo_item"]) is None:
                raise ValueError(f"Item {line['n']}: item do GALINT não encontrado.")
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
            if not novo and documento.movimenta_estoque:
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
        _remember_link(cnpj, line.get("codigo_fornecedor") or "", line.get("descricao") or "", codigo, usuario)
        (novos if novo else existentes).append(codigo)
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
    result["lancamento"] = {"linhas": launched, "novos": novos, "existentes": existentes, "avisos": warnings}
    _save_result(reading, result)
    db.session.commit()
    return {"novos": novos, "existentes": existentes, "avisos": warnings, "numero": numero, "documento": documento}
