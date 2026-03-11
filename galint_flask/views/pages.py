"""Rotas auxiliares: configurações e página sobre."""
from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import abort

from ..services.backup import BackupService
from ..services.backup_restore_jobs import get_job_state, start_restore_job
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


@blueprint.get("/configuracoes")
@login_required
def config():
    return render_template("config.html")


@blueprint.get("/configuracoes/backup")
@login_required
def config_backup():
    # Preencher flag de admin na sessão para compatibilidade com sessões existentes.
    # (Esse request ainda usa login_required e pode consultar DB; é antes da restauração começar.)
    try:
        session.setdefault("galint_is_admin", bool(getattr(current_user, "is_admin", 0)))
        session.setdefault("galint_user_id", str(getattr(current_user, "matricula", "")))
    except Exception:
        pass

    backups = BackupService(current_app).list_backups()
    return render_template("config_backup.html", backups=backups)


@blueprint.post("/configuracoes/backup")
@login_required
def create_backup():
    _require_admin()
    service = BackupService(current_app)
    try:
        backup_name = service.create_backup()
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


@blueprint.post("/configuracoes/backup/excluir")
@login_required
def delete_backup():
    _require_admin()
    backup_name = request.form.get("backup_name")
    if not backup_name:
        flash("Selecione um backup para apagar.", "warning")
        return redirect(url_for("pages.config_backup"))
    service = BackupService(current_app)
    try:
        removed = service.delete_backup(backup_name)
        flash(f"Backup removido: {removed}", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
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

    server_host = (request.form.get("server_host") or "").strip()
    server_port = request.form.get("server_port")
    intent = (request.form.get("intent") or "save").strip().lower()

    try:
        settings = save_network_settings(
            current_app,
            server_host=server_host,
            server_port=server_port,
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
    return render_template("sobre.html")


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
