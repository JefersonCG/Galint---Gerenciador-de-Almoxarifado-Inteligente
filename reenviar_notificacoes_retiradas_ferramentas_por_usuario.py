"""Reenvia notificações Telegram de retiradas de ferramentas por usuário e janela de tempo.

Uso (PowerShell):
    .\\.venv\\Scripts\\python.exe reenviar_notificacoes_retiradas_ferramentas_por_usuario.py --nome "Gabriel (daburra)" --minutes 10 --limit 5

O que faz:
- Busca retiradas em `retiradas_ferramentas` (tabela `RetiradaFerramenta`) filtrando por nome do usuário.
- Para cada retirada encontrada:
  - Se já existe outbox `tool_withdraw:{retirada_id}:admin:{chat_id}` com status pending/failed/dead, requeue (status=pending e available_at=agora).
  - Se já existe com status sent, cria uma nova mensagem com sufixo `:resend:<timestamp>` (força reenvio).
  - Se não existe, enfileira a mensagem padrão.

Obs:
- Envia para os Telegram admins (TelegramUser.is_admin=True) — mesmo comportamento do serviço.
- Não depende de túnel/webhook quando polling está habilitado.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import Item, RetiradaFerramenta, TelegramOutbox, TelegramUser, Usuario
from galint_flask.services.telegram_service import TelegramService
from galint_flask.utils.time_service import TimeService


@dataclass
class ProcessSummary:
    retiradas_encontradas: int = 0
    retiradas_processadas: int = 0
    quantidade_total: int = 0
    outbox_enfileiradas_novas: int = 0
    outbox_requeue: int = 0
    outbox_resend_novas: int = 0
    erros: int = 0


def _utcnow_naive() -> datetime:
    """UTC 'naive' para compatibilidade com colunas DateTime sem timezone."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _build_message(*, retirada: RetiradaFerramenta, item: Item, usuario: Usuario | None) -> str:
    categoria = (item.categoria or "Ferramentas").strip().upper()
    emoji = "🔧" if "FERRAMENT" in categoria else "📦"

    data_fmt = TimeService.format_local(retirada.data_retirada, "%d/%m/%Y %H:%M")
    nome_usuario = usuario.nome if usuario else f"Matrícula {retirada.matricula}"

    message = "📤 <b>RETIRADA DE FERRAMENTA</b>\n\n"
    message += f"{emoji} <b>{item.descricao}</b>\n"
    message += f"🏷️ Código: <code>{item.codigo_item}</code>\n"
    message += f"📦 Quantidade: <b>{retirada.quantidade}</b> {item.unidade or 'un.'}\n\n"
    message += f"👤 <b>Funcionário:</b> {nome_usuario}\n"
    message += f"📅 <b>Data:</b> {data_fmt}\n"

    if retirada.local_servico:
        message += f"📍 <b>Local:</b> {retirada.local_servico}\n"
    if retirada.observacao:
        message += f"📝 <b>Obs:</b> {retirada.observacao}\n"

    return message


def _build_batch_message(*, retiradas: list[RetiradaFerramenta], usuario: Usuario | None) -> str:
    retiradas_sorted = sorted(retiradas, key=lambda r: (getattr(r, "data_retirada", None) or datetime.min, r.id))

    nome_usuario = usuario.nome if usuario else f"Matrícula {retiradas_sorted[0].matricula}"
    data_fmt = TimeService.format_local(retiradas_sorted[-1].data_retirada, "%d/%m/%Y %H:%M")

    linhas_itens: list[str] = []
    for r in retiradas_sorted:
        item = Item.query.get(r.codigo_item)
        if not item:
            continue
        unidade = item.unidade or "un."
        linhas_itens.append(
            f"• <b>{item.descricao}</b> (cód: <code>{item.codigo_item}</code>) — <b>{r.quantidade}</b> {unidade}"
        )

    total_itens = len(linhas_itens)
    total_qtde = sum(int(getattr(r, "quantidade", 0) or 0) for r in retiradas_sorted)

    local_servico = retiradas_sorted[0].local_servico
    if any((r.local_servico or None) != (local_servico or None) for r in retiradas_sorted):
        local_servico = None

    observacao = retiradas_sorted[0].observacao
    if any((r.observacao or None) != (observacao or None) for r in retiradas_sorted):
        observacao = None

    message = "📤 <b>RETIRADA MÚLTIPLA DE FERRAMENTAS</b>\n\n"
    message += f"👤 <b>Funcionário:</b> {nome_usuario}\n"
    message += f"📅 <b>Data:</b> {data_fmt}\n"
    message += f"📦 <b>Itens:</b> {total_itens} (qtde total {total_qtde})\n\n"
    message += "\n".join(linhas_itens)

    if local_servico:
        message += f"\n\n📍 <b>Local:</b> {local_servico}"
    if observacao:
        message += f"\n📝 <b>Obs:</b> {observacao}"

    return message


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nome", required=True, help="Nome do usuário (ex: 'Gabriel (daburra)')")
    parser.add_argument("--minutes", type=int, default=10, help="Janela em minutos para buscar retiradas")
    parser.add_argument("--limit", type=int, default=5, help="Máximo de retiradas a processar")
    args = parser.parse_args()

    minutes = max(1, int(args.minutes))
    limit = max(1, int(args.limit))
    # `RetiradaFerramenta.data_retirada` usa `func.now()` (DB), então aqui usamos
    # `datetime.now()` para evitar erro de fuso (UTC vs local).
    since = datetime.now() - timedelta(minutes=minutes)

    app = create_app()
    summary = ProcessSummary()

    with app.app_context():
        if not TelegramService.is_enabled():
            print("Telegram está desabilitado pela configuração. Nada a fazer.")
            return 2

        retiradas = (
            db.session.query(RetiradaFerramenta)
            .join(Usuario, Usuario.matricula == RetiradaFerramenta.matricula)
            .filter(Usuario.nome.ilike(str(args.nome)))
            .filter(RetiradaFerramenta.data_retirada >= since)
            .order_by(RetiradaFerramenta.data_retirada.desc())
            .all()
        )

        summary.quantidade_total = int(sum((r.quantidade or 0) for r in retiradas) or 0)

        summary.retiradas_encontradas = len(retiradas)
        print(
            f"Retiradas encontradas (usuario='{args.nome}') desde {since.isoformat()}: {len(retiradas)} "
            f"(quantidade_total={summary.quantidade_total})"
        )

        if not retiradas:
            return 0

        admins = (
            db.session.query(TelegramUser)
            .join(Usuario, Usuario.matricula == TelegramUser.matricula)
            .filter(Usuario.is_admin == 1)
            .filter(TelegramUser.enabled == True)
            .filter(TelegramUser.chat_id.isnot(None))
            .all()
        )

        if not admins:
            print("Nenhum Telegram admin com chat_id configurado. Nada a enviar.")
            return 3

        selecionadas = retiradas[:limit]

        print("Retiradas a processar (mais recentes primeiro):")
        for r in selecionadas:
            item = Item.query.get(r.codigo_item)
            u = Usuario.query.get(r.matricula)
            desc = item.descricao if item else "(item não encontrado)"
            nome_u = u.nome if u else "(usuário não encontrado)"
            print(f"- id={r.id} data={r.data_retirada} codigo={r.codigo_item} qtde={r.quantidade} usuario={nome_u} desc={desc}")

        # Notificação consolidada
        u0 = Usuario.query.get(selecionadas[0].matricula)
        message_text = _build_batch_message(retiradas=selecionadas, usuario=u0)

        ids = [str(r.id) for r in sorted(selecionadas, key=lambda r: r.id)]
        digest = hashlib.sha1(",".join(ids).encode("utf-8")).hexdigest()[:16]
        batch_key_prefix = f"tool_withdraw_batch:{selecionadas[0].matricula}:{digest}"

        now_ts = int(_utcnow_naive().timestamp())

        try:
            for admin in admins:
                base_key = f"{batch_key_prefix}:admin:{admin.chat_id}"
                existing = (
                    db.session.query(TelegramOutbox)
                    .filter(TelegramOutbox.idempotency_key == base_key)
                    .first()
                )

                if existing is None:
                    q = TelegramService.enqueue_outbox_message(
                        chat_id=str(admin.chat_id),
                        recipient_name=admin.usuario.nome if getattr(admin, "usuario", None) else None,
                        message_type="tool_withdraw_batch",
                        message_text=message_text,
                        idempotency_key=base_key,
                        commit=False,
                    )
                    if q.get("success"):
                        summary.outbox_enfileiradas_novas += 1
                    continue

                if str(existing.status) in {"pending", "failed", "dead"}:
                    existing.status = "pending"
                    existing.available_at = _utcnow_naive()
                    existing.last_error = None
                    summary.outbox_requeue += 1
                    continue

                # sent: força reenvio criando nova outbox
                resend_key = f"{base_key}:resend:{now_ts}"
                q = TelegramService.enqueue_outbox_message(
                    chat_id=str(admin.chat_id),
                    recipient_name=admin.usuario.nome if getattr(admin, "usuario", None) else None,
                    message_type="tool_withdraw_batch",
                    message_text=message_text,
                    idempotency_key=resend_key,
                    commit=False,
                )
                if q.get("success"):
                    summary.outbox_resend_novas += 1

            summary.retiradas_processadas = len(selecionadas)
        except Exception as e:
            summary.erros += 1
            print(f"Erro ao enfileirar notificação consolidada: {e}")

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Falha ao commit no banco: {e}")
            return 1

        print(
            "Concluído: "
            f"retiradas_processadas={summary.retiradas_processadas} "
            f"outbox_novas={summary.outbox_enfileiradas_novas} "
            f"requeue={summary.outbox_requeue} "
            f"resend_novas={summary.outbox_resend_novas} "
            f"erros={summary.erros}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
