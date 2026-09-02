"""WSGI entry point for the GALINT Flask application."""
import argparse
import atexit
import os
import sys
from pathlib import Path
from typing import Any, cast

from flask import Flask
from galint_flask import create_app
from galint_flask.services.barcode_studio_file_launcher import open_layout_file


_SINGLE_INSTANCE_LOCK_HANDLE = None


def _acquire_single_instance_lock():
    """Acquire a process-held lock before initializing the Flask app."""
    lock_path = Path(__file__).resolve().parent / "instance" / "galint.app.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="ascii")
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            handle.write("0")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
    except (OSError, BlockingIOError):
        handle.close()
        print("Outra instancia do GALINT ja esta em execucao.", file=sys.stderr)
        raise SystemExit(1)

    atexit.register(handle.close)
    return handle


def _bootstrap_command(argv: list[str] | None = None) -> str | None:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        return None
    command = values[0]
    return command if command in {"native-mirror", "native-window", "open-layout-file"} else None


def _register_runtime_fallback_routes(app: Flask) -> None:
    try:
        from flask import jsonify, render_template, request
        from flask_login import login_required

        from galint_flask.extensions import db
        from galint_flask.models import Item
        from galint_flask.services.item_foto_service import ItemFotoService
        from galint_flask.views.inventory import (
            _build_purchase_projection_sync_payload,
            _json_no_store,
            _request_purchase_projection_filters,
            _require_admin_or_supervisor,
            _sync_purchase_projection_report,
        )

        def _apply_photo_from_url():
            payload = cast(dict[str, Any], request.form.to_dict())
            if not payload:
                json_payload = request.get_json(silent=True)
                if isinstance(json_payload, dict):
                    payload = cast(dict[str, Any], json_payload)

            codigo = str(payload.get("codigo") or "").strip()
            image_url = str(payload.get("image_url") or "").strip()
            if not codigo:
                return jsonify({"success": False, "message": "Codigo do item nao informado"}), 400
            if not image_url:
                return jsonify({"success": False, "message": "URL da imagem nao informada"}), 400
            item = Item.query.get(codigo)
            if not item:
                return jsonify({"success": False, "message": "Item nao encontrado"}), 404
            try:
                if item.foto_path:
                    ItemFotoService.deletar_foto(item.foto_path)
                foto_path = ItemFotoService.download_foto_from_url(image_url, codigo)
                item.foto_path = foto_path
                db.session.commit()
                return jsonify({"success": True, "message": "Foto atualizada", "foto_path": foto_path})
            except ValueError as exc:
                return jsonify({"success": False, "message": str(exc)}), 400
            except Exception:
                return jsonify({"success": False, "message": "Falha inesperada ao atualizar foto"}), 500

        if "foto_url_api_fallback" not in app.view_functions:
            app.add_url_rule("/api/itens/foto/url", endpoint="foto_url_api_fallback", view_func=_apply_photo_from_url, methods=["POST"])
        if "foto_url_fallback" not in app.view_functions:
            app.add_url_rule("/itens/foto/url", endpoint="foto_url_fallback", view_func=_apply_photo_from_url, methods=["POST"])

        def _render_dynamic_units_help_fallback():
            return render_template("inventory/dynamic_units_help.html")

        has_dynamic_units_help_route = any(rule.rule == "/itens/ajuda/unidades-dinamicas" for rule in app.url_map.iter_rules())
        if not has_dynamic_units_help_route and "dynamic_units_help_fallback" not in app.view_functions:
            app.add_url_rule(
                "/itens/ajuda/unidades-dinamicas",
                endpoint="dynamic_units_help_fallback",
                view_func=_render_dynamic_units_help_fallback,
                methods=["GET"],
            )

        def _purchase_projection_sync_fallback():
            _require_admin_or_supervisor()
            filters = _request_purchase_projection_filters(request.form)
            report, _ = _sync_purchase_projection_report(filters, request.form, flash_feedback=False)
            return _json_no_store(_build_purchase_projection_sync_payload(report))

        has_purchase_projection_sync_route = any(rule.rule == "/itens/projecao-compras/sync" for rule in app.url_map.iter_rules())
        if not has_purchase_projection_sync_route and "inventory.purchase_projection_sync" not in app.view_functions:
            app.add_url_rule(
                "/itens/projecao-compras/sync",
                endpoint="inventory.purchase_projection_sync",
                view_func=login_required(_purchase_projection_sync_fallback),
                methods=["POST"],
            )
    except Exception:
        pass


def _create_runtime_app() -> Flask:
    runtime_app = create_app()
    _register_runtime_fallback_routes(runtime_app)
    return runtime_app


if _bootstrap_command() is None:
    if __name__ == "__main__":
        _SINGLE_INSTANCE_LOCK_HANDLE = _acquire_single_instance_lock()
    app: Flask | None = _create_runtime_app()
else:
    app = None


def _load_migration_funcs():
    try:
        from flask_migrate import init as _migrate_init, migrate as _migrate, upgrade as _upgrade
    except Exception:
        print("Flask-Migrate não encontrado. Instale com: pip install Flask-Migrate")
        raise

    return _migrate_init, _migrate, _upgrade


def _run_migrations(app: Flask) -> None:
    """Inicliza pasta de migrations (se necessário), gera e aplica migration.

    Usa API programática do Flask-Migrate para suportar ambientes sem CLI.
    """
    from pathlib import Path

    _migrate_init, _migrate, _upgrade = _load_migration_funcs()
    migrations_dir = Path(__file__).resolve().parent / "migrations"
    try:
        if not migrations_dir.exists():
            print("Inicializando pasta de migrations...")
            _migrate_init(directory=str(migrations_dir))

        print("Gerando migration automática (comparando models)...")
        _migrate(message="autogenerated by app.py", directory=str(migrations_dir))

        print("Aplicando migrations (upgrade)...")
        _upgrade(directory=str(migrations_dir))
        print("Migrações aplicadas com sucesso.")
        
    except Exception as e:
        print(f"Erro ao executar migrações: {e}")
        raise


def _run_upgrade(app: Flask) -> None:
    """Aplica migrations existentes sem gerar novas."""
    from pathlib import Path

    _, _, _upgrade = _load_migration_funcs()
    migrations_dir = Path(__file__).resolve().parent / "migrations"
    try:
        print("Aplicando migrations pendentes (upgrade)...")
        _upgrade(directory=str(migrations_dir))
        print("Upgrade aplicado com sucesso.")
    except Exception as e:
        print(f"Erro ao aplicar upgrade: {e}")
        raise


if __name__ == "__main__":
    native_gui_command = _bootstrap_command()

    if native_gui_command == "native-mirror":
        parser = argparse.ArgumentParser(description="Abre o painel espelho em janela nativa")
        parser.add_argument("command")
        parser.add_argument("--url", required=True)
        parser.add_argument("--title", default="GALINT - Painel do colaborador")
        args = parser.parse_args()

        from galint_flask.services.native_panel_window import run_native_panel

        sys.exit(run_native_panel(url=args.url, title=args.title))

    if native_gui_command == "native-window":
        parser = argparse.ArgumentParser(description="Abre uma janela operacional nativa do GALINT")
        parser.add_argument("command")
        parser.add_argument("--url", required=True)
        parser.add_argument("--title", default="GALINT")
        parser.add_argument("--slot", type=int, default=2)
        args = parser.parse_args()

        from galint_flask.services.native_workspace_window import run_native_workspace_window

        sys.exit(run_native_workspace_window(url=args.url, title=args.title, slot=args.slot))

    if native_gui_command == "open-layout-file":
        parser = argparse.ArgumentParser(description="Abre um arquivo do Editor de Etiquetas no GALINT")
        parser.add_argument("command")
        parser.add_argument("layout_file")
        parser.add_argument("--base-url", default=None)
        parser.add_argument("--no-open-browser", action="store_true")
        parser.add_argument("--no-ensure-server", action="store_true")
        args = parser.parse_args()

        layout_path = Path(args.layout_file).expanduser().resolve()
        try:
            result = open_layout_file(
                layout_path,
                base_url=args.base_url,
                ensure_server=not bool(args.no_ensure_server),
                open_browser=not bool(args.no_open_browser),
            )
        except FileNotFoundError:
            print(f"Arquivo nao encontrado: {layout_path}")
            sys.exit(2)
        except ValueError as exc:
            print(str(exc))
            sys.exit(2)
        except Exception as exc:
            print(f"Falha ao abrir layout no GALINT: {exc}")
            sys.exit(1)

        print(result.get("message") or "Arquivo preparado para o Editor de Etiquetas.")
        if result.get("url"):
            print(result["url"])
        sys.exit(0 if result.get("success") else 1)

    if app is None:
        raise RuntimeError("Aplicacao Flask indisponivel para este modo de execucao")

    if len(sys.argv) > 1 and sys.argv[1] in ("migrate", "db-migrate"):
        # Executar migrações programaticamente e sair
        with app.app_context():
            _run_migrations(app)
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] in ("upgrade", "db-upgrade"):
        # Aplicar migrations existentes e sair
        with app.app_context():
            _run_upgrade(app)
        sys.exit(0)

    port = int(os.getenv("PORT", "5000"))

    print("Iniciando servidor em modo HTTP")
    print(f"   URL: http://localhost:{port}")
    print(f"   LAN: http://SEU_IP:{port} (ex.: http://10.0.0.245:{port})")
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False, threaded=True)
