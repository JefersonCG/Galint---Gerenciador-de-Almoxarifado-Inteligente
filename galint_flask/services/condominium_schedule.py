from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from typing import Any

from ..models import CondominiumScheduleEvent
from ..utils.time_service import TimeService


EVENT_TYPE_LABELS = {
    "audiencia_judicial": "Audiência judicial",
    "mudanca_entrada": "Mudança de entrada",
    "mudanca_saida": "Mudança de saída",
    "reserva_espaco": "Reserva de espaço",
    "entrevista": "Entrevista",
    "prestador": "Prestador",
    "reuniao": "Reunião",
    "manutencao": "Manutenção",
    "condominio": "Condomínio",
    "compromisso": "Compromisso",
}

SCOPE_LABELS = {
    "administracao": "Administração",
    "condominio": "Condomínio",
    "morador": "Morador",
    "judicial": "Judicial",
}

STATUS_LABELS = {
    "agendado": "Agendado",
    "confirmado": "Confirmado",
    "em_andamento": "Em andamento",
    "concluido": "Concluído",
    "cancelado": "Cancelado",
}

PRIORITY_LABELS = {
    "baixa": "Baixa",
    "normal": "Normal",
    "alta": "Alta",
    "critica": "Crítica",
}

MONTH_LABELS = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

ACTIVE_STATUSES = ("agendado", "confirmado", "em_andamento")

FIXED_NATIONAL_HOLIDAYS = {
    (1, 1): "Confraternização Universal",
    (4, 21): "Tiradentes",
    (5, 1): "Dia do Trabalho",
    (9, 7): "Independência do Brasil",
    (10, 12): "Nossa Senhora Aparecida",
    (11, 2): "Finados",
    (11, 15): "Proclamação da República",
    (11, 20): "Consciência Negra",
    (12, 25): "Natal",
}

FIXED_RIO_STATE_HOLIDAYS = {
    (4, 23): "São Jorge",
}


def today_local() -> date:
    return TimeService.now_local().date()


def now_local_naive() -> datetime:
    return TimeService.now_local().replace(tzinfo=None)


def normalize_event_type(value: object) -> str:
    event_type = str(value or "").strip().lower()
    return event_type if event_type in EVENT_TYPE_LABELS else "compromisso"


def normalize_scope(value: object) -> str:
    scope = str(value or "").strip().lower()
    return scope if scope in SCOPE_LABELS else "administracao"


def normalize_status(value: object) -> str:
    status = str(value or "").strip().lower()
    return status if status in STATUS_LABELS else "agendado"


def normalize_priority(value: object) -> str:
    priority = str(value or "").strip().lower()
    return priority if priority in PRIORITY_LABELS else "normal"


def event_time_label(event: CondominiumScheduleEvent) -> str:
    return event.time_label()


def event_type_label(event: CondominiumScheduleEvent) -> str:
    return EVENT_TYPE_LABELS.get(event.event_type, "Compromisso")


def event_scope_label(event: CondominiumScheduleEvent) -> str:
    return SCOPE_LABELS.get(event.scope, "Administracao")


def event_status_label(event: CondominiumScheduleEvent) -> str:
    return STATUS_LABELS.get(event.status, "Agendado")


def event_priority_label(event: CondominiumScheduleEvent) -> str:
    return PRIORITY_LABELS.get(event.priority, "Normal")


def event_unit_label(event: CondominiumScheduleEvent) -> str:
    return event.related_label()


def event_to_view(event: CondominiumScheduleEvent) -> dict[str, object]:
    return {
        "id": event.id,
        "date": event.event_date,
        "date_iso": event.event_date.isoformat(),
        "time_label": event_time_label(event),
        "title": event.title,
        "event_type": event.event_type,
        "event_type_label": event_type_label(event),
        "scope": event.scope,
        "scope_label": event_scope_label(event),
        "status": event.status,
        "status_label": event_status_label(event),
        "priority": event.priority,
        "priority_label": event_priority_label(event),
        "related_label": event_unit_label(event),
        "location": event.location,
        "contact_name": event.contact_name,
        "contact_phone": event.contact_phone,
        "description": event.description,
        "reminder_minutes": event.reminder_minutes,
    }


def event_sort_key(event: CondominiumScheduleEvent) -> tuple[Any, ...]:
    return (event.event_date, event.start_time or time.max, event.end_time or time.max, event.title.casefold())


def month_bounds(month_date: date) -> tuple[date, date]:
    _, last_day = calendar.monthrange(month_date.year, month_date.month)
    return date(month_date.year, month_date.month, 1), date(month_date.year, month_date.month, last_day)


def shift_month(month_date: date, offset: int) -> date:
    month_index = (month_date.year * 12) + (month_date.month - 1) + offset
    year = month_index // 12
    month = (month_index % 12) + 1
    return date(year, month, 1)


def easter_date(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def holiday_name(day: date) -> str:
    labels: list[str] = []
    fixed_key = (day.month, day.day)
    national = FIXED_NATIONAL_HOLIDAYS.get(fixed_key)
    if national:
        labels.append(national)

    easter = easter_date(day.year)
    movable_holidays = {
        easter - timedelta(days=48): "Carnaval",
        easter - timedelta(days=47): "Carnaval",
        easter - timedelta(days=2): "Paixão de Cristo",
        easter + timedelta(days=60): "Corpus Christi",
    }
    movable = movable_holidays.get(day)
    if movable:
        labels.append(movable)

    state = FIXED_RIO_STATE_HOLIDAYS.get(fixed_key)
    if state and state not in labels:
        labels.append(state)

    return " · ".join(labels)


def build_calendar_context(*, month_date: date, selected_date: date) -> dict[str, object]:
    first_day, last_day = month_bounds(month_date)
    events = (
        CondominiumScheduleEvent.query
        .filter(CondominiumScheduleEvent.event_date >= first_day, CondominiumScheduleEvent.event_date <= last_day)
        .order_by(CondominiumScheduleEvent.event_date.asc(), CondominiumScheduleEvent.start_time.asc(), CondominiumScheduleEvent.title.asc())
        .all()
    )
    events_by_day: dict[date, list[CondominiumScheduleEvent]] = {}
    for event in events:
        events_by_day.setdefault(event.event_date, []).append(event)

    today = today_local()
    first_weekday, last_day_number = calendar.monthrange(month_date.year, month_date.month)
    cells: list[date | None] = [None] * first_weekday
    cells.extend(date(month_date.year, month_date.month, day) for day in range(1, last_day_number + 1))
    while len(cells) % 7:
        cells.append(None)

    weeks = []
    for index in range(0, len(cells), 7):
        week = []
        for day in cells[index:index + 7]:
            day_events = sorted(events_by_day.get(day, []), key=event_sort_key) if day else []
            holiday = holiday_name(day) if day else ""
            week.append(
                {
                    "date": day,
                    "date_iso": day.isoformat() if day else "",
                    "day_number": day.day if day else "",
                    "is_today": day == today,
                    "is_selected": day == selected_date,
                    "is_holiday": bool(holiday),
                    "holiday_name": holiday,
                    "events": [event_to_view(event) for event in day_events[:4]],
                    "event_count": len(day_events),
                    "has_judicial": any(event.event_type == "audiencia_judicial" or event.scope == "judicial" for event in day_events),
                }
            )
        weeks.append(week)

    selected_events = sorted(events_by_day.get(selected_date, []), key=event_sort_key)
    previous_month = shift_month(month_date, -1)
    next_month = shift_month(month_date, 1)

    return {
        "month_date": month_date,
        "selected_date": selected_date,
        "month_label": f"{MONTH_LABELS[month_date.month]} {month_date.year}",
        "previous_month": previous_month,
        "next_month": next_month,
        "today": today,
        "weeks": weeks,
        "selected_events": [event_to_view(event) for event in selected_events],
        "total_month_events": len(events),
        "judicial_month_events": sum(1 for event in events if event.event_type == "audiencia_judicial" or event.scope == "judicial"),
    }


def build_schedule_dashboard_summary() -> dict[str, object]:
    today = today_local()
    horizon = today + timedelta(days=7)
    upcoming = (
        CondominiumScheduleEvent.query
        .filter(
            CondominiumScheduleEvent.event_date >= today,
            CondominiumScheduleEvent.event_date <= horizon,
            CondominiumScheduleEvent.status.in_(ACTIVE_STATUSES),
        )
        .order_by(CondominiumScheduleEvent.event_date.asc(), CondominiumScheduleEvent.start_time.asc(), CondominiumScheduleEvent.title.asc())
        .all()
    )
    today_events = [event for event in upcoming if event.event_date == today]
    judicial_next = [event for event in upcoming if event.event_type == "audiencia_judicial" or event.scope == "judicial"]
    next_event = min(upcoming, key=event_sort_key) if upcoming else None
    pending_confirmation = [event for event in upcoming if event.status == "agendado"]

    return {
        "today_count": len(today_events),
        "next_7_count": len(upcoming),
        "judicial_count": len(judicial_next),
        "pending_confirmation_count": len(pending_confirmation),
        "next_event": event_to_view(next_event) if next_event else None,
        "today_events": [event_to_view(event) for event in sorted(today_events, key=event_sort_key)[:3]],
    }


def due_schedule_notifications(*, limit: int = 4) -> list[dict[str, object]]:
    now = now_local_naive()
    today = now.date()
    tomorrow = today + timedelta(days=1)
    candidates = (
        CondominiumScheduleEvent.query
        .filter(
            CondominiumScheduleEvent.event_date >= today,
            CondominiumScheduleEvent.event_date <= tomorrow,
            CondominiumScheduleEvent.status.in_(ACTIVE_STATUSES),
            CondominiumScheduleEvent.notify_enabled.is_(True),
            CondominiumScheduleEvent.notification_acknowledged_at.is_(None),
        )
        .order_by(CondominiumScheduleEvent.event_date.asc(), CondominiumScheduleEvent.start_time.asc(), CondominiumScheduleEvent.title.asc())
        .all()
    )

    due: list[CondominiumScheduleEvent] = []
    for event in candidates:
        start_at = datetime.combine(event.event_date, event.start_time or time(8, 0))
        notify_from = start_at - timedelta(minutes=max(int(event.reminder_minutes or 0), 0))
        notify_until = start_at + timedelta(hours=2)
        if notify_from <= now <= notify_until:
            due.append(event)
        if len(due) >= limit:
            break

    return [event_to_view(event) for event in due]
