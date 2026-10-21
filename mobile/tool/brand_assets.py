"""Makes every RATHA MART logo file from one picture of the logo (brand/logo-source.jpg): the logo cut out of its
paper background, the cart mark on its own, the black receipt logo, and the app icons for Android, iOS and the web.

Run from the repo with the server's Python (it has Pillow):
    server\\.venv\\Scripts\\python mobile\\tool\\brand_assets.py [path\\to\\new-logo.jpg]

The picture is the logo on plain light paper, in three rows: the cart, the words RATHA MART, the tagline.
"""
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageMath, ImageStat

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "brand" / "logo-source.jpg"
WEB = ROOT / "web" / "public"
FLUTTER = ROOT / "mobile" / "assets" / "brand"
RES = ROOT / "mobile" / "android" / "app" / "src" / "main" / "res"
IOS = ROOT / "mobile" / "ios" / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"
WHITE = (255, 255, 255, 255)


def cut_out(src: Image.Image) -> Image.Image:
    """The logo on a transparent background. Soft edges keep their softness, and their colour is un-mixed from
    the paper so no light halo shows on a dark background. Paper texture and specks are dropped."""
    w, h = src.size
    edges = [src.crop(box) for box in ((0, 0, w, 40), (0, h - 40, w, h), (0, 0, 40, h), (w - 40, 0, w, h))]
    paper = tuple(round(sum(ImageStat.Stat(e).median[i] for e in edges) / len(edges)) for i in range(3))

    r, g, b = ImageChops.difference(src, Image.new("RGB", src.size, paper)).split()
    distance = ImageChops.lighter(ImageChops.lighter(r, g), b)
    alpha = distance.point(lambda v: max(0, min(255, (v - 30) * 255 // 60)))  # texture is under 30
    # keep only what is near a solid part of the logo (specks in the paper are a few pixels wide)
    solid = distance.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(21))
    alpha = ImageChops.multiply(alpha, solid)

    a = alpha.convert("F")
    channels = []
    for channel, p in zip(src.split(), paper):
        mixed = ImageMath.lambda_eval(
            lambda e: e["min"](e["max"]((e["c"] - (1 - e["a"] / 255) * p) * 255 / e["max"](e["a"], 1), 0), 255),
            c=channel.convert("F"), a=a,
        )
        channels.append(mixed.convert("L"))
    out = Image.merge("RGBA", (*channels, alpha))
    return out.crop(alpha.getbbox())


def rows(logo: Image.Image) -> list[tuple[int, int]]:
    """The top and bottom of each row of the logo (cart, words, tagline), split where a line is empty."""
    alpha = logo.getchannel("A").point(lambda v: 255 if v > 64 else 0)
    found, start = [], None
    for y in range(logo.height + 1):
        on = y < logo.height and alpha.crop((0, y, logo.width, y + 1)).getbbox() is not None
        if on and start is None:
            start = y
        elif not on and start is not None:
            if y - start > 8:
                found.append((start, y))
            start = None
    return found


def trim(img: Image.Image) -> Image.Image:
    return img.crop(img.getchannel("A").getbbox())


def fit(img: Image.Image, size: int, share: float, background=None, shape: str = "square", radius: float = 0.0) -> Image.Image:
    """`img` centred on a size x size canvas, its longer side `share` of the canvas; on a tile when `background`."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if background is not None:
        tile = Image.new("L", (size * 4, size * 4), 0)
        draw = ImageDraw.Draw(tile)
        box = (0, 0, size * 4 - 1, size * 4 - 1)
        if shape == "circle":
            draw.ellipse(box, fill=255)
        else:
            draw.rounded_rectangle(box, radius=radius * size * 4, fill=255)
        canvas.paste(Image.new("RGBA", (size, size), background), (0, 0), tile.resize((size, size), Image.LANCZOS))
    k = share * size / max(img.size)
    small = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)
    canvas.alpha_composite(small, ((size - small.width) // 2, (size - small.height) // 2))
    return canvas


def solid(img: Image.Image, colour: tuple[int, int, int]) -> Image.Image:
    """The same shape in one colour (receipt printers print black; Android's themed icon is one colour)."""
    out = Image.new("RGBA", img.size, (*colour, 255))
    out.putalpha(img.getchannel("A"))
    return out


def save(img: Image.Image, path: Path, opaque: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if opaque:  # iOS wants no transparency
        flat = Image.new("RGB", img.size, WHITE[:3])
        flat.paste(img, (0, 0), img)
        img = flat
    img.save(path, optimize=True)


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    if source.resolve() != SOURCE.resolve():
        SOURCE.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, SOURCE)  # keep the picture with the code, so the files can be made again

    logo = cut_out(Image.open(SOURCE).convert("RGB"))
    found = rows(logo)
    if len(found) < 3:
        sys.exit(f"Expected the cart, the name and the tagline as three rows; found {len(found)}")
    cart, name, tagline = found[0], found[1], found[-1]
    mark = trim(logo.crop((0, cart[0], logo.width, cart[1])))  # the cart with its R and star
    named = trim(logo.crop((0, 0, logo.width, name[1])))  # cart and RATHA MART, without the tagline
    print(f"logo {logo.size}, mark {mark.size}, cart+name {named.size}, tagline rows {tagline}")

    # web app and phone app pictures (transparent)
    full = logo.copy()
    full.thumbnail((900, 900), Image.LANCZOS)
    small_mark = mark.copy()
    small_mark.thumbnail((256, 256), Image.LANCZOS)
    for folder in (WEB, FLUTTER):
        save(full, folder / "logo.png")
        save(small_mark, folder / "brand-mark.png")
    # receipts: black, wide enough for a crisp print at 203 dpi on 80mm paper
    receipt = solid(named, (0, 0, 0))
    receipt.thumbnail((640, 640), Image.LANCZOS)
    save(receipt, WEB / "receipt-logo.png")

    # browser tab and home screen
    save(fit(mark, 64, 0.96), WEB / "favicon.png")
    save(fit(mark, 180, 0.78, WHITE), WEB / "apple-touch-icon.png", opaque=True)
    for size in (192, 512):
        save(fit(mark, size, 0.7, WHITE, radius=0.22), WEB / f"icon-{size}.png")

    # Android: older launchers get a white rounded square / circle; Android 8+ the adaptive layers (108 dp, the
    # launcher shows the middle 72 and may cut it to a circle of 66, so the mark stays inside that circle)
    for density, k in {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}.items():
        folder = RES / f"mipmap-{density}"
        save(fit(mark, round(48 * k), 0.72, WHITE, radius=0.22), folder / "ic_launcher.png")
        save(fit(mark, round(48 * k), 0.66, WHITE, shape="circle"), folder / "ic_launcher_round.png")
        layer = round(108 * k)
        save(Image.new("RGBA", (layer, layer), WHITE), folder / "ic_launcher_background.png")
        save(fit(mark, layer, 0.5), folder / "ic_launcher_foreground.png")
        save(fit(solid(mark, (255, 255, 255)), layer, 0.5), folder / "ic_launcher_monochrome.png")

    # iOS: full squares (iOS rounds the corners)
    for pt, scales in ((20, (1, 2, 3)), (29, (1, 2, 3)), (40, (1, 2, 3)), (60, (2, 3)), (76, (1, 2)), (83.5, (2,)), (1024, (1,))):
        for s in scales:
            save(fit(mark, round(pt * s), 0.78, WHITE), IOS / f"Icon-App-{pt:g}x{pt:g}@{s}x.png", opaque=True)
    print("done")


if __name__ == "__main__":
    main()
