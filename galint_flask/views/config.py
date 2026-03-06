"""Views para configuração da empresa e relatórios."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from ..services.config_service import ConfigService


bp = Blueprint("config", __name__, url_prefix="/configuracoes")


@bp.route("/empresa", methods=["GET", "POST"])
@login_required
def empresa():
    """Configuração da empresa."""
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores podem alterar configurações.", "danger")
        return redirect(url_for("main.index"))
    
    empresa_config = ConfigService.get_empresa_config()
    
    if request.method == "POST":
        try:
            # Coletar dados do formulário
            data = {
                "nome_empresa": request.form.get("nome_empresa", "").strip(),
                "nome_fantasia": request.form.get("nome_fantasia", "").strip(),
                "cnpj": request.form.get("cnpj", "").strip(),
                "endereco_rua": request.form.get("endereco_rua", "").strip(),
                "endereco_numero": request.form.get("endereco_numero", "").strip(),
                "endereco_complemento": request.form.get("endereco_complemento", "").strip(),
                "endereco_bairro": request.form.get("endereco_bairro", "").strip(),
                "endereco_cidade": request.form.get("endereco_cidade", "").strip(),
                "endereco_estado": request.form.get("endereco_estado", "").strip(),
                "endereco_cep": request.form.get("endereco_cep", "").strip(),
                "telefone": request.form.get("telefone", "").strip(),
                "telefone_secundario": request.form.get("telefone_secundario", "").strip(),
                "email": request.form.get("email", "").strip(),
                "site": request.form.get("site", "").strip(),
            }
            
            # Validação básica
            if not data["nome_empresa"]:
                flash("Nome da empresa é obrigatório!", "danger")
                return render_template("config/empresa.html", empresa_config=empresa_config)
            
            # Upload de logo (se houver)
            if "logo" in request.files:
                file = request.files["logo"]
                if file and file.filename:
                    try:
                        logo_path = ConfigService.upload_logo(file)
                        data["logo_path"] = logo_path
                        flash("Logo enviado com sucesso!", "success")
                    except ValueError as e:
                        flash(str(e), "danger")
            
            # Atualizar configuração
            ConfigService.update_empresa_config(data)
            flash("Configurações da empresa atualizadas com sucesso!", "success")
            
            return redirect(url_for("config.empresa"))
            
        except Exception as e:
            flash(f"Erro ao atualizar configurações: {str(e)}", "danger")
    
    return render_template("config/empresa.html", empresa_config=empresa_config)


@bp.route("/relatorios", methods=["GET", "POST"])
@login_required
def relatorios():
    """Configuração de relatórios."""
    if not current_user.is_admin:
        flash("Acesso negado. Apenas administradores podem alterar configurações.", "danger")
        return redirect(url_for("main.index"))
    
    relatorio_config = ConfigService.get_relatorio_config()
    
    if request.method == "POST":
        try:
            # Coletar dados do formulário
            data = {
                "cabecalho_template": request.form.get("cabecalho_template", ""),
                "cabecalho_altura_mm": int(request.form.get("cabecalho_altura_mm", 40)),
                "cabecalho_mostrar_logo": request.form.get("cabecalho_mostrar_logo") == "on",
                "cabecalho_cor_texto": request.form.get("cabecalho_cor_texto", "#000000"),
                "cabecalho_fonte": request.form.get("cabecalho_fonte", "Helvetica"),
                "cabecalho_tamanho_fonte": int(request.form.get("cabecalho_tamanho_fonte", 10)),
                
                "rodape_template": request.form.get("rodape_template", ""),
                "rodape_altura_mm": int(request.form.get("rodape_altura_mm", 20)),
                "rodape_cor_texto": request.form.get("rodape_cor_texto", "#666666"),
                "rodape_tamanho_fonte": int(request.form.get("rodape_tamanho_fonte", 8)),
                "rodape_mostrar_data": request.form.get("rodape_mostrar_data") == "on",
                "rodape_mostrar_pagina": request.form.get("rodape_mostrar_pagina") == "on",
                
                "cor_primaria": request.form.get("cor_primaria", "#007bff"),
                "cor_secundaria": request.form.get("cor_secundaria", "#6c757d"),
                "fonte_principal": request.form.get("fonte_principal", "Helvetica"),
                "fonte_tabelas": request.form.get("fonte_tabelas", "Courier"),
            }
            
            # Atualizar configuração
            ConfigService.update_relatorio_config(data)
            flash("Configurações de relatórios atualizadas com sucesso!", "success")
            
            return redirect(url_for("config.relatorios"))
            
        except Exception as e:
            flash(f"Erro ao atualizar configurações: {str(e)}", "danger")
    
    return render_template("config/relatorios.html", relatorio_config=relatorio_config)


@bp.route("/preview-cabecalho")
@login_required
def preview_cabecalho():
    """Preview do cabeçalho do relatório."""
    if not current_user.is_admin:
        return jsonify({"error": "Acesso negado"}), 403
    
    try:
        cabecalho = ConfigService.render_cabecalho()
        return jsonify({"cabecalho": cabecalho})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/preview-rodape")
@login_required
def preview_rodape():
    """Preview do rodapé do relatório."""
    if not current_user.is_admin:
        return jsonify({"error": "Acesso negado"}), 403
    
    try:
        rodape = ConfigService.render_rodape(pagina=1)
        return jsonify({"rodape": rodape})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/resetar-templates", methods=["POST"])
@login_required
def resetar_templates():
    """Reseta templates para valores padrão."""
    if not current_user.is_admin:
        return jsonify({"error": "Acesso negado"}), 403
    
    try:
        data = {
            "cabecalho_template": ConfigService.CABECALHO_PADRAO,
            "rodape_template": ConfigService.RODAPE_PADRAO,
        }
        ConfigService.update_relatorio_config(data)
        
        return jsonify({
            "success": True,
            "message": "Templates resetados para valores padrão!"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400
