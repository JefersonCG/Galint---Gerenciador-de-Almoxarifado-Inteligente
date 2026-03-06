from __future__ import annotations

from io import BytesIO

from flask import Blueprint, jsonify, request, send_file

from ..services.qrcode_service import QRCodeService


blueprint = Blueprint("qrcode", __name__, url_prefix="/api/qrcode")


@blueprint.get("/<value>.png")
def qrcode_png(value: str):
    """Retorna um QR Code PNG válido a partir de 13 dígitos.

    Requisitos:
    - segno==1.6.1
    - micro=False
    - error='M'
    - border=4
    - scale=10
    """

    try:
        safe_value = QRCodeService.validate_13_digits(value)
        png_bytes = QRCodeService.generate_png(safe_value, scale=10, border=4, error="M")
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    filename = f"qrcode_{safe_value}.png"
    resp = send_file(
        BytesIO(png_bytes),
        mimetype="image/png",
        as_attachment=False,
        download_name=filename,
        max_age=0,
    )
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@blueprint.post("/")
def qrcode_png_post():
    """POST JSON: {"value": "123..."} -> retorna PNG.

    Útil quando o valor não pode/ não deve ir na URL.
    """

    payload = request.get_json(silent=True) or {}
    value = payload.get("value")

    try:
        safe_value = QRCodeService.validate_13_digits(value)
        png_bytes = QRCodeService.generate_png(safe_value, scale=10, border=4, error="M")
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    filename = f"qrcode_{safe_value}.png"
    resp = send_file(
        BytesIO(png_bytes),
        mimetype="image/png",
        as_attachment=False,
        download_name=filename,
        max_age=0,
    )
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@blueprint.get("/validate/<value>")
def validate(value: str):
    """Endpoint auxiliar para diagnosticar erros de formatação do valor."""

    try:
        QRCodeService.validate_13_digits(value)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True}), 200
