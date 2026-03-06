"""Flask CLI commands for database maintenance."""
from __future__ import annotations

from typing import Iterator

import click
from flask import current_app
from flask.cli import with_appcontext

from .extensions import db
from .services.backup import BackupService


def register_cli(app) -> None:
    app.cli.add_command(init_db_command)
    app.cli.add_command(check_db_command)
    app.cli.add_command(repair_db_command)
    app.cli.add_command(restore_db_command)
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


@click.command("repair-db")
@with_appcontext
def repair_db_command() -> None:
    """Cria tabelas ausentes e adiciona colunas faltantes com base nos modelos."""
    result = BackupService(current_app).repair_schema()
    if result["tables"]:
        for table in result["tables"]:
            click.echo(f"Tabela criada: {table}")
    if result["columns"]:
        for column in result["columns"]:
            click.echo(f"Coluna criada: {column}")
    if not result["tables"] and not result["columns"]:
        click.echo("Nenhum ajuste de schema foi necessário.")


@click.command("restore-db")
@click.option("--backup-name", default=None, help="Nome do arquivo de backup .sql")
@click.option("--latest", is_flag=True, help="Restaura o backup mais recente")
@with_appcontext
def restore_db_command(backup_name: str | None, latest: bool) -> None:
    """Restaura um backup SQL com backup de segurança e reparo automático de schema."""
    service = BackupService(current_app)
    selected = (backup_name or "").strip()
    if latest:
        backups = service.list_backups()
        if not backups:
            raise click.ClickException("Nenhum backup disponível para restauração.")
        selected = backups[0]["name"]
    if not selected:
        raise click.ClickException("Informe --backup-name ou use --latest.")
    restored = service.restore_backup(selected)
    click.echo(f"Backup restaurado com sucesso: {restored}")


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
