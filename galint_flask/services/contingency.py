from __future__ import annotations

"""Serviço responsável pela fila de contingência de cadastros."""

from datetime import datetime
from typing import Any

from ..extensions import db
from ..models import ContingenciaCadastro
from .inventory import MovimentoPayload, inventory_service


class ContingencyService:
    """Gerencia cadastros emergenciais quando o banco estiver indisponível."""

    def list_entries(self) -> list[dict[str, Any]]:
        registros = ContingenciaCadastro.query.order_by(ContingenciaCadastro.created_at.desc()).all()
        return [self._to_dict(entry) for entry in registros]

    def enqueue(self, payload: dict[str, Any], *, message: str | None = None, status: str = "pending") -> int:
        entry = ContingenciaCadastro(
            codigo_item=payload.get("codigo_item", ""),
            descricao=payload.get("descricao", ""),
            unidade=payload.get("unidade"),
            localizacao=payload.get("localizacao"),
            setor=payload.get("setor", "Setor Escritório/Materiais de Escritório"),
            estoque_minimo=int(payload.get("estoque_minimo", 0) or 0),
            estoque_minimo_tipo=payload.get("estoque_minimo_tipo", "Unidade"),
            quantidade_inicial=int(payload.get("quantidade_inicial", 0) or 0),
            nota_fiscal=payload.get("nota_fiscal"),
            status=status,
            message=message,
            attempts=0,
        )
        db.session.add(entry)
        db.session.commit()
        return entry.id

    def register_now(self, payload: dict[str, Any]) -> None:
        dados_item = self._map_payload_to_item(payload)
        codigo = inventory_service.create_item(dados_item)
        quantidade_inicial = int(payload.get("quantidade_inicial", 0) or 0)
        if quantidade_inicial > 0:
            inventory_service.registrar_entrada(
                MovimentoPayload(
                    codigo=codigo,
                    quantidade=quantidade_inicial,
                    matricula=None,
                    nota_fiscal=payload.get("nota_fiscal"),
                )
            )

    def register_or_queue(self, payload: dict[str, Any], *, queue_only: bool) -> dict[str, Any]:
        if queue_only:
            entry_id = self.enqueue(payload)
            return {"status": "queued", "entry_id": entry_id}
        try:
            self.register_now(payload)
            return {"status": "created"}
        except ValueError as exc:
            entry_id = self.enqueue(payload, message=str(exc), status="error")
            return {"status": "queued", "entry_id": entry_id, "message": str(exc)}

    def sync_queue(self) -> dict[str, int]:
        pendentes = ContingenciaCadastro.query.order_by(ContingenciaCadastro.created_at.asc()).all()
        sucesso = 0
        erros = 0
        for entry in pendentes:
            try:
                self.register_now(self._to_dict(entry))
                db.session.delete(entry)
                db.session.commit()
                sucesso += 1
            except ValueError as exc:
                entry.attempts += 1
                entry.last_attempt = datetime.utcnow()
                entry.status = "error"
                entry.message = str(exc)
                db.session.commit()
                erros += 1
        return {"sucesso": sucesso, "erros": erros, "restantes": ContingenciaCadastro.query.count()}

    def delete_entry(self, entry_id: int) -> None:
        entry = ContingenciaCadastro.query.get(entry_id)
        if not entry:
            raise ValueError("Registro não encontrado")
        db.session.delete(entry)
        db.session.commit()

    def _map_payload_to_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "codigo": payload.get("codigo_item", ""),
            "descricao": payload.get("descricao", ""),
            "nota_fiscal": payload.get("nota_fiscal"),
            "setor": payload.get("setor", ""),
            "localizacao": payload.get("localizacao"),
            "estoque_minimo": payload.get("estoque_minimo"),
            "quantidade_interna": payload.get("quantidade_interna", 1),
            "tipo_produto": payload.get("tipo_produto", "avulso"),
            "unidade": payload.get("unidade", "Unidade"),
            "estoque_minimo_tipo": payload.get("estoque_minimo_tipo", "Unidade"),
        }

    @staticmethod
    def _to_dict(entry: ContingenciaCadastro) -> dict[str, Any]:
        return {
            "id": entry.id,
            "codigo_item": entry.codigo_item,
            "descricao": entry.descricao,
            "unidade": entry.unidade,
            "localizacao": entry.localizacao,
            "setor": entry.setor,
            "estoque_minimo": entry.estoque_minimo,
            "estoque_minimo_tipo": entry.estoque_minimo_tipo,
            "quantidade_inicial": entry.quantidade_inicial,
            "nota_fiscal": entry.nota_fiscal,
            "status": entry.status,
            "attempts": entry.attempts,
            "message": entry.message,
            "created_at": entry.created_at,
            "last_attempt": entry.last_attempt,
        }


contingency_service = ContingencyService()
