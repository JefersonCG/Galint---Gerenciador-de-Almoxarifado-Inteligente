"""Rotas para gerenciar backups (listar, restaurar, excluir)."""
from __future__ import annotations

import json
import os
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import text

from ..extensions import db
from ..models import Entrada, Saida
from ..services.ledger_backfill import ledger_backfill_service


blueprint = Blueprint("backups", __name__, url_prefix="/backups")


def _sync_serial_sequence(table_name: str, pk_name: str) -> None:
    if db.session.bind is None or db.session.bind.dialect.name != "postgresql":
        return
    db.session.execute(
        text(
            f"SELECT setval(pg_get_serial_sequence('{table_name}', '{pk_name}'), "
            f"GREATEST((SELECT COALESCE(MAX({pk_name}), 0) FROM {table_name}), 1), true)"
        )
    )


def _require_admin():
    # simple check; pages that import current_user will enforce via decorator normally
    from flask_login import current_user

    if not bool(getattr(current_user, "is_admin", False)):
        abort(403)


@blueprint.get("/")
@login_required
def list_backups():
    _require_admin()
    backup_dir = os.path.join(os.getcwd(), "instance", "backups")
    os.makedirs(backup_dir, exist_ok=True)
    files = []
    for name in os.listdir(backup_dir):
        path = os.path.join(backup_dir, name)
        if os.path.isfile(path):
            stat = os.stat(path)
            files.append({
                "name": name,
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime),
            })
    files.sort(key=lambda f: f["mtime"], reverse=True)
    return render_template("backups/list.html", backups=files)


@blueprint.post("/delete")
@login_required
def delete_backup():
    _require_admin()
    filename = (request.form.get("filename") or "").strip()
    if not filename:
        flash("Arquivo inválido.", "danger")
        return redirect(url_for("backups.list_backups"))
    backup_dir = os.path.join(os.getcwd(), "instance", "backups")
    path = os.path.join(backup_dir, filename)
    if not os.path.exists(path):
        flash("Arquivo não encontrado.", "warning")
        return redirect(url_for("backups.list_backups"))
    try:
        os.remove(path)
        flash(f"Backup '{filename}' removido.", "success")
    except Exception as exc:
        flash(f"Erro ao remover: {exc}", "danger")
    return redirect(url_for("backups.list_backups"))


@blueprint.post("/restore")
@login_required
def restore_backup():
    _require_admin()
    filename = (request.form.get("filename") or "").strip()
    if not filename:
        flash("Arquivo inválido.", "danger")
        return redirect(url_for("backups.list_backups"))
    backup_dir = os.path.join(os.getcwd(), "instance", "backups")
    path = os.path.join(backup_dir, filename)
    if not os.path.exists(path):
        flash("Arquivo não encontrado.", "warning")
        return redirect(url_for("backups.list_backups"))
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        flash(f"Não foi possível ler o backup: {exc}", "danger")
        return redirect(url_for("backups.list_backups"))

    restored = {"entradas": 0, "saidas": 0}
    skipped = {"entradas": 0, "saidas": 0}
    restored_entry_ids: list[int] = []
    restored_exit_ids: list[int] = []
    try:
        # If backup has entradas/saidas (format produced by our cleanup script), restore them
        entradas = data.get("entradas") or []
        for e in entradas:
            entry_id = e.get("id_entrada")
            if entry_id is not None and db.session.get(Entrada, int(entry_id)) is not None:
                skipped["entradas"] += 1
                continue
            try:
                dt = datetime.fromisoformat(e["data_entrada"]) if e.get("data_entrada") else None
            except Exception:
                dt = None
            ent = Entrada(
                codigo_item=e.get("codigo_item"),
                matricula=e.get("matricula"),
                quantidade=e.get("quantidade") or 0,
            )
            if entry_id is not None:
                ent.id_entrada = int(entry_id)
            if dt:
                ent.data_entrada = dt
            ent.nota_fiscal = e.get("nota_fiscal")
            db.session.add(ent)
            restored["entradas"] += 1
            if entry_id is not None:
                restored_entry_ids.append(int(entry_id))

        saidas = data.get("saidas") or []
        for s in saidas:
            exit_id = s.get("id_saida")
            if exit_id is not None and db.session.get(Saida, int(exit_id)) is not None:
                skipped["saidas"] += 1
                continue
            try:
                dt = datetime.fromisoformat(s["data_saida"]) if s.get("data_saida") else None
            except Exception:
                dt = None
            sd = Saida(
                codigo_item=s.get("codigo_item"),
                matricula=s.get("matricula"),
                quantidade=s.get("quantidade") or 0,
            )
            if exit_id is not None:
                sd.id_saida = int(exit_id)
            if dt:
                sd.data_saida = dt
            sd.observacao = s.get("observacao")
            sd.local_servico = s.get("local_servico")
            if s.get("tipo_custodia"):
                sd.tipo_custodia = s.get("tipo_custodia")
            db.session.add(sd)
            restored["saidas"] += 1
            if exit_id is not None:
                restored_exit_ids.append(int(exit_id))

        db.session.flush()
        _sync_serial_sequence("entradas", "id_entrada")
        _sync_serial_sequence("saidas", "id_saida")

        sync_summary = ledger_backfill_service.sync_restored_rows(
            entry_ids=restored_entry_ids,
            exit_ids=restored_exit_ids,
        )

        db.session.commit()
        flash(
            "Restauração concluída: "
            f"{restored['entradas']} entradas, {restored['saidas']} saídas; "
            f"{skipped['entradas']} entradas e {skipped['saidas']} saídas já existiam. "
            f"Ledger sincronizado com {sync_summary.processed_entries} entradas e "
            f"{sync_summary.processed_exits} saídas; {sync_summary.skipped_missing_product} movimentos sem item válido.",
            "success",
        )
    except Exception as exc:
        db.session.rollback()
        flash(f"Erro ao restaurar backup: {exc}", "danger")
    return redirect(url_for("backups.list_backups"))
