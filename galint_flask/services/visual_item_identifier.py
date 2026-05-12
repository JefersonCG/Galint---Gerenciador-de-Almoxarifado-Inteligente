from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import requests
from flask import current_app
from PIL import Image, ImageEnhance, ImageOps
from sqlalchemy import or_

from ..models import Item


logger = logging.getLogger(__name__)


class VisualItemIdentifier:
    """Identifica itens do estoque a partir de texto extraido ou aparencia da foto."""

    AUTO_CONFIRM_SCORE = 72.0
    AMBIGUOUS_SCORE = 38.0
    MAX_TEXT_CANDIDATES = 250
    PHOTO_ONLY_EXPERIMENTAL_ENV = "GALINT_ENABLE_PHOTO_SIMILARITY_GUESS"

    STOPWORDS = {
        "A", "AS", "AO", "AOS", "DE", "DA", "DAS", "DO", "DOS", "E", "EM", "NA", "NAS",
        "NO", "NOS", "PARA", "POR", "COM", "SEM", "UM", "UMA", "UN", "UND", "UNID", "UNIDADE",
        "PRODUTO", "ITEM", "USO", "GERAL", "PESO", "LIQUIDO", "LIQ", "FAB", "VAL", "LOTE",
        "INDUSTRIA", "BRASIL", "CONTEM", "CONTEUDO", "NET", "WEIGHT",
    }

    TOKEN_SYNONYMS = {
        "BULB": ["LAMPADA"],
        "LIGHTBULB": ["LAMPADA"],
        "LIGHT": ["LAMPADA"],
        "LAMP": ["LAMPADA"],
        "LAMPARA": ["LAMPADA"],
        "LAMPADAS": ["LAMPADA"],
        "LUMINARIA": ["LUMINARIA", "LED"],
        "LUMINARIALED": ["LUMINARIA", "LED"],
        "SPOTLIGHT": ["SPOT", "LED"],
        "GLUE": ["COLA", "ADESIVO"],
        "ADHESIVE": ["ADESIVO", "COLA"],
        "PAINT": ["TINTA"],
        "TAPE": ["FITA"],
        "SCREW": ["PARAFUSO"],
    }

    NON_CATALOG_TOKENS = {
        "BULB", "LIGHTBULB", "LIGHT", "LAMP", "LAMPARA", "SPOTLIGHT",
        "GLUE", "ADHESIVE", "PAINT", "TAPE", "SCREW",
    }

    @classmethod
    def identify_image(cls, image_bytes: bytes, *, limit: int = 5) -> dict[str, Any]:
        text_result = cls.extract_text_from_image(image_bytes)
        merged: dict[str, dict[str, Any]] = {}

        text = str(text_result.get("text") or "").strip()
        if text:
            for match in cls.search_by_text(text, limit=max(limit, 8)):
                code = match["codigo_item"]
                merged[code] = match

        photo_matches = cls.search_by_photo_similarity(image_bytes, limit=max(limit, 8))
        allow_photo_only = os.environ.get(cls.PHOTO_ONLY_EXPERIMENTAL_ENV, "").strip().lower() in {"1", "true", "yes", "sim"}

        for match in photo_matches:
            code = match["codigo_item"]
            existing = merged.get(code)
            if existing:
                existing["score"] = min(99.0, float(existing["score"]) + float(match["score"]) * 0.35)
                existing["reasons"] = sorted(set(existing.get("reasons", [])) | set(match.get("reasons", [])))
            elif allow_photo_only and float(match.get("score") or 0) >= 97.0:
                merged[code] = match

        matches = sorted(merged.values(), key=lambda item: item["score"], reverse=True)[:limit]
        return {
            "success": bool(matches),
            "text": text,
            "text_provider": text_result.get("provider") or "none",
            "text_error": text_result.get("error"),
            "photo_candidates": len(photo_matches),
            "photo_only_enabled": allow_photo_only,
            "matches": matches,
        }

    @classmethod
    def extract_text_from_image(cls, image_bytes: bytes) -> dict[str, Any]:
        local = cls._extract_text_with_tesseract(image_bytes)
        if local.get("text"):
            return local

        remote = cls._extract_text_with_openai(image_bytes)
        if remote.get("text") or remote.get("error"):
            return remote

        return local

    @classmethod
    def search_by_text(cls, text: str, *, limit: int = 5) -> list[dict[str, Any]]:
        tokens = cls._important_tokens(text)
        if not tokens:
            return []

        conditions = []
        for token in tokens[:10]:
            like = f"%{token}%"
            conditions.extend([
                Item.codigo_item.ilike(like),
                Item.descricao.ilike(like),
                Item.marca.ilike(like),
                Item.categoria.ilike(like),
                Item.modelo.ilike(like),
            ])

        candidates = (
            Item.query.filter(or_(*conditions))
            .limit(cls.MAX_TEXT_CANDIDATES)
            .all()
            if conditions else []
        )

        ranked: list[dict[str, Any]] = []
        for item in candidates:
            score, matched = cls._score_item_by_tokens(item, tokens)
            if score <= 0:
                continue
            ranked.append(cls._build_match(item, score, [f"texto: {', '.join(matched[:6])}"], matched))

        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:limit]

    @classmethod
    def search_by_photo_similarity(cls, image_bytes: bytes, *, limit: int = 5) -> list[dict[str, Any]]:
        source_features = cls._image_features_from_bytes(image_bytes)
        if not source_features:
            return []

        items = (
            Item.query.filter(Item.foto_path.isnot(None), Item.foto_path != "")
            .limit(500)
            .all()
        )
        ranked: list[dict[str, Any]] = []

        for item in items:
            path = cls._item_photo_path(item)
            if not path or not path.exists():
                continue
            try:
                target_features = cls._image_features_from_path(path)
            except Exception:
                logger.debug("Falha ao ler foto cadastrada do item %s", item.codigo_item, exc_info=True)
                continue
            if not target_features:
                continue

            score = cls._compare_image_features(source_features, target_features)
            if score >= cls.AMBIGUOUS_SCORE:
                ranked.append(cls._build_match(item, score, ["foto cadastrada parecida"], []))

        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:limit]

    @classmethod
    def _score_item_by_tokens(cls, item: Item, tokens: list[str]) -> tuple[float, list[str]]:
        code = cls._normalize(getattr(item, "codigo_item", ""))
        description = cls._normalize(getattr(item, "descricao", ""))
        brand = cls._normalize(getattr(item, "marca", ""))
        category = cls._normalize(getattr(item, "categoria", ""))
        model = cls._normalize(getattr(item, "modelo", ""))
        combined = " ".join(part for part in [code, description, brand, category, model] if part)
        compact_brand = brand.replace(" ", "")

        score = 0.0
        matched: list[str] = []
        important_count = 0
        important_matched = 0
        numeric_tokens = [token for token in tokens if token.isdigit()]

        for token in tokens:
            if token in cls.STOPWORDS:
                continue
            important = token.isdigit() or len(token) >= 4
            if important:
                important_count += 1

            token_score = 0.0
            if token == code:
                token_score = 60.0
            elif token.isdigit():
                if token in code:
                    token_score = 42.0
                elif token in description or token in model or token in brand:
                    token_score = 34.0
            else:
                if brand and token == brand:
                    token_score = 38.0
                elif compact_brand and token == compact_brand:
                    token_score = 38.0
                elif brand and token in brand and len(token) >= 4:
                    token_score = 30.0
                elif compact_brand and token in compact_brand and len(token) >= 4:
                    token_score = 30.0
                elif brand and token in brand:
                    token_score = 6.0
                elif compact_brand and token in compact_brand:
                    token_score = 6.0
                elif token in description:
                    token_score = 24.0 if len(token) >= 5 else 13.0
                elif token in model:
                    token_score = 22.0
                elif token in category:
                    token_score = 8.0
                elif token in combined:
                    token_score = 8.0

            if token_score:
                score += token_score
                matched.append(token)
                if important:
                    important_matched += 1

        if "TEK" in tokens and "BOND" in tokens and "TEKBOND" in combined and "TEKBOND" not in matched:
            score += 36.0
            matched.append("TEKBOND")
            important_count += 1
            important_matched += 1

        if important_count:
            score += 18.0 * (important_matched / important_count)

        if numeric_tokens and not any(token in matched for token in numeric_tokens):
            score = min(score, 54.0)

        if not numeric_tokens and matched and not any(token not in {"TEKBOND", "TEK", "BOND"} for token in matched):
            score = min(score, 46.0)

        if important_count <= 1:
            score = min(score, 46.0)

        return min(score, 99.0), matched

    @classmethod
    def _build_match(cls, item: Item, score: float, reasons: list[str], matched_tokens: list[str]) -> dict[str, Any]:
        try:
            saldo = item.get_saldo_atual()
        except Exception:
            saldo = "N/A"
        return {
            "codigo_item": item.codigo_item,
            "descricao": item.descricao,
            "marca": item.marca,
            "categoria": item.categoria,
            "unidade": item.unidade,
            "saldo": saldo,
            "score": round(float(score), 1),
            "reasons": reasons,
            "matched_tokens": matched_tokens,
            "item": item,
        }

    @classmethod
    def _important_tokens(cls, text: str) -> list[str]:
        normalized = cls._normalize(text)
        tokens = re.findall(r"[A-Z0-9]+", normalized)
        expanded: list[str] = []
        seen: set[str] = set()

        for token in tokens:
            if len(token) < 2 or token in cls.STOPWORDS:
                continue
            if token in cls.NON_CATALOG_TOKENS:
                seen.add(token)
                continue
            if token not in seen:
                expanded.append(token)
                seen.add(token)

        if "TEK" in seen and "BOND" in seen and "TEKBOND" not in seen:
            expanded.insert(0, "TEKBOND")
        if "TEKBOND" in seen:
            for token in ("TEK", "BOND"):
                if token not in seen:
                    expanded.append(token)
                    seen.add(token)

        compact_text = "".join(tokens)
        for token in list(expanded) + tokens + [compact_text]:
            for synonym in cls.TOKEN_SYNONYMS.get(token, []):
                if synonym not in seen:
                    expanded.append(synonym)
                    seen.add(synonym)

        return expanded[:18]

    @staticmethod
    def _normalize(value: object) -> str:
        text = str(value or "").upper()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _extract_text_with_tesseract(cls, image_bytes: bytes) -> dict[str, Any]:
        try:
            import pytesseract  # type: ignore
        except Exception:
            return {"provider": "none", "text": "", "error": "pytesseract indisponivel"}

        try:
            try:
                pytesseract.get_tesseract_version()
            except Exception as exc:
                return {"provider": "tesseract", "text": "", "error": str(exc)}

            image = cls._open_image(image_bytes)
            variants = cls._ocr_variants(image)
            chunks: list[str] = []
            for variant in variants:
                text = pytesseract.image_to_string(variant, lang="por+eng", config="--psm 6")
                if text:
                    chunks.append(text)
            return {"provider": "tesseract", "text": cls._clean_ocr_text("\n".join(chunks)), "error": None}
        except Exception as exc:
            logger.debug("Falha no OCR local", exc_info=True)
            return {"provider": "tesseract", "text": "", "error": str(exc)}

    @classmethod
    def _extract_text_with_openai(cls, image_bytes: bytes) -> dict[str, Any]:
        api_key = os.environ.get("GALINT_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return {"provider": "openai", "text": "", "error": None}

        try:
            data_uri = cls._image_data_uri(image_bytes)
            model = os.environ.get("GALINT_VISION_MODEL", "gpt-4o-mini")
            payload = {
                "model": model,
                "temperature": 0,
                "max_tokens": 180,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Identifique o produto de almoxarifado na imagem com foco operacional. "
                                    "Se houver rotulo, extraia marca, modelo, numeros grandes, potencia, cor, peso/volume. "
                                    "Se nao houver texto legivel, classifique o objeto visivel em portugues "
                                    "(ex.: lampada led, cola, tinta, fita, parafuso, ferramenta). "
                                    "Responda somente JSON com as chaves text, brand, model, numbers, description, object_category_pt."
                                ),
                            },
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                    }
                ],
            }
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=25,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            text = cls._text_from_jsonish_response(content)
            return {"provider": "openai", "text": text, "error": None}
        except Exception as exc:
            logger.warning("Falha na identificacao visual OpenAI: %s", exc)
            return {"provider": "openai", "text": "", "error": str(exc)}

    @classmethod
    def _text_from_jsonish_response(cls, content: str) -> str:
        raw = str(content or "").strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.IGNORECASE | re.MULTILINE).strip()
        try:
            data = json.loads(raw)
        except Exception:
            return cls._clean_ocr_text(raw)

        parts: list[str] = []
        for key in ("text", "brand", "model", "description", "object_category_pt"):
            value = data.get(key)
            if value:
                parts.append(str(value))
        numbers = data.get("numbers")
        if isinstance(numbers, list):
            parts.extend(str(number) for number in numbers if number)
        elif numbers:
            parts.append(str(numbers))
        return cls._clean_ocr_text(" ".join(parts))

    @classmethod
    def _ocr_variants(cls, image: Image.Image) -> list[Image.Image]:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((1400, 1400))
        gray = image.convert("L")
        contrast = ImageEnhance.Contrast(gray).enhance(2.2)
        sharp = ImageEnhance.Sharpness(contrast).enhance(2.0)
        binary = sharp.point(lambda value: 255 if value > 145 else 0)
        return [gray, contrast, sharp, binary]

    @staticmethod
    def _clean_ocr_text(text: str) -> str:
        lines = [re.sub(r"\s+", " ", line).strip() for line in str(text or "").splitlines()]
        return " ".join(line for line in lines if line)

    @classmethod
    def _image_data_uri(cls, image_bytes: bytes) -> str:
        image = cls._open_image(image_bytes).convert("RGB")
        image.thumbnail((900, 900))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=82, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"

    @staticmethod
    def _open_image(image_bytes: bytes) -> Image.Image:
        return Image.open(io.BytesIO(image_bytes))

    @classmethod
    def _image_features_from_bytes(cls, image_bytes: bytes) -> dict[str, Any] | None:
        try:
            return cls._image_features(cls._open_image(image_bytes))
        except Exception:
            logger.debug("Falha ao extrair assinatura visual da foto", exc_info=True)
            return None

    @classmethod
    def _image_features_from_path(cls, path: Path) -> dict[str, Any] | None:
        with Image.open(path) as image:
            return cls._image_features(image.copy())

    @classmethod
    def _image_features(cls, image: Image.Image) -> dict[str, Any]:
        image = ImageOps.exif_transpose(image).convert("RGB")
        thumbnail = image.copy()
        thumbnail.thumbnail((256, 256))
        return {
            "ahash": cls._average_hash(thumbnail),
            "dhash": cls._difference_hash(thumbnail),
            "histogram": cls._color_histogram(thumbnail),
        }

    @staticmethod
    def _average_hash(image: Image.Image, size: int = 8) -> int:
        gray = image.convert("L").resize((size, size), Image.Resampling.LANCZOS)
        pixels = list(gray.getdata())
        mean = sum(pixels) / len(pixels)
        value = 0
        for pixel in pixels:
            value = (value << 1) | int(pixel >= mean)
        return value

    @staticmethod
    def _difference_hash(image: Image.Image, size: int = 8) -> int:
        gray = image.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
        pixels = list(gray.getdata())
        value = 0
        for row in range(size):
            offset = row * (size + 1)
            for col in range(size):
                value = (value << 1) | int(pixels[offset + col] > pixels[offset + col + 1])
        return value

    @staticmethod
    def _color_histogram(image: Image.Image, bins: int = 4) -> list[float]:
        small = image.resize((96, 96), Image.Resampling.LANCZOS).convert("RGB")
        histogram = [0] * (bins ** 3)
        for red, green, blue in small.getdata():
            rbin = min(red * bins // 256, bins - 1)
            gbin = min(green * bins // 256, bins - 1)
            bbin = min(blue * bins // 256, bins - 1)
            histogram[(rbin * bins * bins) + (gbin * bins) + bbin] += 1
        total = float(sum(histogram) or 1)
        return [value / total for value in histogram]

    @staticmethod
    def _compare_image_features(source: dict[str, Any], target: dict[str, Any]) -> float:
        ahash_similarity = 1.0 - ((source["ahash"] ^ target["ahash"]).bit_count() / 64.0)
        dhash_similarity = 1.0 - ((source["dhash"] ^ target["dhash"]).bit_count() / 64.0)
        histogram_similarity = sum(min(a, b) for a, b in zip(source["histogram"], target["histogram"]))
        return round((0.28 * ahash_similarity + 0.32 * dhash_similarity + 0.40 * histogram_similarity) * 100, 1)

    @staticmethod
    def _item_photo_path(item: Item) -> Path | None:
        relative = str(getattr(item, "foto_path", "") or "").strip()
        if not relative:
            return None
        relative = relative.replace("\\", "/").lstrip("/")
        if ".." in Path(relative).parts:
            return None
        return Path(current_app.root_path) / "static" / relative