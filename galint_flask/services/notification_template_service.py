"""Gerencia modelos editaveis para notificacoes operacionais."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

from flask import current_app, has_app_context
from jinja2 import Template


class NotificationTemplateService:
    """Armazena e renderiza modelos de notificacao de custodia."""

    STORAGE_FILENAME = "notification_templates.json"
    TEMPLATE_FIELDS = (
        "user_template",
        "supervisor_template",
        "supervisor_batch_template",
    )

    DEFAULT_MODELS: list[dict[str, str]] = [
        {
            "id": "custody-command",
            "name": "Comando de Custodia",
            "description": "Tom direto, foco em responsabilidade e registro operacional.",
            "user_template": """🔐 <b>CUSTODIA PERMANENTE CONFIRMADA</b>\n\n{{ category_emoji }} <b>ITEM:</b> {{ item_name }}\n👤 <b>RESPONSAVEL:</b> {{ employee_name }}\n🪪 <b>MATRICULA:</b> {{ employee_id }}\n📦 <b>QUANTIDADE:</b> {{ quantity_display }}\n🏷️ <b>CATEGORIA:</b> {{ category }}\n📍 <b>LOCAL/USO:</b> {{ destination_display }}\n🗓️ <b>DATA DO REGISTRO:</b> {{ assigned_at }}\n{% if lot %}\n🧾 <b>LOTE:</b> {{ lot }}\n{% endif %}\n🛡️ <b>RESPONSABILIDADE ATIVA</b>\n{{ responsibility_section }}\n\n{% if stock_impact_section %}📊 <b>CONTROLE DE ESTOQUE</b>\n{{ stock_impact_section }}\n\n{% endif %}📎 <i>Registro automatico de custodia permanente</i>""",
            "supervisor_template": """🛰️ <b>CUSTODIA PERMANENTE LANcADA</b>\n\n{{ category_emoji }} <b>{{ item_name }}</b>\n👤 <b>Colaborador:</b> {{ employee_name }} (Mat. {{ employee_id }})\n📦 <b>Quantidade:</b> {{ quantity_display }}\n🏷️ <b>Categoria:</b> {{ category }}\n{% if lot %}🧾 <b>Lote:</b> {{ lot }}\n{% endif %}📍 <b>Destino informado:</b> {{ destination_display }}\n🗓️ <b>Registro:</b> {{ assigned_at }}\n\n📌 <b>Resumo de gestao</b>\n{{ supervisor_summary_section }}\n\n{% if reference_section %}🔎 <b>Referencia operacional</b>\n{{ reference_section }}\n\n{% endif %}{% if stock_impact_section %}📊 <b>Impacto no estoque</b>\n{{ stock_impact_section }}\n\n{% endif %}{{ footer_signature }}""",
            "supervisor_batch_template": """🛰️ <b>LOTE DE CUSTODIAS PERMANENTES REGISTRADO</b>\n\n📦 <b>{{ batch_title }}</b>\n👥 <b>Colaboradores:</b> {{ total_people }}\n🧾 <b>Atribuicoes:</b> {{ total_assignments }}\n📊 <b>Volume total:</b> {{ total_quantity_display }}\n🗓️ <b>Registro base:</b> {{ assigned_at }}\n\n📋 <b>Mapa das atribuicoes</b>\n{{ assignment_list }}\n\n{% if stock_impact_section %}📊 <b>Impacto consolidado</b>\n{{ stock_impact_section }}\n\n{% endif %}{{ footer_signature }}""",
        },
        {
            "id": "custody-radar",
            "name": "Radar de Patrimonio",
            "description": "Modelo mais analitico, com leitura rapida para lideranca.",
            "user_template": """🧰 <b>PATRIMONIO EM SUA RESPONSABILIDADE</b>\n\n{{ category_emoji }} <b>{{ item_name }}</b> entrou em custodia permanente.\n👤 <b>Colaborador:</b> {{ employee_name }}\n🪪 <b>Matricula:</b> {{ employee_id }}\n📦 <b>Quantidade:</b> {{ quantity_display }}\n📍 <b>Aplicacao:</b> {{ destination_display }}\n🗓️ <b>Momento do registro:</b> {{ assigned_at }}\n\n✅ <b>Checklist essencial</b>\n{{ responsibility_section }}\n\n{% if stock_impact_section %}📉 <b>Leitura de estoque</b>\n{{ stock_impact_section }}\n\n{% endif %}{{ footer_signature }}""",
            "supervisor_template": """📡 <b>RADAR DE CUSTODIA ATUALIZADO</b>\n\n{{ category_emoji }} <b>{{ item_name }}</b>\n👤 {{ employee_name }} ({{ employee_id }})\n📦 {{ quantity_display }} | 🏷️ {{ category }}\n📍 {{ destination_display }}\n🗓️ {{ assigned_at }}\n\n🧭 <b>Pontos de controle</b>\n{{ supervisor_summary_section }}\n\n{% if stock_impact_section %}📊 <b>Saldo apos atribuicao</b>\n{{ stock_impact_section }}\n\n{% endif %}{{ footer_signature }}""",
            "supervisor_batch_template": """📡 <b>RADAR DE CUSTODIA EM LOTE</b>\n\n📦 <b>{{ batch_title }}</b>\n👥 {{ total_people }} colaborador(es)\n🧾 {{ total_assignments }} atribuicao(oes)\n📊 {{ total_quantity_display }}\n\n🗂️ <b>Distribuicao registrada</b>\n{{ assignment_list }}\n\n{% if stock_impact_section %}📊 <b>Saldo consolidado</b>\n{{ stock_impact_section }}\n\n{% endif %}{{ footer_signature }}""",
        },
        {
            "id": "custody-field-mission",
            "name": "Missao em Campo",
            "description": "Visual mais energico para operacao e equipes externas.",
            "user_template": """🚧 <b>MISSAO DE CAMPO ATIVADA</b>\n\n{{ category_emoji }} <b>{{ item_name }}</b> foi vinculado em custodia permanente para voce.\n👤 <b>Nome:</b> {{ employee_name }}\n🪪 <b>Matricula:</b> {{ employee_id }}\n📦 <b>Carga registrada:</b> {{ quantity_display }}\n📍 <b>Frente/uso:</b> {{ destination_display }}\n🗓️ <b>Registro:</b> {{ assigned_at }}\n\n🛠️ <b>Conduta esperada</b>\n{{ responsibility_section }}\n\n{% if reference_section %}🧭 <b>Referencia do movimento</b>\n{{ reference_section }}\n\n{% endif %}{{ footer_signature }}""",
            "supervisor_template": """🚨 <b>MISSAO DE CAMPO REGISTRADA</b>\n\n{{ category_emoji }} <b>{{ item_name }}</b>\n👤 <b>Responsavel em campo:</b> {{ employee_name }} ({{ employee_id }})\n📦 <b>Quantidade:</b> {{ quantity_display }}\n📍 <b>Uso informado:</b> {{ destination_display }}\n🗓️ <b>Horario:</b> {{ assigned_at }}\n\n🧾 <b>Leitura rapida</b>\n{{ supervisor_summary_section }}\n\n{% if stock_impact_section %}📉 <b>Reflexo no estoque</b>\n{{ stock_impact_section }}\n\n{% endif %}{{ footer_signature }}""",
            "supervisor_batch_template": """🚨 <b>MISSAO DE CAMPO EM LOTE</b>\n\n📦 <b>{{ batch_title }}</b>\n👥 <b>Equipe coberta:</b> {{ total_people }}\n🧾 <b>Total de registros:</b> {{ total_assignments }}\n📊 <b>Volume movimentado:</b> {{ total_quantity_display }}\n\n🗂️ <b>Escala de responsabilidade</b>\n{{ assignment_list }}\n\n{{ footer_signature }}""",
        },
        {
            "id": "custody-technical-guard",
            "name": "Guarda Tecnica",
            "description": "Mais formal, ideal para materiais sensiveis e auditoria.",
            "user_template": """🧪 <b>GUARDA TECNICA REGISTRADA</b>\n\n{{ category_emoji }} <b>{{ item_name }}</b>\n👤 <b>Custodiante:</b> {{ employee_name }}\n🪪 <b>Matricula:</b> {{ employee_id }}\n🏷️ <b>Categoria:</b> {{ category }}\n📦 <b>Quantidade:</b> {{ quantity_display }}\n{% if lot %}🧾 <b>Lote:</b> {{ lot }}\n{% endif %}🗓️ <b>Data/hora:</b> {{ assigned_at }}\n\n🔐 <b>Orientacoes de guarda</b>\n{{ responsibility_section }}\n\n{% if stock_impact_section %}📊 <b>Registro de saldo</b>\n{{ stock_impact_section }}\n\n{% endif %}{{ footer_signature }}""",
            "supervisor_template": """🧪 <b>GUARDA TECNICA ATRIBUIDA</b>\n\n{{ category_emoji }} <b>{{ item_name }}</b>\n👤 <b>Custodiante:</b> {{ employee_name }} ({{ employee_id }})\n📦 <b>Quantidade:</b> {{ quantity_display }}\n📍 <b>Destino:</b> {{ destination_display }}\n🗓️ <b>Registro:</b> {{ assigned_at }}\n\n📚 <b>Notas de auditoria</b>\n{{ supervisor_summary_section }}\n\n{% if stock_impact_section %}📉 <b>Baixa refletida</b>\n{{ stock_impact_section }}\n\n{% endif %}{{ footer_signature }}""",
            "supervisor_batch_template": """🧪 <b>GUARDA TECNICA CONSOLIDADA</b>\n\n📦 <b>{{ batch_title }}</b>\n👥 <b>Custodiantes:</b> {{ total_people }}\n🧾 <b>Registros:</b> {{ total_assignments }}\n📊 <b>Total atribuido:</b> {{ total_quantity_display }}\n\n📚 <b>Mapa de auditoria</b>\n{{ assignment_list }}\n\n{% if stock_impact_section %}📉 <b>Reflexo consolidado</b>\n{{ stock_impact_section }}\n\n{% endif %}{{ footer_signature }}""",
        },
        {
            "id": "custody-operations-bridge",
            "name": "Ponte Operacional",
            "description": "Modelo conciliando operacao, estoque e supervisao.",
            "user_template": """🌉 <b>PONTE OPERACIONAL DE CUSTODIA</b>\n\n{{ category_emoji }} <b>{{ item_name }}</b> agora segue em custodia permanente com voce.\n👤 <b>Colaborador:</b> {{ employee_name }} ({{ employee_id }})\n📦 <b>Quantidade:</b> {{ quantity_display }}\n📍 <b>Local informado:</b> {{ destination_display }}\n🗓️ <b>Registro:</b> {{ assigned_at }}\n\n🧩 <b>Pontos que exigem sua atencao</b>\n{{ responsibility_section }}\n\n{% if reference_section %}🧾 <b>Vinculo operacional</b>\n{{ reference_section }}\n\n{% endif %}{% if stock_impact_section %}📊 <b>Disponibilidade apos baixa</b>\n{{ stock_impact_section }}\n\n{% endif %}{{ footer_signature }}""",
            "supervisor_template": """🌉 <b>PONTE OPERACIONAL ATUALIZADA</b>\n\n{{ category_emoji }} <b>{{ item_name }}</b>\n👤 <b>Responsavel:</b> {{ employee_name }} ({{ employee_id }})\n📦 <b>Quantidade:</b> {{ quantity_display }}\n🏷️ <b>Categoria:</b> {{ category }}\n📍 <b>Uso:</b> {{ destination_display }}\n🗓️ <b>Registro:</b> {{ assigned_at }}\n\n🧠 <b>Leitura gerencial</b>\n{{ supervisor_summary_section }}\n\n{% if stock_impact_section %}📉 <b>Saldo remanescente</b>\n{{ stock_impact_section }}\n\n{% endif %}{{ footer_signature }}""",
            "supervisor_batch_template": """🌉 <b>PONTE OPERACIONAL EM ESCALA</b>\n\n📦 <b>{{ batch_title }}</b>\n👥 <b>Colaboradores cobertos:</b> {{ total_people }}\n🧾 <b>Atribuicoes registradas:</b> {{ total_assignments }}\n📊 <b>Quantidade total:</b> {{ total_quantity_display }}\n\n🗂️ <b>Distribuicao consolidada</b>\n{{ assignment_list }}\n\n{% if stock_impact_section %}📉 <b>Saldo consolidado</b>\n{{ stock_impact_section }}\n\n{% endif %}{{ footer_signature }}""",
        },
    ]

    @classmethod
    def _storage_path(cls) -> Path:
        if has_app_context():
            return Path(current_app.instance_path) / cls.STORAGE_FILENAME
        return Path("instance") / cls.STORAGE_FILENAME

    @classmethod
    def _default_config(cls) -> dict[str, Any]:
        return {
            "version": 1,
            "rotation_enabled": True,
            "models": deepcopy(cls.DEFAULT_MODELS),
        }

    @classmethod
    def _merge_with_defaults(cls, payload: dict[str, Any] | None) -> dict[str, Any]:
        merged = cls._default_config()
        if not isinstance(payload, dict):
            return merged

        merged["rotation_enabled"] = bool(payload.get("rotation_enabled", True))
        saved_models = payload.get("models") if isinstance(payload.get("models"), list) else []
        saved_by_id = {
            str(model.get("id") or "").strip(): model
            for model in saved_models
            if isinstance(model, dict) and str(model.get("id") or "").strip()
        }

        resolved_models: list[dict[str, str]] = []
        for default_model in cls.DEFAULT_MODELS:
            model_id = str(default_model["id"])
            current = deepcopy(default_model)
            saved = saved_by_id.get(model_id, {})
            if isinstance(saved, dict):
                for field in ("name", "description", *cls.TEMPLATE_FIELDS):
                    value = saved.get(field)
                    if isinstance(value, str) and value.strip():
                        current[field] = value
            resolved_models.append(current)

        merged["models"] = resolved_models
        return merged

    @classmethod
    def load_config(cls) -> dict[str, Any]:
        path = cls._storage_path()
        if not path.exists():
            return cls._default_config()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls._default_config()
        return cls._merge_with_defaults(payload)

    @classmethod
    def save_config(cls, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = cls._merge_with_defaults(payload)
        cls._validate_models(normalized.get("models") or [])
        path = cls._storage_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return normalized

    @classmethod
    def list_models(cls) -> list[dict[str, str]]:
        return list(cls.load_config().get("models") or [])

    @classmethod
    def get_model(cls, model_id: str | None) -> dict[str, str] | None:
        model_id_normalized = str(model_id or "").strip()
        if not model_id_normalized:
            return None
        for model in cls.list_models():
            if model.get("id") == model_id_normalized:
                return model
        return None

    @classmethod
    def update_model(cls, model_id: str, updates: dict[str, str]) -> dict[str, Any]:
        config = cls.load_config()
        model_id_normalized = str(model_id or "").strip()
        if not model_id_normalized:
            raise ValueError("Modelo de notificacao invalido.")

        changed = False
        for model in config["models"]:
            if model.get("id") != model_id_normalized:
                continue
            for field in ("name", "description", *cls.TEMPLATE_FIELDS):
                if field not in updates:
                    continue
                model[field] = str(updates.get(field) or "").strip()
            changed = True
            break

        if not changed:
            raise ValueError("Modelo de notificacao nao encontrado.")
        return cls.save_config(config)

    @classmethod
    def resolve_monthly_model(cls, reference_date: date | None = None) -> dict[str, str]:
        models = cls.list_models()
        if not models:
            raise ValueError("Nenhum modelo de notificacao disponivel.")
        current = reference_date or date.today()
        index = (current.month - 1) % len(models)
        return models[index]

    @classmethod
    def resolve_model(cls, model_id: str | None = None, reference_date: date | None = None) -> dict[str, str]:
        if model_id:
            selected = cls.get_model(model_id)
            if selected is not None:
                return selected
        return cls.resolve_monthly_model(reference_date=reference_date)

    @classmethod
    def render(cls, template_kind: str, context: dict[str, Any], *, model_id: str | None = None, reference_date: date | None = None) -> str:
        field_name = cls._resolve_template_field(template_kind)
        model = cls.resolve_model(model_id=model_id, reference_date=reference_date)
        template_source = str(model.get(field_name) or "").strip()
        if not template_source:
            raise ValueError("Modelo selecionado nao possui conteudo para esse tipo de notificacao.")
        merged_context = dict(context or {})
        merged_context.setdefault("rotation_label", model.get("name") or "Modelo mensal")
        merged_context.setdefault("footer_signature", f"📎 <i>Modelo em escala: {merged_context['rotation_label']}</i>")
        return Template(template_source).render(**merged_context).strip()

    @classmethod
    def describe_current_rotation(cls, reference_date: date | None = None) -> dict[str, str]:
        current = reference_date or date.today()
        model = cls.resolve_monthly_model(reference_date=current)
        return {
            "month": current.strftime("%m/%Y"),
            "model_id": str(model.get("id") or ""),
            "model_name": str(model.get("name") or "Modelo mensal"),
            "description": str(model.get("description") or ""),
        }

    @classmethod
    def sample_context(cls) -> dict[str, str]:
        return {
            "category_emoji": "🔧",
            "item_name": "Martelete SDS Plus 800W",
            "employee_name": "Carlos Silva",
            "employee_id": "20241",
            "quantity_display": "1 unidade",
            "category": "Ferramentas",
            "lot": "FT-2026-041",
            "destination_display": "Obra Jardim Aurora",
            "assigned_at": "08/04/2026 14:32",
            "responsibility_section": "• Este item permanece sob sua guarda por prazo indeterminado\n• Mantenha a ferramenta em local seguro\n• Comunique imediatamente dano, perda, quebra ou troca de frente\n• Em caso de devolucao ou transferencia, a regularizacao deve ser registrada",
            "supervisor_summary_section": "• Custodia permanente atribuida ao colaborador\n• Responsavel ciente e item vinculado ao fluxo operacional\n• Auditoria deve acompanhar saldo e devolucao futura, se houver",
            "reference_section": "• Documento: retirada interna\n• Vinculo: obra ativa e colaborador identificado",
            "stock_impact_section": "• Saldo anterior: 4 unidades\n• Nova disponibilidade: 3 unidades",
            "batch_title": "Lote de marteletes e acessorios",
            "total_people": "3",
            "total_assignments": "4",
            "total_quantity_display": "4 unidades",
            "assignment_list": "1. Carlos Silva (20241) - 1 unidade\n2. Diego Nunes (10492) - 1 unidade\n3. Elaine Rocha (30411) - 2 unidades",
        }

    @classmethod
    def _resolve_template_field(cls, template_kind: str) -> str:
        normalized = str(template_kind or "").strip().lower()
        mapping = {
            "user": "user_template",
            "supervisor": "supervisor_template",
            "supervisor_batch": "supervisor_batch_template",
        }
        field_name = mapping.get(normalized)
        if field_name is None:
            raise ValueError("Tipo de template de notificacao invalido.")
        return field_name

    @classmethod
    def _validate_models(cls, models: list[dict[str, Any]]) -> None:
        if not models:
            raise ValueError("Nenhum modelo de notificacao foi informado.")
        for model in models:
            model_name = str(model.get("name") or "").strip() or "Modelo sem nome"
            if not str(model.get("name") or "").strip():
                raise ValueError("Todos os modelos precisam de um nome.")
            for field in cls.TEMPLATE_FIELDS:
                template_source = str(model.get(field) or "").strip()
                if not template_source:
                    raise ValueError(f"O campo {field} do modelo {model_name} nao pode ficar vazio.")
                try:
                    Template(template_source)
                except Exception as exc:
                    raise ValueError(f"Template invalido em {model_name} ({field}): {exc}") from exc