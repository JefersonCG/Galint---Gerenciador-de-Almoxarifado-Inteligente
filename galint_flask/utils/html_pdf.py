"""Renderização de HTML/CSS para PDF.

Backend principal: WeasyPrint.
Fallback: ReportLab para ambientes sem as bibliotecas nativas do WeasyPrint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from io import BytesIO


@dataclass(frozen=True)
class HtmlToPdfResult:
    pdf_bytes: bytes
    engine: str


def _strip_inline_html_to_text(raw_html: str) -> str:
    cleaned = re.sub(r"<script.*?</script>", "", raw_html, flags=re.I | re.S)
    cleaned = re.sub(r"<style.*?</style>", "", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"<[^>]+>", "\n", cleaned)
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"\r\n?", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _fallback_reportlab_pdf(html: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    title_text = re.sub(r"<[^>]+>", "", title_match.group(1)) if title_match else "Relatório"
    title_text = unescape(title_text).strip() or "Relatório"

    text = _strip_inline_html_to_text(html)
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]

    styles = getSampleStyleSheet()
    story = [Paragraph(title_text, styles["Title"]), Spacer(1, 12)]
    for block in blocks[:30]:
        story.append(Paragraph(block, ParagraphStyle("BodyText", parent=styles["BodyText"], fontSize=9, leading=12)))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=title_text)
    doc.build(story)
    return buffer.getvalue()


def render_html_to_pdf(*, html: str, base_url: str | None = None) -> HtmlToPdfResult:
    """Converte um HTML (string) em PDF.

    - `base_url` é importante para resolver URLs relativas (CSS, imagens, fontes).
    """

    if not isinstance(html, str) or not html.strip():
        raise ValueError("HTML vazio para geração de PDF")

    try:
        from weasyprint import HTML  # type: ignore
        pdf_bytes = HTML(string=html, base_url=base_url).write_pdf()
        return HtmlToPdfResult(pdf_bytes=pdf_bytes, engine="weasyprint")
    except Exception as exc:  # pragma: no cover - fallback para ambientes sem bibliotecas nativas
        try:
            pdf_bytes = _fallback_reportlab_pdf(html)
            return HtmlToPdfResult(pdf_bytes=pdf_bytes, engine="reportlab-fallback")
        except Exception:
            raise RuntimeError(
                "WeasyPrint não está disponível para gerar PDF via HTML/CSS e o fallback do ReportLab também falhou."
            ) from exc
