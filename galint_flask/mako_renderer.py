"""Helper utilities to render Mako templates alongside the existing Jinja setup."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Request, current_app, get_flashed_messages, request, url_for
from flask_login import current_user
from mako.lookup import TemplateLookup
from mako.runtime import Undefined


_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates_mako"
_lookup = TemplateLookup(
    directories=[str(_TEMPLATE_DIR)],
    input_encoding="utf-8",
    default_filters=["h"],
    imports=["from markupsafe import escape"],
    filesystem_checks=True,
)


def render_mako_template(template_name: str, **context: Any) -> str:
    """Render a Mako template injecting Flask helpers and globals."""

    template = _lookup.get_template(template_name)

    def tojson(value: Any) -> str:
        if isinstance(value, Undefined):
            value = []
        return current_app.json.dumps(value)

    # Base context shared with all templates so they mirror the Jinja environment.
    shared_context: dict[str, Any] = dict(current_app.jinja_env.globals)
    shared_context.update(
        {
            "url_for": url_for,
            "current_user": current_user,
            "get_flashed_messages": get_flashed_messages,
            "request": request,
            "system_name": current_app.config.get("SYSTEM_NAME", "Gerenciador de Almoxarifado Inteligente"),
            "tojson": tojson,
        }
    )
    shared_context.update(context)

    rendered = template.render(**shared_context)
    if isinstance(rendered, bytes):
        rendered = rendered.decode("utf-8")
    return rendered


__all__ = ["render_mako_template"]
