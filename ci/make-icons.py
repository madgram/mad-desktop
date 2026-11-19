import argparse
import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
APP_SIZES = (16, 32, 48, 64, 128, 256, 512)
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
MAC_SIZES = (16, 32, 128, 256, 512)
MAC_CONTENT = 824 / 1024
TRAY_SIZES = {"": 22, "@2x": 44, "@3x": 66}
TRAY_GLYPH = 16 / 22


def load_master(path):
    image = Image.open(path).convert("RGBA")
    if image.width != image.height:
        raise SystemExit("the logo must be square")
    corners = [(0, 0), (image.width - 1, 0), (0, image.height - 1), (image.width - 1, image.height - 1)]
    if any(image.getpixel(point)[3] != 0 for point in corners):
        raise SystemExit("the logo corners must be transparent")
    return image


def scaled(image, size):
    return image.resize((size, size), Image.LANCZOS)


def padded(image, size, ratio):
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    content = max(1, round(size * ratio))
    offset = (size - content) // 2
    canvas.alpha_composite(scaled(image, content), (offset, offset))
    return canvas


def glyph_mask(image):
    red, green, blue, alpha = image.split()
    luminance = Image.merge("RGB", (red, green, blue)).convert("L")
    mask = Image.composite(luminance, Image.new("L", image.size, 0), alpha)
    mask = mask.point(lambda value: 255 if value > 127 else 0)
    box = mask.getbbox()
    if not box:
        raise SystemExit("the logo has no light glyph")
    return mask.crop(box)


def fit_mask(mask, size, ratio):
    side = max(1, round(size * ratio))
    scale = side / max(mask.width, mask.height)
    width = max(1, round(mask.width * scale))
    height = max(1, round(mask.height * scale))
    canvas = Image.new("L", (size, size), 0)
    canvas.paste(mask.resize((width, height), Image.LANCZOS), ((size - width) // 2, (size - height) // 2))
    return canvas


def tray_svg(mask, variant):
    size = 256
    glyph = fit_mask(mask, size, 0.86)
    image = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    image.putalpha(glyph)
    if variant == "attention":
        dot = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(dot)
        draw.ellipse((size - 96, 0, size, 96), fill=255)
        cut = Image.new("L", (size, size), 0)
        ImageDraw.Draw(cut).ellipse((size - 112, -16, size + 16, 112), fill=255)
        alpha = Image.composite(Image.new("L", (size, size), 0), image.getchannel("A"), cut)
        alpha = Image.composite(Image.new("L", (size, size), 255), alpha, dot)
        image.putalpha(alpha)
    elif variant == "mute":
        image.putalpha(image.getchannel("A").point(lambda value: value * 45 // 100))
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    data = base64.b64encode(buffer.getvalue()).decode("ascii")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'<image width="{size}" height="{size}" xlink:href="data:image/png;base64,{data}"/></svg>\n'
    )


def write_png(image, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--logo", type=Path, default=ROOT / "packaging/logo.png")
    parser.add_argument("--tdesktop", type=Path, default=ROOT.parent / "tdesktop")
    args = parser.parse_args()
    master = load_master(args.logo)
    telegram = args.tdesktop / "Telegram"
    art = telegram / "Resources/art"
    icons = telegram / "Resources/icons"
    xcassets = telegram / "Telegram/Images.xcassets"

    write_png(scaled(master, 1024), art / "mad.png")
    write_png(scaled(master, 1024), art / "icon_round512@2x.png")
    write_png(scaled(master, 256), art / "logo_256.png")
    write_png(scaled(master, 256), art / "logo_256_no_margin.png")
    for size in APP_SIZES:
        write_png(scaled(master, size), art / f"icon{size}.png")
        write_png(scaled(master, size * 2), art / f"icon{size}@2x.png")
    scaled(master, 256).save(art / "icon256.ico", sizes=[(size, size) for size in ICO_SIZES])

    for size in MAC_SIZES:
        for scale, suffix in ((1, ""), (2, "@2x")):
            image = padded(master, size * scale, MAC_CONTENT)
            write_png(image, xcassets / "Icon.iconset" / f"icon_{size}x{size}{suffix}.png")
            write_png(image, xcassets / "Icon.appiconset" / f"icon{size}{suffix}.png")

    mask = glyph_mask(master)
    for suffix, size in TRAY_SIZES.items():
        tray = Image.merge("RGBA", (*(fit_mask(mask, size, TRAY_GLYPH),) * 3, Image.new("L", (size, size), 255)))
        write_png(tray.convert("RGB"), icons / f"mac_tray_icon{suffix}.png")
    for variant, name in (("", "tray_monochrome"), ("attention", "tray_monochrome_attention"), ("mute", "tray_monochrome_mute")):
        (icons / f"{name}.svg").write_text(tray_svg(mask, variant), encoding="utf-8", newline="\n")
    print("icons written from", args.logo)


if __name__ == "__main__":
    main()
