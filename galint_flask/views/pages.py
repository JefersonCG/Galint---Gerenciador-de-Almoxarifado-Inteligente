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
from ..services.category_catalog import DEFAULT_INVENTORY_CATEGORIES, category_catalog_service
from ..services.conversion_engine import ConversionEngineService, get_conversion_job_state, start_conversion_job
from ..services.native_workspace_launcher import launch_workspace_window, launch_workspace_window_auto
from ..services.network_settings import load_network_settings, save_network_settings


blueprint = Blueprint("pages", __name__)


_ABOUT_CATEGORY_REFERENCE_GROUPS = (
    {
        "id": "infraestrutura",
        "title": "Infraestrutura e acabamento",
        "summary": "Tipologias que organizam instalações, acabamento e manutenção predial com leitura rápida no catálogo.",
        "accent": "#38bdf8",
        "items": (
            {"key": "material-eletrico", "usage": "Painéis, filtros e listagens de itens energizados, cabeamento e componentes elétricos."},
            {"key": "material-hidraulico", "usage": "Tubulações, conexões e peças de manutenção hidráulica seguem a mesma assinatura azul técnica."},
            {"key": "mat-pintura-drywall", "usage": "Tintas, massas e acabamentos ficam agrupados sem depender de leitura textual longa."},
            {"key": "material-construcao", "usage": "Materiais estruturais e de obra civil aparecem com identidade própria em telas e relatórios."},
        ),
    },
    {
        "id": "operacao",
        "title": "Operação, ferramentas e proteção",
        "summary": "Faixa usada para o que tem leitura mais operacional, patrimonial ou de segurança no dia a dia.",
        "accent": "#60a5fa",
        "items": (
            {"key": "ferramentas", "usage": "Ferramentas manuais e apoio técnico usam a faixa central da custódia e dos filtros operacionais."},
            {"key": "equipamento", "usage": "Equipamentos permanentes e itens eletrificados mantêm contraste próprio em documentos e painéis."},
            {"key": "material-ep", "usage": "Materiais de proteção individual preservam uma leitura de segurança sem conflitar com ferramentas."},
        ),
    },
    {
        "id": "apoio",
        "title": "Apoio, limpeza e contingência",
        "summary": "Categorias de apoio operacional e a faixa de contingência para itens ainda não classificados de forma definitiva.",
        "accent": "#34d399",
        "items": (
            {"key": "materiais-limpeza", "usage": "Limpeza operacional e consumo recorrente aparecem com identificação uniforme em todo o sistema."},
            {"key": "material-piscina", "usage": "Tratamento e operação de piscina ficam isolados sem contaminar outras leituras de manutenção."},
            {"key": "material-uso-geral", "usage": "Itens transversais de apoio usam uma assinatura distinta para não virar categoria genérica invisível."},
            {"key": "sem-categoria", "usage": "Faixa transitória para itens que ainda exigem saneamento de classificação antes de entrar no fluxo oficial."},
        ),
    },
)

_ABOUT_CATEGORY_REFERENCE_FLOW = (
    {
        "step": "01",
        "icon": "bi-tags",
        "title": "Catalogar a tipologia",
        "text": "O item nasce com categoria canônica, nome consistente, ícone e cor oficial definidos pelo catálogo central.",
    },
    {
        "step": "02",
        "icon": "bi-palette2",
        "title": "Propagar a identidade visual",
        "text": "A mesma tipologia é reaproveitada em chips, filtros, cards, classificadores e resumos financeiros sem criar versões paralelas.",
    },
    {
        "step": "03",
        "icon": "bi-grid-1x2-fill",
        "title": "Aplicar nos painéis certos",
        "text": "No dashboard ficam só os blocos operacionais. A explicação detalhada da taxonomia sai do fluxo principal e vai para o Sobre.",
    },
    {
        "step": "04",
        "icon": "bi-file-earmark-bar-graph",
        "title": "Ler e decidir sem ambiguidade",
        "text": "Relatórios, financeiro e documentação passam a ler a mesma taxonomia, reduzindo ruído visual e divergência de interpretação.",
    },
)

_ABOUT_CATEGORY_REFERENCE_SURFACES = (
    {
        "icon": "bi-card-checklist",
        "title": "Cadastro do item",
        "text": "É onde a tipologia entra oficialmente e evita descrições improvisadas ou filtros quebrados no restante do produto.",
    },
    {
        "icon": "bi-funnel",
        "title": "Filtros e busca",
        "text": "Os chips de categoria e os filtros de classificação dependem desse catálogo para manter leitura coerente na operação.",
    },
    {
        "icon": "bi-columns-gap",
        "title": "Painéis e cards",
        "text": "Dashboard, laboratórios visuais e cards de apoio devem usar a mesma assinatura, mas só quando isso ajuda a decisão operacional.",
    },
    {
        "icon": "bi-cash-stack",
        "title": "Financeiro e relatórios",
        "text": "KPIs, totais por categoria, planilhas e documentos precisam preservar a mesma semântica visual e textual.",
    },
)

_ABOUT_CATEGORY_REFERENCE_RULES = (
    {
        "title": "Nome canônico primeiro",
        "text": "Cada tipologia oficial tem nome, ícone e cor padronizados. O produto não deve reinventar isso em cada tela.",
    },
    {
        "title": "Mesma paleta em superfícies compartilhadas",
        "text": "Cadastro, filtros, dashboards, financeiro e relatórios devem repetir a mesma cor para a mesma categoria.",
    },
    {
        "title": "Sem categoria é contingência, não destino final",
        "text": "A faixa cinza existe para saneamento operacional e não deve virar categoria definitiva do catálogo saudável.",
    },
    {
        "title": "Documentação separada do fluxo diário",
        "text": "O dashboard fica com leitura operacional enxuta; a explicação completa da taxonomia e das regras vive no Sobre em aba própria.",
    },
)

_ABOUT_DOCUMENT_GUIDE_STEPS = (
    {
        "step": "01",
        "icon": "bi-search",
        "title": "Localize o item e escolha o modo",
        "text": "Busque o item primeiro. Se ele ainda nao existir, crie o item novo na mesma rotina e so depois complete o documento.",
    },
    {
        "step": "02",
        "icon": "bi-receipt-cutoff",
        "title": "Preencha so o que comprova a compra",
        "text": "NF usa numero, datas e fornecedor. Cupom usa comprovacao simples sem chave. Sem NF ou cupom usa referencia interna e observacao.",
    },
    {
        "step": "03",
        "icon": "bi-kanban",
        "title": "Acompanhe pelas abas operacionais",
        "text": "Depois de salvar, o documento segue para Processaveis, Erros ou Historico, sem abrir uma aba separada so para pendencias.",
    },
)

_ABOUT_DOCUMENT_GUIDE_MODES = (
    {
        "icon": "bi-file-earmark-text",
        "title": "Lancar com NF",
        "badge": "Comprovacao fiscal completa",
        "summary": "Use quando a compra ja tem nota fiscal. Se existir chave de acesso, ela entra no mesmo lancamento.",
        "items": (
            "Numero da NF",
            "Datas de emissao e recebimento",
            "Fornecedor e CNPJ",
            "Chave de acesso, se houver",
        ),
    },
    {
        "icon": "bi-receipt",
        "title": "Lancar com cupom",
        "badge": "Comprovacao fiscal simples",
        "summary": "Use para cupom ou comprovante simples de balcao, sem exigir chave de acesso.",
        "items": (
            "Numero do cupom",
            "Datas",
            "Fornecedor ou CNPJ da loja",
            "Itens e valores",
        ),
    },
    {
        "icon": "bi-journal-minus",
        "title": "Lancar sem NF ou cupom",
        "badge": "Sem comprovacao fiscal",
        "summary": "Use quando ainda nao existe comprovante formal. O registro continua rastreavel, mas com status compativel com ausencia de comprovacao fiscal.",
        "items": (
            "Referencia interna compartilhada",
            "Valor e itens",
            "Observacao financeira",
            "Origem do valor",
        ),
    },
)

_ABOUT_DOCUMENT_GUIDE_RULES = (
    {
        "title": "NF e o fluxo mais completo",
        "text": "Quando houver nota fiscal, prefira esse modo para manter o vinculo documental mais forte desde o cadastro.",
    },
    {
        "title": "Cupom nao usa chave de acesso",
        "text": "Cupom serve para compra simples com comprovacao direta, sem abrir um fluxo pesado de nota fiscal.",
    },
    {
        "title": "Sem NF ou cupom usa o modo manual",
        "text": "Quando nao houver comprovacao fiscal, use o lancamento sem NF ou cupom. O sistema continua registrando a compra sem inventar numero fiscal.",
    },
    {
        "title": "A triagem continua nas abas",
        "text": "Depois da gravacao, o acompanhamento segue em Processaveis, Erros e Historico. A explicacao saiu da tela pratica, nao o controle operacional.",
    },
)


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


def _build_about_category_reference() -> dict[str, object]:
    default_rows_by_key = {row.key: row for row in DEFAULT_INVENTORY_CATEGORIES}
    visual_catalog = category_catalog_service.list_visual_catalog(include_inactive=True)
    visuals_by_key = {str(row.get("key") or ""): row for row in visual_catalog}

    groups: list[dict[str, object]] = []
    total_categories = 0

    for group in _ABOUT_CATEGORY_REFERENCE_GROUPS:
        group_items: list[dict[str, object]] = []
        for index, item_meta in enumerate(group["items"]):
            key = str(item_meta["key"])
            default_row = default_rows_by_key.get(key)
            if default_row is not None:
                visual = visuals_by_key.get(key) or category_catalog_service.get_visual(default_row.nome, fallback_index=index)
                description = default_row.descricao
            else:
                visual = visuals_by_key.get(key) or category_catalog_service.get_visual("Sem categoria", fallback_index=index)
                description = "Faixa transitória para itens que ainda aguardam classificação canônica no catálogo oficial."

            group_items.append(
                {
                    "key": key,
                    "label": visual.get("label") or (default_row.nome if default_row is not None else "Sem categoria"),
                    "icon": visual.get("icon") or "📁",
                    "color": visual.get("color") or "#94a3b8",
                    "soft": visual.get("soft") or visual.get("soft_strong") or "rgba(148, 163, 184, 0.18)",
                    "description": description,
                    "usage": item_meta["usage"],
                }
            )

        total_categories += len(group_items)
        groups.append(
            {
                "id": group["id"],
                "title": group["title"],
                "summary": group["summary"],
                "accent": group["accent"],
                "items": group_items,
                "count": len(group_items),
            }
        )

    for group in groups:
        count = int(group["count"] or 0)
        group["share_pct"] = round((count / total_categories) * 100, 1) if total_categories else 0.0

    return {
        "catalog": visual_catalog,
        "groups": groups,
        "flow": list(_ABOUT_CATEGORY_REFERENCE_FLOW),
        "surfaces": list(_ABOUT_CATEGORY_REFERENCE_SURFACES),
        "rules": list(_ABOUT_CATEGORY_REFERENCE_RULES),
        "total_categories": total_categories,
        "group_count": len(groups),
        "surface_count": len(_ABOUT_CATEGORY_REFERENCE_SURFACES),
        "rule_count": len(_ABOUT_CATEGORY_REFERENCE_RULES),
    }


def _build_about_document_guide() -> dict[str, object]:
    return {
        "steps": list(_ABOUT_DOCUMENT_GUIDE_STEPS),
        "modes": list(_ABOUT_DOCUMENT_GUIDE_MODES),
        "rules": list(_ABOUT_DOCUMENT_GUIDE_RULES),
    }


def _build_about_category_reference_fallback() -> dict[str, object]:
    groups: list[dict[str, object]] = []
    total_categories = 0

    for group in _ABOUT_CATEGORY_REFERENCE_GROUPS:
        group_items: list[dict[str, object]] = []
        for item_meta in group["items"]:
            key = str(item_meta["key"])
            label = key.replace("-", " ").strip().title() or "Sem categoria"
            group_items.append(
                {
                    "key": key,
                    "label": label,
                    "icon": "🏷️",
                    "color": group["accent"],
                    "soft": "rgba(148, 163, 184, 0.18)",
                    "description": "Referencia visual carregada em modo reduzido.",
                    "usage": item_meta["usage"],
                }
            )

        total_categories += len(group_items)
        groups.append(
            {
                "id": group["id"],
                "title": group["title"],
                "summary": group["summary"],
                "accent": group["accent"],
                "items": group_items,
                "count": len(group_items),
            }
        )

    for group in groups:
        count = int(group["count"] or 0)
        group["share_pct"] = round((count / total_categories) * 100, 1) if total_categories else 0.0

    return {
        "catalog": [],
        "groups": groups,
        "flow": list(_ABOUT_CATEGORY_REFERENCE_FLOW),
        "surfaces": list(_ABOUT_CATEGORY_REFERENCE_SURFACES),
        "rules": list(_ABOUT_CATEGORY_REFERENCE_RULES),
        "total_categories": total_categories,
        "group_count": len(groups),
        "surface_count": len(_ABOUT_CATEGORY_REFERENCE_SURFACES),
        "rule_count": len(_ABOUT_CATEGORY_REFERENCE_RULES),
        "fallback_mode": True,
    }


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


def _workspace_slot_request_mode(raw_value: object) -> tuple[bool, int | None]:
    normalized = str(raw_value or "").strip().lower()
    if not normalized or normalized == "auto":
        return True, None
    return False, _normalize_workspace_slot(raw_value)


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
    if not bool(current_app.config.get("FEATURE_WORKSPACE_WINDOWS_ENABLED", False)):
        return jsonify({
            "success": False,
            "code": "workspace-windows-disabled",
            "message": "As janelas auxiliares estao desativadas nesta instalacao.",
        }), 404

    payload = request.get_json(silent=True)
    request_data = payload if isinstance(payload, dict) else request.form

    try:
        token = create_workspace_window_token(current_user)
        target_url = _build_workspace_window_url(str((request_data or {}).get("path") or ""), token)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    title = str((request_data or {}).get("title") or "").strip() or current_app.config.get("SYSTEM_NAME", "GALINT")
    auto_mode, slot = _workspace_slot_request_mode((request_data or {}).get("slot"))
    owner_key = getattr(current_user, "matricula", None)
    if auto_mode:
        result = launch_workspace_window_auto(target_url, title[:120], owner_key=owner_key)
    else:
        result = launch_workspace_window(target_url, title[:120], slot=slot, owner_key=owner_key)

    if result.get("success"):
        status_code = 200
    elif result.get("code") in {"slot-limit-reached", "slot-occupied"}:
        status_code = 409
    else:
        status_code = 503
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
    try:
        about_category_reference = _build_about_category_reference()
    except Exception:
        current_app.logger.exception("Falha ao montar a referencia visual do Sobre; usando fallback reduzido.")
        about_category_reference = _build_about_category_reference_fallback()

    try:
        about_document_guide = _build_about_document_guide()
    except Exception:
        current_app.logger.exception("Falha ao montar o guia documental do Sobre; usando fallback reduzido.")
        about_document_guide = {
            "steps": list(_ABOUT_DOCUMENT_GUIDE_STEPS),
            "modes": list(_ABOUT_DOCUMENT_GUIDE_MODES),
            "rules": list(_ABOUT_DOCUMENT_GUIDE_RULES),
        }

    return render_template(
        "sobre.html",
        kit_doc_html=kit_doc_html,
        about_category_reference=about_category_reference,
        about_document_guide=about_document_guide,
        category_visual_catalog=about_category_reference.get("catalog") or [],
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
