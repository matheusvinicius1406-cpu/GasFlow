"""Gera o ícone do GasFlow Desktop (build/icon.ico + icon.png).

Visual: fundo arredondado azul-escuro, cilindro de gás (botijão) laranja
com chama amarela e as letras "GF" na base. Multi-resolução: 16–256 px.

Uso: python scripts/make_icon.py  (requer Pillow)
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "build"
SIZE = 256
S = SIZE / 256  # fator de escala


def rounded_rect(draw: ImageDraw.ImageDraw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def draw_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # ── Fundo arredondado (azul-escuro) ──────────────────────
    rounded_rect(d, (8 * S, 8 * S, 248 * S, 248 * S), 48 * S, (15, 32, 68, 255))
    # brilho sutil no topo
    d.ellipse((30 * S, -60 * S, 226 * S, 120 * S), fill=(28, 55, 105, 90))

    cx = 128 * S  # centro horizontal

    # ── Corpo do botijão (laranja) ───────────────────────────
    body_top = 84 * S
    body_bottom = 210 * S
    body_w = 78 * S
    # base arredondada
    rounded_rect(
        d,
        (cx - body_w / 2, body_top, cx + body_w / 2, body_bottom),
        26 * S,
        (232, 119, 34, 255),
    )
    # anel/ombro superior do botijão
    d.rounded_rectangle(
        (cx - 34 * S, body_top - 12 * S, cx + 34 * S, body_top + 14 * S),
        radius=8 * S,
        fill=(208, 102, 24, 255),
    )
    # válvula
    d.rounded_rectangle(
        (cx - 10 * S, body_top - 30 * S, cx + 10 * S, body_top - 6 * S),
        radius=4 * S,
        fill=(180, 180, 190, 255),
    )
    # reflexo lateral
    d.rounded_rectangle(
        (
            cx - body_w / 2 + 10 * S,
            body_top + 18 * S,
            cx - body_w / 2 + 20 * S,
            body_bottom - 16 * S,
        ),
        radius=5 * S,
        fill=(248, 160, 80, 160),
    )

    # ── Chama (amarela com núcleo claro) ─────────────────────
    flame_cx = cx
    flame_cy = 62 * S
    # externa
    d.polygon(
        [
            (flame_cx, flame_cy - 34 * S),
            (flame_cx + 22 * S, flame_cy + 6 * S),
            (flame_cx + 13 * S, flame_cy + 22 * S),
            (flame_cx - 13 * S, flame_cy + 22 * S),
            (flame_cx - 22 * S, flame_cy + 6 * S),
        ],
        fill=(255, 193, 7, 255),
    )
    # núcleo
    d.polygon(
        [
            (flame_cx, flame_cy - 14 * S),
            (flame_cx + 11 * S, flame_cy + 8 * S),
            (flame_cx - 11 * S, flame_cy + 8 * S),
        ],
        fill=(255, 236, 150, 255),
    )

    # ── Badge "GF" na base ───────────────────────────────────
    badge_r = 34 * S
    badge_cy = 172 * S
    d.ellipse(
        (cx - badge_r, badge_cy - badge_r, cx + badge_r, badge_cy + badge_r),
        fill=(15, 32, 68, 235),
        outline=(255, 193, 7, 255),
        width=4,
    )
    text = "GF"
    font = None
    for candidate in ("arialbd.ttf", "Arial Bold.ttf", "seguisb.ttf", "arial.ttf"):
        try:
            font = ImageFont.truetype(candidate, int(38 * S))
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(
        (cx - tw / 2 - bbox[0], badge_cy - th / 2 - bbox[1]),
        text,
        font=font,
        fill=(255, 255, 255, 255),
    )

    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img = draw_icon()

    png_path = OUT / "icon.png"
    img.save(png_path, "PNG")

    ico_path = OUT / "icon.ico"
    img.save(
        ico_path,
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

    print(f"OK: {png_path}")
    print(f"OK: {ico_path}")


if __name__ == "__main__":
    main()
