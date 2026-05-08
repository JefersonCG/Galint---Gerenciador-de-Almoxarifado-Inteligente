from __future__ import annotations

import json
import secrets
from datetime import datetime
from io import BytesIO
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
        for path in cls.get_layouts_dir().rglob(f"*{cls.LAYOUT_EXTENSION}"):
            if not path.is_file():
                continue
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
    def build_pdf_export(cls, name: str | None, snapshot: dict[str, Any]) -> tuple[BytesIO, str]:
        normalized_snapshot = cls._normalize_snapshot(snapshot)
        pdf_bytes = cls._render_snapshot_pdf(normalized_snapshot)
        buffer = BytesIO(pdf_bytes)
        buffer.seek(0)
        return buffer, cls._build_pdf_filename(name)

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
            "filename": cls._to_layout_filename(path),
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
        normalized_path = Path(normalized.replace("\\", "/"))
        if normalized_path.is_absolute() or not normalized.endswith(cls.LAYOUT_EXTENSION):
            raise ValueError("Arquivo de layout inválido.")
        if any(part in {"", ".", ".."} for part in normalized_path.parts):
            raise ValueError("Arquivo de layout inválido.")
        resolved_path = (cls.get_layouts_dir() / normalized_path).resolve()
        layouts_root = cls.get_layouts_dir().resolve()
        try:
            resolved_path.relative_to(layouts_root)
        except ValueError as exc:
            raise ValueError("Arquivo de layout inválido.") from exc
        return resolved_path

    @classmethod
    def _to_layout_filename(cls, path: Path) -> str:
        return path.relative_to(cls.get_layouts_dir()).as_posix()

    @classmethod
    def _slugify_name(cls, name: str) -> str:
        slug = secure_filename(name).strip("._-")
        if not slug:
            slug = "layout"
        return slug[:80]

    @classmethod
    def _build_pdf_filename(cls, raw_name: Any) -> str:
        base_name = cls._slugify_name(str(raw_name or "").strip() or "etiquetas-a4")
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"{base_name}_{timestamp}.pdf"

    @classmethod
    def _render_snapshot_pdf(cls, snapshot: dict[str, Any]) -> bytes:
        try:
            from reportlab.graphics import renderPDF
            from reportlab.graphics.barcode import createBarcodeDrawing
            from reportlab.lib.colors import HexColor, white
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.units import mm
            from reportlab.pdfbase.pdfmetrics import stringWidth
            from reportlab.pdfgen import canvas as pdf_canvas
        except Exception as exc:
            raise ValueError(
                "Biblioteca de PDF nao instalada. Instale 'reportlab' (pip install reportlab)."
            ) from exc

        page = snapshot.get("page") or {}
        items = snapshot.get("items") or []
        orientation = str(page.get("orientation") or "portrait").strip().lower()
        page_size = landscape(A4) if orientation == "landscape" else A4
        page_width_pt, page_height_pt = page_size
        page_width_mm = page_width_pt / mm
        page_height_mm = page_height_pt / mm

        dark_text = HexColor("#111827")
        muted_text = HexColor("#334155")
        default_border_color = HexColor("#64748b")
        min_visible_border_pt = 1.2

        def _as_float(value: Any, default: float) -> float:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return default
            if numeric != numeric:
                return default
            return numeric

        def _as_bool(value: Any, default: bool) -> bool:
            if value is None:
                return default
            return bool(value)

        def _normalize_border_style(value: Any) -> str:
            return "solid" if str(value or "").strip().lower() == "solid" else "dashed"

        def _normalize_border_color(value: Any):
            raw = str(value or "").strip()
            if len(raw) == 7 and raw.startswith("#"):
                try:
                    return HexColor(raw)
                except Exception:
                    return default_border_color
            return default_border_color

        def _resolve_page_index(raw_item: Any) -> int:
            try:
                return max(0, int(raw_item.get("pageIndex") or 0))
            except (AttributeError, TypeError, ValueError):
                return 0

        def _truncate_text(text: Any, font_name: str, font_size: float, max_width: float) -> str:
            normalized = " ".join(str(text or "").split())
            if not normalized or max_width <= 0:
                return ""
            if stringWidth(normalized, font_name, font_size) <= max_width:
                return normalized
            suffix = "..."
            allowed = normalized
            while allowed and stringWidth(allowed + suffix, font_name, font_size) > max_width:
                allowed = allowed[:-1]
            allowed = allowed.rstrip()
            return (allowed + suffix) if allowed else suffix

        def _draw_aligned_text(
            pdf,
            text: str,
            *,
            left_x: float,
            right_x: float,
            baseline_y: float,
            font_name: str,
            font_size: float,
            align: str,
            fill_color,
        ) -> None:
            if not text:
                return
            pdf.setFillColor(fill_color)
            pdf.setFont(font_name, font_size)
            if align == "left":
                pdf.drawString(left_x, baseline_y, text)
                return
            if align == "right":
                pdf.drawRightString(right_x, baseline_y, text)
                return
            pdf.drawCentredString((left_x + right_x) / 2.0, baseline_y, text)

        def _draw_label_border(
            pdf,
            *,
            x_pt: float,
            y_pt: float,
            width_pt: float,
            height_pt: float,
            border_width_pt: float,
            border_style: str,
            border_color,
        ) -> None:
            if border_width_pt <= 0:
                return
            inset_pt = border_width_pt / 2.0
            border_draw_width_pt = max(0.0, width_pt - border_width_pt)
            border_draw_height_pt = max(0.0, height_pt - border_width_pt)
            if border_draw_width_pt <= 0 or border_draw_height_pt <= 0:
                return
            pdf.saveState()
            pdf.setLineWidth(border_width_pt)
            pdf.setStrokeColor(border_color)
            if border_style == "dashed":
                dash_pt = max(3.2, border_width_pt * 6.0)
                gap_pt = max(2.0, border_width_pt * 3.5)
                pdf.setDash(dash_pt, gap_pt)
            else:
                pdf.setDash()
            pdf.rect(
                x_pt + inset_pt,
                y_pt + inset_pt,
                border_draw_width_pt,
                border_draw_height_pt,
                fill=0,
                stroke=1,
            )
            pdf.restoreState()

        buffer = BytesIO()
        pdf = pdf_canvas.Canvas(buffer, pagesize=page_size, pageCompression=1)
        pdf.setTitle("Editor de Etiquetas")
        pdf.setAuthor("GALINT")

        total_pages = max(1, max((_resolve_page_index(item) for item in items), default=0) + 1)
        for page_index in range(total_pages):
            if page_index > 0:
                pdf.showPage()
                pdf.setPageSize(page_size)

            pdf.setFillColor(white)
            pdf.rect(0, 0, page_width_pt, page_height_pt, fill=1, stroke=0)

            for raw_item in items:
                if _resolve_page_index(raw_item) != page_index or not isinstance(raw_item, dict):
                    continue

                width_mm = max(24.0, min(_as_float(raw_item.get("widthMm"), 72.0), max(24.0, page_width_mm - 4.0)))
                height_mm = max(5.0, min(_as_float(raw_item.get("heightMm"), 40.0), max(5.0, page_height_mm - 4.0)))
                x_mm = max(0.0, min(_as_float(raw_item.get("xMm"), 0.0), max(0.0, page_width_mm - width_mm)))
                y_mm = max(0.0, min(_as_float(raw_item.get("yMm"), 0.0), max(0.0, page_height_mm - height_mm)))
                padding_mm = max(0.2, min(_as_float(raw_item.get("paddingMm"), 3.0), min(12.0, max(0.2, height_mm / 4.0))))

                width_pt = width_mm * mm
                height_pt = height_mm * mm
                x_pt = x_mm * mm
                y_pt = page_height_pt - ((y_mm + height_mm) * mm)
                padding_pt = padding_mm * mm
                content_left_pt = x_pt + padding_pt
                content_right_pt = x_pt + width_pt - padding_pt
                available_width_pt = max(12.0, content_right_pt - content_left_pt)
                available_height_pt = max(1.0, height_pt - (padding_pt * 2.0))

                align = str(raw_item.get("align") or "center").strip().lower()
                if align not in {"left", "center", "right"}:
                    align = "center"
                payload = str(raw_item.get("codigo") or "").strip()
                title_text = str(
                    raw_item.get("customTitle")
                    or raw_item.get("descricao")
                    or payload
                    or ""
                ).strip()
                show_name = _as_bool(raw_item.get("showName"), True) and bool(title_text)
                show_code = _as_bool(raw_item.get("showCode"), True) and bool(payload)
                title_font_pt = max(6.0, min(_as_float(raw_item.get("fontSizePx"), 14.0) * 0.75, 24.0))
                code_font_pt = max(6.0, min(_as_float(raw_item.get("codeFontSizePx"), 11.0) * 0.75, 18.0))
                desired_barcode_pt = max(1.0 * mm, _as_float(raw_item.get("barcodeHeightMm"), 18.0) * mm)
                show_border = _as_bool(raw_item.get("showBorder"), True)
                border_width_pt = max(0.0, min(_as_float(raw_item.get("borderWidthMm"), 0.3), 2.0) * mm)
                rendered_border_width_pt = max(min_visible_border_pt, border_width_pt) if border_width_pt > 0 else 0.0
                border_style = _normalize_border_style(raw_item.get("borderStyle"))
                border_color = _normalize_border_color(raw_item.get("borderColor"))

                title_block_pt = title_font_pt * 1.15 if show_name else 0.0
                title_gap_pt = 1.6 * mm if show_name else 0.0
                code_block_pt = code_font_pt * 1.15 if show_code else 0.0
                code_gap_pt = 1.5 * mm if show_code else 0.0
                max_barcode_pt = max(
                    12.0,
                    available_height_pt - title_block_pt - title_gap_pt - code_block_pt - code_gap_pt,
                )
                barcode_block_pt = min(desired_barcode_pt, max_barcode_pt)
                total_block_pt = title_block_pt + title_gap_pt + barcode_block_pt + code_gap_pt + code_block_pt
                extra_vertical_pt = max(0.0, available_height_pt - total_block_pt)
                current_top_pt = y_pt + height_pt - padding_pt - (extra_vertical_pt / 2.0)

                pdf.setFillColor(white)
                pdf.rect(x_pt, y_pt, width_pt, height_pt, fill=1, stroke=0)

                if show_name:
                    title_draw = _truncate_text(title_text, "Helvetica-Bold", title_font_pt, available_width_pt)
                    title_baseline_pt = current_top_pt - title_font_pt
                    _draw_aligned_text(
                        pdf,
                        title_draw,
                        left_x=content_left_pt,
                        right_x=content_right_pt,
                        baseline_y=title_baseline_pt,
                        font_name="Helvetica-Bold",
                        font_size=title_font_pt,
                        align=align,
                        fill_color=dark_text,
                    )
                    current_top_pt -= title_block_pt + title_gap_pt

                barcode_y_pt = current_top_pt - barcode_block_pt
                if payload:
                    try:
                        drawing = createBarcodeDrawing(
                            "Code128",
                            value=payload,
                            barHeight=barcode_block_pt,
                            humanReadable=False,
                        )
                        drawing_width_pt = max(float(getattr(drawing, "width", 0.0) or 0.0), 1.0)
                        drawing_height_pt = max(float(getattr(drawing, "height", 0.0) or 0.0), 1.0)
                        pdf.saveState()
                        pdf.translate(content_left_pt, barcode_y_pt)
                        pdf.scale(available_width_pt / drawing_width_pt, barcode_block_pt / drawing_height_pt)
                        renderPDF.draw(drawing, pdf, 0, 0)
                        pdf.restoreState()
                    except Exception:
                        fallback_text = _truncate_text(payload, "Helvetica", code_font_pt, available_width_pt)
                        fallback_baseline_pt = barcode_y_pt + (barcode_block_pt / 2.0) - (code_font_pt / 2.0)
                        _draw_aligned_text(
                            pdf,
                            fallback_text,
                            left_x=content_left_pt,
                            right_x=content_right_pt,
                            baseline_y=fallback_baseline_pt,
                            font_name="Helvetica",
                            font_size=code_font_pt,
                            align=align,
                            fill_color=dark_text,
                        )
                current_top_pt = barcode_y_pt - code_gap_pt

                if show_code:
                    code_draw = _truncate_text(payload, "Helvetica", code_font_pt, available_width_pt)
                    code_baseline_pt = current_top_pt - code_font_pt
                    _draw_aligned_text(
                        pdf,
                        code_draw,
                        left_x=content_left_pt,
                        right_x=content_right_pt,
                        baseline_y=code_baseline_pt,
                        font_name="Helvetica",
                        font_size=code_font_pt,
                        align=align,
                        fill_color=muted_text,
                    )

                if show_border:
                    _draw_label_border(
                        pdf,
                        x_pt=x_pt,
                        y_pt=y_pt,
                        width_pt=width_pt,
                        height_pt=height_pt,
                        border_width_pt=rendered_border_width_pt,
                        border_style=border_style,
                        border_color=border_color,
                    )

        pdf.save()
        return buffer.getvalue()

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