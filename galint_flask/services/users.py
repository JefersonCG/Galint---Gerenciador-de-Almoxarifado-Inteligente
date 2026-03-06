"""Serviços de gerenciamento de usuários para a aplicação Flask."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import random

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from ..extensions import db
from ..models import Usuario

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

    def delete_user(self, matricula: str, force_delete: bool = False, reatribuir_para: str | None = None) -> None:
        usuario = Usuario.query.get(matricula)
        if not usuario:
            raise ValueError("Usuário não encontrado")
        
        # Verificar se há registros vinculados
        from ..models import Saida, Entrada, InventarioEvento, TelegramUser
        
        num_saidas = db.session.query(Saida).filter_by(matricula=matricula).count()
        num_entradas = db.session.query(Entrada).filter_by(matricula=matricula).count()
        num_eventos = db.session.query(InventarioEvento).filter_by(matricula=matricula).count()
        
        total_registros = num_saidas + num_entradas + num_eventos
        
        if total_registros > 0:
            # Se force_delete está ativo e há um usuário para reatribuir
            if force_delete and reatribuir_para:
                # Validar que o usuário de destino existe
                usuario_destino = Usuario.query.get(reatribuir_para)
                if not usuario_destino:
                    raise ValueError(f"Usuário de destino '{reatribuir_para}' não encontrado")
                
                # Reatribuir saídas
                db.session.query(Saida).filter_by(matricula=matricula).update(
                    {"matricula": reatribuir_para}, synchronize_session=False
                )
                
                # Reatribuir entradas
                db.session.query(Entrada).filter_by(matricula=matricula).update(
                    {"matricula": reatribuir_para}, synchronize_session=False
                )
                
                # Reatribuir eventos de inventário
                db.session.query(InventarioEvento).filter_by(matricula=matricula).update(
                    {"matricula": reatribuir_para}, synchronize_session=False
                )
                
                db.session.flush()
            
            # Se force_delete está ativo mas sem reatribuir, define matrícula como NULL
            elif force_delete:
                # Definir matrícula como NULL nos registros
                db.session.query(Saida).filter_by(matricula=matricula).update(
                    {"matricula": None}, synchronize_session=False
                )
                
                db.session.query(Entrada).filter_by(matricula=matricula).update(
                    {"matricula": None}, synchronize_session=False
                )
                
                db.session.query(InventarioEvento).filter_by(matricula=matricula).update(
                    {"matricula": None}, synchronize_session=False
                )
                
                db.session.flush()
            
            # Se não há force_delete, lançar erro como antes
            else:
                detalhes = []
                if num_saidas > 0:
                    detalhes.append(f"{num_saidas} saída(s)")
                if num_entradas > 0:
                    detalhes.append(f"{num_entradas} entrada(s)")
                if num_eventos > 0:
                    detalhes.append(f"{num_eventos} evento(s) de inventário")
                
                raise ValueError(
                    f"Não é possível excluir o usuário {usuario.nome}. "
                    f"Existem {total_registros} registro(s) vinculado(s): {', '.join(detalhes)}. "
                    f"Para excluir este usuário, primeiro remova ou reatribua estes registros."
                )
        
        # Remover vinculação do Telegram se existir
        telegram_user = db.session.query(TelegramUser).filter_by(matricula=matricula).first()
        if telegram_user:
            db.session.delete(telegram_user)
        
        db.session.delete(usuario)
        db.session.commit()

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


user_service = UserService()
