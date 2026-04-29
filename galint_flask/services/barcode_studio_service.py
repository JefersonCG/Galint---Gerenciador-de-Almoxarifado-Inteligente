from __future__ import annotations

import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from werkzeug.utils import secure_filename

from ..paths import get_data_dir


class BarcodeStudioService:
    """Gerencia layouts persistidos do Editor de Etiquetas."""

    LAYOUT_FORMAT = "galint-label-layout"
    LAYOUT_VERSION = 1
    LAYOUT_EXTENSION = ".galintetq"
    LAYOUT_DIRNAME = "label_layouts"
    PENDING_IMPORT_DIRNAME = "label_layout_imports"
    PENDING_IMPORT_MAX_AGE_SECONDS = 60 * 60 * 24

    @classmethod
    def get_layouts_dir(cls) -> Path:
        layouts_dir = get_data_dir() / cls.LAYOUT_DIRNAME
        layouts_dir.mkdir(parents=True, exist_ok=True)
        return layouts_dir

    @classmethod
    def get_layouts_dir_display(cls) -> str:
        try:
            return str(cls.get_layouts_dir().resolve())
        except OSError:
            return str(cls.get_layouts_dir())

    @classmethod
    def get_pending_imports_dir(cls) -> Path:
        imports_dir = get_data_dir() / cls.PENDING_IMPORT_DIRNAME
        imports_dir.mkdir(parents=True, exist_ok=True)
        return imports_dir

    @classmethod
    def list_layouts(cls) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for path in cls.get_layouts_dir().glob(f"*{cls.LAYOUT_EXTENSION}"):
            try:
                entries.append(cls._build_layout_response(path, include_snapshot=False))
            except Exception:
                continue
        entries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return entries

    @classmethod
    def get_layout(cls, filename: str) -> dict[str, Any]:
        path = cls._resolve_layout_path(filename)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(filename)
        return cls._build_layout_response(path, include_snapshot=True)

    @classmethod
    def create_layout(cls, name: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        normalized_name = cls._normalize_name(name)
        normalized_snapshot = cls._normalize_snapshot(snapshot)
        path = cls._allocate_new_layout_path(normalized_name)
        cls._write_layout_document(path, normalized_name, normalized_snapshot)
        return cls._build_layout_response(path, include_snapshot=True)

    @classmethod
    def update_layout(cls, filename: str, name: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        path = cls._resolve_layout_path(filename)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(filename)
        normalized_name = cls._normalize_name(name)
        normalized_snapshot = cls._normalize_snapshot(snapshot)
        cls._write_layout_document(path, normalized_name, normalized_snapshot)
        return cls._build_layout_response(path, include_snapshot=True)

    @classmethod
    def delete_layout(cls, filename: str) -> None:
        path = cls._resolve_layout_path(filename)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(filename)
        path.unlink()

    @classmethod
    def build_export_document(cls, name: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        normalized_name = cls._normalize_name(name)
        normalized_snapshot = cls._normalize_snapshot(snapshot)
        return cls._build_layout_document(normalized_name, normalized_snapshot)

    @classmethod
    def register_pending_import(cls, file_path: str | Path) -> dict[str, Any]:
        source_path = Path(file_path)
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(str(source_path))
        document = cls.read_layout_document_file(source_path)
        token = secrets.token_urlsafe(24)
        payload = {
            "created_at": cls._utcnow_iso(),
            "source_name": source_path.name,
            "document": document,
        }
        pending_path = cls.get_pending_imports_dir() / f"{token}.json"
        pending_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cls._cleanup_expired_pending_imports()
        return {
            "token": token,
            "name": str(document.get("name") or source_path.stem).strip() or source_path.stem,
            "source_name": source_path.name,
        }

    @classmethod
    def consume_pending_import(cls, token: str) -> dict[str, Any]:
        pending_path = cls._resolve_pending_import_path(token)
        if not pending_path.exists() or not pending_path.is_file():
            raise FileNotFoundError(str(token))
        payload = json.loads(pending_path.read_text(encoding="utf-8"))
        pending_path.unlink(missing_ok=True)
        if not isinstance(payload, dict):
            raise ValueError("Importação pendente inválida.")
        created_at = str(payload.get("created_at") or "").strip()
        if created_at:
            created_dt = cls._parse_iso_timestamp(created_at)
            if created_dt is not None:
                age_seconds = (datetime.utcnow() - created_dt).total_seconds()
                if age_seconds > cls.PENDING_IMPORT_MAX_AGE_SECONDS:
                    raise FileNotFoundError(str(token))
        document = cls._normalize_layout_document(payload.get("document"), fallback_name=payload.get("source_name") or "Layout importado")
        return {
            "token": token,
            "source_name": str(payload.get("source_name") or "").strip(),
            "name": str(document.get("name") or "Layout importado").strip() or "Layout importado",
            "snapshot": {
                "page": document.get("page") or {},
                "items": document.get("items") or [],
            },
            "format": str(document.get("format") or cls.LAYOUT_FORMAT),
            "version": int(document.get("version") or cls.LAYOUT_VERSION),
        }

    @classmethod
    def read_layout_document_file(cls, file_path: str | Path) -> dict[str, Any]:
        source_path = Path(file_path)
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(str(source_path))
        document = cls._read_json_file(source_path)
        return cls._normalize_layout_document(document, fallback_name=source_path.stem)

    @classmethod
    def _build_layout_response(cls, path: Path, *, include_snapshot: bool) -> dict[str, Any]:
        document = cls._read_layout_document(path)
        saved_at = str(document.get("saved_at") or cls._stat_timestamp(path))
        payload: dict[str, Any] = {
            "filename": path.name,
            "name": str(document.get("name") or path.stem).strip() or path.stem,
            "updated_at": saved_at,
            "saved_at": saved_at,
            "size_bytes": path.stat().st_size,
        }
        if include_snapshot:
            payload["snapshot"] = {
                "page": document.get("page") or {},
                "items": document.get("items") or [],
            }
            payload["format"] = str(document.get("format") or cls.LAYOUT_FORMAT)
            payload["version"] = int(document.get("version") or cls.LAYOUT_VERSION)
        return payload

    @classmethod
    def _write_layout_document(cls, path: Path, name: str, snapshot: dict[str, Any]) -> None:
        document = cls._build_layout_document(name, snapshot)
        serialized = json.dumps(document, ensure_ascii=False, indent=2)
        path.write_text(serialized + "\n", encoding="utf-8")

    @classmethod
    def _build_layout_document(cls, name: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "format": cls.LAYOUT_FORMAT,
            "version": cls.LAYOUT_VERSION,
            "name": name,
            "saved_at": cls._utcnow_iso(),
            "page": snapshot["page"],
            "items": snapshot["items"],
        }

    @classmethod
    def _read_layout_document(cls, path: Path) -> dict[str, Any]:
        document = cls._read_json_file(path)
        return cls._normalize_layout_document(document, fallback_name=path.stem)

    @classmethod
    def _normalize_layout_document(cls, document: Any, *, fallback_name: Any) -> dict[str, Any]:
        if not isinstance(document, dict):
            raise ValueError("Layout inválido.")
        snapshot = cls._normalize_snapshot(
            {
                "page": document.get("page"),
                "items": document.get("items"),
            }
        )
        return {
            **document,
            "page": snapshot["page"],
            "items": snapshot["items"],
            "name": cls._normalize_name(document.get("name") or fallback_name),
            "format": str(document.get("format") or cls.LAYOUT_FORMAT),
            "version": int(document.get("version") or cls.LAYOUT_VERSION),
        }

    @classmethod
    def _normalize_snapshot(cls, snapshot: Any) -> dict[str, Any]:
        if not isinstance(snapshot, dict):
            raise ValueError("Layout inválido. Envie a composição atual da folha.")
        page = snapshot.get("page")
        items = snapshot.get("items")
        if not isinstance(page, dict) or not isinstance(items, list):
            raise ValueError("Layout inválido. Estrutura de folha ou etiquetas ausente.")
        try:
            normalized = json.loads(
                json.dumps(
                    {
                        "page": page,
                        "items": items,
                    },
                    ensure_ascii=False,
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Layout inválido. Há campos não serializáveis.") from exc
        return {
            "page": normalized.get("page") or {},
            "items": normalized.get("items") or [],
        }

    @classmethod
    def _normalize_name(cls, raw_name: Any) -> str:
        name = str(raw_name or "").strip()
        if not name:
            raise ValueError("Informe um nome para o layout.")
        return name[:120]

    @classmethod
    def _allocate_new_layout_path(cls, name: str) -> Path:
        base_slug = cls._slugify_name(name)
        layouts_dir = cls.get_layouts_dir()
        candidate = layouts_dir / f"{base_slug}{cls.LAYOUT_EXTENSION}"
        counter = 2
        while candidate.exists():
            candidate = layouts_dir / f"{base_slug}-{counter}{cls.LAYOUT_EXTENSION}"
            counter += 1
        return candidate

    @classmethod
    def _resolve_layout_path(cls, filename: str) -> Path:
        normalized = str(filename or "").strip()
        if not normalized:
            raise ValueError("Arquivo de layout inválido.")
        if normalized != Path(normalized).name or not normalized.endswith(cls.LAYOUT_EXTENSION):
            raise ValueError("Arquivo de layout inválido.")
        return cls.get_layouts_dir() / normalized

    @classmethod
    def _slugify_name(cls, name: str) -> str:
        slug = secure_filename(name).strip("._-")
        if not slug:
            slug = "layout"
        return slug[:80]

    @classmethod
    def _resolve_pending_import_path(cls, token: str) -> Path:
        normalized = str(token or "").strip()
        if not normalized or normalized != Path(normalized).stem:
            raise ValueError("Token de importação inválido.")
        return cls.get_pending_imports_dir() / f"{normalized}.json"

    @classmethod
    def _cleanup_expired_pending_imports(cls) -> None:
        now = datetime.utcnow()
        for path in cls.get_pending_imports_dir().glob("*.json"):
            try:
                age_seconds = (now - datetime.utcfromtimestamp(path.stat().st_mtime)).total_seconds()
            except OSError:
                continue
            if age_seconds <= cls.PENDING_IMPORT_MAX_AGE_SECONDS:
                continue
            try:
                path.unlink()
            except OSError:
                continue

    @staticmethod
    def _parse_iso_timestamp(value: str) -> datetime | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            return parsed.replace(tzinfo=None)
        return parsed

    @staticmethod
    def _read_json_file(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8-sig"))

    @staticmethod
    def _utcnow_iso() -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    @staticmethod
    def _stat_timestamp(path: Path) -> str:
        return datetime.utcfromtimestamp(path.stat().st_mtime).replace(microsecond=0).isoformat() + "Z"


barcode_studio_service = BarcodeStudioService()