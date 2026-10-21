"""Gera o símbolo unificado do GasFlow em todos os destinos do projeto.

Saídas (todas derivadas da mesma arte, para a marca bater em qualquer lugar):

- ``mobile/android/.../mipmap-*/ic_launcher{,_round}.png`` — launcher Android
  legado (minSdk 24 não lê adaptive icons);
- ``mobile/android/.../mipmap-anydpi-v26/ic_launcher{,_round}.xml`` +
  ``mipmap-xxxhdpi/ic_launcher_foreground.png`` — adaptive icon (Android 8+);
- ``mobile/assets/logo-mark.png`` — marca transparente usada no splash/login;
- ``desktop/build/icon.png`` e ``desktop/build/icon.ico`` — electron-builder;
- ``frontend/public/favicon.svg`` é escrito à mão (vetorial, mesmo desenho).

Uso::

    python scripts/generate_brand_icons.py

A geometria é desenhada em alta resolução (4x) e reduzida com LANCZOS, para a
chama ter borda limpa em 48 px e em 1024 px sem arquivo de origem.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]

MOBILE_RES = ROOT / "mobile" / "android" / "app" / "src" / "main" / "res"
MOBILE_ASSETS = ROOT / "mobile" / "assets"
DESKTOP_BUILD = ROOT / "desktop" / "build"

# Paleta — espelha ``frontend/src/index.css`` (tema dark GasFlow).
BG_TOP = (19, 21, 30)
BG_BOTTOM = (8, 9, 13)
GLOW = (249, 115, 22)
FLAME_TOP = (255, 214, 92)
FLAME_MID = (249, 115, 22)
FLAME_BOTTOM = (217, 79, 11)
CORE_TOP = (255, 247, 224)
CORE_BOTTOM = (255, 214, 130)

SUPERSAMPLE = 4


def lerp(a: tuple[int, ...], b: tuple[int, ...], t: float) -> tuple[int, ...]:
    """Interpola linearmente entre duas cores."""
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def vertical_gradient(
    size: int, top: tuple[int, ...], bottom: tuple[int, ...]
) -> Image.Image:
    """Cria um gradiente vertical ``top`` → ``bottom`` em uma imagem RGB."""
    rows = np.linspace(0.0, 1.0, size)
    ramp = np.array([lerp(top, bottom, float(t)) for t in rows], dtype=np.uint8)
    data = np.broadcast_to(ramp[:, None, :], (size, size, 3)).copy()
    return Image.fromarray(data, "RGB")


def cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = 64,
) -> list[tuple[float, float]]:
    """Amostra uma cúbica de Bézier de ``p0`` a ``p3``."""
    points = []
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
        points.append((x, y))
    return points


def transform(
    points: list[tuple[float, float]], box: tuple[int, int, int, int]
) -> list[tuple[float, float]]:
    """Leva pontos em espaço unitário (-1..1, y para baixo) para o retângulo ``box``."""
    x0, y0, x1, y1 = box
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    rx = (x1 - x0) / 2
    ry = (y1 - y0) / 2
    return [(cx + px * rx, cy + py * ry) for px, py in points]


def flame_segments(lean: float = 0.12) -> list[tuple[tuple[float, float], ...]]:
    """Quatro trechos da chama em espaço unitário (ponta em cima, y baixo).

    A ponta sai do eixo para o desenho não ficar simétrico/estático.
    """
    tip = (lean, -1.0)
    return [
        (tip, (0.44, -0.62), (0.90, -0.14), (0.74, 0.42)),
        ((0.74, 0.42), (0.64, 0.84), (0.32, 0.99), (0.02, 0.99)),
        ((0.02, 0.99), (-0.34, 0.99), (-0.70, 0.80), (-0.75, 0.36)),
        ((-0.75, 0.36), (-0.78, -0.10), (-0.30, -0.62), tip),
    ]


def core_segments() -> list[tuple[tuple[float, float], ...]]:
    """Miolo da chama — a segunda lingueta, com ponta assimétrica."""
    tip = (0.08, -0.54)
    return [
        (tip, (0.34, -0.28), (0.40, 0.08), (0.26, 0.30)),
        ((0.26, 0.30), (0.14, 0.54), (-0.18, 0.54), (-0.28, 0.28)),
        ((-0.28, 0.28), (-0.38, 0.02), (-0.16, -0.30), tip),
    ]


def flame_outline() -> list[tuple[float, float]]:
    """Amostragem do contorno da chama para desenho em PIL."""
    points: list[tuple[float, float]] = []
    for segment in flame_segments():
        points.extend(cubic(*segment))
    return points


def core_outline() -> list[tuple[float, float]]:
    """Amostragem do miolo para desenho em PIL."""
    points: list[tuple[float, float]] = []
    for segment in core_segments():
        points.extend(cubic(*segment))
    return points


def svg_path(
    segments: list[tuple[tuple[float, float], ...]],
    box: tuple[int, int, int, int],
    decimals: int = 1,
) -> str:
    """Converte segmentos em espaço unitário para ``d`` de path SVG no ``box``."""
    cx, cy, _ = _axis(box)
    rx = (box[2] - box[0]) / 2
    ry = (box[3] - box[1]) / 2

    def px(point: tuple[float, float]) -> str:
        return f"{cx + point[0] * rx:.{decimals}f} {cy + point[1] * ry:.{decimals}f}"

    commands = [f"M{px(segments[0][0])}"]
    for seg in segments:
        commands.append(f"C{px(seg[1])} {px(seg[2])} {px(seg[3])}")
    return " ".join(commands) + " Z"


def shape_mask(size: int, polygons: list[list[tuple[float, float]]]) -> Image.Image:
    """Máscara L branca com os polígonos (já em pixels) desenhados."""
    scale = SUPERSAMPLE
    mask = Image.new("L", (size * scale, size * scale), 0)
    draw = ImageDraw.Draw(mask)
    for polygon in polygons:
        draw.polygon([(x * scale, y * scale) for x, y in polygon], fill=255)
    return mask.resize((size, size), Image.Resampling.LANCZOS)


def flame_layer(
    size: int,
    box: tuple[int, int, int, int],
    top: tuple[int, ...],
    bottom: tuple[int, ...],
    outline: list[tuple[float, float]],
) -> tuple[Image.Image, Image.Image]:
    """Camada de chama: gradiente recortado pela máscara do contorno."""
    gradient = vertical_gradient(size, top, bottom).convert("RGBA")
    mask = shape_mask(size, [transform(outline, box)])
    return gradient, mask


def boxes(
    size: int, margin: float = 0.30
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Retângulos da chama e do miolo para um canvas de ``size`` px."""
    span = int(size * (1 - margin))
    offset = (size - span) // 2
    flame = (
        offset,
        offset + int(size * 0.04),
        offset + span,
        offset + span + int(size * 0.04),
    )
    x0, y0, _, y1 = flame
    core = (
        x0 + int(span * 0.28),
        y0 + int(span * 0.45),
        x0 + int(span * 0.72),
        y0 + int(span * 0.94),
    )
    return flame, core


def _axis(box: tuple[int, int, int, int]) -> tuple[float, float, float]:
    """Centro e raio (eixo x) do retângulo — usado por PIL e pelo SVG."""
    x0, y0, x1, y1 = box
    return (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2


def render_mark(size: int, background: str = "dark") -> Image.Image:
    """Renderiza a marca completa (``dark`` = badge do launcher, ``none`` = PNG transparente)."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if background == "dark":
        gradient = vertical_gradient(size, BG_TOP, BG_BOTTOM).convert("RGBA")
        glow = _radial_glow(size)
        gradient = Image.alpha_composite(gradient, glow)
        radius = round(size * 0.225)
        badge = Image.new(
            "RGBA", (size * SUPERSAMPLE, size * SUPERSAMPLE), (0, 0, 0, 0)
        )
        ImageDraw.Draw(badge).rounded_rectangle(
            [0, 0, size * SUPERSAMPLE - 1, size * SUPERSAMPLE - 1],
            radius=radius * SUPERSAMPLE,
            fill=(255, 255, 255, 255),
        )
        badge = badge.resize((size, size), Image.Resampling.LANCZOS)
        canvas.paste(gradient, (0, 0), badge)

    margin = 0.30 if background == "dark" else 0.06
    flame_box, core_box = boxes(size, margin)
    flame, flame_mask = flame_layer(
        size, flame_box, FLAME_TOP, FLAME_BOTTOM, flame_outline()
    )
    canvas = Image.alpha_composite(canvas, _paste_mask(flame, flame_mask))

    core, core_mask = flame_layer(size, core_box, CORE_TOP, CORE_BOTTOM, core_outline())
    return Image.alpha_composite(canvas, _paste_mask(core, core_mask))


def _paste_mask(layer: Image.Image, mask: Image.Image) -> Image.Image:
    """Devolve ``layer`` recortado por ``mask`` como RGBA."""
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.paste(layer, (0, 0), mask)
    return out


def _radial_glow(size: int) -> Image.Image:
    """Globo laranja suave atrás da chama (dá profundidade ao badge escuro)."""
    scale = SUPERSAMPLE
    field = Image.new("L", (size * scale, size * scale), 0)
    draw = ImageDraw.Draw(field)
    radius = int(size * scale * 0.34)
    cx = cy = size * scale // 2
    for step in range(24, 0, -1):
        r = int(radius * step / 24)
        value = round(26 * (1 - step / 24) ** 2)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=value)
    field = field.resize((size, size), Image.Resampling.LANCZOS)
    glow = Image.new("RGBA", (size, size), (*GLOW, 0))
    glow.putalpha(field)
    return glow


def save_rgba(image: Image.Image, path: Path) -> None:
    """Grava PNG criando a pasta de destino quando preciso."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def write_android_icons() -> None:
    """Launcher legado (todas as densidades) + adaptive icon do Android 8+."""
    densities = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    for density, size in densities.items():
        folder = MOBILE_RES / f"mipmap-{density}"
        save_rgba(render_mark(size, "dark"), folder / "ic_launcher.png")

        circle = Image.new(
            "RGBA", (size * SUPERSAMPLE, size * SUPERSAMPLE), (0, 0, 0, 0)
        )
        ImageDraw.Draw(circle).ellipse(
            [0, 0, size * SUPERSAMPLE - 1, size * SUPERSAMPLE - 1],
            fill=(255, 255, 255, 255),
        )
        clip = circle.resize((size, size), Image.Resampling.LANCZOS)
        round_icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        round_icon.paste(render_mark(size, "dark"), (0, 0), clip)
        save_rgba(round_icon, folder / "ic_launcher_round.png")

    # Adaptive: camada de fundo é cor (values/colors.xml), foreground é a arte
    # com folga — o launcher recorta o círculo/mask por conta dele.
    save_rgba(
        render_mark(432, "none"),
        MOBILE_RES / "mipmap-xxxhdpi" / "ic_launcher_foreground.png",
    )
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
            '    <background android:drawable="@color/ic_launcher_background"/>\n'
            '    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>\n'
            "</adaptive-icon>\n"
        )
        target = MOBILE_RES / "mipmap-anydpi-v26" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(xml, encoding="utf-8")


def write_app_logo() -> None:
    """Marca transparente usada pela UI (splash, login)."""
    save_rgba(render_mark(512, "none"), MOBILE_ASSETS / "logo-mark.png")
    save_rgba(render_mark(512, "dark"), MOBILE_ASSETS / "logo-badge.png")


def write_desktop_icons() -> None:
    """``icon.png`` (512) e ``icon.ico`` multi-tamanho do electron-builder."""
    save_rgba(render_mark(512, "dark"), DESKTOP_BUILD / "icon.png")
    source = render_mark(256, "dark").convert("RGBA")
    DESKTOP_BUILD.mkdir(parents=True, exist_ok=True)
    source.save(
        DESKTOP_BUILD / "icon.ico",
        format="ICO",
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )


FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100" role="img" aria-label="GasFlow">
  <defs>
    <linearGradient id="gfBg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#{bg_top}" />
      <stop offset="1" stop-color="#{bg_bottom}" />
    </linearGradient>
    <radialGradient id="gfGlow" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#{glow}" stop-opacity="0.16" />
      <stop offset="0.65" stop-color="#{glow}" stop-opacity="0.05" />
      <stop offset="1" stop-color="#{glow}" stop-opacity="0" />
    </radialGradient>
    <linearGradient id="gfFlame" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#{flame_top}" />
      <stop offset="0.5" stop-color="#{flame_mid}" />
      <stop offset="1" stop-color="#{flame_bottom}" />
    </linearGradient>
    <linearGradient id="gfCore" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#{core_top}" />
      <stop offset="1" stop-color="#{core_bottom}" />
    </linearGradient>
  </defs>
  <rect width="100" height="100" rx="22.5" fill="url(#gfBg)" />
  <circle cx="50" cy="50" r="34" fill="url(#gfGlow)" />
  <path fill="url(#gfFlame)" d="{flame}" />
  <path fill="url(#gfCore)" d="{core}" />
</svg>
"""


def hex_of(color: tuple[int, ...]) -> str:
    """Cor RGB em ``#rrggbb``."""
    return "".join(f"{channel:02X}" for channel in color)


def write_favicon_svg() -> None:
    """Favicon vetorial do web — mesma geometria dos PNG."""
    flame_box, core_box = boxes(100)
    svg = FAVICON_SVG.format(
        bg_top=hex_of(BG_TOP),
        bg_bottom=hex_of(BG_BOTTOM),
        glow=hex_of(GLOW),
        flame_top=hex_of(FLAME_TOP),
        flame_mid=hex_of(FLAME_MID),
        flame_bottom=hex_of(FLAME_BOTTOM),
        core_top=hex_of(CORE_TOP),
        core_bottom=hex_of(CORE_BOTTOM),
        flame=svg_path(flame_segments(), flame_box),
        core=svg_path(core_segments(), core_box),
    )
    save_text(svg, ROOT / "frontend" / "public" / "favicon.svg")


def save_text(content: str, path: Path) -> None:
    """Grava UTF-8 sem BOM criando a pasta de destino quando preciso."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    """Gera todos os artefatos de marca."""
    write_android_icons()
    write_app_logo()
    write_desktop_icons()
    write_favicon_svg()
    print(
        "ok: mipmaps Android + adaptive, logo do app, icon.png/ico do desktop, favicon.svg"
    )


if __name__ == "__main__":
    main()
