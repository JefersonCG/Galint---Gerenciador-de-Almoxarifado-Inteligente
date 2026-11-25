"""Ler NF (PDF ou foto) e mandar os itens para o pré-cadastro (24/11/2026).

Página "Ler NF" do menu Suprimentos, só para administrador (como o lançamento de NF do site):
- envia um ou mais PDFs/fotos de NF; a leitura (texto do PDF ou OCR com Tesseract) roda em segundo plano;
- "Conferir" abre o formulário compacto: cabeçalho (número, fornecedor, datas) e uma linha por item
  com quantidade, valor e o item do GALINT sugerido (ou "Item novo", que vai para o pré-cadastro);
- "Lançar" grava a NF; itens novos abrem na lista de pré-cadastro, onde cada um é concluído na
  página do item (categoria, unidade básica, quantidade, valores).
- NF que já está no GALINT não é lançada de novo (25/11/2026): o arquivo fica guardado como a NF física do
  documento, com "Ver" e "Imprimir" aqui e em Documentos Fiscais (função nf_fisica dos templates).
Regras e motor: services/nf_leitura_service.py e services/nf_ocr.py.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Item, NFLeitura
from ..services import nf_leitura_service as service
from ..services import nf_ocr

blueprint = Blueprint("nf_leitura", __name__, url_prefix="/nf/leitura")

STATUS_LABELS = {
    "lendo": "Lendo…",
    "lida": "Pronta para conferir",
    "erro": "Erro",
    "lancada": "Lançada",
    "arquivada": "Já no GALINT · arquivo guardado",
}


def _require_admin() -> None:
    if not bool(getattr(current_user, "is_admin", False)):
        abort(403)


def _user_id() -> str | None:
    return getattr(current_user, "matricula", None) or getattr(current_user, "id", None)


def _get_reading(reading_id: int) -> NFLeitura:
    reading = db.session.get(NFLeitura, reading_id)
    if reading is None or reading.status == "descartada":
        abort(404)
    return reading


def _parse_iso(value: str | None) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip()) if value else None
    except ValueError:
        return None


@blueprint.get("/")
@login_required
def index():
    _require_admin()
    readings = service.listar_leituras()
    # Fila: a mais antiga é a que está sendo lida; as outras esperam a vez (1 = lendo agora).
    reading_ids = sorted(reading.id for reading in readings if reading.status == "lendo")
    return render_template(
        "nf/leitura.html",
        readings=readings,
        results={reading.id: service.load_result(reading) for reading in readings},
        fila_pos={reading_id: position for position, reading_id in enumerate(reading_ids, start=1)},
        status_labels=STATUS_LABELS,
        ocr=nf_ocr.ocr_status(),
        accept=",".join(sorted(nf_ocr.ACCEPTED_SUFFIXES)),
    )


@blueprint.post("/enviar")
@login_required
def enviar():
    _require_admin()
    try:
        created = service.enviar_arquivos(request.files.getlist("arquivos"), usuario=_user_id())
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("nf_leitura.index"))
    flash(f"{len(created)} arquivo(s) enviado(s). A leitura leva de alguns segundos a 1 minuto por página.", "info")
    return redirect(url_for("nf_leitura.index"))


@blueprint.get("/situacao")
@login_required
def situacao():
    _require_admin()
    ids = [int(part) for part in str(request.args.get("ids") or "").split(",") if part.strip().isdigit()]
    rows = NFLeitura.query.filter(NFLeitura.id.in_(ids)).all() if ids else []
    return jsonify({str(row.id): row.status for row in rows})


@blueprint.get("/<int:reading_id>")
@login_required
def conferir(reading_id: int):
    _require_admin()
    reading = _get_reading(reading_id)
    found = service.verificar_nf_existente(reading)  # a NF pode ter entrado por outro caminho depois da leitura
    if found:
        flash(f"NF {found['numero']} já está no GALINT: o arquivo ficou guardado como NF física.", "info")
        return redirect(url_for("nf_leitura.index"))
    if reading.status != "lida":
        flash(STATUS_LABELS.get(reading.status, reading.status) + (f": {reading.mensagem}" if reading.mensagem else "."), "warning")
        return redirect(url_for("nf_leitura.index"))
    result = service.load_result(reading)
    # Prova real (24/11/2026): embalagem atual de cada item sugerido (vale também para leituras antigas).
    from ..services.item_lookup_service import carregar_modelos, packaging_proof_fields

    sugestoes = [s for item in result.get("itens", []) for s in item.get("sugestoes", [])]
    modelos = carregar_modelos(sorted({str(s.get("codigo") or "") for s in sugestoes if s.get("codigo")}))
    for sugestao in sugestoes:
        sugestao.update(packaging_proof_fields(modelos.get(str(sugestao.get("codigo") or ""))))
    return render_template(
        "nf/leitura_conferir.html",
        reading=reading,
        result=result,
        header=result.get("cabecalho", {}),
        items=result.get("itens", []),
        launched=set(result.get("lancamento", {}).get("linhas", [])),
        today=date.today().isoformat(),
    )


@blueprint.post("/<int:reading_id>/lancar")
@login_required
def lancar(reading_id: int):
    _require_admin()
    reading = _get_reading(reading_id)
    form = request.form
    result = service.load_result(reading)
    header = {
        "numero": form.get("numero"),
        "chave": form.get("chave"),
        "cnpj": form.get("cnpj"),
        "fornecedor": form.get("fornecedor"),
        "data_emissao": _parse_iso(form.get("data_emissao")),
        "data_recebimento": _parse_iso(form.get("data_recebimento")) or date.today(),
    }
    lines = []
    for item in result.get("itens", []):
        n = int(item["n"])
        acao = str(form.get(f"acao_{n}") or "novo").strip()
        codigo_item = None
        if acao == "outro":
            codigo_item = str(form.get(f"outro_{n}") or "").strip()
            acao = "existente"
        elif acao != "novo":
            codigo_item, acao = acao, "existente"
        lines.append(
            {
                "n": n,
                "incluir": bool(form.get(f"incluir_{n}")),
                "acao": acao,
                "codigo_item": codigo_item,
                "descricao": form.get(f"descricao_{n}") or item.get("descricao"),
                "unidade_nf": form.get(f"unidade_{n}") or item.get("unidade"),
                "quantidade": nf_ocr.parse_number(form.get(f"quantidade_{n}")) or 0,
                "valor_unitario": nf_ocr.parse_number(form.get(f"valor_unitario_{n}")),
                "codigo_fornecedor": item.get("codigo"),
            }
        )
    try:
        launched = service.lancar_leitura(reading, header, lines, usuario=_user_id(), usuario_nome=getattr(current_user, "nome", None))
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("nf_leitura.conferir", reading_id=reading.id))
    novos, existentes = len(launched["novos"]), len(launched["existentes"])
    partes = []
    if novos:
        partes.append(f"{novos} item(ns) novo(s) no pré-cadastro")
    if existentes:
        partes.append(f"{existentes} com entrada no estoque")
    flash(f"NF {launched['numero']} lançada: " + " e ".join(partes) + ".", "success")
    for warning in launched["avisos"]:
        flash(warning, "warning")
    if novos:
        return redirect(url_for("inventory.list_items", open_pre_registered=1, pre_registered_document_number=launched["numero"]))
    return redirect(url_for("nf_leitura.index"))


@blueprint.post("/<int:reading_id>/reler")
@login_required
def reler(reading_id: int):
    _require_admin()
    try:
        service.reler(_get_reading(reading_id))
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("nf_leitura.index"))


@blueprint.post("/<int:reading_id>/descartar")
@login_required
def descartar(reading_id: int):
    _require_admin()
    try:
        service.descartar(_get_reading(reading_id))
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("nf_leitura.index"))


def _reading_with_file(reading_id: int) -> NFLeitura:
    """Arquivo da leitura: o administrador vê todos; os outros, só a NF física de um documento, que já
    aparece para eles em Documentos Fiscais."""
    reading = _get_reading(reading_id)
    is_proof = reading.status in service.PROOF_STATUSES and reading.documento_id
    if not (bool(getattr(current_user, "is_admin", False)) or is_proof):
        abort(403)
    if not service.reading_file_path(reading).is_file():
        abort(404)
    return reading


@blueprint.get("/<int:reading_id>/arquivo")
@login_required
def arquivo(reading_id: int):
    reading = _reading_with_file(reading_id)
    return send_file(service.reading_file_path(reading), download_name=reading.arquivo_nome, as_attachment=False)


@blueprint.get("/<int:reading_id>/imprimir")
@login_required
def imprimir(reading_id: int):
    """Abre o arquivo da NF (PDF ou foto) e chama a impressão do navegador."""
    reading = _reading_with_file(reading_id)
    return render_template(
        "nf/leitura_imprimir.html",
        reading=reading,
        is_pdf=Path(reading.arquivo_nome or reading.arquivo_path).suffix.lower() in nf_ocr.PDF_SUFFIXES,
        file_url=url_for("nf_leitura.arquivo", reading_id=reading.id),
    )


@blueprint.app_template_global("nf_fisica")
def nf_fisica(documento_id) -> list[NFLeitura]:
    """Arquivos de NF física (lida no Ler NF) ligados ao documento; usada em Documentos Fiscais.

    Uma consulta por página: a lista de NFs chama esta função para cada documento.
    """
    try:
        documento_id = int(documento_id)
    except (TypeError, ValueError):
        return []
    cache = g.get("_nf_fisica")
    if cache is None:
        cache = {}
        try:
            rows = (
                NFLeitura.query.filter(NFLeitura.documento_id.isnot(None), NFLeitura.status.in_(service.PROOF_STATUSES))
                .order_by(NFLeitura.id)
                .all()
            )
        except Exception:  # a página de Documentos Fiscais não pode cair por causa disto
            db.session.rollback()
            rows = []
        for row in rows:
            cache.setdefault(row.documento_id, []).append(row)
        g._nf_fisica = cache
    return cache.get(documento_id, [])


@blueprint.app_template_global("nf_rastro")
def nf_rastro(documento_id) -> list[dict]:
    """Para onde foram os itens da NF: cada retirada que gastou o que ela trouxe (services/nf_rastro.py).
    Usada no detalhe do documento em Documentos Fiscais (25/11/2026)."""
    from ..services.nf_rastro import rastro_do_documento

    try:
        return rastro_do_documento(int(documento_id))
    except (TypeError, ValueError):
        return []
    except Exception:  # a página de Documentos Fiscais não pode cair por causa disto
        db.session.rollback()
        import logging

        logging.getLogger(__name__).exception("Rastro da NF %s", documento_id)
        return []


@blueprint.get("/itens")
@login_required
def buscar_itens():
    """Busca de item do GALINT para a opção "Outro item" da conferência (código ou nome)."""
    _require_admin()
    query = str(request.args.get("q") or "").strip()
    if len(query) < 2:
        return jsonify([])
    exact = db.session.get(Item, query)
    found = []
    if exact is not None:
        from ..services.item_lookup_service import packaging_proof_fields

        found.append({"codigo": exact.codigo_item, "descricao": exact.descricao, "marca": exact.marca or "", "unidade": exact.unidade or "", **packaging_proof_fields(exact)})
    catalog = service.load_catalog()
    for suggestion in service.suggest_items({"codigo": "", "descricao": query}, catalog, limit=10):
        if not any(row["codigo"] == suggestion["codigo"] for row in found):
            found.append(suggestion)
    if len(found) < 10:
        needle = service._normalize(query)
        for item in catalog:
            if len(found) >= 10:
                break
            if (needle in item.norm or item.codigo.startswith(query)) and not any(row["codigo"] == item.codigo for row in found):
                found.append({"codigo": item.codigo, "descricao": item.descricao, "marca": item.marca, "unidade": item.unidade,
                              "fator_embalagem": item.fator_embalagem, "unidade_documental": item.unidade_documental})
    return jsonify(found[:10])
