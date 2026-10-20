"""Drawn product pictures for the demo products, so the sell screen has photos without any downloads.

Fill in every demo product that has no photo yet (database from server/.env):

    .venv\\Scripts\\python -m app.demo_images
"""

import io
import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from sqlalchemy import select
from sqlalchemy.orm import Session

from .images import save_product_image
from .models import Product

SIZE = 800
SCALE = 2  # drawn at double size, then shrunk: smooth edges

# name: (shape, body colour, accent colour, label lines)
ART: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "Coca-Cola 330ml": ("can", "#d7141a", "#ffffff", ("Cola", "330ml")),
    "Angkor Beer 330ml": ("can", "#c9a227", "#7a1f1f", ("ANGKOR", "Beer")),
    "Mineral Water 500ml": ("bottle", "#7cc4f0", "#1565c0", ("Mineral", "Water")),
    "Iced Coffee": ("cup", "#6f4e37", "#f3e5d0", ("Iced", "Coffee")),
    "Red Bull 250ml": ("slimcan", "#1e3a8a", "#e11d48", ("Energy", "250ml")),
    "Sprite 330ml": ("can", "#16a34a", "#facc15", ("Lemon", "Lime")),
    "Cambodia Beer 330ml": ("can", "#1d4ed8", "#facc15", ("CAMBODIA", "Beer")),
    "Green Tea 500ml": ("bottle", "#65a30d", "#ecfccb", ("Green", "Tea")),
    "Fresh Milk 1L": ("carton", "#f8fafc", "#2563eb", ("Fresh", "Milk")),
    "Orange Juice 1L": ("carton", "#f97316", "#fef3c7", ("Orange", "Juice")),
    "Lay's Classic 50g": ("bag", "#facc15", "#dc2626", ("Potato", "Chips")),
    "Oreo 133g": ("pack", "#1e40af", "#f8fafc", ("Cookies", "133g")),
    "Peanuts 100g": ("bag", "#b45309", "#fde68a", ("Roasted", "Peanuts")),
    "Pringles Original 107g": ("tube", "#dc2626", "#fef2f2", ("Crisps", "Original")),
    "KitKat 4 Finger": ("bar", "#dc2626", "#ffffff", ("Wafer", "4 Finger")),
    "Dried Mango 100g": ("bag", "#f59e0b", "#7c2d12", ("Dried", "Mango")),
    "Cup Cake Vanilla": ("cupcake", "#fde68a", "#ec4899", ()),
    "Jasmine Rice 5kg": ("sack", "#f5f5f4", "#15803d", ("Jasmine", "Rice 5kg")),
    "Mama Instant Noodles": ("pack", "#f59e0b", "#b91c1c", ("Instant", "Noodles")),
    "Fish Sauce 700ml": ("bottle", "#92400e", "#fef3c7", ("Fish", "Sauce")),
    "Eggs (10 pcs)": ("eggs", "#d6b48a", "#fff7ed", ()),
    "Cooking Oil 1L": ("bottle", "#eab308", "#166534", ("Cooking", "Oil")),
    "Sugar 1kg": ("sack", "#ffffff", "#0ea5e9", ("Sugar", "1kg")),
    "Kampot Pepper 100g": ("jar", "#1c1917", "#b91c1c", ("Kampot", "Pepper")),
    "Canned Sardines": ("tin", "#0369a1", "#fde047", ("Sardines", "")),
    "Colgate Toothpaste 150g": ("tube_h", "#dc2626", "#ffffff", ("Toothpaste",)),
    "Sunsilk Shampoo 320ml": ("bottle", "#db2777", "#fdf2f8", ("Shampoo", "320ml")),
    "Lux Soap 85g": ("bar", "#c084fc", "#ffffff", ("Soap", "85g")),
    "Toothbrush Soft": ("brush", "#0ea5e9", "#ffffff", ()),
    "Tissue Box 150 sheets": ("tissue", "#a5f3fc", "#0e7490", ("Tissue",)),
    "Dish Soap 500ml": ("bottle", "#22c55e", "#f0fdf4", ("Dish", "Soap")),
    "Laundry Powder 900g": ("box", "#2563eb", "#facc15", ("Laundry", "Powder")),
    "Trash Bags (30 pcs)": ("roll", "#1f2937", "#9ca3af", ("Trash", "Bags")),
    "AA Batteries (4 pcs)": ("batteries", "#111827", "#f59e0b", ()),
    "Mosquito Coil (10 pcs)": ("coil", "#15803d", "#fde68a", ()),
}


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _shade(colour: str, factor: float) -> tuple[int, int, int]:
    """factor < 1 darker, > 1 lighter."""
    r, g, b = _rgb(colour)
    if factor < 1:
        return int(r * factor), int(g * factor), int(b * factor)
    return tuple(int(c + (255 - c) * (factor - 1)) for c in (r, g, b))  # type: ignore[return-value]


def _text_colour(colour: str) -> tuple[int, int, int]:
    r, g, b = _rgb(colour)
    return (30, 41, 59) if r * 0.299 + g * 0.587 + b * 0.114 > 160 else (255, 255, 255)


def _label(d: ImageDraw.ImageDraw, cx: float, cy: float, lines: tuple[str, ...], colour, width: float) -> None:
    lines = tuple(line for line in lines if line)
    if not lines:
        return
    size = int(width * 0.22)
    fonts = []
    for i, line in enumerate(lines):
        s = size if i == 0 else int(size * 0.7)
        font = _font(s)
        while d.textlength(line, font=font) > width * 0.72 and s > 10:
            s -= 2
            font = _font(s)
        fonts.append(font)
    heights = [f.size * 1.15 for f in fonts]
    y = cy - sum(heights) / 2
    for line, font, h in zip(lines, fonts, heights):
        d.text((cx, y + h / 2), line, fill=colour, font=font, anchor="mm")
        y += h


def _shine(d: ImageDraw.ImageDraw, box, alpha: int = 70) -> None:
    x0, y0, x1, y1 = box
    w = x1 - x0
    d.rounded_rectangle((x0 + w * 0.05, y0, x0 + w * 0.1, y1), radius=w * 0.025, fill=(255, 255, 255, alpha))


def _draw(shape: str, body: str, accent: str, lines: tuple[str, ...]) -> Image.Image:
    S = SIZE * SCALE
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = S / 2
    text = _text_colour(body)
    dark, light = _shade(body, 0.75), _shade(body, 1.25)

    if shape in ("can", "slimcan", "tin", "tube"):
        w, h = {"can": (0.40, 0.62), "slimcan": (0.32, 0.66), "tin": (0.62, 0.30), "tube": (0.34, 0.70)}[shape]
        x0, x1 = c - S * w / 2, c + S * w / 2
        y0, y1 = c - S * h / 2, c + S * h / 2
        e = S * w * 0.14  # ellipse height of top / bottom
        d.ellipse((x0, y1 - e, x1, y1 + e), fill=dark)
        d.rectangle((x0, y0, x1, y1), fill=body)
        band = (y1 - y0) * 0.36
        d.rectangle((x0, c - band / 2, x1, c + band / 2), fill=accent)
        if shape == "slimcan":  # two-tone can
            d.rectangle((x0, y0, c, y1), fill=_rgb(body))
            d.rectangle((c, y0, x1, y1), fill=(203, 213, 225))
            d.rectangle((x0, c - band / 2, x1, c + band / 2), fill=accent)
        d.ellipse((x0, y0 - e, x1, y0 + e), fill=(203, 213, 225) if shape != "tube" else dark)
        if shape in ("can", "slimcan"):
            d.ellipse((x0 + S * 0.03, y0 - e * 0.7, x1 - S * 0.03, y0 + e * 0.7), fill=(148, 163, 184))
            d.rounded_rectangle((c - S * 0.04, y0 - e * 0.35, c + S * 0.04, y0 + e * 0.2), radius=8, fill=(100, 116, 139))
        _shine(d, (x0, y0, x1, y1))
        _label(d, c, c, lines, _text_colour(accent), min(x1 - x0, S * 0.42))

    elif shape == "bottle":
        bw, bh = S * 0.34, S * 0.50
        x0, x1 = c - bw / 2, c + bw / 2
        y1 = c + S * 0.36
        y0 = y1 - bh
        neck = S * 0.11
        cap_top = y0 - S * 0.20
        d.rounded_rectangle((c - neck / 2, cap_top + S * 0.05, c + neck / 2, y0 + S * 0.05), radius=10, fill=body)
        d.pieslice((x0, y0 - S * 0.08, x1, y0 + S * 0.10), 180, 360, fill=body)
        d.rounded_rectangle((x0, y0, x1, y1), radius=bw * 0.14, fill=body)
        d.rounded_rectangle((c - neck * 0.65, cap_top, c + neck * 0.65, cap_top + S * 0.07), radius=10, fill=accent)
        d.rectangle((x0, y0 + bh * 0.25, x1, y0 + bh * 0.75), fill=accent)
        _shine(d, (x0, y0, x1, y1 - bw * 0.1))
        _label(d, c, y0 + bh * 0.5, lines, _text_colour(accent), bw)

    elif shape == "carton":
        w, h = S * 0.36, S * 0.52
        x0, x1 = c - w / 2, c + w / 2
        y0, y1 = c - h / 2 + S * 0.06, c + h / 2 + S * 0.06
        roof = S * 0.12
        d.polygon([(x0, y0), (c, y0 - roof), (x1, y0)], fill=dark)
        d.rectangle((c - S * 0.12, y0 - roof - S * 0.03, c + S * 0.12, y0 - roof + S * 0.02), fill=_shade(body, 0.85))
        d.rectangle((x0, y0, x1, y1), fill=body)
        d.rectangle((x0, y0 + h * 0.3, x1, y0 + h * 0.8), fill=accent)
        if body.lower() == "#f8fafc":
            for i in range(3):  # cow spots on the milk carton
                d.ellipse((x0 + w * (0.15 + i * 0.28), y0 + h * 0.08, x0 + w * (0.3 + i * 0.28), y0 + h * 0.22), fill=(30, 41, 59))
        _shine(d, (x0, y0, x1, y1), 50)
        _label(d, c, y0 + h * 0.55, lines, _text_colour(accent), w)

    elif shape in ("bag", "sack"):
        w, h = S * (0.50 if shape == "bag" else 0.52), S * (0.62 if shape == "bag" else 0.60)
        x0, x1 = c - w / 2, c + w / 2
        y0, y1 = c - h / 2, c + h / 2
        pts = []
        for i in range(21):  # crimped top edge
            pts.append((x0 + w * i / 20, y0 + (S * 0.015 if i % 2 else 0)))
        bulge = S * 0.03
        pts += [(x1 + bulge, c), (x1, y1)]
        pts += [(x0 + w * i / 20, y1 - (S * 0.015 if i % 2 else 0)) for i in range(20, -1, -1)]
        pts += [(x0 - bulge, c)]
        d.polygon(pts, fill=body)
        d.rectangle((x0, y0 + S * 0.03, x1, y0 + S * 0.06), fill=dark)
        d.ellipse((x0 + w * 0.12, y0 + h * 0.22, x1 - w * 0.12, y0 + h * 0.78), fill=accent)
        if shape == "sack":
            d.rectangle((x0, y1 - S * 0.06, x1, y1 - S * 0.03), fill=accent)
        _shine(d, (x0, y0 + S * 0.08, x1, y1 - S * 0.08), 45)
        _label(d, c, c, lines, _text_colour(accent), w * 0.72)

    elif shape in ("pack", "box", "bar", "tissue"):
        w, h = {"pack": (0.64, 0.40), "box": (0.46, 0.58), "bar": (0.68, 0.26), "tissue": (0.62, 0.36)}[shape]
        w, h = S * w, S * h
        x0, x1 = c - w / 2, c + w / 2
        y0, y1 = c - h / 2, c + h / 2
        depth = S * 0.05
        d.polygon([(x0, y0), (x0 + depth, y0 - depth), (x1 + depth, y0 - depth), (x1, y0)], fill=light)
        d.polygon([(x1, y0), (x1 + depth, y0 - depth), (x1 + depth, y1 - depth), (x1, y1)], fill=dark)
        d.rounded_rectangle((x0, y0, x1, y1), radius=S * 0.01, fill=body)
        if shape == "tissue":
            d.ellipse((c - w * 0.28, y0 - S * 0.012, c + w * 0.28, y0 + S * 0.03), fill=_shade(body, 0.6))
            d.polygon([(c - S * 0.1, y0), (c - S * 0.02, y0 - S * 0.16), (c + S * 0.08, y0 - S * 0.12), (c + S * 0.1, y0)],
                      fill=(255, 255, 255), outline=(203, 213, 225), width=4)
            d.rounded_rectangle((x0 + w * 0.08, y0 + h * 0.25, x1 - w * 0.08, y1 - h * 0.15), radius=20, fill=accent)
            _label(d, c, c + h * 0.05, lines, _text_colour(accent), w * 0.8)
        elif shape == "bar":
            for i in range(1, 4):
                d.line((x0 + w * i / 4, y0, x0 + w * i / 4, y1), fill=dark, width=6)
            d.rounded_rectangle((x0 + w * 0.2, y0 + h * 0.18, x1 - w * 0.2, y1 - h * 0.18), radius=30, fill=accent)
            _label(d, c, c, lines, _text_colour(accent), w * 0.55)
        else:
            d.rounded_rectangle((x0 + w * 0.1, y0 + h * 0.2, x1 - w * 0.1, y1 - h * 0.2), radius=30, fill=accent)
            _label(d, c, c, lines, _text_colour(accent), w * 0.75)

    elif shape == "jar":
        w, h = S * 0.40, S * 0.46
        x0, x1 = c - w / 2, c + w / 2
        y0, y1 = c - h / 2 + S * 0.05, c + h / 2 + S * 0.05
        d.rounded_rectangle((x0, y0, x1, y1), radius=w * 0.18, fill=(226, 232, 240, 230))
        for i in range(140):  # peppercorns
            a = i * 2.39996
            r = math.sqrt(i / 140) * w * 0.42
            px, py = c + math.cos(a) * r, y0 + h * 0.55 + math.sin(a) * r * 0.9
            if y0 + w * 0.1 < py < y1 - w * 0.06:
                d.ellipse((px - 14, py - 14, px + 14, py + 14), fill=body)
        d.rounded_rectangle((x0 - S * 0.01, y0 - S * 0.09, x1 + S * 0.01, y0 + S * 0.01), radius=16, fill=accent)
        d.rounded_rectangle((x0 + w * 0.08, y0 + h * 0.3, x1 - w * 0.08, y0 + h * 0.72), radius=16, fill=(255, 251, 235))
        _label(d, c, y0 + h * 0.51, lines, (127, 29, 29), w * 0.8)

    elif shape == "tube_h":
        w, h = S * 0.72, S * 0.22
        x0, x1 = c - w / 2, c + w / 2
        y0, y1 = c - h / 2, c + h / 2
        d.polygon([(x0, y0 - S * 0.02), (x1 - S * 0.08, y0), (x1 - S * 0.08, y1), (x0, y1 + S * 0.02)], fill=body)
        d.rectangle((x0, y0 - S * 0.02, x0 + S * 0.03, y1 + S * 0.02), fill=dark)
        d.rounded_rectangle((x1 - S * 0.09, c - S * 0.06, x1, c + S * 0.06), radius=12, fill=(248, 250, 252))
        d.rectangle((x0 + w * 0.15, c - h * 0.28, x1 - w * 0.2, c + h * 0.28), fill=accent)
        _label(d, c - w * 0.03, c, lines, _text_colour(accent), w * 0.6)

    elif shape == "cup":
        top, bottom = S * 0.40, S * 0.30
        y0, y1 = c - S * 0.22, c + S * 0.32
        d.polygon([(c - top / 2, y0), (c + top / 2, y0), (c + bottom / 2, y1), (c - bottom / 2, y1)], fill=(241, 245, 249, 200))
        d.polygon([(c - top * 0.47, y0 + S * 0.08), (c + top * 0.47, y0 + S * 0.08), (c + bottom / 2, y1), (c - bottom / 2, y1)], fill=body)
        d.polygon([(c - top * 0.47, y0 + S * 0.08), (c + top * 0.47, y0 + S * 0.08), (c + top * 0.45, y0 + S * 0.16), (c - top * 0.45, y0 + S * 0.16)], fill=accent)
        for dx, dy in ((-0.08, 0.22), (0.05, 0.27), (-0.02, 0.36)):  # ice
            d.rounded_rectangle((c + S * dx, y0 + S * dy, c + S * (dx + 0.07), y0 + S * (dy + 0.06)), radius=10, fill=(255, 255, 255, 110))
        d.ellipse((c - top / 2 - S * 0.02, y0 - S * 0.12, c + top / 2 + S * 0.02, y0 + S * 0.04), fill=(241, 245, 249, 230))
        d.line((c + S * 0.06, y0 - S * 0.26, c - S * 0.02, y0 + S * 0.1), fill=(34, 197, 94), width=28)

    elif shape == "cupcake":
        y1 = c + S * 0.30
        d.polygon([(c - S * 0.22, c), (c + S * 0.22, c), (c + S * 0.16, y1), (c - S * 0.16, y1)], fill=accent)
        for i in range(7):
            x = c - S * 0.19 + i * S * 0.063
            d.line((x, c, x + (i - 3) * S * -0.008, y1), fill=_shade(accent, 0.8), width=10)
        d.ellipse((c - S * 0.27, c - S * 0.16, c + S * 0.27, c + S * 0.06), fill=body)
        d.ellipse((c - S * 0.20, c - S * 0.30, c + S * 0.20, c - S * 0.04), fill=body)
        d.ellipse((c - S * 0.05, c - S * 0.38, c + S * 0.05, c - S * 0.28), fill=(220, 38, 38))
        for i in range(10):
            a = i * 1.7
            px, py = c + math.cos(a) * S * 0.16, c - S * 0.1 + math.sin(a) * S * 0.07
            d.rounded_rectangle((px - 14, py - 5, px + 14, py + 5), radius=4, fill=[(59, 130, 246), (236, 72, 153), (34, 197, 94)][i % 3])

    elif shape == "eggs":
        w, h = S * 0.66, S * 0.30
        x0, y0 = c - w / 2, c - S * 0.02
        for row in range(2):
            for col in range(5):
                ex = x0 + w * (col + 0.5) / 5
                ey = y0 + S * 0.02 + row * S * 0.06
                d.ellipse((ex - S * 0.052, ey - S * 0.075, ex + S * 0.052, ey + S * 0.06), fill=_rgb(body) if (row + col) % 3 else (250, 250, 249))
        d.rounded_rectangle((x0 - S * 0.02, y0 + S * 0.08, x0 + w + S * 0.02, y0 + h), radius=24, fill=(214, 211, 209))
        for col in range(5):
            ex = x0 + w * (col + 0.5) / 5
            d.ellipse((ex - S * 0.05, y0 + S * 0.12, ex + S * 0.05, y0 + h - S * 0.02), fill=(231, 229, 228))

    elif shape == "brush":
        d.rounded_rectangle((c - S * 0.36, c - S * 0.035, c + S * 0.20, c + S * 0.035), radius=30, fill=body)
        d.rounded_rectangle((c - S * 0.30, c - S * 0.015, c + S * 0.12, c + S * 0.015), radius=12, fill=_shade(body, 1.4))
        d.rounded_rectangle((c + S * 0.18, c - S * 0.03, c + S * 0.38, c + S * 0.02), radius=12, fill=body)
        for i in range(9):
            x = c + S * 0.2 + i * S * 0.02
            d.rounded_rectangle((x, c - S * 0.13, x + S * 0.014, c - S * 0.03), radius=6, fill=(255, 255, 255) if i % 2 else (125, 211, 252))

    elif shape == "roll":
        r = S * 0.24
        d.rectangle((c - S * 0.30, c - r, c + S * 0.10, c + r), fill=body)
        d.ellipse((c - S * 0.30 - r * 0.45, c - r, c - S * 0.30 + r * 0.45, c + r), fill=_shade(body, 0.7))
        d.ellipse((c + S * 0.10 - r * 0.45, c - r, c + S * 0.10 + r * 0.45, c + r), fill=_shade(body, 1.3))
        d.ellipse((c + S * 0.10 - r * 0.15, c - r * 0.3, c + S * 0.10 + r * 0.15, c + r * 0.3), fill=(255, 255, 255))
        d.polygon([(c + S * 0.12, c + r * 0.8), (c + S * 0.38, c + r * 0.6), (c + S * 0.36, c + r * 1.2), (c + S * 0.10, c + r)], fill=body)
        d.rounded_rectangle((c - S * 0.24, c - r * 0.45, c + S * 0.04, c + r * 0.45), radius=16, fill=accent)
        _label(d, c - S * 0.10, c, lines, (17, 24, 39), S * 0.27)

    elif shape == "batteries":
        for i in range(4):
            x = c - S * 0.30 + i * S * 0.15
            y0, y1 = c - S * 0.26, c + S * 0.28
            d.rounded_rectangle((x + S * 0.035, y0 - S * 0.03, x + S * 0.085, y0 + S * 0.01), radius=8, fill=(203, 213, 225))
            d.rounded_rectangle((x, y0, x + S * 0.12, y1), radius=20, fill=body)
            d.rectangle((x, y0, x + S * 0.12, y0 + S * 0.18), fill=accent)
            d.text((x + S * 0.06, c + S * 0.08), "AA", fill=(255, 255, 255), font=_font(int(S * 0.045)), anchor="mm")
            _shine(d, (x, y0, x + S * 0.12, y1), 50)

    elif shape == "coil":
        d.ellipse((c - S * 0.35, c - S * 0.12, c + S * 0.35, c + S * 0.18), fill=(30, 41, 59, 40))
        pts = [(c + math.cos(t / 10) * (S * 0.01 + t * S * 0.0024), c + math.sin(t / 10) * (S * 0.01 + t * S * 0.0024) * 0.95)
               for t in range(0, 125)]
        d.line(pts, fill=body, width=34, joint="curve")
        d.ellipse((pts[-1][0] - 22, pts[-1][1] - 22, pts[-1][0] + 22, pts[-1][1] + 22), fill=(249, 115, 22))
        for i in range(3):  # smoke
            y = pts[-1][1] - S * 0.06 - i * S * 0.05
            d.arc((pts[-1][0] - S * 0.04 + (i % 2) * S * 0.03, y - S * 0.04, pts[-1][0] + S * 0.04 + (i % 2) * S * 0.03, y),
                  200, 340, fill=(148, 163, 184), width=12)

    # soft shadow under the product, light background behind it
    alpha = layer.getchannel("A")
    shadow = Image.new("RGBA", (S, S), (15, 23, 42, 0))
    shadow.putalpha(alpha.point(lambda v: 70 if v else 0).filter(ImageFilter.GaussianBlur(S * 0.02)))
    bg = _background(body, S)
    bg.alpha_composite(shadow, (int(S * 0.015), int(S * 0.03)))
    bg.alpha_composite(layer)
    return bg.convert("RGB").resize((SIZE, SIZE), Image.LANCZOS)


def _background(body: str, S: int) -> Image.Image:
    tint = _shade(body, 1.85) if sum(_rgb(body)) < 690 else (226, 232, 240)
    top = tuple(int(255 * 0.55 + t * 0.45) for t in tint)
    bottom = tint
    gradient = Image.new("RGBA", (1, S))
    for y in range(S):
        k = y / S
        gradient.putpixel((0, y), tuple(int(a + (b - a) * k) for a, b in zip(top, bottom)) + (255,))
    return gradient.resize((S, S))


def demo_image(name: str) -> bytes | None:
    """PNG picture for a demo product name, or None for any other product."""
    art = ART.get(name)
    if art is None:
        return None
    buffer = io.BytesIO()
    _draw(*art).save(buffer, "PNG")
    return buffer.getvalue()


def add_demo_images(db: Session, products: list[Product] | None = None) -> int:
    """Gives each demo product without a photo its drawn picture. Returns how many were added."""
    if products is None:
        products = list(db.scalars(select(Product).where(Product.image_url.is_(None))))
    added = 0
    for product in products:
        if product.image_url:
            continue
        data = demo_image(product.name)
        if data:
            product.image_url = save_product_image(product.id, data)
            added += 1
    return added


if __name__ == "__main__":
    from .database import SessionLocal

    with SessionLocal() as session:
        count = add_demo_images(session)
        session.commit()
    print(f"Added {count} product pictures.")
