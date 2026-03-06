from __future__ import annotations

from io import BytesIO
import re


class QRCodeService:
    DIGITS_13_RE = re.compile(r"^\d{13}$")

    @classmethod
    def validate_13_digits(cls, value: object) -> str:
        if value is None:
            raise ValueError("Valor ausente")
        if not isinstance(value, str):
            value = str(value)

        # Regras estritas: não aceitar espaços, \n, tabs ou caracteres invisíveis.
        if value != value.strip():
            raise ValueError("Valor inválido: não pode conter espaços no início/fim")
        if any(ch.isspace() for ch in value):
            raise ValueError("Valor inválido: não pode conter espaços/quebras de linha")

        if not cls.DIGITS_13_RE.fullmatch(value):
            raise ValueError("Valor inválido: precisa ter exatamente 13 dígitos numéricos")
        return value

    @classmethod
    def generate_png(cls, value: str, *, scale: int = 10, border: int = 4, error: str = "M") -> bytes:
        """Gera um QR Code PNG (não Micro QR) a partir de 13 dígitos.

        - segno==1.6.1
        - micro=False
        - error='M' (ou superior)
        - border=4 (quiet zone obrigatória)
        - scale >= 8 (padrão 10)
        """

        if scale < 8:
            raise ValueError("scale inválido: use >= 8")
        if border != 4:
            # Mantemos rígido por requisito
            raise ValueError("border inválido: use 4")

        payload = cls.validate_13_digits(value)

        try:
            import segno
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("Biblioteca 'segno' não instalada") from exc

        qr = segno.make(payload, error=error, micro=False)
        buffer = BytesIO()
        qr.save(
            buffer,
            kind="png",
            scale=scale,
            border=border,
            dark="black",
            light="white",
        )
        return buffer.getvalue()
