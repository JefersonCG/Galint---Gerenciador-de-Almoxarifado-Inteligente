"""Blueprint registration for the GALINT Flask app."""
from __future__ import annotations

from . import (
    admin_mobile,
    api,
    api_mobile,
    auth,
    backups,
    config,
    dashboard,
    ferramentas,

    inventory,
    mobile_panel,
    movements,
    nf,
    pages,
    qrcode,
    reparo,
    reports,
    telegram_config,
    telegram_bot,
    tool_custody,
    updates,
    users,
)


BLUEPRINTS = (
    dashboard.blueprint,
    auth.blueprint,
    inventory.blueprint,
    nf.blueprint,
    movements.blueprint,
    users.blueprint,

    backups.blueprint,
    pages.blueprint,
    api.api_bp,
    api_mobile.blueprint,
    qrcode.blueprint,
    admin_mobile.blueprint,
    mobile_panel.blueprint,
    telegram_config.bp,
    telegram_bot.bp,
    ferramentas.blueprint,
    reports.bp,
    reparo.blueprint,
    tool_custody.bp,
    config.bp,
    updates.blueprint,
)


def register_blueprints(app) -> None:
    for bp in BLUEPRINTS:
        app.register_blueprint(bp)
