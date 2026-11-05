"""Stage 4: render a print-ready oval patch from the locked design, then check it.

The design (from the Badge Style Explorations canvas, "Oval patches in a row"):
  * wide oval, cut at a thin white rim
  * black "road" ring with a dashed white center line on both sides
  * white title arched across the top, white year at the bottom (no stars)
  * orange center with a black picture of exactly what the title says

All geometry is in "design units": the patch is drawn in a 320 x 240 box and the cut
oval is 316 x 236 units, so 1 unit = width_in / 316 inches.

Outputs per badge (in the run folder):
  badge.svg     master artwork with bleed, font embedded
  print.png     300 dpi with 3 mm white bleed: send this to the print vendor
  cutline.svg   the die line alone
  pod.png       2 x 2 in square, transparent outside the patch: upload this to Printify
                (kiss-cut; the vendor cuts around the shape and adds its own white border)
  preview.png   cut shape on transparent background: listing photo
  thumb.png     small preview
"""
import base64
import os
import re
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

MM_PER_IN = 25.4
CX, CY = 160.0, 120.0
CUT_RX, CUT_RY = 158.0, 118.0          # outer white rim = the die line
RING_RX, RING_RY = 151.0, 111.0        # the road
FIELD_CX, FIELD_CY, FIELD_RX, FIELD_RY = 160.0, 122.0, 112.0, 72.0
TITLE_ARC = "M 36 120 A 124 85 0 0 1 284 120"     # baseline, glyphs grow outward
YEAR_ARC = "M 24 120 A 136 98 0 0 0 296 120"      # baseline, glyphs grow inward
# Road center line on the two sides only, so it never runs under the title or the year.
ROAD_DASHES = "M 273.4 74.3 A 131 91.5 0 0 1 209.1 204.8 M 110.9 204.8 A 131 91.5 0 0 1 46.6 74.3"
TITLE_ROOM_UNITS = 225.0               # usable arc length before the dashes begin (238 minus margin)
TITLE_SIZES = [22, 21, 20, 19]         # 19 is the smallest that keeps letters >= 1.8 mm tall
MIN_SQUEEZE = 0.82                     # last resort: condense a long title up to 18%
YEAR_SIZE = 19
ICON_BOX = 124.0                       # icons are drawn on a 200 x 200 grid, scaled to this

FALLBACK_FONTS = [
    os.path.join(os.path.dirname(__file__), "fonts", "Archivo_Condensed-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",   # stand-in for tests
    "/Library/Fonts/Arial Narrow Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
    "C:/Windows/Fonts/ARIALNB.TTF",
]


def _font_path(cfg):
    for p in [cfg.title_font] + FALLBACK_FONTS:
        if p and os.path.exists(p):
            return p
    raise RuntimeError("No title font: download Archivo Narrow from fonts.google.com and set BADGE_FONT")


def _load_font(path, size):
    # BASIC layout: the same measurements on every computer (Windows, Mac, Linux)
    f = ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.BASIC)
    try:                                   # Archivo Narrow ships as a variable font
        f.set_variation_by_name("Bold")
    except Exception:
        pass
    return f


def _luminance(hexcolor):
    h = hexcolor.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _text_width_units(font_path, text, size_units, spacing_units):
    """Width of a string at size_units, measured at 10x for precision."""
    f = _load_font(font_path, int(size_units * 10))
    return f.getlength(text) / 10 + spacing_units * max(0, len(text) - 1)


def _cap_height_units(font_path, size_units):
    f = _load_font(font_path, int(size_units * 10))
    b = f.getbbox("H")
    return (b[3] - b[1]) / 10


@dataclass
class BadgeResult:
    files: dict
    checks: dict
    passed: bool
    failures: list = field(default_factory=list)


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_svg(hook, icon_inner, cfg):
    pal = cfg.palette
    font_path = _font_path(cfg)
    title = hook.title.strip()

    size = next((s for s in TITLE_SIZES
                 if _text_width_units(font_path, title, s, 1.0) <= TITLE_ROOM_UNITS), None)
    squeeze = 1.0
    if size is None:                     # smallest size still too wide: condense the letters
        size = TITLE_SIZES[-1]
        squeeze = TITLE_ROOM_UNITS / _text_width_units(font_path, title, size, 1.0)
        if squeeze < MIN_SQUEEZE:
            raise ValueError(f"title '{title}' does not fit the patch arc")
    width_units = _text_width_units(font_path, title, size, 1.0) * squeeze
    fit_attr = (f' textLength="{width_units:.1f}" lengthAdjust="spacingAndGlyphs"' if squeeze < 1 else "")

    unit_in = cfg.width_in / (2 * CUT_RX)
    bleed_u = cfg.bleed_mm / MM_PER_IN / unit_in
    vx, vy = CX - CUT_RX - bleed_u, CY - CUT_RY - bleed_u
    vw, vh = 2 * (CUT_RX + bleed_u), 2 * (CUT_RY + bleed_u)

    with open(font_path, "rb") as fh:
        font_b64 = base64.b64encode(fh.read()).decode()
    tok = {"paper": pal["icon"], "accent": pal["highlight"], "ink": pal["field"]}
    icon = re.sub(r'"(paper|accent|ink)"', lambda m: f'"{tok[m.group(1)]}"', icon_inner)
    k = ICON_BOX / 200.0
    ix, iy = FIELD_CX - ICON_BOX / 2, FIELD_CY - ICON_BOX / 2

    cut = f"M {CX - CUT_RX} {CY} A {CUT_RX} {CUT_RY} 0 1 0 {CX + CUT_RX} {CY} A {CUT_RX} {CUT_RY} 0 1 0 {CX - CUT_RX} {CY} Z"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{vw * unit_in:.4f}in" height="{vh * unit_in:.4f}in" viewBox="{vx:.2f} {vy:.2f} {vw:.2f} {vh:.2f}">
<defs><style>@font-face{{font-family:PatchFont;src:url(data:font/ttf;base64,{font_b64});font-weight:700;}}</style>
<path id="tarc" d="{TITLE_ARC}"/><path id="yarc" d="{YEAR_ARC}"/>
<clipPath id="field"><ellipse cx="{FIELD_CX}" cy="{FIELD_CY}" rx="{FIELD_RX}" ry="{FIELD_RY}"/></clipPath></defs>
<rect id="bleed" x="{vx:.2f}" y="{vy:.2f}" width="{vw:.2f}" height="{vh:.2f}" fill="{pal['edge']}"/>
<ellipse cx="{CX}" cy="{CY}" rx="{CUT_RX}" ry="{CUT_RY}" fill="{pal['edge']}"/>
<ellipse cx="{CX}" cy="{CY}" rx="{RING_RX}" ry="{RING_RY}" fill="{pal['ring']}"/>
<ellipse cx="{FIELD_CX}" cy="{FIELD_CY}" rx="{FIELD_RX}" ry="{FIELD_RY}" fill="{pal['field']}"/>
<g clip-path="url(#field)"><g transform="translate({ix:.2f} {iy:.2f}) scale({k:.4f})">{icon}</g></g>
<path d="{ROAD_DASHES}" fill="none" stroke="{pal['text']}" stroke-width="3.5" stroke-dasharray="12 9"/>
<text font-family="PatchFont" font-weight="700" font-size="{size}" letter-spacing="1" fill="{pal['text']}"><textPath href="#tarc" startOffset="50%" text-anchor="middle"{fit_attr}>{_esc(title)}</textPath></text>
<text font-family="PatchFont" font-weight="700" font-size="{YEAR_SIZE}" letter-spacing="3" fill="{pal['text']}"><textPath href="#yarc" startOffset="50%" text-anchor="middle">{hook.year}</textPath></text>
</svg>"""
    cutline = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{vw * unit_in:.4f}in" height="{vh * unit_in:.4f}in" '
               f'viewBox="{vx:.2f} {vy:.2f} {vw:.2f} {vh:.2f}"><path d="{cut}" fill="none" stroke="#FF00FF" stroke-width="0.5"/></svg>')
    geo = dict(squeeze=round(squeeze, 3), unit_in=unit_in, vx=vx, vy=vy, vw=vw, vh=vh, size=size, width_units=width_units,
               cap_units=_cap_height_units(font_path, size), font=os.path.basename(font_path))
    return svg, cutline, geo


def render_png(svg, out_path, width_px, height_px, dpi=300):
    """Render with headless Chromium so the embedded font and text-on-path match a browser."""
    from playwright.sync_api import sync_playwright
    css_w, css_h = width_px / 3.125, height_px / 3.125     # 300 dpi = 3.125 x 96 css px/in
    tag = f'<svg style="width:{css_w}px;height:{css_h}px;display:block" '
    html = f"<html><body style='margin:0;background:transparent'>{svg.replace('<svg ', tag, 1)}</body></html>"
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": int(css_w) + 1, "height": int(css_h) + 1}, device_scale_factor=3.125)
        pg.set_content(html)
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(100)
        pg.screenshot(path=out_path, omit_background=True, clip={"x": 0, "y": 0, "width": css_w, "height": css_h})
        b.close()
    with Image.open(out_path) as src:     # close before overwriting: Windows locks open files
        im = src.resize((round(width_px), round(height_px)), Image.LANCZOS)
    im.save(out_path, dpi=(dpi, dpi))


def make_badge(hook, icon_inner, cfg, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    svg, cutline, g = build_svg(hook, icon_inner, cfg)
    files = {k: os.path.join(out_dir, v) for k, v in dict(
        svg="badge.svg", print="print.png", cutline="cutline.svg", preview="preview.png", thumb="thumb.png",
        pod="pod.png").items()}
    with open(files["svg"], "w", encoding="utf-8") as f:
        f.write(svg)
    with open(files["cutline"], "w", encoding="utf-8") as f:
        f.write(cutline)
    px_per_unit = cfg.dpi * g["unit_in"]
    W, H = g["vw"] * px_per_unit, g["vh"] * px_per_unit
    render_png(svg, files["print"], W, H)

    # Print-on-demand file: square sheet, no bleed, transparent around the patch.
    side_u = cfg.pod_sheet_in / g["unit_in"]
    pod = re.sub(r'<rect id="bleed"[^>]*/>\n', "", svg)
    pod = re.sub(r'width="[^"]+" height="[^"]+" viewBox="[^"]+"',
                 f'width="{cfg.pod_sheet_in}in" height="{cfg.pod_sheet_in}in" '
                 f'viewBox="{CX - side_u / 2:.2f} {CY - side_u / 2:.2f} {side_u:.2f} {side_u:.2f}"', pod, count=1)
    render_png(pod, files["pod"], cfg.pod_px, cfg.pod_px, dpi=round(cfg.pod_px / cfg.pod_sheet_in))

    # Preview: the cut oval only, transparent outside.
    full = Image.open(files["print"]).convert("RGBA")
    def to_px(x, y):
        return ((x - g["vx"]) * px_per_unit, (y - g["vy"]) * px_per_unit)
    x0, y0 = to_px(CX - CUT_RX, CY - CUT_RY)
    x1, y1 = to_px(CX + CUT_RX, CY + CUT_RY)
    mask = Image.new("L", full.size, 0)
    ImageDraw.Draw(mask).ellipse([x0, y0, x1, y1], fill=255)
    full.putalpha(mask)
    prev = full.crop((int(x0), int(y0), int(x1) + 1, int(y1) + 1))
    prev.save(files["preview"])
    prev.resize((190, int(190 * prev.height / prev.width)), Image.LANCZOS).save(files["thumb"])

    pal = cfg.palette
    mm = lambda units: round(units * g["unit_in"] * MM_PER_IN, 2)
    with Image.open(files["print"]) as im:
        dpi_ok = abs(im.width - round(W)) <= 1 and round(im.info.get("dpi", (0, 0))[0]) == 300
    checks = {
        "shape": cfg.shape,
        "cut_size_in": f"{cfg.width_in} x {round(2 * CUT_RY * g['unit_in'], 2)}",
        "print_dpi": 300 if dpi_ok else 0,
        "bleed_mm": cfg.bleed_mm,
        "road_band_mm": mm(min(RING_RX - FIELD_RX, RING_RY - FIELD_RY)),
        "title_font": g["font"],
        "title_font_units": g["size"],
        "title_squeeze": g["squeeze"],
        "title_width_units": round(g["width_units"], 1),
        "title_room_units": TITLE_ROOM_UNITS,
        "title_cap_height_mm": mm(g["cap_units"]),
        "contrast_text_vs_ring": round(contrast(pal["text"], pal["ring"]), 1),
        "contrast_icon_vs_field": round(contrast(pal["icon"], pal["field"]), 1),
    }
    failures = []
    if checks["print_dpi"] != 300:
        failures.append("print file is not 300 dpi at full size")
    if cfg.bleed_mm < 3.0:
        failures.append("bleed under 3 mm")
    if checks["road_band_mm"] < 3.0:
        failures.append("road ring under 3 mm: picture too close to the cut")
    if checks["title_cap_height_mm"] < cfg.min_cap_height_mm:
        failures.append(f"title letters {checks['title_cap_height_mm']} mm tall < {cfg.min_cap_height_mm} mm")
    for k in ("contrast_text_vs_ring", "contrast_icon_vs_field"):
        if checks[k] < cfg.min_contrast:
            failures.append(f"{k} {checks[k]} < {cfg.min_contrast}")
    return BadgeResult(files, checks, not failures, failures)
