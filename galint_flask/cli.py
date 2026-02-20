"""Flask CLI commands for database maintenance."""
from __future__ import annotations

from typing import Iterator

import click
from flask import current_app
from flask.cli import with_appcontext

from .extensions import db


def register_cli(app) -> None:
    app.cli.add_command(init_db_command)
    app.cli.add_command(check_db_command)
    app.cli.add_command(reset_users_command)


@click.command("init-db")
@with_appcontext
def init_db_command() -> None:
    """Create database tables if they do not already exist."""
    db.create_all()
    click.echo("Banco de dados inicializado.")


@click.command("check-db")
@with_appcontext
def check_db_command() -> None:
    """Validate that required tables/columns are present in the configured database."""
    missing = list(_missing_tables())
    if missing:
        for table in missing:
            click.echo(f"Tabela ausente: {table}")
        raise SystemExit(1)
    click.echo("Estrutura do banco está consistente.")


def _missing_tables() -> Iterator[str]:
    inspector = db.inspect(db.engine)
    required = {"itens", "usuarios", "entradas", "saidas", "inventario_eventos", "chat_messages"}
    existing = set(inspector.get_table_names())
    for table in sorted(required - existing):
        yield table


@click.command("reset-users")
@click.option("--matricula", default=None, help="Matrícula Code13 para o usuário de teste")
@click.option("--nome", default="Usuário de Teste", show_default=True, help="Nome exibido")
@click.option("--setor", default="Testes", show_default=True)
@click.option("--senha", default="teste123", show_default=True, help="Senha inicial")
@with_appcontext
def reset_users_command(matricula: str | None, nome: str, setor: str, senha: str) -> None:
    """Apaga todos os usuários e deixa apenas um usuário de teste criado automaticamente."""
    from .models import Usuario
    from .services.users import UserPayload, user_service

    db.session.query(Usuario).delete()
    db.session.commit()

    matricula_final = matricula.strip() if matricula else None
    if matricula_final and not user_service._is_valid_code13(matricula_final):
        raise click.BadParameter("Matrícula deve conter 13 dígitos válidos (Code13)")

    payload = UserPayload(
        matricula=matricula_final,
        nome=nome,
        setor=setor,
        cargo="",
        senha=senha,
        is_admin=True,
        is_standard=True,
    )
    created = user_service.create_user(payload)
    click.echo(f"Usuário de teste criado: {created}")
