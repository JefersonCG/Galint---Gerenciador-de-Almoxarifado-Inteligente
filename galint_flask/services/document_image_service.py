"""Gera uma representação visual estável do documento para conferência."""
from __future__ import annotations

from html import escape
from pathlib import Path

from flask import current_app


def generate_document_illustration(documento, item_row=None) -> str:
    folder = Path(current_app.root_path) / "static" / "uploads" / "documentos"
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"documento_{documento.id_documento}.svg"
    path = folder / filename
    item_label = getattr(getattr(item_row, "item", None), "descricao", None) if item_row else None
    quantity = getattr(item_row, "quantidade", None) if item_row else None
    lines = [
        ("GALINT - ESPELHO DE CONFERENCIA", "#123047", 30),
        (f"{str(documento.tipo_documento or 'documento').upper()} {documento.numero_documento}", "#1f2937", 48),
        (f"Emissao: {documento.data_emissao or 'N/D'}    Entrada: {documento.data_recebimento or 'N/D'}", "#475569", 80),
        (f"Chave: {documento.chave_acesso or 'Nao informada'}", "#475569", 108),
        (f"Item: {item_label or 'Consultar linhas do documento'}    Quantidade: {quantity if quantity is not None else 'N/D'}", "#0f766e", 150),
    ]
    text = "".join(
        f'<text x="48" y="{y}" font-family="DejaVu Sans, sans-serif" font-size="{22 if y < 60 else 16}px" font-weight="{700 if y < 60 else 400}" fill="{color}">{escape(str(value))}</text>'
        for value, color, y in lines
    )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="220" viewBox="0 0 1000 220"><rect width="1000" height="220" fill="#f8fafc"/><rect x="20" y="20" width="960" height="180" rx="8" fill="white" stroke="#cbd5e1"/>{text}</svg>',
        encoding="utf-8",
    )
    return f"uploads/documentos/{filename}"