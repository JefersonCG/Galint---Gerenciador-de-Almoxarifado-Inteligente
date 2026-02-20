from __future__ import annotations

import pathlib
import sqlite3
from typing import Any


def _table_columns(cur: sqlite3.Cursor, table: str) -> list[str]:
    rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
    return [row[1] for row in rows]


def main() -> None:
    db_path = pathlib.Path("instance") / "galint.db"
    if not db_path.exists():
        raise SystemExit(f"DB não encontrado: {db_path}")

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")] 
    print(f"DB: {db_path}")
    print(f"Tables: {len(tables)}")

    telegram_tables = [t for t in tables if "telegram" in t.lower()]
    print("Telegram tables:", telegram_tables)

    # Count users/admins (best-effort: tries common table names)
    for table in tables:
        lower = table.lower()
        if lower in {"usuario", "usuarios", "user", "users"}:
            cols = _table_columns(cur, table)
            if "is_admin" in cols:
                total, admins = cur.execute(
                    f"SELECT COUNT(*), SUM(CASE WHEN is_admin=1 THEN 1 ELSE 0 END) FROM {table}"
                ).fetchone()
                print(f"{table}: total={total} admins={admins or 0}")

    for table in telegram_tables:
        cols = _table_columns(cur, table)
        if "enabled" in cols:
            total, enabled = cur.execute(
                f"SELECT COUNT(*), SUM(CASE WHEN enabled=1 THEN 1 ELSE 0 END) FROM {table}"
            ).fetchone()
            print(f"{table}: total={total} enabled={enabled or 0}")

    outbox_table = next((t for t in tables if t.lower() == "telegram_outbox"), None)
    if not outbox_table:
        print("TelegramOutbox: tabela não encontrada")
        con.close()
        return

    outbox_cols = _table_columns(cur, outbox_table)
    print("TelegramOutbox cols:", outbox_cols)

    id_col = "id" if "id" in outbox_cols else ("id_outbox" if "id_outbox" in outbox_cols else outbox_cols[0])
    total_outbox = cur.execute(f"SELECT COUNT(*) FROM {outbox_table}").fetchone()[0]
    print("TelegramOutbox total:", total_outbox)

    rows = cur.execute(f"SELECT * FROM {outbox_table} ORDER BY {id_col} DESC LIMIT 15").fetchall()
    print("TelegramOutbox last 15:")

    def pick(row: sqlite3.Row, keys: list[str]) -> dict[str, Any]:
        return {k: row[k] for k in keys if k in row.keys()}

    for row in rows:
        subset = pick(
            row,
            [
                id_col,
                "created_at",
                "created_em",
                "status",
                "sent_at",
                "attempts",
                "error",
                "erro",
                "saida_id",
                "entrada_id",
                "chat_id",
                "matricula",
                "tipo",
                "message_type",
            ],
        )
        if not subset:
            subset = {k: row[k] for k in list(row.keys())[:10]}
        print(subset)

    con.close()


if __name__ == "__main__":
    main()
