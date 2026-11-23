"""Aparência do GALINT: três cores escolhidas (menu lateral, destaque e fundo) e os tons tirados delas.

Mesma skin do Pipocas do Biel (pipoca/tema.py), pedida pelo usuário em 21/11/2026. Como lá:
- o fundo é a cor das páginas (a área de conteúdo do GALINT é clara) e só aceita tons claros,
  para os textos escuros continuarem legíveis; ganha os mesmos brilhos suaves do Pipocas;
- o menu lateral aceita qualquer cor: o texto dele fica claro ou escuro sozinho (WCAG);
- o destaque pinta botões, links, abas ativas e o item selecionado do menu;
- os cards (Bootstrap .card, summary-card, section-panel) ganham borda e cabeçalho no tom do menu.

Correção de 21/11/2026: a primeira versão tratava o GALINT inteiro como escuro (fundo só escuro,
textos claros) e a tela Aparência ficou ilegível sobre o conteúdo claro. Uma skin salva naquela
versão com fundo escuro volta ao fundo padrão em current().

Sem personalização nenhuma variável --skin-* é definida e o site fica idêntico ao padrão: cada regra
do galint-skin.css usa a cor original como reserva. O app lê as mesmas cores em /api/mobile/tema.
"""
from __future__ import annotations

import colorsys
import re
from typing import Any

HEX = re.compile(r"^#[0-9a-f]{6}$")
LIGHT_TEXT = "#f8fafc"  # --text-light do qss_like.css
DARK_TEXT = "#0f172a"  # --text-dark do qss_like.css (texto das páginas)
INK, MUTED = "#0f172a", "#64748b"
MIN_BACKGROUND_CONTRAST = 7  # texto das páginas sobre o fundo (nível AAA), como no Pipocas
SIMILAR = 50  # distância de cor abaixo da qual duas partes se confundem

DEFAULTS = {"menu": "#111827", "destaque": "#2563eb", "fundo": "#eef4fb"}
TARGETS = {"menu": "Menu lateral", "destaque": "Destaque", "fundo": "Fundo"}

# Paletas e skins do Pipocas (pipoca/tema.py), mais a GALINT padrão.
PASTEIS = [("Rosa bebê", "#f8c8dc"), ("Pêssego", "#ffd8b1"), ("Salmão", "#ffaa95"), ("Baunilha", "#fff1b5"),
           ("Menta", "#bdf0d4"), ("Verde-água", "#b5ead7"), ("Céu", "#bfe3ff"), ("Lavanda", "#d9c8f5"),
           ("Lilás", "#e3c6f0"), ("Algodão-doce", "#f7c6e8"), ("Areia", "#eadbc8"), ("Nuvem", "#dde3ea")]
SOLIDAS = [("Roxo pipoca", "#442260"), ("Vermelho", "#d62839"), ("Laranja", "#f47c20"), ("Amarelo pipoca", "#f9bd29"),
           ("Verde", "#2e8b57"), ("Azul", "#1f6feb"), ("Marinho", "#1b2a4a"), ("Turquesa", "#0fa3b1"),
           ("Rosa choque", "#e0218a"), ("Vinho", "#7b1e3a"), ("Grafite", "#2b2d33"), ("Preto", "#111111")]
PRESETS = [("GALINT", DEFAULTS["menu"], DEFAULTS["destaque"], DEFAULTS["fundo"]),
           ("Pipoca", "#442260", "#f9bd29", "#fffaf2"),
           ("Algodão-doce", "#f7c6e8", "#bfe3ff", "#fff8fc"),
           ("Menta", "#bdf0d4", "#ffd8b1", "#f6fff9"),
           ("Lavanda", "#d9c8f5", "#fff1b5", "#fbf8ff"),
           ("Grafite", "#2b2d33", "#f9bd29", "#f5f5f7"),
           ("Oceano", "#1b2a4a", "#0fa3b1", "#f3f8fb"),
           ("Morango", "#7b1e3a", "#f8c8dc", "#fff6f7")]


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


def tint(color: str, lightness: float, saturation: float | None = None) -> str:
    """Mesmo matiz com outra luminosidade (e saturação limitada): faixas, bordas e fundos suaves."""
    hue, _, sat = _hls(color)
    return _from_hls(hue, lightness, sat if saturation is None else min(sat, saturation))


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


def _darken_for(background: str) -> bool:
    return contrast("#000000", background) >= contrast("#ffffff", background)


def readable(background: str) -> str:
    """Texto claro ou escuro, o que tiver mais contraste com o fundo (puro nos tons médios)."""
    light, dark = contrast(LIGHT_TEXT, background), contrast(DARK_TEXT, background)
    if max(light, dark) >= 4.5:
        return LIGHT_TEXT if light >= dark else DARK_TEXT
    return "#000000" if _darken_for(background) else "#ffffff"


def legible(color: str, background: str, minimum: float = 4.5) -> str:
    """A cor do mesmo matiz mais próxima da escolhida que se lê sobre o fundo (escurece ou clareia)."""
    hue, lightness, saturation = _hls(color)
    step = -0.02 if _darken_for(background) else 0.02
    tone = color
    while contrast(tone, background) < minimum and (lightness > 0 if step < 0 else lightness < 1):
        lightness = max(0.0, min(1.0, lightness + step))
        tone = _from_hls(hue, lightness, saturation)
    return tone


def _alpha(color: str, opacity: float) -> str:
    return f"{color}{max(0, min(255, round(opacity * 255))):02x}"


def _rgb_text(color: str) -> str:
    return ", ".join(str(c) for c in _rgb(color))


def derive(menu: str, destaque: str, fundo: str) -> dict[str, str]:
    """Variáveis CSS do site; as regras que as usam ficam no galint-skin.css."""
    hue, lightness, saturation = _hls(menu)
    on_menu = readable(menu)
    dark_menu = luminance(on_menu) > 0.5  # texto claro: o menu é escuro
    side_text = tint(menu, 0.93, 0.6) if dark_menu else tint(menu, 0.15, 0.5)
    on_accent = readable(destaque)
    accent_hover = shade(destaque, -0.08 if luminance(on_accent) > 0.5 else 0.08)
    brand = legible(_from_hls(hue, max(lightness, 0.38), saturation), fundo)
    accent_text = legible(destaque, fundo, 4.5)  # destaque usado como texto (links) sobre o fundo
    # Barra do topo (textos claros): degradê do destaque quando ele aguenta texto claro; destaque
    # claro (amarelo, pêssego) escurecido ficava cor de oliva, então aí a barra usa o menu e o
    # destaque vira uma faixa embaixo dela.
    accent_on_top = contrast(LIGHT_TEXT, destaque) >= 2.5
    top_base = destaque if accent_on_top else menu
    topbar_mid = legible(top_base, LIGHT_TEXT, 3)
    b_hue, b_light, b_sat = _hls(top_base)
    glow_1, glow_2 = tint(destaque, 0.86), tint(menu, 0.95)
    # Modais escuros (23/11/2026: "todos os modais se adaptem às mudanças de cor"): superfícies no
    # matiz do menu, sempre escuras (o texto deles é claro), com o brilho e as bordas do destaque.
    s_sat = min(saturation, 0.55)
    surfaces = [_from_hls(hue, lightness_value, s_sat) for lightness_value in (0.05, 0.075, 0.11, 0.15)]
    accent_rgb = _rgb_text(destaque)
    return {
        # menu lateral
        "--skin-menu-1": shade(menu, 0.01),
        "--skin-menu-2": menu,
        "--skin-menu-3": shade(menu, -0.02),
        "--skin-on-menu": on_menu,
        "--skin-nav": legible(side_text, menu),
        "--skin-menu-soft": mix(on_menu, menu, 0.06),
        "--skin-menu-hover": mix(on_menu, menu, 0.12),
        "--skin-menu-line": mix(on_menu, menu, 0.18),
        "--skin-menu-footer": shade(menu, -0.03),
        # destaque
        "--skin-accent": destaque,
        "--skin-on-accent": on_accent,
        "--skin-accent-hover": accent_hover,
        "--skin-accent-soft": _alpha(destaque, 0.28),
        "--skin-accent-softer": _alpha(destaque, 0.14),
        "--skin-accent-line": _alpha(destaque, 0.45),
        "--skin-accent-text": accent_text,
        "--skin-topbar-1": shade(topbar_mid, -0.2 if accent_on_top else -0.06),
        "--skin-topbar-2": topbar_mid,
        "--skin-topbar-3": (_from_hls(b_hue - 0.03, min(0.62, b_light + 0.12), b_sat) if accent_on_top
                            else legible(shade(topbar_mid, 0.08), LIGHT_TEXT, 3)),
        "--skin-topbar-border": "1px solid rgba(255, 255, 255, 0.08)" if accent_on_top else f"4px solid {destaque}",
        # fundo das páginas (igual ao body do Pipocas: a cor e dois brilhos suaves)
        "--skin-bg": fundo,
        "--skin-content-bg": (
            f"radial-gradient(circle at 95% 3%, {glow_1} 0, transparent 25%), "
            f"radial-gradient(circle at 40% 30%, {glow_2} 0, transparent 35%), {fundo}"
        ),
        "--skin-muted": legible(MUTED, fundo),
        # cards
        "--skin-brand": brand,
        "--skin-eyebrow": legible(_from_hls(hue + 0.04, max(lightness, 0.47), saturation * 0.6), fundo),
        "--skin-brand-soft": tint(menu, 0.96),
        "--skin-panel-line": tint(menu, 0.86, 0.35),
        "--skin-panel-shadow": "0 6px 25px " + _alpha(tint(menu, 0.25, 0.4), 0.08),
        # Bootstrap (botões, links, abas, caixas marcadas)
        "--bs-primary": accent_text,
        "--bs-primary-rgb": _rgb_text(accent_text),
        "--bs-link-color": accent_text,
        "--bs-link-color-rgb": _rgb_text(accent_text),
        "--bs-link-hover-color": shade(accent_text, -0.1),
        "--bs-link-hover-color-rgb": _rgb_text(shade(accent_text, -0.1)),
        # modais (regras em static/css/galint-skin-modais.css, carregada só com aparência personalizada)
        "--skin-surface-0": surfaces[0],
        "--skin-surface-1": surfaces[1],
        "--skin-surface-2": surfaces[2],
        "--skin-surface-3": surfaces[3],
        "--skin-surface-1-rgb": _rgb_text(surfaces[1]),
        "--skin-surface-2-rgb": _rgb_text(surfaces[2]),
        "--skin-accent-rgb": accent_rgb,
        "--skin-accent-on-dark": legible(destaque, surfaces[1], 4.5),
        "--skin-modal-bg": (
            f"radial-gradient(circle at top right, rgba({accent_rgb}, 0.16), transparent 34%), "
            f"linear-gradient(180deg, {surfaces[1]} 0%, {surfaces[2]} 100%)"
        ),
        "--skin-modal-head": (
            f"radial-gradient(circle at top right, rgba({accent_rgb}, 0.2), transparent 34%), "
            f"linear-gradient(135deg, {surfaces[3]} 0%, {surfaces[1]} 100%)"
        ),
        "--skin-modal-foot": f"linear-gradient(180deg, {surfaces[0]} 0%, {surfaces[1]} 100%)",
        "--skin-modal-line": f"rgba({accent_rgb}, 0.24)",
        "--skin-modal-light-head": f"linear-gradient(180deg, {tint(menu, 0.97)} 0%, {tint(menu, 0.92, 0.45)} 100%)",
    }


NAMES = tuple(derive(**DEFAULTS))


def background_ok(fundo: str) -> bool:
    return contrast(INK, fundo) >= MIN_BACKGROUND_CONTRAST


def problems(colors: dict[str, str]) -> tuple[list[str], list[str]]:
    """Erros impedem salvar (texto ilegível); avisos só alertam. As mesmas regras do Pipocas."""
    errors: list[str] = []
    warnings: list[str] = []
    if not background_ok(colors["fundo"]):
        errors.append(
            "O fundo está escuro demais: os textos das páginas ficariam difíceis de ler. "
            "Escolha um tom mais claro (os pastéis funcionam bem)."
        )
    if distance(colors["destaque"], colors["menu"]) < SIMILAR:
        warnings.append("O destaque está quase igual ao menu lateral: o item selecionado do menu fica difícil de ver.")
    if min(distance(colors["destaque"], "#ffffff"), distance(colors["destaque"], colors["fundo"])) < SIMILAR:
        warnings.append("O destaque está quase igual ao fundo: os botões ficam apagados.")
    if distance(colors["menu"], colors["fundo"]) < SIMILAR:
        warnings.append("O menu lateral está quase igual ao fundo: a divisão entre eles some.")
    return errors, warnings


def current(config: Any) -> dict[str, str]:
    colors = {
        key: normalize(getattr(config, f"tema_{key}", None)) or default
        for key, default in DEFAULTS.items()
    }
    if not background_ok(colors["fundo"]):
        # Skin salva na primeira versão (fundo só escuro): o conteúdo do GALINT é claro.
        colors["fundo"] = DEFAULTS["fundo"]
    return colors


# Na prévia da skin padrão, as variáveis do Bootstrap voltam aos valores dele: 'initial' numa
# variável que o próprio Bootstrap define apagaria a cor (text-primary, links) em vez de restaurá-la.
BOOTSTRAP_DEFAULTS = {
    "--bs-primary": "#0d6efd",
    "--bs-primary-rgb": "13, 110, 253",
    "--bs-link-color": "#0d6efd",
    "--bs-link-color-rgb": "13, 110, 253",
    "--bs-link-hover-color": "#0a58ca",
    "--bs-link-hover-color-rgb": "10, 88, 202",
}


def preview(colors: dict[str, str]) -> dict[str, Any]:
    """Prévia ao vivo: as variáveis (ou 'initial', que volta à cor original de cada regra) e os alertas."""
    errors, warnings = problems(colors)
    if colors != DEFAULTS:
        variables = derive(**colors)
    else:
        variables = {name: BOOTSTRAP_DEFAULTS.get(name, "initial") for name in NAMES}
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


MODALS_CSS_VERSION = "20261123"


def _modals_css_url() -> str:
    try:
        from flask import url_for

        return url_for("static", filename="css/galint-skin-modais.css", v=MODALS_CSS_VERSION)
    except Exception:
        return f"/static/css/galint-skin-modais.css?v={MODALS_CSS_VERSION}"


def stylesheet(config: Any) -> str:
    """Folha dinâmica (/tema.css): só existe quando a aparência foi personalizada. Aí define as
    variáveis e puxa as regras dos modais (galint-skin-modais.css), que não têm cor de reserva:
    sem tema, nem são carregadas, e os modais ficam exatamente como antes."""
    colors = current(config)
    if colors == DEFAULTS:
        return "/* Aparência padrão: valem as cores originais do GALINT. */\n"
    variables = ":root{" + ";".join(f"{name}:{value}" for name, value in derive(**colors).items()) + "}\n"
    return f'@import url("{_modals_css_url()}");\n' + variables


def app_palette(config: Any) -> dict[str, Any]:
    """Cores para o app (abertura e login inclusive). O app é escuro: o fundo e os painéis saem do
    matiz do menu (sempre escurecido, mesmo de um menu pastel) e os botões e realces do destaque,
    clareado até ler bem sobre esse fundo (o texto dos botões do app é escuro)."""
    colors = current(config)
    menu, destaque, fundo = colors["menu"], colors["destaque"], colors["fundo"]
    hue, _, sat = _hls(menu)
    sat = min(sat, 0.55)

    def dark(lightness: float) -> str:
        return _from_hls(hue, lightness, sat)

    bg = dark(0.07)
    strong = legible(destaque, bg, 4.5)
    soft = legible(shade(strong, 0.12), bg, 7)
    return {
        "personalizada": colors != DEFAULTS,
        "menu": menu,
        "destaque": destaque,
        "fundo": fundo,
        "texto_menu": readable(menu),
        "texto_destaque": readable(destaque),
        "app": {
            "bg": bg,
            "bgAlt": dark(0.11),
            "hero": dark(0.13),
            "heroAlt": dark(0.18),
            "panel": dark(0.12),
            "panelAlt": dark(0.16),
            "panelSoft": dark(0.2),
            "primary": soft,
            "primaryStrong": strong,
            "borderStrong": f"rgba({_rgb_text(strong)}, 0.28)",
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
