"""Serviço de sugestões de preço de reposição (Mercado Livre como provedor 1).

Este módulo é usado para sugerir um preço médio/mediano de mercado quando o item
não possui comprovante de compra. O fluxo foi pensado para ser auditável:
o sistema sugere, o usuário confirma e então salvamos o valor escolhido.
"""

from __future__ import annotations

import json
import statistics
import time
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests


def _normalize_uf(value: object) -> str | None:
    if not value:
        return None
    raw = str(value).strip().upper()
    if not raw:
        return None
    if len(raw) == 2 and raw.isalpha():
        return raw
    m = re.search(r"([A-Z]{2})$", raw)
    if m:
        return m.group(1)
    return None


def _dig(obj: dict[str, Any], *keys: str) -> Any:
    cur: Any = obj
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


@dataclass(frozen=True, slots=True)
class PriceSuggestion:
    source: str
    title: str
    price: float
    currency: str
    url: str | None
    uf: str | None
    uf_raw: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "price": self.price,
            "currency": self.currency,
            "url": self.url,
            "uf": self.uf,
            "uf_raw": self.uf_raw,
        }


class PriceSuggestionService:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, str | None, int], tuple[float, dict[str, Any]]] = {}

    @staticmethod
    def _request_headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.mercadolivre.com.br/",
        }

    def get_replacement_suggestions(self, *, query: str, uf: str | None, limit: int = 20) -> dict[str, Any]:
        query_norm = (query or "").strip()
        if not query_norm:
            return {
                "query": query_norm,
                "uf": _normalize_uf(uf),
                "suggestions": [],
                "stats": {"count": 0, "median": None, "min": None, "max": None},
                "providers": [{"name": "MercadoLivre", "ok": True}],
            }

        uf_norm = _normalize_uf(uf)
        limit_i = max(1, min(int(limit or 20), 50))
        cache_key = (query_norm.lower(), uf_norm, limit_i)
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

        providers: list[dict[str, Any]] = []
        suggestions: list[PriceSuggestion] = []

        try:
            ml = self._fetch_mercado_livre(query=query_norm, uf=uf_norm, limit=limit_i)
            suggestions.extend(ml)
            providers.append({"name": "MercadoLivre", "ok": True, "count": len(ml)})
        except Exception as exc:
            providers.append({"name": "MercadoLivre", "ok": False, "error": str(exc)})

        # (Fallbacks futuros podem ser adicionados aqui mantendo a mesma interface)

        prices = [s.price for s in suggestions if isinstance(s.price, (int, float)) and s.price > 0]
        stats = {
            "count": len(prices),
            "median": float(statistics.median(prices)) if prices else None,
            "min": float(min(prices)) if prices else None,
            "max": float(max(prices)) if prices else None,
        }

        payload = {
            "query": query_norm,
            "uf": uf_norm,
            "suggestions": [s.to_dict() for s in suggestions],
            "stats": stats,
            "providers": providers,
        }

        # Cache (TTL 1 hora)
        self._cache[cache_key] = (now + 3600, payload)
        return payload

    def _fetch_mercado_livre(self, *, query: str, uf: str | None, limit: int) -> list[PriceSuggestion]:
        try:
            url = "https://api.mercadolibre.com/sites/MLB/search"
            resp = requests.get(
                url,
                params={"q": query, "limit": limit},
                headers=self._request_headers(),
                timeout=6,
            )
            if resp.status_code == 403:
                return self._fetch_mercado_livre_web(query=query, uf=uf, limit=limit)
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
            results = data.get("results") or []
            if not isinstance(results, list):
                return []
            parsed = self._parse_mercado_livre_api_results(results)
        except requests.RequestException:
            parsed = self._fetch_mercado_livre_web(query=query, uf=uf, limit=limit)

        if uf:
            matches = [s for s in parsed if s.uf == uf]
            if len(matches) >= 5:
                return matches[:limit]
        return parsed[:limit]

    def _parse_mercado_livre_api_results(self, results: list[dict[str, Any]]) -> list[PriceSuggestion]:
        parsed: list[PriceSuggestion] = []
        for r in results:
            if not isinstance(r, dict):
                continue
            price = r.get("price")
            try:
                price_f = float(price)
            except (TypeError, ValueError):
                continue
            if price_f <= 0:
                continue

            title = str(r.get("title") or "").strip()
            permalink = r.get("permalink")
            url_item = str(permalink).strip() if permalink else None
            currency = str(r.get("currency_id") or "BRL").strip() or "BRL"

            uf_raw = (
                _dig(r, "seller_address", "state", "id")
                or _dig(r, "seller_address", "state_id")
                or _dig(r, "address", "state_id")
                or _dig(r, "address", "state", "id")
            )
            uf_item = _normalize_uf(uf_raw)
            parsed.append(
                PriceSuggestion(
                    source="Mercado Livre",
                    title=title or "(sem título)",
                    price=price_f,
                    currency=currency,
                    url=url_item,
                    uf=uf_item,
                    uf_raw=str(uf_raw) if uf_raw else None,
                )
            )
        return parsed

    def _fetch_mercado_livre_web(self, *, query: str, uf: str | None, limit: int) -> list[PriceSuggestion]:
        slug = quote(re.sub(r"\s+", "-", query.strip()), safe="-")
        url = f"https://lista.mercadolivre.com.br/{slug}"
        resp = requests.get(url, headers=self._request_headers(), timeout=8)
        resp.raise_for_status()
        html = resp.text or ""
        cards = self._extract_polycard_objects(html)
        parsed: list[PriceSuggestion] = []
        for card in cards:
            polycard = card.get("polycard") if isinstance(card, dict) else None
            if not isinstance(polycard, dict):
                continue
            metadata = polycard.get("metadata") or {}
            components = polycard.get("components") or []
            title = self._extract_polycard_title(components)
            price_f = self._extract_polycard_price(components)
            if price_f is None or price_f <= 0:
                continue
            url_item = self._build_polycard_url(metadata)
            parsed.append(
                PriceSuggestion(
                    source="Mercado Livre",
                    title=title or "(sem título)",
                    price=price_f,
                    currency="BRL",
                    url=url_item,
                    uf=uf,
                    uf_raw=uf,
                )
            )
            if len(parsed) >= limit:
                break
        return parsed

    def _extract_polycard_objects(self, html: str) -> list[dict[str, Any]]:
        objects: list[dict[str, Any]] = []
        marker = '{"id":"POLYCARD"'
        start = 0
        while True:
            idx = html.find(marker, start)
            if idx < 0:
                break
            chunk = self._extract_balanced_json(html, idx)
            start = idx + len(marker)
            if not chunk:
                continue
            try:
                payload = json.loads(chunk)
            except Exception:
                continue
            if isinstance(payload, dict):
                objects.append(payload)
        return objects

    @staticmethod
    def _extract_balanced_json(text: str, start_idx: int) -> str | None:
        depth = 0
        in_string = False
        escaped = False
        begin = -1
        for idx in range(start_idx, len(text)):
            ch = text[idx]
            if begin < 0:
                if ch == '{':
                    begin = idx
                    depth = 1
                continue
            if in_string:
                if escaped:
                    escaped = False
                elif ch == '\\':
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[begin:idx + 1]
        return None

    @staticmethod
    def _extract_polycard_title(components: list[dict[str, Any]]) -> str:
        for component in components:
            if not isinstance(component, dict) or component.get("type") != "title":
                continue
            title_data = component.get("title") or {}
            if not isinstance(title_data, dict):
                continue
            return str(title_data.get("text") or "").strip()
        return ""

    @staticmethod
    def _extract_polycard_price(components: list[dict[str, Any]]) -> float | None:
        for component in components:
            if not isinstance(component, dict) or component.get("type") != "price":
                continue
            price_data = component.get("price") or {}
            if not isinstance(price_data, dict):
                continue
            current = price_data.get("current_price") or {}
            if not isinstance(current, dict):
                continue
            try:
                return float(current.get("value"))
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _build_polycard_url(metadata: dict[str, Any]) -> str | None:
        if not isinstance(metadata, dict):
            return None
        raw_url = str(metadata.get("url") or "").strip()
        if not raw_url:
            return None
        if not raw_url.startswith("http"):
            raw_url = f"https://{raw_url}"
        fragments = str(metadata.get("url_fragments") or "")
        params = str(metadata.get("url_params") or "")
        return f"{raw_url}{params}{fragments}"


price_suggestion_service = PriceSuggestionService()

