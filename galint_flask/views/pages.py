"""Rotas auxiliares: configurações e página sobre."""
from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import abort

from ..services.backup import BackupService
from ..services.auth import create_workspace_window_token
from ..services.backup_restore_jobs import get_job_state, start_restore_job
from ..services.conversion_engine import ConversionEngineService, get_conversion_job_state, start_conversion_job
from ..services.native_workspace_launcher import launch_workspace_window
from ..services.network_settings import load_network_settings, save_network_settings


blueprint = Blueprint("pages", __name__)


def _inline_markdown_to_html(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


def _markdown_file_to_html(file_path: Path) -> str:
    lines = file_path.read_text(encoding="utf-8").splitlines()
    parts: list[str] = []
    in_ul = False
    in_ol = False
    in_pre = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            parts.append("</ul>")
            in_ul = False
        if in_ol:
            parts.append("</ol>")
            in_ol = False

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            close_lists()
            if in_pre:
                parts.append("</code></pre>")
                in_pre = False
            else:
                parts.append('<pre class="doc-code"><code>')
                in_pre = True
            continue

        if in_pre:
            parts.append(html.escape(line))
            continue

        if not stripped:
            close_lists()
            continue

        if stripped == "---":
            close_lists()
            parts.append("<hr>")
            continue

        if stripped.startswith("### "):
            close_lists()
            parts.append(f"<h3>{_inline_markdown_to_html(stripped[4:])}</h3>")
            continue
        if stripped.startswith("## "):
            close_lists()
            parts.append(f"<h2>{_inline_markdown_to_html(stripped[3:])}</h2>")
            continue
        if stripped.startswith("# "):
            close_lists()
            parts.append(f"<h1>{_inline_markdown_to_html(stripped[2:])}</h1>")
            continue

        if re.match(r"^\d+\.\s+", stripped):
            if not in_ol:
                close_lists()
                parts.append('<ol class="doc-list">')
                in_ol = True
            item_text = re.sub(r"^\d+\.\s+", "", stripped)
            parts.append(f"<li>{_inline_markdown_to_html(item_text)}</li>")
            continue

        if stripped.startswith("- "):
            if not in_ul:
                close_lists()
                parts.append('<ul class="doc-list">')
                in_ul = True
            parts.append(f"<li>{_inline_markdown_to_html(stripped[2:])}</li>")
            continue

        close_lists()
        parts.append(f"<p>{_inline_markdown_to_html(stripped)}</p>")

    close_lists()
    if in_pre:
        parts.append("</code></pre>")

    return "\n".join(parts)


def _require_admin() -> None:
    if not bool(getattr(current_user, "is_admin", False)):
        abort(403)


def _prime_admin_session() -> None:
    try:
        session.setdefault("galint_is_admin", bool(getattr(current_user, "is_admin", 0)))
        session.setdefault("galint_user_id", str(getattr(current_user, "matricula", "")))
    except Exception:
        pass


def _require_admin_session_json() -> tuple[str | None, tuple[object, int] | None]:
    """Auth leve (sem DB) para endpoints JSON de restore.

    Retorna (user_key, error_response). Se error_response não for None,
    deve ser retornado diretamente pela view.
    """
    user_id = session.get("_user_id")
    if not user_id:
        return None, (jsonify({"ok": False, "error": "Não autenticado. Faça login novamente."}), 401)
    if not bool(session.get("galint_is_admin")):
        return None, (jsonify({"ok": False, "error": "Acesso negado. Apenas administradores."}), 403)
    return str(user_id), None


def _normalize_workspace_slot(raw_value: object) -> int:
    try:
        value = int(raw_value or 2)
    except (TypeError, ValueError):
        value = 2
    return value if value in (2, 3) else 2


def _build_workspace_window_url(path: str, token: str) -> str:
    raw_path = str(path or "").strip() or url_for("dashboard.index")
    split = urlsplit(raw_path)

    if split.scheme or split.netloc:
        if split.scheme not in {"http", "https"}:
            raise ValueError("A janela auxiliar aceita apenas URLs HTTP locais do GALINT.")
        if split.netloc != request.host:
            raise ValueError("A janela auxiliar so pode abrir paginas do proprio GALINT.")
        normalized_path = split.path or "/"
        query_pairs = parse_qsl(split.query, keep_blank_values=True)
    else:
        normalized = raw_path if raw_path.startswith("/") else f"/{raw_path.lstrip('/')}"
        normalized_split = urlsplit(normalized)
        normalized_path = normalized_split.path or "/"
        query_pairs = parse_qsl(normalized_split.query, keep_blank_values=True)

    query_pairs = [(key, value) for key, value in query_pairs if key not in {"workspace_token", "workspace_window"}]
    query_pairs.append(("workspace_window", "1"))
    query_pairs.append(("workspace_token", token))
    return urlunsplit((request.scheme, request.host, normalized_path, urlencode(query_pairs, doseq=True), ""))


@blueprint.post("/workspace/native-open")
@login_required
def workspace_native_open_api():
    payload = request.get_json(silent=True)
    request_data = payload if isinstance(payload, dict) else request.form

    try:
        token = create_workspace_window_token(current_user)
        target_url = _build_workspace_window_url(str((request_data or {}).get("path") or ""), token)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    title = str((request_data or {}).get("title") or "").strip() or current_app.config.get("SYSTEM_NAME", "GALINT")
    slot = _normalize_workspace_slot((request_data or {}).get("slot"))
    result = launch_workspace_window(target_url, title[:120], slot=slot)
    status_code = 200 if result.get("success") else 503
    return jsonify(result), status_code


@blueprint.get("/configuracoes")
@login_required
def config():
    return render_template("config.html")


@blueprint.get("/configuracoes/backup")
@login_required
def config_backup():
    # Preencher flag de admin na sessão para compatibilidade com sessões existentes.
    # (Esse request ainda usa login_required e pode consultar DB; é antes da restauração começar.)
    _prime_admin_session()

    service = BackupService(current_app)
    backups = service.list_backups()
    diagnostic = service.diagnostic_report()
    return render_template("config_backup.html", backups=backups, diagnostic=diagnostic)


@blueprint.get("/configuracoes/backup/checklist-final")
@login_required
def backup_final_checklist():
    checklist_path = Path(current_app.root_path).parent / "CHECKLIST_FINAL_BACKUP_GALINT.md"
    if not checklist_path.exists():
        abort(404)
    return send_file(checklist_path, as_attachment=True, download_name=checklist_path.name)


@blueprint.get("/configuracoes/conversionengine")
@login_required
def config_conversionengine():
    _require_admin()
    _prime_admin_session()
    service = ConversionEngineService(current_app)
    doc_path = Path(current_app.root_path).parent / "CONVERSIONENGINE.md"
    content_html = _markdown_file_to_html(doc_path) if doc_path.exists() else ""
    return render_template(
        "config_conversionengine.html",
        dashboard=service.dashboard_payload(),
        content_html=content_html,
        initial_job_id=(request.args.get("job_id") or "").strip(),
    )


@blueprint.post("/configuracoes/backup")
@login_required
def create_backup():
    _require_admin()
    service = BackupService(current_app)
    backup_kind = (
        request.form.get("selected_backup_kind")
        or request.form.get("backup_kind")
        or BackupService.DATABASE_BACKUP_KIND
    ).strip().lower()
    try:
        backup_name = service.create_backup(backup_kind=backup_kind)
        flash(f"Backup criado: {backup_name}", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("pages.config_backup"))


@blueprint.post("/configuracoes/restaurar")
@login_required
def restore_backup():
    _require_admin()
    backup_name = request.form.get("backup_name")
    if not backup_name:
        flash("Selecione um backup para restaurar.", "warning")
        return redirect(url_for("pages.config_backup"))
    service = BackupService(current_app)
    try:
        restored = service.restore_backup(backup_name)
        flash(f"Backup restaurado: {restored}", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("pages.config_backup"))


@blueprint.post("/configuracoes/restaurar/iniciar")
def start_restore_backup():
    """Inicia restauração em background e retorna um job_id."""
    user_key, error = _require_admin_session_json()
    if error:
        return error
    backup_name = (request.form.get("backup_name") or "").strip()
    if not backup_name:
        return jsonify({"ok": False, "error": "Selecione um backup para restaurar."}), 400

    app = current_app._get_current_object()

    def _restore(reporter):
        service = BackupService(app)
        service.restore_backup_with_progress(backup_name, reporter)

    try:
        job_id = start_restore_job(
            app=app,
            backup_name=backup_name,
            user_key=user_key,
            restore_callable=_restore,
        )
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    return jsonify({"ok": True, "job_id": job_id})


@blueprint.get("/configuracoes/restaurar/status/<job_id>")
def restore_backup_status(job_id: str):
    user_key, error = _require_admin_session_json()
    if error:
        return error
    state = get_job_state(job_id=job_id, user_key=user_key)
    if not state:
        return jsonify({"ok": False, "error": "Job não encontrado."}), 404
    return jsonify({"ok": True, "state": state})


@blueprint.post("/configuracoes/conversionengine/iniciar")
def conversionengine_start():
    user_key, error = _require_admin_session_json()
    if error:
        return error

    upload = request.files.get("source_dump")
    if upload is None:
        return jsonify({"ok": False, "error": "Envie um arquivo .sql, .zip, .sqlite ou .db para análise."}), 400

    try:
        service = ConversionEngineService(current_app)
        stored = service.store_upload(upload)
        job_id = start_conversion_job(
            app=current_app._get_current_object(),
            user_key=user_key,
            source_name=stored["source_name"],
            stored_name=stored["stored_name"],
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "job_id": job_id})


@blueprint.post("/configuracoes/conversionengine/analisar-backup")
@login_required
def conversionengine_start_from_backup():
    _require_admin()
    _prime_admin_session()

    selected_names = [str(name).strip() for name in request.form.getlist("backup_names") if str(name).strip()]
    backup_name = selected_names[0] if len(selected_names) == 1 else ""
    if not backup_name:
        flash("Selecione um backup para enviar ao ConversionEngine.", "warning")
        return redirect(url_for("pages.config_backup"))

    user_key = str(session.get("_user_id") or "").strip()
    if not user_key:
        flash("Sessão administrativa inválida para iniciar o ConversionEngine.", "danger")
        return redirect(url_for("pages.config_backup"))

    try:
        service = ConversionEngineService(current_app)
        stored = service.register_existing_backup(backup_name)
        job_id = start_conversion_job(
            app=current_app._get_current_object(),
            user_key=user_key,
            source_name=stored["source_name"],
            stored_name=stored["stored_name"],
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("pages.config_backup"))

    flash(f"Backup enviado ao ConversionEngine: {backup_name}", "success")
    return redirect(url_for("pages.config_conversionengine", job_id=job_id))


@blueprint.get("/configuracoes/conversionengine/status/<job_id>")
def conversionengine_status(job_id: str):
    user_key, error = _require_admin_session_json()
    if error:
        return error
    state = get_conversion_job_state(job_id=job_id, user_key=user_key)
    if not state:
        return jsonify({"ok": False, "error": "Job do ConversionEngine não encontrado."}), 404
    return jsonify({"ok": True, "state": state})


@blueprint.get("/configuracoes/conversionengine/download/<job_id>")
def conversionengine_download_sql(job_id: str):
    user_key, error = _require_admin_session_json()
    if error:
        return error
    state = get_conversion_job_state(job_id=job_id, user_key=user_key)
    if not state:
        return jsonify({"ok": False, "error": "Job do ConversionEngine não encontrado."}), 404
    sql_name = (((state.get("result") or {}).get("artifacts") or {}).get("converted_sql_name") or "").strip()
    if not sql_name:
        return jsonify({"ok": False, "error": "Nenhuma base convertida apta para download foi gerada."}), 409

    target = ConversionEngineService(current_app).outputs_dir / sql_name
    if not target.exists():
        return jsonify({"ok": False, "error": "Arquivo convertido não encontrado."}), 404
    return send_file(target, mimetype="application/sql", as_attachment=True, download_name=target.name)


@blueprint.get("/configuracoes/conversionengine/pacote/<job_id>")
def conversionengine_download_package(job_id: str):
    user_key, error = _require_admin_session_json()
    if error:
        return error
    state = get_conversion_job_state(job_id=job_id, user_key=user_key)
    if not state:
        return jsonify({"ok": False, "error": "Job do ConversionEngine não encontrado."}), 404
    package_name = (((state.get("result") or {}).get("artifacts") or {}).get("package_name") or "").strip()
    if not package_name:
        return jsonify({"ok": False, "error": "Nenhum pacote técnico disponível para download."}), 409

    target = ConversionEngineService(current_app).outputs_dir / package_name
    if not target.exists():
        return jsonify({"ok": False, "error": "Pacote técnico não encontrado."}), 404
    return send_file(target, mimetype="application/zip", as_attachment=True, download_name=target.name)


@blueprint.post("/configuracoes/conversionengine/implantar/<job_id>")
def conversionengine_deploy(job_id: str):
    user_key, error = _require_admin_session_json()
    if error:
        return error
    state = get_conversion_job_state(job_id=job_id, user_key=user_key)
    if not state:
        return jsonify({"ok": False, "error": "Job do ConversionEngine não encontrado."}), 404

    summary = ((state.get("result") or {}).get("summary") or {})
    artifacts = ((state.get("result") or {}).get("artifacts") or {})
    backup_name = (artifacts.get("deploy_backup_name") or "").strip()
    source_kind = str(summary.get("source_kind") or "")
    package_backup_kind = str(summary.get("package_backup_kind") or "")
    if not summary.get("deployable"):
        return jsonify({"ok": False, "error": "Esta conversão não foi liberada para implantação direta."}), 409

    app = current_app._get_current_object()
    conversion_service = ConversionEngineService(current_app)

    def _restore(reporter):
        service = BackupService(app)
        if source_kind == "zip_package" and package_backup_kind == BackupService.COMPLETE_BACKUP_KIND:
            source_path = conversion_service.sources_dir / str(state.get("stored_name") or "")
            service.restore_complete_package(source_path, reporter)
            return
        if not backup_name:
            raise ValueError("Nenhum artefato de restore foi gerado para esta conversão.")
        service.restore_backup_with_progress(backup_name, reporter)

    try:
        restore_job_id = start_restore_job(
            app=app,
            backup_name=backup_name,
            user_key=user_key,
            restore_callable=_restore,
        )
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409

    return jsonify({"ok": True, "restore_job_id": restore_job_id})


@blueprint.post("/configuracoes/backup/excluir")
@login_required
def delete_backup():
    _require_admin()
    backup_names = [str(name).strip() for name in request.form.getlist("backup_names") if str(name).strip()]
    if not backup_names:
        flash("Selecione ao menos um backup para apagar.", "warning")
        return redirect(url_for("pages.config_backup"))

    service = BackupService(current_app)
    removed_names: list[str] = []
    failed_messages: list[str] = []
    for backup_name in backup_names:
        try:
            removed_names.append(service.delete_backup(backup_name))
        except ValueError as exc:
            failed_messages.append(f"{backup_name}: {exc}")

    if removed_names:
        if len(removed_names) == 1:
            flash(f"Backup removido: {removed_names[0]}", "success")
        else:
            flash(f"{len(removed_names)} backups removidos com sucesso.", "success")

    for message in failed_messages:
        flash(message, "danger")

    return redirect(url_for("pages.config_backup"))


@blueprint.get("/configuracoes/rede")
@login_required
def config_rede():
    token = current_app.config.get("DASHBOARD_SHARE_TOKEN")
    share_url = None
    if token:
        share_url = url_for("dashboard.rede_galint", token=token, _external=True)

    settings = load_network_settings(current_app)
    return render_template(
        "config_rede.html",
        share_url=share_url,
        token_configured=bool(token),
        settings=settings,
    )


def _test_mobile_endpoint(url: str) -> tuple[bool, str]:
    try:
        req = Request(url, method="GET")
        with urlopen(req, timeout=5) as response:
            body = response.read(1024).decode("utf-8", errors="replace")
            return True, f"OK (HTTP {response.status}). Resposta: {body}"
    except HTTPError as exc:
        try:
            body = exc.read(1024).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return False, f"Falhou (HTTP {exc.code}). {body}".strip()
    except URLError as exc:
        return False, f"Falhou (rede). {exc.reason}"
    except Exception as exc:
        return False, f"Falhou. {exc}"


@blueprint.post("/configuracoes/rede")
@login_required
def update_rede():
    _require_admin()

    base_url = (request.form.get("base_url") or "").strip()
    intent = (request.form.get("intent") or "save").strip().lower()

    try:
        settings = save_network_settings(
            current_app,
            base_url=base_url,
        )
        flash("Configurações de rede salvas.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("pages.config_rede"))

    if intent == "test":
        url = f"{settings.base_url()}/api/mobile/health"
        ok, message = _test_mobile_endpoint(url)
        flash(f"Teste de comunicação: {message}", "success" if ok else "danger")

    return redirect(url_for("pages.config_rede"))


@blueprint.get("/sobre")
@login_required
def sobre():
    kit_readme_path = Path(current_app.root_path).parent / "README_CENTRAL_KITS_FERRAMENTAS.md"
    kit_doc_html = _markdown_file_to_html(kit_readme_path) if kit_readme_path.exists() else ""
    return render_template(
        "sobre.html",
        kit_doc_html=kit_doc_html,
    )


@blueprint.get("/documentacao")
@login_required
def documentacao():
    return render_template("documentacao.html")


@blueprint.get("/documentacao/percentual-movimentos")
@login_required
def documentacao_percentual_movimentos():
    readme_path = Path(current_app.root_path).parent / "README_PERCENTUAL_MOVIMENTOS.md"
    if not readme_path.exists():
        abort(404)
    content_html = _markdown_file_to_html(readme_path)
    return render_template(
        "documentacao_percentual_movimentos.html",
        content_html=content_html,
    )


@blueprint.get("/documentacao/central-kits")
@login_required
def documentacao_central_kits():
    readme_path = Path(current_app.root_path).parent / "README_CENTRAL_KITS_FERRAMENTAS.md"
    if not readme_path.exists():
        abort(404)
    content_html = _markdown_file_to_html(readme_path)
    return render_template(
        "documentacao_central_kits.html",
        content_html=content_html,
    )
