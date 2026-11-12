"""SEFAZ Distribuição DF-e client and encrypted recipient configuration."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import logging
import re
import threading
from datetime import date, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import select

from ..extensions import db
from ..models import NFeDistributionConfig, NFeDistributionDocument

logger = logging.getLogger(__name__)
_POLL_LOCK = threading.Lock()
_MINIMUM_POLL_INTERVAL = timedelta(hours=1)
_VALID_UF_CODES = {
    "11", "12", "13", "14", "15", "16", "17", "21", "22", "23", "24", "25",
    "26", "27", "28", "29", "31", "32", "33", "35", "41", "42", "43", "50",
    "51", "52", "53",
}

PRODUCTION_ENDPOINT = (
    "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
)
HOMOLOGATION_ENDPOINT = (
    "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
)


def _fernet():
    from cryptography.fernet import Fernet

    secret = str(current_app.config.get("SECRET_KEY") or "").encode("utf-8")
    if not secret:
        raise RuntimeError("A chave secreta persistente do GALINT não está configurada.")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def _encrypt(value: bytes) -> str:
    return _fernet().encrypt(value).decode("ascii")


def _decrypt(value: str) -> bytes:
    return _fernet().decrypt(value.encode("ascii"))


def _digits(value: str | None) -> str:
    return "".join(character for character in (value or "") if character.isdigit())


def _valid_cnpj(value: str) -> bool:
    digits = _digits(value)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    for length, weights in ((12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)), (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))):
        remainder = sum(int(digits[index]) * weight for index, weight in enumerate(weights)) % 11
        expected = 0 if remainder < 2 else 11 - remainder
        if int(digits[length]) != expected:
            return False
    return True


def _get_or_create_config(*, create: bool = False) -> NFeDistributionConfig | None:
    config = db.session.execute(
        select(NFeDistributionConfig).where(NFeDistributionConfig.id == 1)
    ).scalar_one_or_none()
    if config is None and create:
        config = NFeDistributionConfig(id=1)
        db.session.add(config)
        db.session.flush()
    return config


def public_config() -> dict[str, Any]:
    config = _get_or_create_config()
    if config is None:
        return {
            "enabled": False,
            "cnpj_destinatario": "",
            "uf_autor": "",
            "ambiente": "producao",
            "has_certificate": False,
            "ultimo_nsu": "0",
            "maximo_nsu": "0",
            "consultado_em": None,
            "proxima_consulta_em": None,
            "ultimo_status": None,
            "ultima_mensagem": None,
        }
    return {
        "enabled": bool(config.enabled),
        "cnpj_destinatario": config.cnpj_destinatario,
        "uf_autor": config.uf_autor,
        "ambiente": config.ambiente,
        "has_certificate": bool(config.certificado_pfx_criptografado),
        "ultimo_nsu": config.ultimo_nsu,
        "maximo_nsu": config.maximo_nsu,
        "consultado_em": config.consultado_em,
        "proxima_consulta_em": config.proxima_consulta_em,
        "ultimo_status": config.ultimo_status,
        "ultima_mensagem": config.ultima_mensagem,
    }


def save_configuration(
    *,
    cnpj_destinatario: str,
    uf_autor: str,
    ambiente: str,
    enabled: bool,
    certificate_data: bytes | None = None,
    certificate_password: str = "",
) -> None:
    cnpj = _digits(cnpj_destinatario)
    uf = str(uf_autor or "").strip().upper()
    ambiente = str(ambiente or "").strip().lower()
    if not _valid_cnpj(cnpj):
        raise ValueError("Informe um CNPJ destinatário válido.")
    if uf not in _VALID_UF_CODES:
        raise ValueError("Selecione a UF do estabelecimento destinatário.")
    if ambiente not in {"producao", "homologacao"}:
        raise ValueError("Ambiente fiscal inválido.")

    config = _get_or_create_config(create=True)
    assert config is not None
    identity_changed = (
        config.cnpj_destinatario != cnpj
        or config.uf_autor != uf
        or config.ambiente != ambiente
    )
    if certificate_data is not None:
        if not certificate_data:
            raise ValueError("O arquivo do certificado está vazio.")
        if len(certificate_data) > 10 * 1024 * 1024:
            raise ValueError("O certificado deve ter no máximo 10 MB.")
        try:
            from cryptography.hazmat.primitives.serialization import pkcs12

            private_key, certificate, _ = pkcs12.load_key_and_certificates(
                certificate_data,
                certificate_password.encode("utf-8") if certificate_password else None,
            )
        except Exception as exc:
            raise ValueError("Não foi possível abrir o certificado .PFX/.P12 com essa senha.") from exc
        if private_key is None or certificate is None:
            raise ValueError("O arquivo precisa conter um certificado A1 e sua chave privada.")
        config.certificado_pfx_criptografado = _encrypt(certificate_data)
        config.senha_certificado_criptografada = _encrypt(certificate_password.encode("utf-8"))
    elif enabled and not config.certificado_pfx_criptografado:
        raise ValueError("Envie o certificado digital A1 antes de ativar a consulta.")

    config.cnpj_destinatario = cnpj
    config.uf_autor = uf
    config.ambiente = ambiente
    config.enabled = bool(enabled)
    if identity_changed:
        config.ultimo_nsu = "0"
        config.maximo_nsu = "0"
        config.consultado_em = None
        config.proxima_consulta_em = None
    config.ultima_mensagem = None
    db.session.commit()


def _local_name(element: Any) -> str:
    return str(element.tag).rsplit("}", 1)[-1]


def _child(parent: Any, name: str) -> Any | None:
    if parent is None:
        return None
    return next((element for element in parent if _local_name(element) == name), None)


def _text(parent: Any, *path: str) -> str | None:
    element = parent
    for name in path:
        element = _child(element, name)
        if element is None:
            return None
    return (element.text or "").strip() or None


def _find_first(root: Any, name: str) -> Any | None:
    return next((element for element in root.iter() if _local_name(element) == name), None)


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_document(xml_data: bytes) -> dict[str, Any] | None:
    from defusedxml import ElementTree

    root = ElementTree.fromstring(xml_data)
    inf_nfe = _find_first(root, "infNFe")
    summary = _find_first(root, "resNFe")
    if inf_nfe is not None:
        ide = _child(inf_nfe, "ide")
        emit = _child(inf_nfe, "emit")
        total = _child(inf_nfe, "total")
        icms_total = _child(total, "ICMSTot")
        access_key = str(inf_nfe.attrib.get("Id") or "").removeprefix("NFe")
        items = []
        for detail in inf_nfe:
            if _local_name(detail) != "det":
                continue
            product = _child(detail, "prod")
            if product is None:
                continue
            items.append(
                {
                    "numero_item": detail.attrib.get("nItem"),
                    "codigo": _text(product, "cProd"),
                    "descricao": _text(product, "xProd"),
                    "ncm": _text(product, "NCM"),
                    "cfop": _text(product, "CFOP"),
                    "unidade": _text(product, "uCom"),
                    "quantidade": _float(_text(product, "qCom")),
                    "valor_unitario": _float(_text(product, "vUnCom")),
                    "valor_total": _float(_text(product, "vProd")),
                }
            )
        return {
            "chave_acesso": access_key,
            "numero_documento": _text(ide, "nNF"),
            "serie": _text(ide, "serie"),
            "cnpj_emitente": _digits(_text(emit, "CNPJ")),
            "emitente": _text(emit, "xNome"),
            "data_emissao": _date(_text(ide, "dhEmi") or _text(ide, "dEmi")),
            "valor_total": _float(_text(icms_total, "vNF")),
            "resumo": False,
            "itens": items,
        }
    if summary is None:
        return None
    return {
        "chave_acesso": _text(summary, "chNFe") or "",
        "numero_documento": _text(summary, "nNF"),
        "serie": _text(summary, "serie"),
        "cnpj_emitente": _digits(_text(summary, "CNPJ")),
        "emitente": _text(summary, "xNome"),
        "data_emissao": _date(_text(summary, "dhEmi")),
        "valor_total": _float(_text(summary, "vNF")),
        "resumo": True,
        "itens": [],
    }


def _decode_doc_zip(element: Any) -> bytes:
    encoded = "".join((element.text or "").split())
    if not encoded:
        raise ValueError("A SEFAZ retornou um documento compactado vazio.")
    compressed = base64.b64decode(encoded, validate=True)
    try:
        return gzip.decompress(compressed)
    except OSError as exc:
        raise ValueError("A SEFAZ retornou um documento com compactação inválida.") from exc


def _soap_body(cnpj: str, uf: str, ambiente: str, ultimo_nsu: str) -> bytes:
    tp_amb = "1" if ambiente == "producao" else "2"
    payload = (
        '<distDFeInt versao="1.01" xmlns="http://www.portalfiscal.inf.br/nfe">'
        f"<tpAmb>{tp_amb}</tpAmb><cUFAutor>{uf}</cUFAutor><CNPJ>{cnpj}</CNPJ>"
        f"<distNSU><ultNSU>{ultimo_nsu.zfill(15)}</ultNSU></distNSU></distDFeInt>"
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
        "<soap12:Body><nfeDistDFeInteresse "
        'xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">'
        f"<nfeDadosMsg>{payload}</nfeDadosMsg>"
        "</nfeDistDFeInteresse></soap12:Body></soap12:Envelope>"
    ).encode("utf-8")


def _request_distribution(
    *,
    cnpj_destinatario: str,
    uf_autor: str,
    ambiente: str,
    ultimo_nsu: str,
    pfx_data: bytes,
    password: bytes,
) -> bytes:
    from requests import Session
    from requests_pkcs12 import Pkcs12Adapter

    endpoint = (
        PRODUCTION_ENDPOINT if ambiente == "producao" else HOMOLOGATION_ENDPOINT
    )
    session = Session()
    session.mount(
        "https://",
        Pkcs12Adapter(pkcs12_data=pfx_data, pkcs12_password=password.decode("utf-8") or None),
    )
    response = session.post(
        endpoint,
        data=_soap_body(cnpj_destinatario, uf_autor, ambiente, ultimo_nsu),
        headers={
            "Content-Type": 'application/soap+xml; charset=utf-8; action="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse"',
            "Accept": "application/soap+xml, application/xml, text/xml",
        },
        timeout=(15, 60),
    )
    response.raise_for_status()
    return response.content


def _process_response(config: NFeDistributionConfig, response_data: bytes) -> dict[str, Any]:
    from defusedxml import ElementTree

    root = ElementTree.fromstring(response_data)
    response_payload = root
    result_element = _find_first(root, "nfeDistDFeInteresseResult")
    if result_element is not None and not list(result_element) and result_element.text:
        serialized_xml = result_element.text.strip()
        if serialized_xml.startswith("<"):
            response_payload = ElementTree.fromstring(serialized_xml)
    status = _text(response_payload, "retDistDFeInt", "cStat")
    if status is None:
        status_element = _find_first(response_payload, "cStat")
        status = (status_element.text or "").strip() if status_element is not None else None
    message_element = _find_first(response_payload, "xMotivo")
    message = (message_element.text or "").strip() if message_element is not None else ""
    if not status:
        raise ValueError("A SEFAZ respondeu sem informar o código de situação do serviço.")
    result = _find_first(response_payload, "retDistDFeInt")
    ultimo_nsu = _text(result, "ultNSU") if result is not None else None
    maximo_nsu = _text(result, "maxNSU") if result is not None else None
    imported = 0

    if status in {"137", "138"}:
        for doc_zip in (element for element in response_payload.iter() if _local_name(element) == "docZip"):
            xml_data = _decode_doc_zip(doc_zip)
            parsed = _parse_document(xml_data)
            nsu = str(doc_zip.attrib.get("NSU") or "").strip()
            schema = str(doc_zip.attrib.get("schema") or "desconhecido")
            if not parsed or not re.fullmatch(r"\d{1,15}", nsu):
                continue
            access_key = str(parsed["chave_acesso"] or "")
            if not re.fullmatch(r"\d{44}", access_key):
                continue
            normalized_nsu = nsu.zfill(15)
            existing = db.session.execute(
                select(NFeDistributionDocument).where(
                    (
                        (NFeDistributionDocument.cnpj_destinatario == config.cnpj_destinatario)
                        & (NFeDistributionDocument.nsu == normalized_nsu)
                    )
                    | (NFeDistributionDocument.chave_acesso == access_key)
                ).limit(1)
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.session.add(
                NFeDistributionDocument(
                    cnpj_destinatario=config.cnpj_destinatario,
                    nsu=normalized_nsu,
                    schema_documento=schema[:80],
                    chave_acesso=access_key,
                    numero_documento=parsed["numero_documento"],
                    serie=parsed["serie"],
                    cnpj_emitente=parsed["cnpj_emitente"] or None,
                    emitente=parsed["emitente"],
                    data_emissao=parsed["data_emissao"],
                    valor_total=parsed["valor_total"],
                    resumo=bool(parsed["resumo"]),
                    itens_json=json.dumps(parsed["itens"], ensure_ascii=False),
                    xml_original=xml_data.decode("utf-8", errors="replace"),
                )
            )
            imported += 1

    if status in {"137", "138"}:
        if ultimo_nsu and re.fullmatch(r"\d{1,15}", ultimo_nsu):
            config.ultimo_nsu = ultimo_nsu.zfill(15)
        if maximo_nsu and re.fullmatch(r"\d{1,15}", maximo_nsu):
            config.maximo_nsu = maximo_nsu.zfill(15)
    config.ultimo_status = status
    config.ultima_mensagem = f"{message} ({imported} documento(s) novo(s) recebido(s)).".strip()
    return {
        "status": status,
        "message": config.ultima_mensagem,
        "imported": imported,
        "ultimo_nsu": config.ultimo_nsu,
        "maximo_nsu": config.maximo_nsu,
    }


def poll_once() -> dict[str, Any]:
    """Run at most one permitted query; the persisted cooldown also covers restarts."""
    if not _POLL_LOCK.acquire(blocking=False):
        return {"ok": False, "message": "Já existe uma consulta à SEFAZ em andamento."}
    try:
        config = db.session.execute(
            select(NFeDistributionConfig)
            .where(NFeDistributionConfig.id == 1)
            .with_for_update()
        ).scalar_one_or_none()
        if config is None or not config.enabled:
            return {"ok": False, "message": "Consulta automática está desativada."}
        now = datetime.utcnow()
        next_allowed = config.proxima_consulta_em
        if next_allowed and next_allowed > now:
            return {
                "ok": False,
                "message": f"A próxima consulta estará liberada após {next_allowed:%d/%m/%Y %H:%M}.",
                "next_allowed": next_allowed,
            }
        try:
            if not config.certificado_pfx_criptografado or not config.senha_certificado_criptografada:
                raise RuntimeError("O certificado digital não está configurado.")
            pfx_data = _decrypt(config.certificado_pfx_criptografado)
            password = _decrypt(config.senha_certificado_criptografada)
            request_identity = (
                config.cnpj_destinatario,
                config.uf_autor,
                config.ambiente,
                config.ultimo_nsu,
            )
        except Exception as exc:
            config.ultimo_status = "erro"
            config.ultima_mensagem = str(exc)[:2000]
            db.session.commit()
            logger.exception("Falha ao carregar o certificado da integração de NF-e")
            return {"ok": False, "message": config.ultima_mensagem}
        config.consultado_em = now
        config.proxima_consulta_em = now + _MINIMUM_POLL_INTERVAL
        config.ultimo_status = "consultando"
        config.ultima_mensagem = "Consulta enviada à SEFAZ."
        db.session.commit()

        try:
            response_data = _request_distribution(
                cnpj_destinatario=request_identity[0],
                uf_autor=request_identity[1],
                ambiente=request_identity[2],
                ultimo_nsu=request_identity[3],
                pfx_data=pfx_data,
                password=password,
            )
            latest_config = db.session.execute(
                select(NFeDistributionConfig)
                .where(NFeDistributionConfig.id == 1)
                .with_for_update()
            ).scalar_one_or_none()
            if latest_config is None or (
                latest_config.cnpj_destinatario,
                latest_config.uf_autor,
                latest_config.ambiente,
                latest_config.ultimo_nsu,
            ) != request_identity:
                if latest_config is not None:
                    latest_config.ultimo_status = "configuracao_alterada"
                    latest_config.ultima_mensagem = (
                        "A configuração do destinatário mudou durante a consulta; a resposta foi descartada."
                    )
                    db.session.commit()
                return {
                    "ok": False,
                    "message": "A configuração do destinatário mudou durante a consulta; a resposta foi descartada.",
                }
            result = _process_response(latest_config, response_data)
            db.session.commit()
            return {"ok": result["status"] in {"137", "138"}, **result}
        except Exception as exc:
            db.session.rollback()
            failed_config = _get_or_create_config()
            if failed_config is not None:
                failed_config.ultimo_status = "erro"
                failed_config.ultima_mensagem = str(exc)[:2000]
                db.session.commit()
            logger.exception("Falha na consulta de NF-e à SEFAZ")
            return {"ok": False, "message": str(exc)}
    finally:
        _POLL_LOCK.release()


def list_documents(limit: int = 100) -> list[NFeDistributionDocument]:
    config = _get_or_create_config()
    if config is None:
        return []
    return list(
        db.session.execute(
            select(NFeDistributionDocument)
            .where(NFeDistributionDocument.cnpj_destinatario == config.cnpj_destinatario)
            .order_by(NFeDistributionDocument.recebido_em.desc(), NFeDistributionDocument.id.desc())
            .limit(max(1, min(int(limit), 500)))
        ).scalars()
    )


def get_document(document_id: int) -> NFeDistributionDocument | None:
    return db.session.get(NFeDistributionDocument, document_id)
