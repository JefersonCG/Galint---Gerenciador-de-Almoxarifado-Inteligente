"""Serviços de gerenciamento de usuários para a aplicação Flask."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import random

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect as sa_inspect
from werkzeug.security import generate_password_hash

from ..extensions import db
from ..models import Usuario
from .user_deletion_archive_sqlite import archive_deleted_user_snapshot

_LEGACY_ADMIN_DEFAULT = ("0000000000000", "Administrador", "admin")


@dataclass(slots=True)
class UserPayload:
    matricula: str | None
    nome: str
    setor: str
    cargo: str | None
    senha: str | None
    is_admin: bool
    is_standard: bool


class UserService:
    """Reimplementa a lógica de usuários do legado para o contexto Flask."""

    def list_users(self) -> list[dict[str, Any]]:
        usuarios = Usuario.query.order_by(Usuario.nome).all()
        return [self._to_dict(usuario) for usuario in usuarios]

    def get_user(self, matricula: str) -> dict[str, Any] | None:
        usuario = Usuario.query.get(matricula)
        return self._to_dict(usuario) if usuario else None

    def find_by_identifier(self, identifier: str) -> Usuario | None:
        if not identifier:
            return None
        identifier = identifier.strip()
        candidato = Usuario.query.get(identifier)
        if candidato:
            return candidato
        return Usuario.query.filter_by(barcode_token=identifier).first()

    def search_by_name(self, query: str, *, limit: int = 8) -> list[Usuario]:
        query = (query or "").strip()
        if not query:
            return []
        return (
            Usuario.query.filter(Usuario.nome.ilike(f"%{query}%"))
            .order_by(Usuario.nome)
            .limit(limit)
            .all()
        )

    def create_user(self, payload: UserPayload) -> str:
        payload.nome = self._normalize_name(payload.nome)
        self._ensure_unique_single_name(payload.nome)
        matricula = payload.matricula.strip() if payload.matricula else ""
        if not matricula:
            matricula = self.generate_unique_matricula(payload.nome)
        else:
            if not self._is_valid_code13(matricula):
                raise ValueError("Matrícula deve conter 13 dígitos válidos (Code13)")

        if Usuario.query.get(matricula):
            raise ValueError("Matrícula já existe")

        if payload.is_admin and not payload.senha:
            raise ValueError("Senha obrigatória para administradores")

        senha_hash = generate_password_hash(payload.senha) if payload.senha else None
        usuario = Usuario(
            matricula=matricula,
            nome=payload.nome,
            setor=payload.setor,
            cargo=(payload.cargo or ""),
            senha_hash=senha_hash,
            is_admin=int(payload.is_admin),
            is_standard=int(payload.is_standard),
            barcode_token=self._generate_unique_barcode(matricula),
        )
        db.session.add(usuario)
        try:
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            raise ValueError("Não foi possível salvar o usuário") from exc
        return matricula

    def update_user(self, matricula: str, payload: UserPayload) -> None:
        usuario = Usuario.query.get(matricula)
        if not usuario:
            raise ValueError("Usuário não encontrado")

        payload.nome = self._normalize_name(payload.nome)
        self._ensure_unique_single_name(payload.nome, exclude_matricula=matricula)

        if payload.is_admin and not (payload.senha or usuario.senha_hash):
            raise ValueError("Administradores precisam de senha definida")

        usuario.nome = payload.nome
        usuario.setor = payload.setor
        usuario.cargo = payload.cargo or ""
        usuario.is_admin = int(payload.is_admin)
        usuario.is_standard = int(payload.is_standard)
        if payload.senha:
            usuario.senha_hash = generate_password_hash(payload.senha)

        db.session.commit()

    def delete_user(self, matricula: str, *, deleted_by: str | None = None, deleted_by_name: str | None = None) -> None:
        usuario = Usuario.query.get(matricula)
        if not usuario:
            raise ValueError("Usuário não encontrado")

        from ..models import (
            ApkAuditLog,
            ApkVersion,
            ChatMessage,
            Device,
            DevicePushToken,
            DeviceSession,
            Entrada,
            EquipamentoReparo,
            FerramentaEmUso,
            FeatureAssignment,
            FeatureFlag,
            FinanceLedgerEntry,
            GalintNotifyRecipient,
            InventarioEvento,
            MaterialInventario,
            OperationLog,
            RetiradaFerramenta,
            Saida,
            TelegramUser,
        )

        saidas = Saida.query.filter_by(matricula=matricula).all()
        entradas = Entrada.query.filter_by(matricula=matricula).all()
        eventos = InventarioEvento.query.filter_by(matricula=matricula).all()
        retiradas = RetiradaFerramenta.query.filter_by(matricula=matricula).all()
        reparos_responsavel = EquipamentoReparo.query.filter_by(matricula_responsavel=matricula).all()
        reparos_atualizados = EquipamentoReparo.query.filter_by(atualizado_por=matricula).all()
        ferramentas_em_uso = FerramentaEmUso.query.filter_by(matricula=matricula).all()
        telegram_users = TelegramUser.query.filter_by(matricula=matricula).all()
        device_sessions = DeviceSession.query.filter_by(user_id=matricula).all()
        device_push_tokens = DevicePushToken.query.filter_by(matricula=matricula).all()
        notify_recipients = GalintNotifyRecipient.query.filter_by(matricula=matricula).all()
        chat_messages = ChatMessage.query.filter_by(matricula=matricula).all()
        material_inventario = MaterialInventario.query.filter_by(matricula=matricula).all()
        operation_logs = OperationLog.query.filter_by(user_id=matricula).all()
        finance_entries = FinanceLedgerEntry.query.filter_by(usuario_matricula=matricula).all()
        devices = Device.query.filter(
            or_(Device.current_user_id == matricula, Device.blocked_by == matricula)
        ).all()
        device_sessions_revoked = DeviceSession.query.filter_by(revoked_by=matricula).all()
        apk_versions = ApkVersion.query.filter_by(created_by=matricula).all()
        feature_flags = FeatureFlag.query.filter_by(created_by=matricula).all()
        feature_assignments = FeatureAssignment.query.filter_by(assigned_by=matricula).all()
        apk_audit_logs = ApkAuditLog.query.filter(
            or_(ApkAuditLog.user_id == matricula, ApkAuditLog.admin_id == matricula)
        ).all()

        archive_payload = {
            "user": self._to_dict(usuario),
            "deleted_by": {
                "matricula": deleted_by,
                "nome": deleted_by_name,
            },
            "counts": {
                "saidas": len(saidas),
                "entradas": len(entradas),
                "inventario_eventos": len(eventos),
                "retiradas_ferramentas": len(retiradas),
                "equipamentos_reparo_responsavel": len(reparos_responsavel),
                "equipamentos_reparo_atualizados": len(reparos_atualizados),
                "ferramentas_em_uso": len(ferramentas_em_uso),
                "telegram_users": len(telegram_users),
                "device_sessions": len(device_sessions),
                "device_push_tokens": len(device_push_tokens),
                "notify_recipients": len(notify_recipients),
                "chat_messages": len(chat_messages),
                "material_inventario": len(material_inventario),
                "operation_logs": len(operation_logs),
                "finance_entries": len(finance_entries),
                "devices": len(devices),
                "device_sessions_revoked": len(device_sessions_revoked),
                "apk_versions": len(apk_versions),
                "feature_flags": len(feature_flags),
                "feature_assignments": len(feature_assignments),
                "apk_audit_logs": len(apk_audit_logs),
            },
            "records": {
                "saidas": self._serialize_rows(saidas),
                "entradas": self._serialize_rows(entradas),
                "inventario_eventos": self._serialize_rows(eventos),
                "retiradas_ferramentas": self._serialize_rows(retiradas),
                "equipamentos_reparo_responsavel": self._serialize_rows(reparos_responsavel),
                "equipamentos_reparo_atualizados": self._serialize_rows(reparos_atualizados),
                "ferramentas_em_uso": self._serialize_rows(ferramentas_em_uso),
                "telegram_users": self._serialize_rows(telegram_users),
                "device_sessions": self._serialize_rows(device_sessions),
                "device_push_tokens": self._serialize_rows(device_push_tokens),
                "notify_recipients": self._serialize_rows(notify_recipients),
                "chat_messages": self._serialize_rows(chat_messages),
                "material_inventario": self._serialize_rows(material_inventario),
                "operation_logs": self._serialize_rows(operation_logs),
                "finance_entries": self._serialize_rows(finance_entries),
                "devices": self._serialize_rows(devices),
                "device_sessions_revoked": self._serialize_rows(device_sessions_revoked),
                "apk_versions": self._serialize_rows(apk_versions),
                "feature_flags": self._serialize_rows(feature_flags),
                "feature_assignments": self._serialize_rows(feature_assignments),
                "apk_audit_logs": self._serialize_rows(apk_audit_logs),
            },
        }

        try:
            archive_deleted_user_snapshot(details=archive_payload)
        except Exception as exc:
            raise ValueError(
                "Não foi possível gravar o arquivo morto SQLite deste colaborador. A exclusão foi cancelada."
            ) from exc

        session_ids = [session.id for session in device_sessions]

        try:
            db.session.query(Saida).filter_by(matricula=matricula).update(
                {"matricula": None}, synchronize_session=False
            )
            db.session.query(Entrada).filter_by(matricula=matricula).update(
                {"matricula": None}, synchronize_session=False
            )
            db.session.query(InventarioEvento).filter_by(matricula=matricula).update(
                {"matricula": None}, synchronize_session=False
            )
            db.session.query(MaterialInventario).filter_by(matricula=matricula).update(
                {"matricula": None, "responsavel_nome": None}, synchronize_session=False
            )
            db.session.query(OperationLog).filter_by(user_id=matricula).update(
                {"user_id": None}, synchronize_session=False
            )
            db.session.query(FinanceLedgerEntry).filter_by(usuario_matricula=matricula).update(
                {"usuario_matricula": None}, synchronize_session=False
            )
            db.session.query(Device).filter(Device.current_user_id == matricula).update(
                {"current_user_id": None}, synchronize_session=False
            )
            db.session.query(Device).filter(Device.blocked_by == matricula).update(
                {"blocked_by": None}, synchronize_session=False
            )
            db.session.query(DeviceSession).filter(DeviceSession.revoked_by == matricula).update(
                {"revoked_by": None}, synchronize_session=False
            )
            db.session.query(ApkVersion).filter_by(created_by=matricula).update(
                {"created_by": None}, synchronize_session=False
            )
            db.session.query(FeatureFlag).filter_by(created_by=matricula).update(
                {"created_by": None}, synchronize_session=False
            )
            db.session.query(FeatureAssignment).filter_by(assigned_by=matricula).update(
                {"assigned_by": None}, synchronize_session=False
            )
            db.session.query(ApkAuditLog).filter(ApkAuditLog.user_id == matricula).update(
                {"user_id": None}, synchronize_session=False
            )
            db.session.query(ApkAuditLog).filter(ApkAuditLog.admin_id == matricula).update(
                {"admin_id": None}, synchronize_session=False
            )
            db.session.query(EquipamentoReparo).filter_by(atualizado_por=matricula).update(
                {"atualizado_por": None}, synchronize_session=False
            )

            if session_ids:
                db.session.query(ApkAuditLog).filter(ApkAuditLog.session_id.in_(session_ids)).update(
                    {"session_id": None}, synchronize_session=False
                )

            db.session.query(ChatMessage).filter_by(matricula=matricula).delete(synchronize_session=False)
            db.session.query(RetiradaFerramenta).filter_by(matricula=matricula).delete(synchronize_session=False)
            db.session.query(FerramentaEmUso).filter_by(matricula=matricula).delete(synchronize_session=False)
            db.session.query(EquipamentoReparo).filter(
                EquipamentoReparo.matricula_responsavel == matricula
            ).delete(synchronize_session=False)
            db.session.query(DevicePushToken).filter_by(matricula=matricula).delete(synchronize_session=False)
            db.session.query(GalintNotifyRecipient).filter_by(matricula=matricula).delete(synchronize_session=False)
            db.session.query(DeviceSession).filter_by(user_id=matricula).delete(synchronize_session=False)

            for telegram_user in telegram_users:
                db.session.delete(telegram_user)

            db.session.flush()
            db.session.delete(usuario)
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            raise ValueError(
                "Não foi possível concluir a exclusão arquivada do colaborador por causa de vínculos ainda existentes."
            ) from exc
        except Exception as exc:
            db.session.rollback()
            raise ValueError(
                "Falha ao concluir a exclusão arquivada do colaborador. Nenhuma alteração parcial foi mantida."
            ) from exc

    def generate_unique_matricula(self, nome: str) -> str:
        for _ in range(10000):
            candidato = self._generate_code13()
            if not Usuario.query.get(candidato):
                return candidato
        raise RuntimeError("Não foi possível gerar matrícula única no padrão Code13")

    def ensure_default_admin(self) -> None:
        matricula, nome, senha = _LEGACY_ADMIN_DEFAULT
        if Usuario.query.get(matricula):
            return
        payload = UserPayload(
            matricula=matricula,
            nome=nome,
            setor="Setor Escritório/Materiais de Escritório",
            cargo="",
            senha=senha,
            is_admin=True,
            is_standard=True,
        )
        self.create_user(payload)

    def get_distinct_setores(self) -> list[str]:
        """Retorna lista de setores únicos ordenados."""
        result = db.session.query(Usuario.setor).distinct().filter(
            Usuario.setor.isnot(None)
        ).order_by(Usuario.setor).all()
        return [row[0] for row in result if row[0]]

    def _generate_unique_barcode(self, matricula: str) -> str:
        candidato = (matricula or "").strip()
        if self._is_valid_code13(candidato) and not Usuario.query.filter_by(barcode_token=candidato).first():
            return candidato
        while True:
            token = self._generate_code13()
            if not Usuario.query.filter_by(barcode_token=token).first():
                return token

    def _generate_code13(self) -> str:
        digits = "".join(str(random.randint(0, 9)) for _ in range(12))
        check = self._code13_checksum(digits)
        return f"{digits}{check}"

    @staticmethod
    def _normalize_name(nome: str) -> str:
        return " ".join((nome or "").strip().split())

    @staticmethod
    def _is_single_name(nome: str) -> bool:
        return " " not in (nome or "").strip()

    def _ensure_unique_single_name(self, nome: str, *, exclude_matricula: str | None = None) -> None:
        if not nome:
            return
        if not self._is_single_name(nome):
            return

        query = Usuario.query.filter(func.lower(Usuario.nome) == nome.lower())
        if exclude_matricula:
            query = query.filter(Usuario.matricula != exclude_matricula)

        if query.first():
            raise ValueError(
                "Já existe um usuário com esse nome. Informe sobrenome para concluir o cadastro."
            )

    @staticmethod
    def _code13_checksum(data: str) -> str:
        if len(data) != 12 or not data.isdigit():
            raise ValueError("Dados inválidos para calcular Code13")
        soma = 0
        for idx, char in enumerate(data):
            peso = 1 if idx % 2 == 0 else 3
            soma += int(char) * peso
        resto = soma % 10
        digito = (10 - resto) % 10
        return str(digito)

    def _is_valid_code13(self, codigo: str) -> bool:
        codigo = (codigo or "").strip()
        if len(codigo) != 13 or not codigo.isdigit():
            return False
        esperado = self._code13_checksum(codigo[:12])
        return codigo[-1] == esperado

    @staticmethod
    def _to_dict(usuario: Usuario) -> dict[str, Any]:
        return {
            "matricula": usuario.matricula,
            "nome": usuario.nome,
            "setor": usuario.setor,
            "cargo": usuario.cargo,
            "is_admin": bool(usuario.is_admin),
            "is_standard": bool(usuario.is_standard),
            "barcode_token": usuario.barcode_token,
        }

    @classmethod
    def _serialize_rows(cls, rows: list[Any]) -> list[dict[str, Any]]:
        return [cls._serialize_model(row) for row in rows]

    @staticmethod
    def _serialize_model(instance: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for column in sa_inspect(instance.__class__).columns:
            payload[column.key] = UserService._serialize_value(getattr(instance, column.key))
        return payload

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, dict)):
            return value
        isoformat = getattr(value, "isoformat", None)
        if callable(isoformat):
            return isoformat()
        return str(value)


user_service = UserService()
