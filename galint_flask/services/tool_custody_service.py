"""Serviço para controle de custódia de ferramentas."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from flask import current_app
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import Entrada, Item, RetiradaFerramenta, Saida, Usuario, InventarioEvento
from ..services.inventory import MovimentoPayload, inventory_service
from ..services.item_foto_service import ItemFotoService
from ..utils.time_service import TimeService


class ToolCustodyService:
    """Gerencia custódia de ferramentas por funcionário."""

    _PERMANENT_MARKERS = (
        "responsab",
        "uso no condominio",
        "uso no condomínio",
        "uso no condomin",
        "uso exclusivo",
        "ficou sob",
        "permanente",
    )
    _EMPLOYEE_PHOTO_DIR = ("uploads", "funcionarios")

    @staticmethod
    def _build_employee_initials(nome: str | None) -> str:
        partes = [parte[:1].upper() for parte in (nome or "").split() if parte.strip()]
        if not partes:
            return "FN"
        return "".join(partes[:2])

    @classmethod
    def _employee_photo_folder(cls) -> Path:
        folder = Path(current_app.root_path) / "static"
        for segment in cls._EMPLOYEE_PHOTO_DIR:
            folder /= segment
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @classmethod
    def _employee_photo_candidates(cls, matricula: str) -> list[Path]:
        matricula_segura = secure_filename(matricula or "")
        if not matricula_segura:
            return []

        folder = cls._employee_photo_folder()
        return sorted(folder.glob(f"{matricula_segura}.*"), key=lambda item: item.stat().st_mtime, reverse=True)

    @classmethod
    def get_employee_photo_path(cls, matricula: str) -> str | None:
        candidatos = cls._employee_photo_candidates(matricula)
        if not candidatos:
            return None

        return "/".join([*cls._EMPLOYEE_PHOTO_DIR, candidatos[0].name])

    @classmethod
    def delete_employee_photo(cls, matricula: str) -> bool:
        candidatos = cls._employee_photo_candidates(matricula)
        if not candidatos:
            return False

        removed = False
        for candidato in candidatos:
            try:
                candidato.unlink()
                removed = True
            except OSError:
                current_app.logger.warning("Não foi possível remover foto do funcionário %s", matricula)
        return removed

    @classmethod
    def upload_employee_photo(cls, file: Any, matricula: str) -> str:
        valido, mensagem = ItemFotoService.validar_arquivo(file)
        if not valido:
            raise ValueError(mensagem)

        matricula_segura = secure_filename(matricula or "")
        if not matricula_segura:
            raise ValueError("Matrícula inválida para foto")

        if not getattr(file, "filename", None):
            raise ValueError("Arquivo de foto não informado")

        folder = cls._employee_photo_folder()
        for existente in cls._employee_photo_candidates(matricula_segura):
            try:
                existente.unlink()
            except OSError:
                current_app.logger.warning("Não foi possível substituir foto do funcionário %s", matricula_segura)

        extensao = secure_filename(file.filename).rsplit('.', 1)[1].lower()
        filename = f"{matricula_segura}.{extensao}"
        file_path = folder / filename
        file.save(str(file_path))

        return "/".join([*cls._EMPLOYEE_PHOTO_DIR, filename])

    @classmethod
    def is_permanent_custody(cls, *, tipo_custodia_raw: str | None = None, local_servico: str | None = None, observacao: str | None = None, days_in_use: int = 0) -> bool:
        raw = (tipo_custodia_raw or "").strip().lower()
        if raw == "permanente":
            return True

        texto = f"{local_servico or ''} {observacao or ''}".lower()
        if any(marker in texto for marker in cls._PERMANENT_MARKERS):
            return True

        # Se ficar muito tempo em posse, assume custódia permanente para evitar alerta indevido.
        return days_in_use >= 30

    @classmethod
    def _infer_tipo_custodia(cls, saida: Saida, days_in_use: int) -> str:
        if cls.is_permanent_custody(
            tipo_custodia_raw=getattr(saida, "tipo_custodia", None),
            local_servico=saida.local_servico,
            observacao=saida.observacao,
            days_in_use=days_in_use,
        ):
            return "permanente"
        return "temporaria"

    @staticmethod
    def _normalize_custody_type(value: str | None) -> str:
        raw = (value or "").strip().lower()
        if raw in {"diaria", "diária", "daily", "d"}:
            return "temporaria"
        if raw in {"perm", "p"}:
            return "permanente"
        if raw not in {"temporaria", "permanente"}:
            return "temporaria"
        return raw

    @staticmethod
    def get_all_employees_with_tools() -> list[dict[str, Any]]:
        """Retorna todos os funcionários que possuem ferramentas ativas."""
        # Buscar saídas sem devolução (ferramentas ativas)
        query = (
            db.session.query(
                Usuario.matricula,
                Usuario.nome,
                Usuario.setor,
                Usuario.cargo,
                func.count(Saida.id_saida).label("total_ferramentas"),
                func.min(Saida.data_saida).label("mais_antiga"),
            )
            .join(Saida, Usuario.matricula == Saida.matricula)
            .join(Item, Saida.codigo_item == Item.codigo_item)
            .filter(func.lower(Item.categoria).contains("ferrament"))
            .group_by(Usuario.matricula, Usuario.nome, Usuario.setor, Usuario.cargo)
            .order_by(Usuario.nome)
        )
        
        results = query.all()
        employees = []
        
        for row in results:
            # Verificar se tem ferramentas sem devolução
            active_tools = ToolCustodyService._get_active_tools_for_employee(row.matricula)
            if not active_tools:
                continue
                
            days_oldest = (datetime.utcnow() - row.mais_antiga).days if row.mais_antiga else 0
            
            # Contar alertas apenas em ferramentas temporárias atrasadas.
            alerts = sum(1 for tool in active_tools if tool.get("is_alert", False))
            
            # Separar por tipo de custódia
            tools_temporaria = [t for t in active_tools if t.get("tipo_custodia") == "temporaria"]
            tools_permanente = [t for t in active_tools if t.get("tipo_custodia") == "permanente"]
            
            employees.append({
                "matricula": row.matricula,
                "nome": row.nome,
                "setor": row.setor or "N/D",
                "cargo": row.cargo or "N/D",
                "total_ferramentas": len(active_tools),
                "days_oldest": days_oldest,
                "has_alerts": alerts > 0,
                "alerts_count": alerts,
                "tools": active_tools,
                "has_temporaria": len(tools_temporaria) > 0,
                "has_permanente": len(tools_permanente) > 0,
                "total_temporaria": len(tools_temporaria),
                "total_permanente": len(tools_permanente),
            })
        
        return employees

    @staticmethod
    def get_daily_custody_feed_items() -> list[dict[str, Any]]:
        """Retorna itens de custódia diária ativos para painéis operacionais."""
        employees = ToolCustodyService.get_all_employees_with_tools()
        itens: list[dict[str, Any]] = []

        for employee in employees:
            matricula_full = employee.get("matricula") or ""
            matricula_short = (
                matricula_full[-5:] if isinstance(matricula_full, str) and len(matricula_full) >= 5 else matricula_full
            )

            for tool in employee.get("tools", []):
                if tool.get("tipo_custodia") == "permanente":
                    continue

                data_saida = tool.get("data_saida")
                dias_em_uso = int(tool.get("days_in_use") or 0)

                itens.append(
                    {
                        "id": tool.get("saida_id"),
                        "source": "saida",
                        "codigo": tool.get("codigo_item"),
                        "descricao": tool.get("descricao") or "",
                        "observacao": tool.get("observacao") or "",
                        "foto_path": tool.get("foto_path") or None,
                        "quantidade": tool.get("quantidade") or 0,
                        "usuario": employee.get("nome") or "",
                        "matricula": matricula_short,
                        "matricula_full": matricula_full,
                        "local_servico": tool.get("local_servico") or "Não informado",
                        "data_retirada_iso": TimeService.isoformat_utc(data_saida),
                        "dias_em_uso": dias_em_uso,
                        "atrasada": bool(tool.get("is_alert", False)),
                        "data_prevista_devolucao": None,
                    }
                )

        pares_ja_no_feed = {
            (str(i.get("matricula_full") or ""), str(i.get("codigo") or ""))
            for i in itens
            if i.get("matricula_full") and i.get("codigo")
        }

        retiradas_abertas = (
            db.session.query(RetiradaFerramenta, Item, Usuario)
            .join(Item, RetiradaFerramenta.codigo_item == Item.codigo_item)
            .join(Usuario, RetiradaFerramenta.matricula == Usuario.matricula)
            .filter(
                RetiradaFerramenta.status.in_(["em_uso", "atrasada"]),
                func.lower(Item.categoria).contains("ferrament"),
            )
            .order_by(RetiradaFerramenta.data_retirada.desc())
            .limit(200)
            .all()
        )

        for retirada, item, usuario in retiradas_abertas:
            matricula_full = usuario.matricula or ""
            matricula_short = (
                matricula_full[-5:]
                if isinstance(matricula_full, str) and len(matricula_full) >= 5
                else matricula_full
            )
            key = (str(matricula_full), str(item.codigo_item))
            if key in pares_ja_no_feed:
                continue

            try:
                dias_em_uso = int((datetime.utcnow() - retirada.data_retirada).days)
            except Exception:
                dias_em_uso = 0

            if ToolCustodyService.is_permanent_custody(
                tipo_custodia_raw=None,
                local_servico=getattr(retirada, "local_servico", None),
                observacao=getattr(retirada, "observacao", None),
                days_in_use=dias_em_uso,
            ):
                continue

            data_prevista = getattr(retirada, "data_prevista_devolucao", None)
            if data_prevista is not None:
                atrasada = date.today() > data_prevista
            else:
                atrasada = dias_em_uso > 30

            itens.append(
                {
                    "id": retirada.id,
                    "source": "retirada_ferramenta",
                    "codigo": item.codigo_item,
                    "descricao": item.descricao or "",
                    "observacao": getattr(retirada, "observacao", "") or "",
                    "foto_path": item.foto_path or None,
                    "quantidade": retirada.quantidade or 0,
                    "usuario": usuario.nome or "",
                    "matricula": matricula_short,
                    "matricula_full": matricula_full,
                    "local_servico": getattr(retirada, "local_servico", None) or "Não informado",
                    "data_retirada_iso": TimeService.isoformat_utc(getattr(retirada, "data_retirada", None)),
                    "dias_em_uso": dias_em_uso,
                    "atrasada": bool(atrasada),
                    "data_prevista_devolucao": TimeService.isoformat_utc(datetime.combine(data_prevista, datetime.min.time())) if data_prevista is not None else None,
                }
            )

        return itens

    @staticmethod
    def _get_active_tools_for_employee(matricula: str) -> list[dict[str, Any]]:
        """Retorna ferramentas ativas (sem devolução) de um funcionário."""
        # Buscar todas as saídas de ferramentas
        saidas = (
            db.session.query(Saida, Item)
            .join(Item, Saida.codigo_item == Item.codigo_item)
            .filter(
                Saida.matricula == matricula,
                func.lower(Item.categoria).contains("ferrament")
            )
            .order_by(Saida.data_saida.desc())
            .all()
        )
        
        active_tools = []
        
        for saida, item in saidas:
            # Verificar se tem devolução registrada
            devolucao = (
                db.session.query(InventarioEvento)
                .filter(
                    InventarioEvento.matricula == matricula,
                    InventarioEvento.codigo_item == saida.codigo_item,
                    InventarioEvento.tipo.in_([
                        "devolucao_ferramenta",
                        "devolucao_material",
                        "quebra_ferramenta",
                        "reparo_ferramenta",
                    ]),
                    InventarioEvento.data_evento >= saida.data_saida,
                )
                .first()
            )

            # Compatibilidade (legado mobile): algumas devoluções antigas de ferramentas geravam
            # Entrada com NF = NULL. Isso não deve ser tratado como "adição" no histórico, mas
            # precisamos reconhecer como devolução para não bloquear a custódia.
            entrada_legado = (
                db.session.query(Entrada.id_entrada)
                .filter(
                    Entrada.codigo_item == saida.codigo_item,
                    Entrada.matricula == matricula,
                    Entrada.nota_fiscal.is_(None),
                    Entrada.data_entrada >= saida.data_saida,
                )
                .first()
            )

            retirada_devolvida = (
                db.session.query(RetiradaFerramenta.id)
                .filter(
                    RetiradaFerramenta.codigo_item == saida.codigo_item,
                    RetiradaFerramenta.matricula == matricula,
                    RetiradaFerramenta.status.in_(["devolvida", "para_reparo"]),
                    RetiradaFerramenta.data_retirada >= saida.data_saida,
                )
                .first()
            )
            
            if not devolucao and not entrada_legado and not retirada_devolvida:
                days_in_use = (datetime.utcnow() - saida.data_saida).days
                # Tratar NULL como 'temporaria' (getattr não trata None)
                tipo_custodia = ToolCustodyService._infer_tipo_custodia(saida, days_in_use)
                
                # Alertas só para ferramentas temporárias
                is_alert = (tipo_custodia == 'temporaria' and days_in_use > 30)
                
                active_tools.append({
                    "saida_id": saida.id_saida,
                    "codigo_item": item.codigo_item,
                    "descricao": item.descricao,
                    "categoria": item.categoria,
                    "marca": item.marca or "N/D",
                    "foto_path": item.foto_path,
                    "quantidade": saida.quantidade,
                    "data_saida": saida.data_saida,
                    "data_saida_formatada": TimeService.format_local(saida.data_saida, "%d/%m/%Y %H:%M"),
                    "local_servico": saida.local_servico or "Não informado",
                    "observacao": saida.observacao or "",
                    "days_in_use": days_in_use,
                    "is_alert": is_alert,
                    "tipo_custodia": tipo_custodia,
                })
        
        return active_tools

    @staticmethod
    def _get_active_tool_saida(saida_id: int) -> tuple[Saida, Item]:
        """Localiza uma saída de ferramenta ainda ativa na custódia."""
        row = (
            db.session.query(Saida, Item)
            .join(Item, Saida.codigo_item == Item.codigo_item)
            .filter(Saida.id_saida == saida_id)
            .first()
        )

        if not row:
            raise ValueError("Saída não encontrada")

        saida, item = row
        if "ferrament" not in str(item.categoria or "").lower():
            raise ValueError("Saída não é ferramenta")

        devolucao = (
            db.session.query(InventarioEvento.id_evento)
            .filter(
                InventarioEvento.matricula == saida.matricula,
                InventarioEvento.codigo_item == saida.codigo_item,
                InventarioEvento.tipo.in_([
                    "devolucao_ferramenta",
                    "devolucao_material",
                    "quebra_ferramenta",
                    "reparo_ferramenta",
                ]),
                InventarioEvento.data_evento >= saida.data_saida,
            )
            .first()
        )

        entrada_legado = (
            db.session.query(Entrada.id_entrada)
            .filter(
                Entrada.codigo_item == saida.codigo_item,
                Entrada.matricula == saida.matricula,
                Entrada.nota_fiscal.is_(None),
                Entrada.data_entrada >= saida.data_saida,
            )
            .first()
        )

        retirada_fechada = (
            db.session.query(RetiradaFerramenta.id)
            .filter(
                RetiradaFerramenta.codigo_item == saida.codigo_item,
                RetiradaFerramenta.matricula == saida.matricula,
                RetiradaFerramenta.status.in_(["devolvida", "para_reparo"]),
                RetiradaFerramenta.data_retirada >= saida.data_saida,
            )
            .first()
        )

        if devolucao or entrada_legado or retirada_fechada:
            raise ValueError("Ferramenta já não está ativa em custódia")

        return saida, item

    @staticmethod
    def add_tool_to_employee(
        *,
        matricula: str,
        codigo_item: str,
        quantidade: int = 1,
        tipo_custodia: str = "temporaria",
        local_servico: str | None = None,
        observacao: str | None = None,
    ) -> int:
        """Adiciona uma ferramenta diretamente à custódia de um funcionário."""
        codigo_norm = (codigo_item or "").strip()
        matricula_norm = (matricula or "").strip()
        tipo_norm = ToolCustodyService._normalize_custody_type(tipo_custodia)

        if not matricula_norm:
            raise ValueError("Funcionário não informado")
        if not codigo_norm:
            raise ValueError("Ferramenta não informada")

        usuario = Usuario.query.get(matricula_norm)
        if not usuario:
            raise ValueError("Funcionário não encontrado")

        item = Item.query.get(codigo_norm)
        if not item:
            raise ValueError("Ferramenta não encontrada")
        if "ferrament" not in str(item.categoria or "").lower():
            raise ValueError("O item selecionado não é uma ferramenta")

        item_data = inventory_service.get_item(codigo_norm)
        if item_data and item_data.get("is_available") is False:
            raise ValueError(
                str(
                    item_data.get("unavailable_detail")
                    or item_data.get("unavailable_reason")
                    or "Ferramenta indisponível para retirada."
                )
            )

        try:
            quantidade_int = int(quantidade)
        except (TypeError, ValueError):
            raise ValueError("Quantidade inválida")

        if quantidade_int < 1:
            raise ValueError("Quantidade deve ser maior que zero")

        observacao_norm = (observacao or "").strip() or None
        local_norm = (local_servico or "").strip() or None

        saida_id = inventory_service.registrar_saida(
            MovimentoPayload(
                codigo=codigo_norm,
                quantidade=float(quantidade_int),
                matricula=matricula_norm,
                observacao=observacao_norm,
                local_servico=local_norm,
                tipo_custodia=tipo_norm,
            )
        )

        if tipo_norm != "permanente":
            retirada = RetiradaFerramenta(
                codigo_item=codigo_norm,
                matricula=matricula_norm,
                quantidade=quantidade_int,
                local_servico=local_norm,
                observacao=observacao_norm,
                data_prevista_devolucao=date.today(),
                status="em_uso",
            )
            db.session.add(retirada)
            db.session.commit()

        return int(saida_id)

    @staticmethod
    def transfer_tool(
        *,
        saida_id: int,
        nova_matricula: str,
        local_servico: str | None = None,
        observacao: str | None = None,
    ) -> int:
        """Transfere a custódia de uma ferramenta para outro funcionário."""
        saida, item = ToolCustodyService._get_active_tool_saida(saida_id)

        nova_matricula_norm = (nova_matricula or "").strip()
        if not nova_matricula_norm:
            raise ValueError("Informe o funcionário de destino")
        if str(saida.matricula or "").strip() == nova_matricula_norm:
            raise ValueError("Selecione um funcionário diferente do atual")

        usuario_atual = Usuario.query.get(saida.matricula)
        usuario_destino = Usuario.query.get(nova_matricula_norm)
        if not usuario_destino:
            raise ValueError("Funcionário de destino não encontrado")

        try:
            quantidade_float = float(saida.quantidade or 0)
        except (TypeError, ValueError):
            quantidade_float = 0.0

        if quantidade_float <= 0:
            raise ValueError("Quantidade inválida para transferência")
        if not quantidade_float.is_integer():
            raise ValueError("Transferência disponível apenas para quantidades inteiras de ferramentas")

        quantidade_int = int(quantidade_float)
        days_in_use = max(0, int((datetime.utcnow() - saida.data_saida).days)) if saida.data_saida else 0
        tipo_custodia = ToolCustodyService._infer_tipo_custodia(saida, days_in_use)

        local_final = (local_servico or saida.local_servico or "").strip() or None
        observacao_norm = (observacao or "").strip()

        origem_label = usuario_atual.nome if usuario_atual else str(saida.matricula or "N/D")
        destino_label = usuario_destino.nome or nova_matricula_norm

        observacao_saida_parts = [f"Transferência de custódia para {destino_label} ({nova_matricula_norm})"]
        if observacao_norm:
            observacao_saida_parts.append(observacao_norm)

        observacao_destino_parts = []
        if str(saida.observacao or "").strip():
            observacao_destino_parts.append(str(saida.observacao).strip())
        observacao_destino_parts.append(f"Transferida de {origem_label} ({saida.matricula})")
        if observacao_norm:
            observacao_destino_parts.append(observacao_norm)

        ToolCustodyService.register_return(saida_id, " | ".join(observacao_saida_parts))

        return ToolCustodyService.add_tool_to_employee(
            matricula=nova_matricula_norm,
            codigo_item=item.codigo_item,
            quantidade=quantidade_int,
            tipo_custodia=tipo_custodia,
            local_servico=local_final,
            observacao=" | ".join(part for part in observacao_destino_parts if part),
        )

    @staticmethod
    def get_employee_details(matricula: str) -> dict[str, Any] | None:
        """Retorna detalhes completos de um funcionário e suas ferramentas."""
        usuario = Usuario.query.get(matricula)
        if not usuario:
            return None
        
        active_tools = ToolCustodyService._get_active_tools_for_employee(matricula)
        history = ToolCustodyService._get_employee_history(matricula, days=30)
        
        # Separar por tipo de custódia
        tools_permanente = [t for t in active_tools if t.get("tipo_custodia") == "permanente"]
        tools_temporaria = [t for t in active_tools if t.get("tipo_custodia") != "permanente"]
        overdue_count = sum(1 for tool in tools_temporaria if tool.get("is_alert"))
        average_daily_days = round(
            sum(tool.get("days_in_use", 0) for tool in tools_temporaria) / len(tools_temporaria),
            1,
        ) if tools_temporaria else 0
        longest_open_days = max((tool.get("days_in_use", 0) for tool in active_tools), default=0)

        return_actions = sum(1 for item in history if item.get("tipo") == "Devolveu")
        repair_actions = sum(1 for item in history if item.get("tipo") == "Enviou para Reparo")
        damage_actions = sum(1 for item in history if item.get("tipo") == "Quebrou/Danificou")

        performance_score = 100
        performance_score -= overdue_count * 18
        performance_score -= repair_actions * 7
        performance_score -= damage_actions * 10
        performance_score += min(return_actions * 2, 8)
        performance_score = max(0, min(100, performance_score))

        if performance_score >= 85:
            performance_label = "Excelente controle"
            performance_tone = "success"
        elif performance_score >= 70:
            performance_label = "Operação estável"
            performance_tone = "info"
        elif performance_score >= 50:
            performance_label = "Ponto de atenção"
            performance_tone = "warning"
        else:
            performance_label = "Risco elevado"
            performance_tone = "danger"

        timeline = []
        for item in history:
            tipo = item.get("tipo") or "Ação"
            if tipo == "Devolveu":
                icon = "bi-arrow-return-left"
                accent = "success"
            elif tipo == "Enviou para Reparo":
                icon = "bi-wrench-adjustable-circle"
                accent = "info"
            elif tipo == "Quebrou/Danificou":
                icon = "bi-exclamation-octagon"
                accent = "warning"
            else:
                icon = "bi-clock-history"
                accent = "secondary"

            timeline.append({
                **item,
                "icon": icon,
                "accent": accent,
            })

        cargo_display = usuario.cargo or usuario.setor or "N/D"
        photo_path = ToolCustodyService.get_employee_photo_path(usuario.matricula)
        
        return {
            "matricula": usuario.matricula,
            "nome": usuario.nome,
            "setor": usuario.setor or "N/D",
            "cargo": usuario.cargo or "N/D",
            "cargo_display": cargo_display,
            "initials": ToolCustodyService._build_employee_initials(usuario.nome),
            "photo_path": photo_path,
            "active_tools": active_tools,
            "tools_permanente": tools_permanente,
            "tools_temporaria": tools_temporaria,
            "history": history,
            "timeline": timeline,
            "total_active": len(active_tools),
            "total_history": len(history),
            "kpis": {
                "permanent_count": len(tools_permanente),
                "temporary_count": len(tools_temporaria),
                "overdue_count": overdue_count,
                "average_daily_days": average_daily_days,
                "longest_open_days": longest_open_days,
                "return_actions": return_actions,
                "repair_actions": repair_actions,
                "damage_actions": damage_actions,
                "performance_score": performance_score,
                "performance_label": performance_label,
                "performance_tone": performance_tone,
            },
        }

    @staticmethod
    def _get_employee_history(matricula: str, days: int = 30) -> list[dict[str, Any]]:
        """Retorna histórico de devoluções dos últimos N dias."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        devolucoes = (
            db.session.query(InventarioEvento, Item, Usuario)
            .join(Item, InventarioEvento.codigo_item == Item.codigo_item)
            .outerjoin(Usuario, Usuario.matricula == InventarioEvento.matricula)
            .filter(
                InventarioEvento.matricula == matricula,
                InventarioEvento.tipo.in_([
                    "devolucao_ferramenta",
                    "devolucao_material",
                    "quebra_ferramenta",
                    "reparo_ferramenta",
                ]),
                InventarioEvento.data_evento >= cutoff,
            )
            .order_by(InventarioEvento.data_evento.desc())
            .all()
        )
        
        history = []
        for evento, item, usuario_dev in devolucoes:
            tipo_label = {
                "devolucao_ferramenta": "Devolveu",
                "devolucao_material": "Devolveu",
                "quebra_ferramenta": "Quebrou/Danificou",
                "reparo_ferramenta": "Enviou para Reparo",
            }.get(evento.tipo, "Ação")
            
            history.append({
                "data": evento.data_evento,
                "tipo": tipo_label,
                "descricao": item.descricao,
                "observacao": evento.descricao or "",
                "devolvido_por": usuario_dev.nome if usuario_dev else None,
                "matricula_dev": usuario_dev.matricula if usuario_dev else None,
            })
        
        return history

    @staticmethod
    def register_return(retirada_id: int, observacao: str | None = None) -> None:
        """Registra devolução de ferramenta (custódia diária).

        Importante: os endpoints desta aplicação enviam `Saida.id_saida`.
        Por isso, tentamos resolver primeiro como Saida para evitar colisão
        com `RetiradaFerramenta.id` (pode haver ids iguais em tabelas distintas).
        """

        def _has_return_evidence(matricula: str, codigo_item: str, data_base: datetime) -> tuple[bool, int | None]:
            devolucao_evento = (
                db.session.query(InventarioEvento.id_evento)
                .filter(
                    InventarioEvento.matricula == matricula,
                    InventarioEvento.codigo_item == codigo_item,
                    InventarioEvento.tipo.in_(
                        [
                            "devolucao_ferramenta",
                            "devolucao_material",
                            "quebra_ferramenta",
                            "reparo_ferramenta",
                        ]
                    ),
                    InventarioEvento.data_evento >= data_base,
                )
                .first()
            )
            if devolucao_evento:
                return True, None

            entrada_legado = (
                db.session.query(Entrada.id_entrada)
                .filter(
                    Entrada.codigo_item == codigo_item,
                    Entrada.matricula == matricula,
                    Entrada.nota_fiscal.is_(None),
                    Entrada.data_entrada >= data_base,
                )
                .order_by(Entrada.data_entrada.asc())
                .first()
            )
            if entrada_legado:
                return True, int(entrada_legado[0])
            return False, None

        saida = Saida.query.get(retirada_id)
        if saida:
            categoria = (saida.item.categoria or "").lower() if saida.item else ""
            if "ferrament" not in categoria:
                raise ValueError("Saída não é ferramenta")

            retirada = (
                RetiradaFerramenta.query
                .filter(
                    RetiradaFerramenta.codigo_item == saida.codigo_item,
                    RetiradaFerramenta.matricula == saida.matricula,
                    RetiradaFerramenta.status.in_(["em_uso", "atrasada"]),
                )
                .order_by(RetiradaFerramenta.data_retirada.desc())
                .first()
            )

            has_evidence, entrada_legado_id = _has_return_evidence(
                saida.matricula,
                saida.codigo_item,
                saida.data_saida,
            )

            # Se a devolução já foi registrada no estoque por outro caminho,
            # só “dá baixa” na custódia (não duplica ajuste no saldo).
            if retirada and has_evidence:
                if retirada.status == "para_reparo":
                    raise ValueError("Ferramenta está marcada para reparo")

                observacao_final = observacao or "Devolução conciliada (já registrada no estoque)"
                if entrada_legado_id:
                    observacao_final = f"{observacao_final} | entrada legada id={entrada_legado_id}"

                retirada.registrar_devolucao(observacao_final)
                db.session.commit()
                return

            # Se não há RetiradaFerramenta aberta, ainda podemos reconciliar a devolução
            # (mantém compatibilidade para casos legados/fora de fluxo).
            if not retirada:
                if has_evidence:
                    raise ValueError("Ferramenta já foi devolvida")

                quantidade_evento = float(saida.quantidade or 1)
                descricao_base = observacao or f"Devolução de Ferramenta: {saida.item.descricao if saida.item else 'Item'}"

                ledger_result = inventory_service.mirror_legacy_movement(
                    product_id=saida.codigo_item or "",
                    movement_type="devolucao",
                    quantity=float(saida.quantidade or 1),
                    payload=MovimentoPayload(
                        codigo=saida.codigo_item or "",
                        quantidade=float(saida.quantidade or 1),
                        matricula=saida.matricula,
                        observacao=descricao_base,
                        is_devolucao=True,
                    ),
                    metadata={"reference_type": "tool_custody_service", "legacy_event_type": "devolucao_ferramenta"},
                )

                evento = InventarioEvento(
                    codigo_item=saida.codigo_item,
                    matricula=saida.matricula,
                    quantidade=quantidade_evento,
                    tipo="devolucao_ferramenta",
                    descricao=descricao_base,
                    data_evento=datetime.utcnow(),
                )
                db.session.add(evento)
                db.session.commit()
                if ledger_result is not None:
                    ledger_result.metadata["reference_id"] = str(evento.id_evento)
                    inventory_service.finalize_ledger_mirror(ledger_result)

                try:
                    from ..services.notification_router import NotificationRouterService

                    NotificationRouterService.route_inventory_event(evento.id_evento)
                except Exception:
                    pass
                return

            # Fluxo normal quando há custódia aberta e ainda não há devolução registrada.
            if retirada.status == "devolvida":
                raise ValueError("Ferramenta já foi devolvida")
            if retirada.status == "para_reparo":
                raise ValueError("Ferramenta está marcada para reparo")

            retirada.registrar_devolucao(observacao)

            ledger_result = inventory_service.mirror_legacy_movement(
                product_id=retirada.codigo_item or "",
                movement_type="devolucao",
                quantity=float(retirada.quantidade or 1),
                payload=MovimentoPayload(
                    codigo=retirada.codigo_item or "",
                    quantidade=float(retirada.quantidade or 1),
                    matricula=retirada.matricula,
                    observacao=observacao or f"Devolução de Ferramenta: {retirada.item.descricao if retirada.item else 'Item'}",
                    is_devolucao=True,
                ),
                metadata={"reference_type": "tool_custody_service", "legacy_event_type": "devolucao_ferramenta"},
            )

            evento = InventarioEvento(
                codigo_item=retirada.codigo_item,
                matricula=retirada.matricula,
                quantidade=retirada.quantidade,
                tipo="devolucao_ferramenta",
                descricao=observacao or f"Devolução de Ferramenta: {retirada.item.descricao if retirada.item else 'Item'}",
                data_evento=datetime.utcnow(),
            )
            db.session.add(evento)
            db.session.commit()
            if ledger_result is not None:
                ledger_result.metadata["reference_id"] = str(evento.id_evento)
                inventory_service.finalize_ledger_mirror(ledger_result)

            try:
                from ..services.notification_router import NotificationRouterService

                NotificationRouterService.route_inventory_event(evento.id_evento)
            except Exception:
                pass
            return

        # Fallback: compatibilidade para lugares que enviem `RetiradaFerramenta.id`
        retirada = RetiradaFerramenta.query.get(retirada_id)
        if not retirada:
            raise ValueError("Retirada não encontrada")

        if retirada.status == "devolvida":
            raise ValueError("Ferramenta já foi devolvida")

        if retirada.status == "para_reparo":
            raise ValueError("Ferramenta está marcada para reparo")

        # Se já existe devolução/entrada legada após a retirada, concilia e não duplica estoque.
        has_evidence, entrada_legado_id = _has_return_evidence(
            retirada.matricula,
            retirada.codigo_item,
            retirada.data_retirada,
        )
        if has_evidence:
            observacao_final = observacao or "Devolução conciliada (já registrada no estoque)"
            if entrada_legado_id:
                observacao_final = f"{observacao_final} | entrada legada id={entrada_legado_id}"
            retirada.registrar_devolucao(observacao_final)
            db.session.commit()
            return

        retirada.registrar_devolucao(observacao)

        ledger_result = inventory_service.mirror_legacy_movement(
            product_id=retirada.codigo_item or "",
            movement_type="devolucao",
            quantity=float(retirada.quantidade or 1),
            payload=MovimentoPayload(
                codigo=retirada.codigo_item or "",
                quantidade=float(retirada.quantidade or 1),
                matricula=retirada.matricula,
                observacao=observacao or f"Devolução de Ferramenta: {retirada.item.descricao if retirada.item else 'Item'}",
                is_devolucao=True,
            ),
            metadata={"reference_type": "tool_custody_service", "legacy_event_type": "devolucao_ferramenta"},
        )

        evento = InventarioEvento(
            codigo_item=retirada.codigo_item,
            matricula=retirada.matricula,
            quantidade=retirada.quantidade,
            tipo="devolucao_ferramenta",
            descricao=observacao or f"Devolução de Ferramenta: {retirada.item.descricao if retirada.item else 'Item'}",
            data_evento=datetime.utcnow(),
        )
        db.session.add(evento)
        db.session.commit()
        if ledger_result is not None:
            ledger_result.metadata["reference_id"] = str(evento.id_evento)
            inventory_service.finalize_ledger_mirror(ledger_result)

        try:
            from ..services.notification_router import NotificationRouterService

            NotificationRouterService.route_inventory_event(evento.id_evento)
        except Exception:
            pass

    @staticmethod
    def register_damage(saida_id: int, observacao: str | None = None) -> None:
        """Registra ferramenta quebrada/danificada."""
        saida = Saida.query.get(saida_id)
        if not saida:
            raise ValueError("Saída não encontrada")
        
        ledger_result = inventory_service.mirror_legacy_movement(
            product_id=saida.codigo_item or "",
            movement_type="ajuste",
            quantity=-float(saida.quantidade or 0),
            payload=MovimentoPayload(
                codigo=saida.codigo_item or "",
                quantidade=float(saida.quantidade or 0),
                matricula=saida.matricula,
                observacao=observacao or f"Ferramenta danificada/perdida: {saida.item.descricao if saida.item else 'Item'}",
            ),
            metadata={"reference_type": "tool_custody_service", "legacy_event_type": "quebra_ferramenta"},
        )

        evento = InventarioEvento(
            codigo_item=saida.codigo_item,
            matricula=saida.matricula,
            quantidade=saida.quantidade,
            tipo="quebra_ferramenta",
            descricao=observacao or f"Ferramenta danificada/perdida: {saida.item.descricao if saida.item else 'Item'}",
            data_evento=datetime.utcnow(),
        )
        
        db.session.add(evento)
        # Não ajusta estoque - ferramenta foi perdida/quebrada
        db.session.commit()
        if ledger_result is not None:
            ledger_result.metadata["reference_id"] = str(evento.id_evento)
            inventory_service.finalize_ledger_mirror(ledger_result)

        try:
            from ..services.telegram_service import TelegramService

            TelegramService.notify_tool_damage(evento.id_evento)
        except Exception:
            pass

    @staticmethod
    def register_repair(saida_id: int, observacao: str | None = None) -> None:
        """Registra envio para reparo."""
        saida = Saida.query.get(saida_id)
        if not saida:
            raise ValueError("Saída não encontrada")
        
        ledger_result = inventory_service.mirror_legacy_movement(
            product_id=saida.codigo_item or "",
            movement_type="ajuste",
            quantity=-float(saida.quantidade or 0),
            payload=MovimentoPayload(
                codigo=saida.codigo_item or "",
                quantidade=float(saida.quantidade or 0),
                matricula=saida.matricula,
                observacao=observacao or f"Enviada para reparo: {saida.item.descricao if saida.item else 'Item'}",
            ),
            metadata={"reference_type": "tool_custody_service", "legacy_event_type": "reparo_ferramenta"},
        )

        evento = InventarioEvento(
            codigo_item=saida.codigo_item,
            matricula=saida.matricula,
            quantidade=saida.quantidade,
            tipo="reparo_ferramenta",
            descricao=observacao or f"Enviada para reparo: {saida.item.descricao if saida.item else 'Item'}",
            data_evento=datetime.utcnow(),
        )
        
        db.session.add(evento)
        db.session.commit()
        if ledger_result is not None:
            ledger_result.metadata["reference_id"] = str(evento.id_evento)
            inventory_service.finalize_ledger_mirror(ledger_result)

        try:
            from ..services.telegram_service import TelegramService

            TelegramService.notify_tool_repair(evento.id_evento)
        except Exception:
            pass

    @staticmethod
    def get_statistics() -> dict[str, Any]:
        """Retorna estatísticas gerais do controle de ferramentas."""
        employees = ToolCustodyService.get_all_employees_with_tools()
        
        total_tools = sum(e["total_ferramentas"] for e in employees)
        total_alerts = sum(e["alerts_count"] for e in employees)
        
        # Devoluções hoje
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        returns_today = (
            db.session.query(func.count(InventarioEvento.id_evento))
            .filter(
                InventarioEvento.tipo.in_(["devolucao_ferramenta", "devolucao_material"]),
                InventarioEvento.data_evento >= today_start,
            )
            .scalar()
        ) or 0
        
        return {
            "total_employees": len(employees),
            "total_tools": total_tools,
            "total_alerts": total_alerts,
            "returns_today": returns_today,
        }

    @staticmethod
    def delete_tool_record(saida_id: int) -> None:
        """Exclui registro de saída de ferramenta (APENAS PARA ADMINISTRADORES)."""
        saida = Saida.query.get(saida_id)
        if not saida:
            raise ValueError("Registro não encontrado")
        
        # Excluir eventos relacionados (inventario)
        InventarioEvento.query.filter(
            InventarioEvento.codigo_item == saida.codigo_item,
            InventarioEvento.matricula == saida.matricula,
            InventarioEvento.data_evento >= saida.data_saida,
        ).delete()
        
        # Excluir registro de saída
        db.session.delete(saida)
        db.session.commit()

    @staticmethod
    def change_custody_type(saida_id: int, novo_tipo: str) -> None:
        """Altera tipo de custódia (permanente ou temporaria)."""
        saida = Saida.query.get(saida_id)
        if not saida:
            raise ValueError("Registro não encontrado")

        raw = (novo_tipo or "").strip().lower()
        # Compat: evitar persistir o valor legado "diaria".
        if raw in {"diaria", "diária", "daily", "d"}:
            raw = "temporaria"

        if raw not in ["temporaria", "permanente"]:
            raise ValueError("Tipo inválido. Use 'temporaria' ou 'permanente'")

        saida.tipo_custodia = raw
        db.session.commit()

    @staticmethod
    def send_telegram_alert(saida_id: int) -> bool:
        """Envia alerta via Telegram sobre ferramenta não devolvida."""
        saida = db.session.query(Saida, Item, Usuario).join(
            Item, Saida.codigo_item == Item.codigo_item
        ).join(
            Usuario, Saida.matricula == Usuario.matricula
        ).filter(
            Saida.id_saida == saida_id
        ).first()
        
        if not saida:
            raise ValueError("Registro não encontrado")
        
        saida_obj, item, usuario = saida
        
        # Verificar se já foi devolvida
        devolucao = db.session.query(InventarioEvento).filter(
            InventarioEvento.matricula == saida_obj.matricula,
            InventarioEvento.codigo_item == saida_obj.codigo_item,
            InventarioEvento.tipo.in_([
                "devolucao_ferramenta",
                "devolucao_material",
                "quebra_ferramenta",
                "reparo_ferramenta",
            ]),
            InventarioEvento.data_evento >= saida_obj.data_saida,
        ).first()
        
        if devolucao:
            raise ValueError("Ferramenta já foi devolvida")

        # Compatibilidade (legado): tratar Entrada sem NF pós-saída como devolução já registrada.
        entrada_legado = db.session.query(Entrada.id_entrada).filter(
            Entrada.codigo_item == saida_obj.codigo_item,
            Entrada.matricula == saida_obj.matricula,
            Entrada.nota_fiscal.is_(None),
            Entrada.data_entrada >= saida_obj.data_saida,
        ).first()

        if entrada_legado:
            raise ValueError("Ferramenta já foi devolvida")
        
        try:
            from ..services.telegram_service import TelegramService
            from ..utils.time_service import TimeService
            from ..models import TelegramUser
            
            days_late = (datetime.utcnow() - saida_obj.data_saida).days
            data_retirada = TimeService.format_local(saida_obj.data_saida, "%d/%m/%Y")
            
            mensagem = (
                f"⚠️ <b>ALERTA DE FERRAMENTA NÃO DEVOLVIDA</b>\n\n"
                f"<b>Funcionário:</b> {usuario.nome}\n"
                f"<b>Matrícula:</b> {usuario.matricula}\n"
                f"<b>Ferramenta:</b> {item.descricao}\n"
                f"<b>Marca:</b> {item.marca or 'N/D'}\n"
                f"<b>Quantidade:</b> {saida_obj.quantidade}\n"
                f"<b>Data da retirada:</b> {data_retirada}\n"
                f"<b>Dias sem devolução:</b> {days_late}\n"
                f"<b>Status:</b> ❌ NÃO DEVOLVIDA"
            )
            
            # Buscar todos os usuários Telegram habilitados
            telegram_users = db.session.query(TelegramUser).filter_by(enabled=True).all()
            
            # Enviar para todos os usuários habilitados
            success_count = 0
            for telegram_user in telegram_users:
                result = TelegramService.send_message(
                    chat_id=telegram_user.chat_id,
                    text=mensagem,
                    parse_mode="HTML"
                )
                if result.get("success", False):
                    success_count += 1
            
            return success_count > 0
        except Exception as e:
            import logging
            logging.error(f"Erro ao enviar alerta Telegram: {e}")
            return False

    @staticmethod
    def send_grouped_alert_by_employee(matricula: str) -> bool:
        """Envia alerta agrupado de todas as ferramentas atrasadas de um funcionário."""
        from ..services.telegram_service import TelegramService
        from ..utils.time_service import TimeService
        
        # Buscar funcionário
        usuario = Usuario.query.get(matricula)
        if not usuario:
            raise ValueError("Funcionário não encontrado")
        
        # Buscar todas as ferramentas ativas (sem devolução)
        active_tools = ToolCustodyService._get_active_tools_for_employee(matricula)
        
        # Filtrar apenas ferramentas temporárias atrasadas (> 30 dias)
        overdue_tools = [
            tool for tool in active_tools 
            if tool.get('tipo_custodia') == 'temporaria' and tool.get('days_in_use', 0) > 30
        ]
        
        if not overdue_tools:
            raise ValueError("Nenhuma ferramenta atrasada encontrada para este funcionário")
        
        # Criar mensagem consolidada
        if len(overdue_tools) == 1:
            # Se tiver apenas 1, usar formato individual
            tool = overdue_tools[0]
            data_retirada = TimeService.format_local(tool['data_saida'], "%d/%m/%Y")
            mensagem = (
                f"⚠️ <b>ALERTA: Ferramenta não devolvida</b>\n\n"
                f"👤 <b>{usuario.nome}</b>\n"
                f"📋 Matrícula: {usuario.matricula}\n"
                f"🏢 Setor: {usuario.setor or 'N/D'}\n\n"
                f"🔧 <b>{tool['descricao']}</b>\n"
                f"📦 Marca: {tool['marca']}\n"
                f"📅 Desde: {data_retirada}\n"
                f"⏰ <b>{tool['days_in_use']} dias sem devolução</b>"
            )
        else:
            # Múltiplas ferramentas - formato agrupado
            mensagem = (
                f"⚠️ <b>ALERTA: Múltiplas ferramentas não devolvidas</b>\n\n"
                f"👤 <b>{usuario.nome}</b>\n"
                f"📋 Matrícula: {usuario.matricula}\n"
                f"🏢 Setor: {usuario.setor or 'N/D'}\n"
                f"📦 <b>{len(overdue_tools)} ferramentas pendentes:</b>\n\n"
            )
            
            for i, tool in enumerate(overdue_tools, 1):
                data_retirada = TimeService.format_local(tool['data_saida'], "%d/%m/%Y")
                mensagem += (
                    f"<b>{i}. {tool['descricao']}</b>\n"
                    f"   • Marca: {tool['marca']}\n"
                    f"   • Desde: {data_retirada}\n"
                    f"   • ⏰ <b>{tool['days_in_use']} dias sem devolução</b>\n\n"
                )
        
        try:
            from ..models import TelegramUser
            
            # Buscar todos os usuários Telegram habilitados
            telegram_users = db.session.query(TelegramUser).filter_by(enabled=True).all()
            
            # Enviar para todos os usuários habilitados
            success_count = 0
            for telegram_user in telegram_users:
                result = TelegramService.send_message(
                    chat_id=telegram_user.chat_id,
                    text=mensagem,
                    parse_mode="HTML"
                )
                if result.get("success", False):
                    success_count += 1
            
            return success_count > 0
        except Exception as e:
            import logging
            logging.error(f"Erro ao enviar alerta agrupado: {e}")
            return False


tool_custody_service = ToolCustodyService()
