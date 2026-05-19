from __future__ import annotations

import base64
import binascii
import re
import uuid
from pathlib import Path
from typing import Any

from flask import current_app
from werkzeug.datastructures import FileStorage, MultiDict
from werkzeug.utils import secure_filename

from ...extensions import db
from ...models import CondominiumBuilding, CondominiumOwner, CondominiumUnit
from ..finance_service import FinanceService

DOCUMENT_LABELS: dict[str, str] = {
    "document_onus_reais": "Certidao de Onus Reais atualizada",
    "document_itbi": "Comprovante de Pagamento do ITBI",
    "document_escritura": "Escritura ou Contrato de Compra e Venda",
    "document_owner_ids": "RG e CPF do(s) proprietario(s)",
    "document_proxy": "Procuracao registrada em cartorio do RJ",
}

ALLOWED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_ATTACHMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
MAX_PHOTO_BYTES = 6 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 12 * 1024 * 1024


def _clean(value: object) -> str:
    return str(value or "").strip()


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _truthy(form_data: MultiDict[str, Any], name: str) -> bool:
    value = form_data.get(name)
    if value is None:
        return False
    return str(value).strip().lower() not in {"", "0", "false", "off", "nao"}


def _optional_text_dict(items: dict[str, object]) -> dict[str, str]:
    return {key: text for key, value in items.items() if (text := _clean(value))}


def _text_lines(value: object) -> list[str]:
    lines: list[str] = []
    for raw_line in str(value or "").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if line:
            lines.append(line)
    return lines


def _split_pipe_line(line: str, keys: tuple[str, ...]) -> dict[str, str]:
    values = [part.strip() for part in line.split("|")]
    row = {key: values[index] for index, key in enumerate(keys) if index < len(values) and values[index]}
    if not row and line.strip():
        row["description"] = line.strip()
    return row


def _structured_lines(value: object, keys: tuple[str, ...]) -> list[dict[str, str]]:
    rows = [_split_pipe_line(line, keys) for line in _text_lines(value)]
    return [row for row in rows if row]


def _owner_notes_from_form(form_data: MultiDict[str, Any]) -> str | None:
    base_notes = _clean(form_data.get("notes"))
    sections = []
    for label, field_name in (
        ("Moradores da unidade", "unit_residents"),
        ("Veiculos autorizados", "authorized_vehicles"),
        ("Animais de estimacao", "pets"),
        ("Funcionarios particulares", "private_staff"),
        ("Procuracao", "proxy_notes"),
    ):
        value = _clean(form_data.get(field_name))
        if value:
            sections.append(f"[{label}]\n{value}")
    content = [part for part in (base_notes, *sections) if part]
    return "\n\n".join(content) or None


def _owner_correspondence_payload(form_data: MultiDict[str, Any]) -> tuple[str | None, dict[str, str]]:
    structured = _optional_text_dict(
        {
            "cep": form_data.get("correspondence_cep"),
            "street": form_data.get("correspondence_street"),
            "number": form_data.get("correspondence_number"),
            "complement": form_data.get("correspondence_complement"),
            "neighborhood": form_data.get("correspondence_neighborhood"),
            "city": form_data.get("correspondence_city"),
            "state": _clean(form_data.get("correspondence_state")).upper(),
            "reference": form_data.get("correspondence_reference"),
        }
    )

    address_lines: list[str] = []
    first_line_parts = [structured.get("street"), structured.get("number")]
    first_line = ", ".join(part for part in first_line_parts if part)
    complement = structured.get("complement")
    if complement:
        first_line = f"{first_line} - {complement}" if first_line else complement
    if first_line:
        address_lines.append(first_line)
    if structured.get("neighborhood"):
        address_lines.append(str(structured["neighborhood"]))
    city_state = " - ".join(part for part in (structured.get("city"), structured.get("state")) if part)
    if city_state:
        address_lines.append(city_state)
    if structured.get("cep"):
        address_lines.append(f"CEP {structured['cep']}")
    if structured.get("reference"):
        address_lines.append(str(structured["reference"]))

    composed = "\n".join(address_lines).strip()
    if composed:
        return composed, structured

    fallback_text = _clean(form_data.get("correspondence_address"))
    return fallback_text or None, structured


def _emergency_contact_from_form(form_data: MultiDict[str, Any]) -> str | None:
    name = _clean(form_data.get("emergency_contact_name"))
    phone = _clean(form_data.get("emergency_contact_phone"))
    fallback = _clean(form_data.get("emergency_contact"))
    if name and phone:
        return f"{name} - {phone}"
    return name or phone or fallback or None


def _registry_data_from_form(form_data: MultiDict[str, Any]) -> tuple[str | None, dict[str, object]]:
    correspondence_address, correspondence_structured = _owner_correspondence_payload(form_data)
    owner_profile = _optional_text_dict(
        {
            "rg_issuer": form_data.get("rg_issuer"),
            "civil_status": form_data.get("civil_status"),
            "property_regime": form_data.get("property_regime"),
            "nationality": form_data.get("nationality"),
            "profession": form_data.get("profession"),
        }
    )
    unit_identity = _optional_text_dict(
        {
            "garage_spaces": form_data.get("garage_spaces"),
            "iptu_registration": form_data.get("iptu_registration"),
            "rgi_circumscription": form_data.get("rgi_circumscription"),
            "property_registry_number": form_data.get("property_registry_number"),
        }
    )
    if _truthy(form_data, "garage_free"):
        unit_identity["garage_free"] = "true"

    communication = _optional_text_dict(
        {
            "email": form_data.get("email"),
            "phone": form_data.get("phone"),
            "emergency_contact_name": form_data.get("emergency_contact_name"),
            "emergency_contact_phone": form_data.get("emergency_contact_phone"),
        }
    )
    if _truthy(form_data, "email_authorized_for_notices"):
        communication["email_authorized_for_notices"] = "true"

    occupancy = _optional_text_dict(
        {
            "occupancy_status": form_data.get("occupancy_status"),
            "tenant_name": form_data.get("tenant_name"),
            "tenant_document": form_data.get("tenant_document"),
            "tenant_phone": form_data.get("tenant_phone"),
            "proxy_notes": form_data.get("proxy_notes"),
        }
    )
    occupancy["has_proxy"] = "true" if _truthy(form_data, "has_proxy") else "false"

    access_security: dict[str, object] = {
        "residents": _structured_lines(form_data.get("unit_residents"), ("name", "relationship", "document")),
        "vehicles": _structured_lines(form_data.get("authorized_vehicles"), ("brand", "model", "color", "plate", "garage_space")),
        "pets": _structured_lines(form_data.get("pets"), ("species", "breed", "size", "name")),
        "private_staff": _structured_lines(form_data.get("private_staff"), ("name", "document", "role", "frequency")),
    }
    raw_access = _optional_text_dict(
        {
            "unit_residents_text": form_data.get("unit_residents"),
            "authorized_vehicles_text": form_data.get("authorized_vehicles"),
            "pets_text": form_data.get("pets"),
            "private_staff_text": form_data.get("private_staff"),
        }
    )
    if raw_access:
        access_security["raw"] = raw_access

    compliance = {
        "truth_declaration": bool(_truthy(form_data, "truth_declaration")),
        "lgpd_authorized": bool(_truthy(form_data, "lgpd_authorized")),
        "email_authorized_for_notices": bool(_truthy(form_data, "email_authorized_for_notices")),
    }

    data: dict[str, object] = {}
    for key, section in (
        ("unit_identity", unit_identity),
        ("owner_profile", owner_profile),
        ("correspondence_address", correspondence_structured),
        ("communication", communication),
        ("occupancy", occupancy),
        ("access_security", access_security),
        ("compliance", compliance),
    ):
        if section:
            data[key] = section
    return correspondence_address, data


def _static_root() -> Path:
    return Path(current_app.static_folder or (Path(current_app.root_path) / "static"))


def _relative_upload_path(*parts: str) -> Path:
    return Path("uploads", "condominio", *parts)


def _save_upload_file(file: FileStorage, relative_dir: Path, *, owner_id: int, prefix: str, allowed_extensions: set[str], max_size: int) -> dict[str, object] | None:
    if not file or not file.filename:
        return None
    filename = secure_filename(file.filename)
    extension = Path(filename).suffix.lower()
    if extension not in allowed_extensions:
        raise ValueError("Anexos devem ser PDF, JPG, PNG ou WEBP." if ".pdf" in allowed_extensions else "Foto deve ser JPG, PNG ou WEBP.")

    upload_dir = _static_root() / relative_dir
    upload_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f"{prefix}_{owner_id}_{uuid.uuid4().hex[:12]}{extension}"
    relative_path = relative_dir / unique_name
    destination = _static_root() / relative_path
    file.save(destination)
    size = destination.stat().st_size if destination.exists() else 0
    if size <= 0:
        destination.unlink(missing_ok=True)
        raise ValueError("O arquivo enviado esta vazio.")
    if size > max_size:
        destination.unlink(missing_ok=True)
        raise ValueError("Um dos arquivos enviados excede o limite permitido.")
    return {
        "original_name": filename,
        "path": relative_path.as_posix(),
        "size_bytes": size,
        "extension": extension.lstrip("."),
    }


def _owner_photo_upload(owner_id: int, form_data: MultiDict[str, Any], files) -> str | None:
    captured_data = _clean(form_data.get("photo_capture_data"))
    file = files.get("photo") if files else None
    if (not file or not file.filename) and not captured_data:
        return None

    relative_dir = _relative_upload_path("proprietarios")
    upload_dir = _static_root() / relative_dir
    upload_dir.mkdir(parents=True, exist_ok=True)

    if captured_data:
        match = re.match(r"^data:(image\/(?:png|jpeg|webp));base64,(.+)$", captured_data, re.IGNORECASE)
        if not match:
            raise ValueError("Formato da foto capturada e invalido.")
        mime_type = match.group(1).lower()
        encoded = match.group(2)
        extension_by_mime = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
        extension = extension_by_mime.get(mime_type)
        if not extension:
            raise ValueError("Foto capturada deve ser JPG, PNG ou WEBP.")
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Nao foi possivel processar a foto capturada.") from exc
        if not image_bytes:
            raise ValueError("A foto capturada veio vazia.")
        if len(image_bytes) > MAX_PHOTO_BYTES:
            raise ValueError("A foto capturada excede o limite de 6 MB.")
        relative_path = relative_dir / f"proprietario_{owner_id}{extension}"
        (_static_root() / relative_path).write_bytes(image_bytes)
        return relative_path.as_posix()

    saved = _save_upload_file(
        file,
        relative_dir,
        owner_id=owner_id,
        prefix="proprietario",
        allowed_extensions=ALLOWED_PHOTO_EXTENSIONS,
        max_size=MAX_PHOTO_BYTES,
    )
    return str(saved["path"]) if saved else None


def _attachment_checklist_from_form(owner_id: int, form_data: MultiDict[str, Any], files) -> dict[str, object]:
    checklist: dict[str, object] = {"documents": {}, "additional_files": []}
    relative_dir = _relative_upload_path("proprietarios", str(owner_id), "documentos")

    for document_key, label in DOCUMENT_LABELS.items():
        file_field = f"{document_key}_files"
        saved_files = []
        if files:
            for file in files.getlist(file_field):
                saved = _save_upload_file(
                    file,
                    relative_dir,
                    owner_id=owner_id,
                    prefix=document_key,
                    allowed_extensions=ALLOWED_ATTACHMENT_EXTENSIONS,
                    max_size=MAX_ATTACHMENT_BYTES,
                )
                if saved:
                    saved_files.append(saved)
        present = _truthy(form_data, document_key) or bool(saved_files)
        checklist["documents"][document_key] = {
            "label": label,
            "present": present,
            "files": saved_files,
        }

    additional_files = []
    if files:
        for file in files.getlist("document_additional_files"):
            saved = _save_upload_file(
                file,
                relative_dir,
                owner_id=owner_id,
                prefix="documento_adicional",
                allowed_extensions=ALLOWED_ATTACHMENT_EXTENSIONS,
                max_size=MAX_ATTACHMENT_BYTES,
            )
            if saved:
                additional_files.append(saved)
    checklist["additional_files"] = additional_files
    return checklist


def owner_attachment_count(owner: CondominiumOwner) -> int:
    checklist = owner.attachment_checklist_json if isinstance(owner.attachment_checklist_json, dict) else {}
    total = 0
    documents = checklist.get("documents") if isinstance(checklist.get("documents"), dict) else {}
    for value in documents.values():
        if isinstance(value, dict):
            total += len(value.get("files") or [])
    total += len(checklist.get("additional_files") or []) if isinstance(checklist.get("additional_files"), list) else 0
    return total


def condominium_unit_options() -> list[CondominiumUnit]:
    return (
        CondominiumUnit.query
        .join(CondominiumBuilding)
        .filter(CondominiumUnit.active.is_(True), CondominiumBuilding.active.is_(True))
        .order_by(
            CondominiumBuilding.display_order.asc(),
            CondominiumBuilding.id.asc(),
            CondominiumUnit.floor_number.asc(),
            CondominiumUnit.position.asc(),
            CondominiumUnit.number.asc(),
        )
        .all()
    )


def active_building_options() -> list[CondominiumBuilding]:
    return (
        CondominiumBuilding.query
        .filter(CondominiumBuilding.active.is_(True))
        .order_by(CondominiumBuilding.display_order.asc(), CondominiumBuilding.id.asc())
        .all()
    )


def condominium_owner_rows(*, limit: int = 80) -> list[CondominiumOwner]:
    return (
        CondominiumOwner.query
        .outerjoin(CondominiumUnit)
        .outerjoin(CondominiumBuilding)
        .order_by(
            CondominiumOwner.status.asc(),
            CondominiumBuilding.display_order.asc(),
            CondominiumUnit.floor_number.asc(),
            CondominiumUnit.position.asc(),
            CondominiumOwner.full_name.asc(),
        )
        .limit(limit)
        .all()
    )


def _unit_status_from_occupancy(occupancy_status: str) -> str:
    if occupancy_status == "imovel_vago":
        return "vago"
    return "ocupado"


def create_condominium_owner_from_form(form_data: MultiDict[str, Any], files, *, actor_matricula: str | None = None) -> CondominiumOwner:
    unit_id = form_data.get("unit_id", type=int)
    building_id = form_data.get("building_id", type=int)
    unit = CondominiumUnit.query.get(unit_id) if unit_id else None
    if unit is None or not unit.active or not unit.building or not unit.building.active:
        raise ValueError("Selecione uma unidade ativa.")
    if building_id and unit.building_id != building_id:
        raise ValueError("A unidade selecionada nao pertence ao edificio informado.")

    full_name = _clean(form_data.get("full_name"))
    document_number = _clean(form_data.get("document_number"))
    if not full_name:
        raise ValueError("Informe o nome completo ou razao social.")
    if not document_number:
        raise ValueError("Informe CPF ou CNPJ.")
    if not _truthy(form_data, "truth_declaration"):
        raise ValueError("Confirme a declaracao de veracidade para salvar o cadastro.")
    if not _truthy(form_data, "lgpd_authorized"):
        raise ValueError("Confirme a autorizacao LGPD para salvar o cadastro.")

    occupancy_status = _clean(form_data.get("occupancy_status")) or "nao_informado"
    correspondence_address, registry_data = _registry_data_from_form(form_data)
    owner = CondominiumOwner(
        unit=unit,
        relationship_type=_clean(form_data.get("relationship_type")) or "proprietario",
        person_type=_clean(form_data.get("person_type")) or "fisica",
        full_name=full_name,
        document_number=document_number,
        rg=_clean(form_data.get("rg")) or None,
        cnh=_clean(form_data.get("cnh")) or None,
        phone=_clean(form_data.get("phone")) or None,
        email=_clean(form_data.get("email")) or None,
        correspondence_address=correspondence_address,
        emergency_contact=_emergency_contact_from_form(form_data),
        occupancy_status=occupancy_status,
        registry_data_json=registry_data or None,
        lgpd_authorized=True,
        notes=_owner_notes_from_form(form_data),
        created_by_matricula=actor_matricula,
        updated_by_matricula=actor_matricula,
    )
    db.session.add(owner)
    db.session.flush()

    owner.attachment_checklist_json = _attachment_checklist_from_form(owner.id, form_data, files)
    photo_path = _owner_photo_upload(owner.id, form_data, files)
    if photo_path:
        owner.photo_path = photo_path
    unit.status = _unit_status_from_occupancy(occupancy_status)
    return owner


def lookup_company_owner_payload_by_cnpj(cnpj: str) -> dict[str, object]:
    digits = _digits(cnpj)
    if len(digits) != 14:
        raise ValueError("Informe um CNPJ com 14 digitos.")
    payload = FinanceService.fetch_supplier_by_cnpj(digits)
    owner_payload = {
        "person_type": "juridica",
        "full_name": payload.get("razao_social") or payload.get("nome") or "",
        "document_number": payload.get("cnpj") or digits,
        "rg": payload.get("nome_fantasia") or "",
        "rg_issuer": payload.get("inscricao_estadual") or "",
        "civil_status": payload.get("situacao_cadastral") or "",
        "profession": payload.get("observacoes") or "",
        "phone": payload.get("telefone") or "",
        "email": payload.get("email") or "",
        "correspondence_cep": payload.get("endereco_cep") or "",
        "correspondence_street": payload.get("endereco_rua") or "",
        "correspondence_number": payload.get("endereco_numero") or "",
        "correspondence_complement": payload.get("endereco_complemento") or "",
        "correspondence_neighborhood": payload.get("endereco_bairro") or "",
        "correspondence_city": payload.get("endereco_cidade") or "",
        "correspondence_state": payload.get("endereco_estado") or "",
        "source": payload.get("api_origem") or "",
    }
    return {"success": True, "owner": owner_payload}
