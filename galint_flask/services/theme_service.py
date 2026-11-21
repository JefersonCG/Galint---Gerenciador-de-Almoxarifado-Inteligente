"""Aparência do GALINT: três cores escolhidas (menu lateral, destaque e fundo) e os tons tirados delas.

Mesma ideia da skin do Pipocas do Biel (pipoca/tema.py), pedida pelo usuário em 21/11/2026, com uma
diferença: o GALINT é escuro (textos claros sobre fundo escuro), então aqui o menu e o fundo só aceitam
tons escuros, e o destaque aceita qualquer cor (o texto sobre ele fica claro ou escuro sozinho).

Sem personalização nenhuma variável --skin-* é definida e o site fica idêntico ao padrão: cada regra do
galint-skin.css usa a cor original como reserva. O app lê as mesmas cores em /api/mobile/tema.
"""
from __future__ import annotations

import colorsys
import re
from typing import Any

HEX = re.compile(r"^#[0-9a-f]{6}$")
LIGHT_TEXT = "#f8fafc"  # --text-light do qss_like.css
DARK_TEXT = "#0f172a"
MIN_BACKGROUND_CONTRAST = 7  # texto claro sobre o fundo das páginas (nível AAA)
MIN_MENU_CONTRAST = 4.5
SIMILAR = 50  # distância de cor abaixo da qual duas partes se confundem

DEFAULTS = {"menu": "#111827", "destaque": "#2563eb", "fundo": "#141822"}
TARGETS = {"menu": "Menu lateral", "destaque": "Destaque", "fundo": "Fundo"}

ESCURAS = [
    ("Azul-noite", "#141822"), ("Noite", "#0b1220"), ("Ardósia", "#1e293b"), ("Marinho", "#1b2a4a"),
    ("Petróleo", "#0b2a33"), ("Floresta", "#0f2a1d"), ("Oliva", "#24260f"), ("Café", "#2a1d14"),
    ("Vinho", "#3a0f1f"), ("Berinjela", "#2a1736"), ("Grafite", "#1f2125"), ("Preto", "#0a0a0a"),
]
VIVAS = [
    ("Azul", "#2563eb"), ("Ciano", "#0ea5e9"), ("Turquesa", "#0fa3b1"), ("Verde", "#16a34a"),
    ("Esmeralda", "#10b981"), ("Amarelo", "#f9bd29"), ("Laranja", "#f47c20"), ("Vermelho", "#dc2626"),
    ("Rosa", "#e0218a"), ("Roxo", "#7c3aed"), ("Lilás", "#a78bfa"), ("Gelo", "#e2e8f0"),
]
PRESETS = [
    ("GALINT", DEFAULTS["menu"], DEFAULTS["destaque"], DEFAULTS["fundo"]),
    ("Oceano", "#0b2234", "#0fa3b1", "#0a1a26"),
    ("Grafite", "#1f2125", "#f9bd29", "#16171a"),
    ("Floresta", "#0f2a1d", "#16a34a", "#0c1f16"),
    ("Vinho", "#2a0f18", "#e0218a", "#1d0b11"),
    ("Ametista", "#241337", "#a78bfa", "#170d24"),
    ("Brasa", "#1f1a14", "#f47c20", "#15120e"),
]


def normalize(color: Any) -> str | None:
    """#rrggbb em minúsculas, ou None se não for uma cor hexadecimal de 6 dígitos."""
    color = str(color or "").strip().lower()
    return color if HEX.match(color) else None


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def _hls(color: str) -> tuple[float, float, float]:
    return colorsys.rgb_to_hls(*(c / 255 for c in _rgb(color)))


def _from_hls(hue: float, lightness: float, saturation: float) -> str:
    rgb = colorsys.hls_to_rgb(hue % 1, max(0, min(1, lightness)), max(0, min(1, saturation)))
    return _hex(c * 255 for c in rgb)


def mix(a: str, b: str, weight: float) -> str:
    """Mistura: weight de a e (1 - weight) de b."""
    return _hex(x * weight + y * (1 - weight) for x, y in zip(_rgb(a), _rgb(b)))


def shade(color: str, delta: float) -> str:
    """Mesmo matiz e saturação, luminosidade deslocada (positivo clareia)."""
    hue, lightness, saturation = _hls(color)
    return _from_hls(hue, lightness + delta, saturation)


def luminance(color: str) -> float:
    def channel(c: int) -> float:
        value = c / 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def distance(a: str, b: str) -> float:
    """Distância entre cores ponderada pela visão (redmean): 0 é igual; abaixo de SIMILAR, se confundem."""
    (r1, g1, b1), (r2, g2, b2) = _rgb(a), _rgb(b)
    red = (r1 + r2) / 2
    return ((2 + red / 256) * (r1 - r2) ** 2 + 4 * (g1 - g2) ** 2 + (2 + (255 - red) / 256) * (b1 - b2) ** 2) ** 0.5


def readable(background: str) -> str:
    """Texto claro ou escuro, o que tiver mais contraste com o fundo."""
    return LIGHT_TEXT if contrast(LIGHT_TEXT, background) >= contrast(DARK_TEXT, background) else DARK_TEXT


def legible(color: str, background: str, minimum: float = 4.5) -> str:
    """A cor do mesmo matiz mais próxima da escolhida que se lê sobre o fundo (clareia ou escurece)."""
    hue, lightness, saturation = _hls(color)
    step = 0.02 if luminance(background) < 0.5 else -0.02
    tone = color
    while contrast(tone, background) < minimum and (lightness < 1 if step > 0 else lightness > 0):
        lightness = max(0.0, min(1.0, lightness + step))
        tone = _from_hls(hue, lightness, saturation)
    return tone


def _alpha(color: str, opacity: float) -> str:
    return f"{color}{max(0, min(255, round(opacity * 255))):02x}"


def derive(menu: str, destaque: str, fundo: str) -> dict[str, str]:
    """Variáveis CSS do site; as regras que as usam ficam no galint-skin.css."""
    on_accent = readable(destaque)
    accent_hover = shade(destaque, -0.08 if luminance(on_accent) > 0.5 else 0.08)
    # Barra do topo: degradê do destaque, escurecido o bastante para os textos claros dela.
    topbar_mid = legible(destaque, LIGHT_TEXT, 3)
    topbar_start = shade(topbar_mid, -0.2)
    hue, light, sat = _hls(destaque)
    topbar_end = _from_hls(hue - 0.03, min(0.62, light + 0.12), sat)
    brand = legible(destaque, fundo, 4.5)
    return {
        "--skin-bg": fundo,
        "--skin-body-1": shade(fundo, -0.03),
        "--skin-body-2": fundo,
        "--skin-panel": shade(fundo, 0.04),
        "--skin-menu-1": shade(menu, -0.02),
        "--skin-menu-2": menu,
        "--skin-menu-3": shade(menu, -0.01),
        "--skin-on-menu": readable(menu),
        "--skin-accent": destaque,
        "--skin-on-accent": on_accent,
        "--skin-accent-hover": accent_hover,
        "--skin-accent-soft": _alpha(destaque, 0.22),
        "--skin-accent-softer": _alpha(destaque, 0.12),
        "--skin-accent-line": _alpha(brand, 0.32),
        "--skin-topbar-1": topbar_start,
        "--skin-topbar-2": topbar_mid,
        "--skin-topbar-3": topbar_end,
        "--skin-brand": brand,
        "--skin-brand-soft": _alpha(brand, 0.16),
    }


NAMES = tuple(derive(**DEFAULTS))


def problems(colors: dict[str, str]) -> tuple[list[str], list[str]]:
    """Erros impedem salvar (texto ilegível); avisos só alertam."""
    errors: list[str] = []
    warnings: list[str] = []
    if contrast(LIGHT_TEXT, colors["fundo"]) < MIN_BACKGROUND_CONTRAST:
        errors.append(
            "O fundo está claro demais: os textos do GALINT são claros e ficariam difíceis de ler. "
            "Escolha um tom escuro (a paleta Escuras funciona bem)."
        )
    if contrast(LIGHT_TEXT, colors["menu"]) < MIN_MENU_CONTRAST:
        errors.append("O menu lateral está claro demais: os nomes do menu ficariam difíceis de ler. Escolha um tom escuro.")
    if distance(colors["destaque"], colors["menu"]) < SIMILAR:
        warnings.append("O destaque está quase igual ao menu lateral: o item selecionado do menu fica difícil de ver.")
    if distance(colors["destaque"], colors["fundo"]) < SIMILAR:
        warnings.append("O destaque está quase igual ao fundo: os botões ficam apagados.")
    return errors, warnings


def current(config: Any) -> dict[str, str]:
    return {
        key: normalize(getattr(config, f"tema_{key}", None)) or default
        for key, default in DEFAULTS.items()
    }


def preview(colors: dict[str, str]) -> dict[str, Any]:
    """Prévia ao vivo: as variáveis (ou 'initial', que volta à cor original de cada regra) e os alertas."""
    errors, warnings = problems(colors)
    variables = derive(**colors) if colors != DEFAULTS else dict.fromkeys(NAMES, "initial")
    return {"variables": variables, "errors": errors, "warnings": warnings}


def preset_cards(colors: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "name": name, "menu": menu, "destaque": destaque, "fundo": fundo,
            "on_menu": readable(menu),
            "active": colors == {"menu": menu, "destaque": destaque, "fundo": fundo},
        }
        for name, menu, destaque, fundo in PRESETS
    ]


def stylesheet(config: Any) -> str:
    """Folha dinâmica (/tema.css): só define as variáveis quando a aparência foi personalizada."""
    colors = current(config)
    if colors == DEFAULTS:
        return "/* Aparência padrão: valem as cores originais do GALINT. */\n"
    return ":root{" + ";".join(f"{name}:{value}" for name, value in derive(**colors).items()) + "}\n"


def app_palette(config: Any) -> dict[str, Any]:
    """Cores para o app (abertura e login inclusive). O app continua escuro: o fundo e os painéis saem
    do fundo escolhido, a barra e o menu do app saem do menu, e os botões e realces do destaque
    (clareado até ler bem sobre o fundo, porque o texto dos botões do app é escuro)."""
    colors = current(config)
    menu, destaque, fundo = colors["menu"], colors["destaque"], colors["fundo"]
    strong = legible(destaque, fundo, 4.5)
    soft = legible(shade(strong, 0.12), fundo, 7)
    return {
        "personalizada": colors != DEFAULTS,
        "menu": menu,
        "destaque": destaque,
        "fundo": fundo,
        "texto_menu": readable(menu),
        "texto_destaque": readable(destaque),
        "app": {
            "bg": fundo,
            "bgAlt": menu,
            "hero": mix(menu, fundo, 0.5),
            "heroAlt": shade(mix(menu, strong, 0.8), 0.04),
            "panel": shade(fundo, 0.04),
            "panelAlt": shade(fundo, 0.08),
            "panelSoft": shade(fundo, 0.12),
            "primary": soft,
            "primaryStrong": strong,
            "borderStrong": f"rgba({', '.join(str(c) for c in _rgb(strong))}, 0.28)",
        },
    }


def save(config: Any, form: Any) -> dict[str, str]:
    """Salva as cores do formulário (ou volta ao padrão). ValueError com a mensagem se não der."""
    if form.get("acao") == "padrao":
        colors = dict(DEFAULTS)
    else:
        colors = {key: normalize(form.get(key)) for key in DEFAULTS}  # type: ignore[misc]
        if not all(colors.values()):
            raise ValueError("Escolha as três cores em hexadecimal, como #2563eb.")
        errors, _ = problems(colors)  # type: ignore[arg-type]
        if errors:
            raise ValueError(errors[0])
    for key, value in colors.items():
        setattr(config, f"tema_{key}", None if colors == DEFAULTS else value)
    return colors  # type: ignore[return-value]
