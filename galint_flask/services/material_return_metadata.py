from __future__ import annotations

import re
from typing import Any


_ACTOR_SUFFIX_PATTERN = re.compile(r"\(\s*Mat\.\s*([^)]+?)\s*\)\s*$", re.IGNORECASE)


def format_material_return_actor_label(*, nome: str | None = None, matricula: str | None = None) -> str | None:
    nome_text = str(nome or "").strip()
    matricula_text = str(matricula or "").strip()

    if nome_text and matricula_text:
        return f"{nome_text} (Mat. {matricula_text})"
    if nome_text:
        return nome_text
    if matricula_text:
        return f"Matrícula {matricula_text}"
    return None


def _parse_actor_value(raw_value: str | None) -> dict[str, str | None]:
    raw = str(raw_value or "").strip()
    if not raw:
        return {"raw": None, "nome": None, "matricula": None}

    actor_match = _ACTOR_SUFFIX_PATTERN.search(raw)
    if actor_match:
        matricula = actor_match.group(1).strip() or None
        nome = raw[:actor_match.start()].strip(" -:") or None
        if nome and nome.lower().startswith("matrícula "):
            nome = None
        return {"raw": raw, "nome": nome, "matricula": matricula}

    lowered = raw.lower()
    if lowered.startswith("matrícula "):
        matricula = raw[len("matrícula "):].strip() or None
        return {"raw": raw, "nome": None, "matricula": matricula}
    if lowered.startswith("matricula "):
        matricula = raw[len("matricula "):].strip() or None
        return {"raw": raw, "nome": None, "matricula": matricula}

    return {"raw": raw, "nome": raw, "matricula": None}


def extract_material_return_metadata(description: str | None) -> dict[str, Any]:
    withdrawer = {"raw": None, "nome": None, "matricula": None}
    returner = {"raw": None, "nome": None, "matricula": None}
    return_unit = None
    notes: list[str] = []

    for chunk in str(description or "").split("|"):
        part = chunk.strip()
        if not part:
            continue

        lowered = part.lower()
        if lowered.startswith("retirado por:"):
            withdrawer = _parse_actor_value(part.split(":", 1)[1].strip())
            continue
        if lowered.startswith("devolvido por:"):
            returner = _parse_actor_value(part.split(":", 1)[1].strip())
            continue
        if lowered.startswith("retorno_unit="):
            return_unit = part.split("=", 1)[1].strip().lower() or None
            continue
        notes.append(part)

    return {
        "withdrawer": withdrawer,
        "returner": returner,
        "return_unit": return_unit,
        "notes": notes,
        "clean_description": " | ".join(notes),
    }