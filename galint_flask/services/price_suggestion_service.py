"""Serviço de sugestões de preço de reposição (Mercado Livre como provedor 1).

Este módulo é usado para sugerir um preço médio/mediano de mercado quando o item
não possui comprovante de compra. O fluxo foi pensado para ser auditável:
o sistema sugere, o usuário confirma e então salvamos o valor escolhido.
"""

from __future__ import annotations

import statistics
import time
import re
from dataclasses import dataclass
from typing import Any

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
        url = "https://api.mercadolibre.com/sites/MLB/search"
        resp = requests.get(url, params={"q": query, "limit": limit}, timeout=4)
        resp.raise_for_status()
        data = resp.json() if resp.content else {}
        results = data.get("results") or []
        if not isinstance(results, list):
            return []

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

        if uf:
            matches = [s for s in parsed if s.uf == uf]
            # Se houver amostra suficiente da UF, prioriza. Senão, retorna tudo.
            if len(matches) >= 5:
                return matches[:limit]
        return parsed[:limit]


price_suggestion_service = PriceSuggestionService()

