"""The "I SURVIVED" base sticker: 15 x 3.75 in, the print-on-demand bumper-sticker standard.

Output: a 4500 x 1125 px PNG at 300 dpi (Printify/Printful's requested file size), yellow
edge to edge (the vendor trims a rectangle, so no white border that could print unevenly),
with six dashed oval slots sized for the 2 x 2 in kiss-cut patches.

    python -m badgebot.basesticker out/   [--url SeattleTrafficBadges.com] [--mockup pod1.png ...]
"""
import argparse
import base64
import os

from PIL import Image, ImageFont

from .badge import render_png
from .config import Config

DPI = 300
W_IN, H_IN = 15.0, 3.75
W, H = int(W_IN * DPI), int(H_IN * DPI)          # 4500 x 1125
SLOTS = 6
SLOT_W, SLOT_H = 2.0 * DPI, 1.5 * DPI           # room for a ~1.94 x 1.48 in patch incl. vendor border
SLOT_GAP = 0.17 * DPI
COLORS = {"ground": "#FCCC0A", "ink": "#111111", "slot": "#9A7C00"}


def _b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _cap(path, size):
    b = ImageFont.truetype(path, size).getbbox("H")
    return b[3] - b[1]


def build_svg(cfg, url="SeattleTrafficBadges.com"):
    banner_size, url_size = 360, 120
    top, gap = 90, 75
    banner_base = top + _cap(cfg.banner_font, banner_size)
    slot_top = banner_base + gap
    url_base = slot_top + SLOT_H + gap + _cap(cfg.body_font, url_size)
    row_w = SLOTS * SLOT_W + (SLOTS - 1) * SLOT_GAP
    x0 = (W - row_w) / 2
    slots = "".join(
        f'<ellipse cx="{x0 + i * (SLOT_W + SLOT_GAP) + SLOT_W / 2:.1f}" cy="{slot_top + SLOT_H / 2:.1f}" '
        f'rx="{SLOT_W / 2 - 6:.1f}" ry="{SLOT_H / 2 - 6:.1f}" fill="none" stroke="{COLORS["slot"]}" '
        f'stroke-width="10" stroke-dasharray="36 28"/>' for i in range(SLOTS))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W_IN}in" height="{H_IN}in" viewBox="0 0 {W} {H}">
<defs><style>
@font-face{{font-family:Banner;src:url(data:font/ttf;base64,{_b64(cfg.banner_font)});}}
@font-face{{font-family:Body;src:url(data:font/ttf;base64,{_b64(cfg.body_font)});font-weight:500;}}
@font-face{{font-family:Body;src:url(data:font/ttf;base64,{_b64(cfg.title_font)});font-weight:700;}}
</style></defs>
<rect width="{W}" height="{H}" fill="{COLORS['ground']}"/>
<text x="{W / 2}" y="{banner_base:.1f}" text-anchor="middle" font-family="Banner" font-size="{banner_size}" letter-spacing="8" fill="{COLORS['ink']}">I SURVIVED</text>
{slots}
<text x="{W / 2}" y="{url_base:.1f}" text-anchor="middle" font-family="Body" font-size="{url_size}" fill="{COLORS['ink']}"><tspan font-weight="500">Get yours at </tspan><tspan font-weight="700">{url}</tspan></text>
</svg>"""
    slot_boxes = [(x0 + i * (SLOT_W + SLOT_GAP), slot_top) for i in range(SLOTS)]
    return svg, slot_boxes, url_base


def render(out_dir, cfg=None, url="SeattleTrafficBadges.com", mockup_patches=()):
    cfg = cfg or Config()
    os.makedirs(out_dir, exist_ok=True)
    svg, boxes, url_base = build_svg(cfg, url)
    svg_path, png_path = os.path.join(out_dir, "base_sticker.svg"), os.path.join(out_dir, "base_sticker_15x3.75.png")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)
    render_png(svg, png_path, W, H)
    out = {"svg": svg_path, "print": png_path}
    if mockup_patches:   # how it looks with patches applied (not a print file)
        base = Image.open(png_path).convert("RGBA")
        for (x, y), pod in zip(boxes, mockup_patches):
            im = Image.open(pod).convert("RGBA").resize((int(SLOT_W), int(SLOT_W)), Image.LANCZOS)
            base.alpha_composite(im, (int(x), int(y + SLOT_H / 2 - SLOT_W / 2)))
        mock = os.path.join(out_dir, "mockup_with_patches.png")
        base.convert("RGB").save(mock, dpi=(DPI, DPI))
        out["mockup"] = mock
    checks = {"size_px": Image.open(png_path).size, "dpi": DPI, "content_bottom_margin_in": round((H - url_base) / DPI, 2)}
    return out, checks


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--url", default="SeattleTrafficBadges.com")
    ap.add_argument("--mockup", nargs="*", default=[])
    a = ap.parse_args()
    print(render(a.out, url=a.url, mockup_patches=a.mockup))
