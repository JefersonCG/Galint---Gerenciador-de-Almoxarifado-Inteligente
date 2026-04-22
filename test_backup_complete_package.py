from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from galint_flask.services.backup import BackupService


def _make_fake_app(*, root_path: Path, instance_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        config={
            "SQLALCHEMY_DATABASE_URI": "postgresql://user:secret@localhost/galint",
            "BACKUP_RETENTION_DAYS": 0,
            "BACKUP_RETENTION_COUNT": 0,
        },
        root_path=str(root_path),
        instance_path=str(instance_path),
    )


def test_create_complete_backup_package_gera_zip_e_remove_sql_intermediario() -> None:
    with tempfile.TemporaryDirectory(prefix="galint_backup_root_") as root_dir_name:
        root_dir = Path(root_dir_name)
        instance_dir = root_dir / "instance"
        instance_dir.mkdir(parents=True, exist_ok=True)
        app = _make_fake_app(root_path=root_dir, instance_path=instance_dir)
        service = BackupService(app)

        sql_name = "galint_backup_20260421_230000.sql"
        sql_path = service._backup_root / sql_name
        sql_path.write_text("SELECT 1;\n", encoding="utf-8")

        manifest = {
            "backup_kind": BackupService.COMPLETE_BACKUP_KIND,
            "manifest_schema_version": BackupService.MANIFEST_SCHEMA_VERSION,
            "database_dump": {
                "name": sql_name,
                "archive_path": f"database/{sql_name}",
            },
            "asset_entries": [],
            "compatibility": {},
        }

        with patch.object(BackupService, "_create_postgres_backup", return_value=sql_name), patch.object(
            BackupService,
            "_collect_complete_backup_assets",
            return_value=[],
        ), patch.object(
            BackupService,
            "_build_complete_backup_manifest",
            return_value=manifest,
        ), patch.object(
            BackupService,
            "_build_complete_backup_readme",
            return_value="backup completo",
        ):
            created_name = service._create_complete_backup_package()

        package_path = service._backup_root / created_name

        assert created_name.endswith(".zip")
        assert package_path.exists()
        assert not sql_path.exists()

        with zipfile.ZipFile(package_path) as archive:
            assert f"database/{sql_name}" in archive.namelist()
            assert "manifest.json" in archive.namelist()
            assert "README_backup_completo.txt" in archive.namelist()
            payload = json.loads(archive.read("manifest.json").decode("utf-8"))

        assert payload["backup_kind"] == BackupService.COMPLETE_BACKUP_KIND


def main() -> int:
    test_create_complete_backup_package_gera_zip_e_remove_sql_intermediario()
    print("OK - backup complete package")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())