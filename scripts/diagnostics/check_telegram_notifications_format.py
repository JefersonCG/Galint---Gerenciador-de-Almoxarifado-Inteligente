"""Diagnóstico: gerar texto das notificações (Telegram) sem enviar nada.

Uso (exemplos):
    ./.venv/Scripts/python.exe check_telegram_notifications_format.py --codigo 7891323003242
    ./.venv/Scripts/python.exe check_telegram_notifications_format.py --descricao "BRANCO FOSCO"

Este script desabilita serviços em background (scheduler/polling/saudação) para
que a execução seja segura e previsível.
"""

from __future__ import annotations

import argparse
import os


def _set_safe_env() -> None:
    # Forçar UTF-8 no console do Windows (evita UnicodeEncodeError ao imprimir emojis)
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    os.environ.setdefault("GALINT_DISABLE_BACKGROUND_SERVICES", "true")
    os.environ.setdefault("GALINT_TELEGRAM_POLLING", "false")
    os.environ.setdefault("GALINT_TELEGRAM_STARTUP_GREETING", "false")
    os.environ.setdefault("GALINT_TELEGRAM_OUTBOX_ENABLED", "false")
    os.environ.setdefault("GALINT_TELEGRAM_KEEP_WEBHOOK", "false")


_set_safe_env()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera o texto das notificações de inventário (devolução/ajuste) sem enviar Telegram.",
    )
    parser.add_argument("--codigo", help="Código/EAN do item (codigo_item)")
    parser.add_argument(
        "--descricao",
        help="Trecho da descrição do item (busca por contém, case-insensitive)",
    )
    args = parser.parse_args()

    from galint_flask import create_app
    from galint_flask.extensions import db
    from galint_flask.models import InventarioEvento, Item
    from galint_flask.services.embalagem_service import EmbalagemService
    from galint_flask.services.telegram_service import TelegramService

    app = create_app()

    with app.app_context():
        item = None

        if args.codigo:
            item = db.session.get(Item, args.codigo)

        if item is None and args.descricao:
            item = (
                db.session.query(Item)
                .filter(Item.descricao.ilike(f"%{args.descricao.strip()}%"))
                .order_by(Item.descricao.asc())
                .first()
            )

        if item is None:
            print("Item não encontrado. Use --codigo ou --descricao.")
            return 2

        print("=" * 90)
        print(f"ITEM: {item.codigo_item} — {item.descricao}")
        try:
            print(f"SALDO (display): {item.get_saldo_fisico_display()}")
        except Exception:
            pass

        try:
            if EmbalagemService.tem_embalagem(item) or EmbalagemService.tem_rolo_legacy(item):
                print(f"ESTOQUE FÍSICO: {EmbalagemService.formatar_estoque(item)}")
        except Exception:
            pass

        print("=" * 90)

        eventos = (
            db.session.query(InventarioEvento)
            .filter(InventarioEvento.codigo_item == item.codigo_item)
            .order_by(InventarioEvento.data_evento.desc())
            .all()
        )

        if not eventos:
            print("Nenhum InventarioEvento encontrado para este item.")
            return 0

        def _is_devolucao(ev: InventarioEvento) -> bool:
            t = (getattr(ev, "tipo", "") or "").lower()
            d = (getattr(ev, "descricao", "") or "").lower()
            return "devolu" in t or "devolu" in d

        evento_devolucao = next((ev for ev in eventos if _is_devolucao(ev)), None)
        evento_ajuste = next(
            (
                ev
                for ev in eventos
                if (not _is_devolucao(ev)) and float(getattr(ev, "quantidade", 0) or 0) != 0
            ),
            None,
        )

        if evento_devolucao:
            print("\n" + "#" * 90)
            print(f"DEVOLUÇÃO (evento id={evento_devolucao.id_evento}, qtd={evento_devolucao.quantidade:g})")
            print("#" * 90)
            print(TelegramService.format_devolucao_message(evento_devolucao, item))
        else:
            print("\nNenhum evento de devolução encontrado para este item.")

        if evento_ajuste:
            print("\n" + "#" * 90)
            print(f"AJUSTE (evento id={evento_ajuste.id_evento}, qtd={evento_ajuste.quantidade:g})")
            print("#" * 90)
            msg, msg_type, is_devolucao = TelegramService.format_inventory_event_message(evento_ajuste, item)
            print(f"(message_type={msg_type}, is_devolucao={is_devolucao})\n")
            print(msg)
        else:
            print("\nNenhum evento de ajuste encontrado para este item.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
