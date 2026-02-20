from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Mapping, cast

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


@dataclass(frozen=True)
class NetworkTimeResult:
    utc_datetime: datetime
    source: str


def _tz_name() -> str:
    return "America/Sao_Paulo"


def get_local_tz():
    name = _tz_name()
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


def _parse_iso_utc(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _fetch_time_via_json_api(
    request_get: Callable[[str, float], tuple[int, Any, str]],
    url: str,
    timeout: float,
) -> NetworkTimeResult | None:
    status, data, _raw = request_get(url, timeout)
    if status < 200 or status >= 300:
        return None

    if not isinstance(data, dict):
        return None

    data = cast(dict[str, Any], data)

    for key in ("datetime", "currentDateTime", "dateTime", "utc_datetime"):
        value = data.get(key)
        if isinstance(value, str):
            dt = _parse_iso_utc(value)
            if dt is not None:
                return NetworkTimeResult(utc_datetime=dt, source=url)
    return None


def _fetch_time_via_date_header(
    request_head: Callable[[str, float], tuple[int, Mapping[str, str], str]],
    url: str,
    timeout: float,
) -> NetworkTimeResult | None:
    status, headers, _raw = request_head(url, timeout)
    if status < 200 or status >= 400:
        return None
    date_header = None
    for k, v in (headers or {}).items():
        if str(k).lower() == "date":
            date_header = v
            break
    if not date_header:
        return None
    try:
        dt = parsedate_to_datetime(str(date_header))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return NetworkTimeResult(utc_datetime=dt.astimezone(timezone.utc), source=url)
    except Exception:
        return None


class TimeService:
    """Serviço de horário com sincronização via internet.

    Ideia: calcula um offset (UTC remoto - relógio local) e aplica sempre que precisar do "agora".
    Se internet falhar, usa o último offset conhecido (ou 0).
    """

    _offset_seconds: float = 0.0
    _last_sync_monotonic: float = 0.0
    _last_failure_monotonic: float = 0.0

    @classmethod
    def _ttl_seconds(cls) -> float:
        try:
            return float(os.environ.get("GALINT_TIME_SYNC_TTL_SECONDS") or 600)
        except Exception:
            return 600.0

    @classmethod
    def _sync_enabled(cls) -> bool:
        return True

    @classmethod
    def _per_request_timeout_seconds(cls) -> float:
        try:
            return float(os.environ.get("GALINT_TIME_SYNC_TIMEOUT_SECONDS") or 1.5)
        except Exception:
            return 1.5

    @classmethod
    def _max_total_sync_seconds(cls) -> float:
        try:
            return float(os.environ.get("GALINT_TIME_SYNC_MAX_TOTAL_SECONDS") or 3.0)
        except Exception:
            return 3.0

    @classmethod
    def _failure_backoff_seconds(cls) -> float:
        try:
            return float(os.environ.get("GALINT_TIME_SYNC_FAILURE_BACKOFF_SECONDS") or 3600)
        except Exception:
            return 3600.0

    @classmethod
    def _should_sync(cls) -> bool:
        if not cls._sync_enabled():
            return False

        backoff = cls._failure_backoff_seconds()
        if backoff > 0 and cls._last_failure_monotonic > 0:
            if (time.monotonic() - cls._last_failure_monotonic) < backoff:
                return False

        ttl = cls._ttl_seconds()
        if ttl <= 0:
            return False
        if cls._last_sync_monotonic <= 0:
            return True
        return (time.monotonic() - cls._last_sync_monotonic) >= ttl

    @classmethod
    def _requests_adapters(cls):
        try:
            import requests  # type: ignore

            def _get(url: str, timeout: float) -> tuple[int, Any, str]:
                r = requests.get(url, timeout=timeout)
                try:
                    return r.status_code, r.json(), r.text
                except Exception:
                    return r.status_code, cast(Any, {}), r.text

            def _head(url: str, timeout: float) -> tuple[int, Mapping[str, str], str]:
                r = requests.head(url, timeout=timeout, allow_redirects=True)
                return r.status_code, dict(r.headers), ""

            return _get, _head
        except Exception:
            return None

    @classmethod
    def _sync_from_network(cls) -> NetworkTimeResult | None:
        adapters = cls._requests_adapters()
        if adapters is None:
            return None
        request_get, request_head = adapters

        per_request_timeout = max(0.2, float(cls._per_request_timeout_seconds()))
        max_total = max(per_request_timeout, float(cls._max_total_sync_seconds()))
        start = time.monotonic()

        json_sources = (
            "https://worldtimeapi.org/api/ip",
            "https://timeapi.io/api/Time/current/zone?timeZone=UTC",
            "http://worldclockapi.com/api/json/utc/now",
        )
        for url in json_sources:
            remaining = max_total - (time.monotonic() - start)
            if remaining <= 0:
                return None
            try:
                r = _fetch_time_via_json_api(request_get, url, timeout=min(per_request_timeout, remaining))
                if r is not None:
                    return r
            except Exception:
                continue

        header_sources = (
            "https://www.google.com/generate_204",
            "https://www.cloudflare.com/cdn-cgi/trace",
        )
        for url in header_sources:
            remaining = max_total - (time.monotonic() - start)
            if remaining <= 0:
                return None
            try:
                r = _fetch_time_via_date_header(request_head, url, timeout=min(per_request_timeout, remaining))
                if r is not None:
                    return r
            except Exception:
                continue

        return None

    @classmethod
    def sync(cls) -> None:
        if not cls._should_sync():
            return
        cls._last_sync_monotonic = time.monotonic()
        result = cls._sync_from_network()
        if result is None:
            cls._last_failure_monotonic = time.monotonic()
            return

        remote_epoch = result.utc_datetime.timestamp()
        local_epoch = time.time()
        cls._offset_seconds = remote_epoch - local_epoch

    @classmethod
    def now_utc(cls) -> datetime:
        cls.sync()
        epoch = time.time() + float(cls._offset_seconds)
        return datetime.fromtimestamp(epoch, tz=timezone.utc)

    @classmethod
    def now_local(cls) -> datetime:
        return cls.now_utc().astimezone(get_local_tz())

    @classmethod
    def to_local(cls, dt: datetime) -> datetime:
        tz = get_local_tz()
        if dt.tzinfo is None:
            # padrão do projeto: datetimes do banco são UTC sem tzinfo
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz)

    @classmethod
    def format_local(cls, dt: datetime | None, fmt: str = "%d/%m/%Y %H:%M") -> str:
        if not dt:
            return "N/D"
        return cls.to_local(dt).strftime(fmt)

    @classmethod
    def is_within_business_hours(cls, dt: datetime, start_hour: int = 8, end_hour: int = 17) -> bool:
        """Verifica se o horário está dentro do expediente.
        
        Args:
            dt: datetime a verificar
            start_hour: hora de início do expediente (padrão: 8h)
            end_hour: hora de fim do expediente (padrão: 17h)
        
        Returns:
            True se estiver entre start_hour:00 e end_hour:00 (exclusive)
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        local_dt = cls.to_local(dt)
        hour = local_dt.hour
        
        return start_hour <= hour < end_hour
    
    @classmethod
    def get_business_day_tag(cls, dt: datetime) -> str:
        """Retorna a tag do dia útil para a movimentação.
        
        Se a movimentação foi feita fora do expediente (antes das 8h ou após 17h),
        retorna "APÓS O EXPEDIENTE", caso contrário retorna vazio.
        """
        if not cls.is_within_business_hours(dt):
            return "APÓS O EXPEDIENTE"
        return ""
