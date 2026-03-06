import os
import json
import time
from typing import Any


def _ensure_backup_dir() -> str:
    backup_dir = os.path.join(os.getcwd(), "instance", "backups")
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def save_json_backup(data: Any, prefix: str = "backup", keep: int = 2) -> str:
    """Save `data` as a JSON backup file and prune older backups keeping `keep` files.

    Returns the path to the created backup file.
    """
    backup_dir = _ensure_backup_dir()
    ts = int(time.time())
    filename = f"{prefix}_{ts}.json"
    path = os.path.join(backup_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    _prune_backups(backup_dir, prefix, keep)
    return path


def _prune_backups(backup_dir: str, prefix: str, keep: int) -> None:
    """Keep only the most recent `keep` files matching prefix in backup_dir."""
    files = []
    for name in os.listdir(backup_dir):
        if name.startswith(prefix + "_") and name.endswith(".json"):
            full = os.path.join(backup_dir, name)
            try:
                mtime = os.path.getmtime(full)
            except OSError:
                mtime = 0
            files.append((mtime, full))
    # sort by modification time descending (newest first)
    files.sort(key=lambda x: x[0], reverse=True)
    # keep the first `keep`, remove the rest
    to_remove = files[keep:]
    for _mtime, path in to_remove:
        try:
            os.remove(path)
        except OSError:
            pass


if __name__ == "__main__":
    # simple demo when run directly
    p = save_json_backup({"demo": True, "ts": int(time.time())}, prefix="demo_backup", keep=2)
    print("Wrote:", p)
