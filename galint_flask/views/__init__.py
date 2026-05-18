"""Blueprint registration for the GALINT Flask app."""
from __future__ import annotations

from . import (
    analytics,
    admin_mobile,
    api,
    api_mobile,
    auth,
    backups,
    central_kits,
    config,
    dashboard,
    ferramentas,

    inventory,
    mobile_panel,
    movements,
    nf,
    operations,
    pages,
    condominium,
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
    analytics.blueprint,
    auth.blueprint,
    inventory.blueprint,
    operations.blueprint,
    nf.blueprint,
    movements.blueprint,
    users.blueprint,

    backups.blueprint,
    pages.blueprint,
    condominium.blueprint,
    api.api_bp,
    api_mobile.blueprint,
    qrcode.blueprint,
    admin_mobile.blueprint,
    mobile_panel.blueprint,
    telegram_config.bp,
    telegram_bot.bp,
    central_kits.blueprint,
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
