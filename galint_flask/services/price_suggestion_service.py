"""Serviço de sugestões de preço de reposição (Mercado Livre como provedor 1).

Este módulo é usado para sugerir um preço médio/mediano de mercado quando o item
não possui comprovante de compra. O fluxo foi pensado para ser auditável:
o sistema sugere, o usuário confirma e então salvamos o valor escolhido.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import json
import os
import statistics
import time
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, unquote, urlparse

import requests


class PriceProviderUnavailable(RuntimeError):
    pass


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
    seller_name: str | None = None
    seller_identifier: str | None = None
    seller_cnpj: str | None = None
    seller_city: str | None = None
    seller_state: str | None = None
    seller_address: str | None = None
    seller_contact_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "price": self.price,
            "currency": self.currency,
            "url": self.url,
            "uf": self.uf,
            "uf_raw": self.uf_raw,
            "seller_name": self.seller_name,
            "seller_identifier": self.seller_identifier,
            "seller_cnpj": self.seller_cnpj,
            "seller_city": self.seller_city,
            "seller_state": self.seller_state,
            "seller_address": self.seller_address,
            "seller_contact_url": self.seller_contact_url,
        }


class PriceSuggestionService:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, str | None, int], tuple[float, dict[str, Any]]] = {}

    @staticmethod
    def _empty_payload(*, query: str, uf: str | None) -> dict[str, Any]:
        return {
            "query": query,
            "uf": uf,
            "suggestions": [],
            "stats": {"count": 0, "median": None, "min": None, "max": None},
            "providers": [{"name": "MercadoLivre", "ok": True}],
        }

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

    @staticmethod
    def _mercado_livre_access_token() -> str:
        for key in (
            "MERCADO_LIVRE_ACCESS_TOKEN",
            "MERCADOLIVRE_ACCESS_TOKEN",
            "MELI_ACCESS_TOKEN",
            "ML_ACCESS_TOKEN",
        ):
            value = os.getenv(key)
            if value and value.strip():
                return value.strip()
        return ""

    def get_replacement_suggestions(self, *, query: str, uf: str | None, limit: int = 20) -> dict[str, Any]:
        query_norm = (query or "").strip()
        if not query_norm:
            return self._empty_payload(query=query_norm, uf=_normalize_uf(uf))

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

        if len(suggestions) < min(limit_i, 5):
            try:
                web = self._fetch_public_web_prices(query=query_norm, limit=limit_i)
                suggestions.extend(self._dedupe_suggestions([*suggestions, *web]))
                suggestions = self._dedupe_suggestions(suggestions)
                providers.append({"name": "BuscaWeb", "ok": True, "count": len(web)})
            except Exception as exc:
                providers.append({"name": "BuscaWeb", "ok": False, "error": str(exc)})

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

    def get_replacement_suggestions_batch(
        self,
        *,
        requests_payload: list[dict[str, Any]],
        uf: str | None,
        suggestion_limit: int = 10,
        max_workers: int = 4,
    ) -> dict[str, Any]:
        uf_norm = _normalize_uf(uf)
        limit_i = max(1, min(int(suggestion_limit or 10), 50))

        normalized_requests: list[dict[str, Any]] = []
        for entry in requests_payload or []:
            if not isinstance(entry, dict):
                continue
            query_norm = str(entry.get("query") or "").strip()
            if not query_norm:
                continue
            normalized_requests.append(
                {
                    "item_id": str(entry.get("item_id") or "").strip() or None,
                    "query": query_norm,
                }
            )

        if not normalized_requests:
            return {
                "uf": uf_norm,
                "items": [],
                "summary": {
                    "requested": 0,
                    "completed": 0,
                    "failed": 0,
                    "with_results": 0,
                },
            }

        results: list[dict[str, Any] | None] = [None] * len(normalized_requests)

        def _fetch(entry: dict[str, Any]) -> dict[str, Any]:
            payload = self.get_replacement_suggestions(query=entry["query"], uf=uf_norm, limit=limit_i)
            payload["success"] = True
            payload["item_id"] = entry.get("item_id")
            return payload

        worker_count = max(1, min(int(max_workers or 4), len(normalized_requests), 8))

        if worker_count == 1:
            for index, entry in enumerate(normalized_requests):
                try:
                    results[index] = _fetch(entry)
                except Exception as exc:
                    results[index] = {
                        **self._empty_payload(query=entry["query"], uf=uf_norm),
                        "success": False,
                        "item_id": entry.get("item_id"),
                        "error": str(exc),
                        "providers": [{"name": "MercadoLivre", "ok": False, "error": str(exc)}],
                    }
        else:
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="price-batch") as executor:
                futures = {
                    executor.submit(_fetch, entry): index
                    for index, entry in enumerate(normalized_requests)
                }
                for future in as_completed(futures):
                    index = futures[future]
                    entry = normalized_requests[index]
                    try:
                        results[index] = future.result()
                    except Exception as exc:
                        results[index] = {
                            **self._empty_payload(query=entry["query"], uf=uf_norm),
                            "success": False,
                            "item_id": entry.get("item_id"),
                            "error": str(exc),
                            "providers": [{"name": "MercadoLivre", "ok": False, "error": str(exc)}],
                        }

        safe_results = [row for row in results if isinstance(row, dict)]
        failed = sum(1 for row in safe_results if not row.get("success"))
        with_results = sum(1 for row in safe_results if row.get("stats", {}).get("count"))
        return {
            "uf": uf_norm,
            "items": safe_results,
            "summary": {
                "requested": len(normalized_requests),
                "completed": len(safe_results),
                "failed": failed,
                "with_results": with_results,
            },
        }

    def _fetch_mercado_livre(self, *, query: str, uf: str | None, limit: int) -> list[PriceSuggestion]:
        headers = self._request_headers()
        token = self._mercado_livre_access_token()
        if token:
            headers = {**headers, "Authorization": f"Bearer {token}"}
        try:
            url = "https://api.mercadolibre.com/sites/MLB/search"
            resp = requests.get(
                url,
                params={"q": query, "limit": limit},
                headers=headers,
                timeout=6,
            )
            if resp.status_code in {401, 403}:
                if token:
                    raise PriceProviderUnavailable("MercadoLivre recusou o token configurado.")
                raise PriceProviderUnavailable("MercadoLivre bloqueou consultas anonimas no momento.")
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
            results = data.get("results") or []
            if not isinstance(results, list):
                return []
            parsed = self._parse_mercado_livre_api_results(results)
        except PriceProviderUnavailable:
            raise
        except requests.RequestException as exc:
            raise PriceProviderUnavailable(f"MercadoLivre indisponivel: {exc}") from exc

        if uf:
            matches = [s for s in parsed if s.uf == uf]
            if len(matches) >= 5:
                return matches[:limit]
        return parsed[:limit]

    def _dedupe_suggestions(self, suggestions: list[PriceSuggestion]) -> list[PriceSuggestion]:
        seen: set[tuple[str, str, int]] = set()
        deduped: list[PriceSuggestion] = []
        for suggestion in suggestions:
            key = (
                re.sub(r"\s+", " ", suggestion.title.lower()).strip(),
                str(suggestion.url or "").split("?", 1)[0].lower(),
                int(round(float(suggestion.price or 0) * 100)),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(suggestion)
        return deduped

    def _fetch_public_web_prices(self, *, query: str, limit: int) -> list[PriceSuggestion]:
        result_links = self._fetch_duckduckgo_result_links(query=query, limit=min(8, max(4, limit)))
        suggestions: list[PriceSuggestion] = []
        for result in result_links:
            if len(suggestions) >= limit:
                break
            url = str(result.get("url") or "").strip()
            title = str(result.get("title") or "").strip()
            if not url:
                continue
            host = urlparse(url).netloc.lower()
            if "mercadolivre" in host or "mercadolibre" in host:
                continue
            try:
                page = requests.get(url, headers=self._request_headers(), timeout=8, allow_redirects=True)
                if page.status_code >= 400:
                    continue
                price = self._extract_best_page_price(page.text or "")
            except requests.RequestException:
                continue
            if price is None or price <= 0:
                continue
            final_url = str(page.url or url).strip()
            source_host = urlparse(final_url).netloc.lower().replace("www.", "")
            suggestions.append(
                PriceSuggestion(
                    source=f"Busca web: {source_host or 'site'}",
                    title=title or source_host or query,
                    price=float(price),
                    currency="BRL",
                    url=final_url,
                    uf=None,
                    uf_raw=None,
                    seller_name=source_host or None,
                    seller_identifier=source_host or None,
                    seller_contact_url=final_url,
                )
            )
        return suggestions[:limit]

    def _fetch_duckduckgo_result_links(self, *, query: str, limit: int) -> list[dict[str, str]]:
        search_query = f"{query} preco R$ comprar"
        response = requests.get(
            "https://duckduckgo.com/html/",
            params={"q": search_query},
            headers=self._request_headers(),
            timeout=8,
        )
        response.raise_for_status()
        raw_html = response.text or ""
        blocks = re.findall(
            r'<div[^>]+class="[^"]*result__body[^"]*"[\s\S]*?</div>\s*</div>',
            raw_html,
            flags=re.I,
        )
        links: list[dict[str, str]] = []
        for block in blocks:
            if len(links) >= limit:
                break
            match = re.search(
                r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>',
                block,
                flags=re.I,
            )
            if not match:
                continue
            href = html.unescape(match.group(1))
            if href.startswith("//duckduckgo.com/l/"):
                href = f"https:{href}"
            parsed = urlparse(href)
            if "duckduckgo.com" in parsed.netloc:
                href = parse_qs(parsed.query).get("uddg", [""])[0]
            href = html.unescape(unquote(str(href or "").strip()))
            if not href.startswith("http"):
                continue
            title = html.unescape(re.sub(r"<[^>]+>", " ", match.group(2)))
            title = re.sub(r"\s+", " ", title).strip()
            links.append({"title": title, "url": href})
        return links

    def _extract_best_page_price(self, html_text: str) -> float | None:
        structured_patterns = [
            r'property=["\']product:price:amount["\'][^>]+content=["\']([^"\']+)["\']',
            r'content=["\']([^"\']+)["\'][^>]+property=["\']product:price:amount["\']',
            r'itemprop=["\']price["\'][^>]+content=["\']([^"\']+)["\']',
            r'content=["\']([^"\']+)["\'][^>]+itemprop=["\']price["\']',
            r'["\']price["\']\s*:\s*["\']?([0-9]+(?:[\.,][0-9]{1,2})?)["\']?',
            r'["\']priceAmount["\']\s*:\s*["\']?([0-9]+(?:[\.,][0-9]{1,2})?)["\']?',
            r'["\']salePrice["\']\s*:\s*["\']?([0-9]+(?:[\.,][0-9]{1,2})?)["\']?',
        ]
        text = html.unescape(html_text or "")
        for pattern in structured_patterns:
            for match in re.findall(pattern, text, flags=re.I):
                parsed = self._parse_price_number(match)
                if parsed is not None:
                    return parsed

        for match in re.findall(r"R\$\s*([0-9]{1,4}(?:\.[0-9]{3})*,[0-9]{2})", text, flags=re.I):
            parsed = self._parse_price_number(match)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _parse_price_number(value: Any) -> float | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        raw = raw.replace("R$", "").replace("\xa0", " ").strip()
        raw = re.sub(r"[^0-9,\.]", "", raw)
        if not raw:
            return None
        if re.fullmatch(r"[0-9]+", raw):
            numeric = float(raw)
            if len(raw) == 4:
                numeric = numeric / 10.0
            elif len(raw) >= 5:
                numeric = numeric / 100.0
        elif "," in raw:
            numeric = float(raw.replace(".", "").replace(",", "."))
        else:
            numeric = float(raw.replace(",", ""))
        if 1.0 <= numeric <= 100000.0:
            return float(numeric)
        return None

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
            seller_id = r.get("seller_id") or _dig(r, "seller", "id")
            seller_name = _dig(r, "seller", "nickname") or r.get("official_store_name")
            seller_city = _dig(r, "seller_address", "city", "name") or _dig(r, "address", "city_name")
            seller_state = (
                _dig(r, "seller_address", "state", "name")
                or _dig(r, "address", "state_name")
                or uf_item
            )
            parsed.append(
                PriceSuggestion(
                    source="Mercado Livre",
                    title=title or "(sem título)",
                    price=price_f,
                    currency=currency,
                    url=url_item,
                    uf=uf_item,
                    uf_raw=str(uf_raw) if uf_raw else None,
                    seller_name=str(seller_name).strip() if seller_name else None,
                    seller_identifier=str(seller_id).strip() if seller_id else None,
                    seller_city=str(seller_city).strip() if seller_city else None,
                    seller_state=str(seller_state).strip() if seller_state else None,
                    seller_contact_url=url_item,
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
                    seller_contact_url=url_item,
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

