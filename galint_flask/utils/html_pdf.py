"""Renderização de HTML/CSS para PDF.

Backend principal: WeasyPrint.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HtmlToPdfResult:
    pdf_bytes: bytes
    engine: str


def render_html_to_pdf(*, html: str, base_url: str | None = None) -> HtmlToPdfResult:
    """Converte um HTML (string) em PDF.

    - `base_url` é importante para resolver URLs relativas (CSS, imagens, fontes).
    """

    try:
        from weasyprint import HTML  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "WeasyPrint não está disponível para gerar PDF via HTML/CSS. "
            "Instale com: pip install weasyprint"
        ) from exc

    if not isinstance(html, str) or not html.strip():
        raise ValueError("HTML vazio para geração de PDF")

    pdf_bytes = HTML(string=html, base_url=base_url).write_pdf()
    return HtmlToPdfResult(pdf_bytes=pdf_bytes, engine="weasyprint")
