from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _coerce_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return Decimal(int(value))
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def format_number_br(value, decimals: int = 0, strip_trailing_zeros: bool = False, default: str = "0") -> str:
    number = _coerce_decimal(value)
    if number is None:
        return default

    decimals = max(0, int(decimals))
    quantum = Decimal("1") if decimals == 0 else Decimal("1." + ("0" * decimals))
    rounded = number.quantize(quantum, rounding=ROUND_HALF_UP)
    text = f"{rounded:,.{decimals}f}"
    text = text.replace(",", "X").replace(".", ",").replace("X", ".")

    if strip_trailing_zeros and decimals > 0:
        text = text.rstrip("0").rstrip(",")

    return text


def format_currency_br(value, default: str = "R$ 0,00") -> str:
    number = _coerce_decimal(value)
    if number is None:
        return default
    return f"R$ {format_number_br(number, 2)}"


def format_percent_br(value, decimals: int = 0, default: str = "0%") -> str:
    number = _coerce_decimal(value)
    if number is None:
        return default
    percent_value = number * Decimal("100")
    return f"{format_number_br(percent_value, decimals)}%"


def format_datetime_br(value, fmt: str = "%d/%m/%Y %H:%M", default: str = "-") -> str:
    if value is None or value == "":
        return default

    if isinstance(value, datetime):
        return value.strftime(fmt)

    if isinstance(value, date):
        return value.strftime(fmt.split()[0] if " " in fmt else fmt)

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.strftime(fmt)
        except ValueError:
            try:
                parsed_date = date.fromisoformat(value)
                return parsed_date.strftime(fmt.split()[0] if " " in fmt else fmt)
            except ValueError:
                return value

    return str(value)