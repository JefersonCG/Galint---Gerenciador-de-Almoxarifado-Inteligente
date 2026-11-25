"""Configurações: fornecedores e aparência do site.

Em 25/11/2026 o usuário mandou tirar do sistema, por não serem úteis, as páginas Imagens do Sistema,
Empresa, Relatórios, Notificações e Editor de Notificações (além de Atualizações e Painel Mobile, em
outros arquivos). Os dados que elas gravavam continuam no banco e seguem valendo (logo, cabeçalho dos
relatórios, canal das notificações, modelos de mensagem); só as telas de edição saíram.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_login import login_required, current_user

from ..services.config_service import ConfigService
from ..services.finance_service import finance_service
from ..extensions import db
from ..models import EmpresaConfig
from ..services import theme_service


bp = Blueprint("config", __name__, url_prefix="/configuracoes")


@bp.route("/fornecedores", methods=["GET", "POST"])
@login_required
def fornecedores():
    """Cadastro mestre de fornecedores financeiros."""
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores podem alterar configurações.", "danger")
        return redirect(url_for("dashboard.index"))

    supplier_edit = None
    if request.method == "POST":
        try:
            payload = {
                "id": request.form.get("id") or None,
                "razao_social": request.form.get("razao_social", "").strip(),
                "nome_fantasia": request.form.get("nome_fantasia", "").strip(),
                "cnpj": request.form.get("cnpj", "").strip(),
                "inscricao_estadual": request.form.get("inscricao_estadual", "").strip(),
                "endereco_rua": request.form.get("endereco_rua", "").strip(),
                "endereco_numero": request.form.get("endereco_numero", "").strip(),
                "endereco_complemento": request.form.get("endereco_complemento", "").strip(),
                "endereco_bairro": request.form.get("endereco_bairro", "").strip(),
                "endereco_cidade": request.form.get("endereco_cidade", "").strip(),
                "endereco_estado": request.form.get("endereco_estado", "").strip(),
                "endereco_cep": request.form.get("endereco_cep", "").strip(),
                "telefone": request.form.get("telefone", "").strip(),
                "email": request.form.get("email", "").strip(),
                "site": request.form.get("site", "").strip(),
                "situacao_cadastral": request.form.get("situacao_cadastral", "").strip(),
                "observacoes": request.form.get("observacoes", "").strip(),
                "api_origem": request.form.get("api_origem", "").strip(),
                "ativo": request.form.get("ativo") == "on",
            }
            supplier = finance_service.save_supplier(payload)
            flash(f"Fornecedor salvo com sucesso: {supplier.nome_exibicao()}", "success")
            return redirect(url_for("config.fornecedores", supplier_id=supplier.id))
        except Exception as exc:
            db.session.rollback()
            flash(f"Erro ao salvar fornecedor: {exc}", "danger")

    supplier_id = request.args.get("supplier_id", type=int)
    if supplier_id:
        supplier = finance_service.get_supplier(supplier_id)
        supplier_edit = supplier.to_dict() if supplier else None

    return render_template(
        "config/fornecedores.html",
        fornecedores=finance_service.list_suppliers(),
        supplier_edit=supplier_edit,
    )


@bp.get("/api/fornecedores/autocomplete")
@login_required
def fornecedores_autocomplete():
    if not current_user.is_authenticated:
        return jsonify({"success": False, "message": "Não autenticado"}), 401
    term = request.args.get("q", "")
    return jsonify({"success": True, "results": finance_service.search_suppliers(term, limit=12)})


@bp.get("/api/fornecedores/cnpj/<cnpj>")
@login_required
def fornecedores_por_cnpj(cnpj: str):
    if not current_user.is_admin:
        return jsonify({"success": False, "message": "Acesso negado"}), 403
    try:
        existing = finance_service.get_supplier_by_cnpj(cnpj)
        if existing:
            supplier_data = existing.to_dict()
            supplier_data["source"] = "local"
            return jsonify({"success": True, "supplier": supplier_data})
        data = finance_service.fetch_supplier_by_cnpj(cnpj)
        data["source"] = "remote"
        return jsonify({"success": True, "supplier": data})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 400


# --- Aparência (21/11/2026): as cores do site e do app, no molde da skin do Pipocas ----------
def _empresa_config() -> EmpresaConfig | None:
    return EmpresaConfig.query.order_by(EmpresaConfig.id).first()


@bp.get("/aparencia")
@login_required
def aparencia():
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores podem mudar a aparência.", "danger")
        return redirect(url_for("pages.config"))
    colors = theme_service.current(_empresa_config())
    return render_template(
        "config/aparencia.html",
        colors=colors,
        targets=theme_service.TARGETS,
        pasteis=theme_service.PASTEIS,
        solidas=theme_service.SOLIDAS,
        presets=theme_service.preset_cards(colors),
    )


@bp.post("/aparencia")
@login_required
def aparencia_salvar():
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores podem mudar a aparência.", "danger")
        return redirect(url_for("pages.config"))
    config = _empresa_config() or ConfigService.get_empresa_config()  # a página Empresa saiu (25/11/2026)
    try:
        colors = theme_service.save(config, request.form)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("config.aparencia"))
    db.session.commit()
    if colors == theme_service.DEFAULTS:
        flash("Aparência padrão restaurada.", "success")
    else:
        flash("Aparência salva: o site já usa as novas cores, e o app passa a usar ao abrir de novo.", "success")
    return redirect(url_for("config.aparencia"))


@bp.get("/aparencia/previa.json")
@login_required
def aparencia_previa():
    if not current_user.is_admin:
        return jsonify({"error": "Acesso negado"}), 403
    colors = {key: theme_service.normalize(request.args.get(key)) for key in theme_service.DEFAULTS}
    if not all(colors.values()):
        return jsonify({"error": "Informe as três cores em hexadecimal, como #2563eb."}), 400
    return jsonify(theme_service.preview(colors))


@bp.get("/tema.css")
def theme_css():
    """Liberada sem login (só expõe cores). Sem cache, para a aparência salva valer no próximo carregamento."""
    response = make_response(theme_service.stylesheet(_empresa_config()))
    response.headers["Content-Type"] = "text/css; charset=utf-8"
    response.headers["Cache-Control"] = "no-store"
    return response
