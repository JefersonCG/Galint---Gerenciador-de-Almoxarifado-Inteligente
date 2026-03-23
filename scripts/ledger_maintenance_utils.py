from __future__ import annotations

from datetime import datetime
from pathlib import Path

EXIT_OK = 0
EXIT_CRITICAL_DIVERGENCE = 2
EXIT_ORPHANS_FOUND = 3
EXIT_CRITICAL_DIVERGENCE_AND_ORPHANS = 4


def build_report_path(root: Path, prefix: str) -> Path:
    reports_dir = root / "reports" / "ledger_maintenance"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return reports_dir / f"{prefix}_{timestamp}.log"


def persist_execution_report(report_path: Path, lines: list[str]) -> Path:
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def write_execution_report(root: Path, prefix: str, lines: list[str]) -> Path:
    report_path = build_report_path(root, prefix)
    return persist_execution_report(report_path, lines)


def resolve_exit_code(*, has_critical_divergence: bool, has_orphans: bool) -> int:
    if has_critical_divergence and has_orphans:
        return EXIT_CRITICAL_DIVERGENCE_AND_ORPHANS
    if has_critical_divergence:
        return EXIT_CRITICAL_DIVERGENCE
    if has_orphans:
        return EXIT_ORPHANS_FOUND
    return EXIT_OK