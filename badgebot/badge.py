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
import hashlib
import math
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
RIM_W = 4.4                            # gold edge on the outside of the road
# The middle of the visible road: halfway between the picture's edge and the inside of the rim,
# measured at the top, bottom and sides. Title, year and dashes are all centered on this line.
ROAD_MID_CX = FIELD_CX
ROAD_MID_RX = ((RING_RX - RIM_W) + FIELD_RX) / 2
_road_top = ((CY - (RING_RY - RIM_W)) + (FIELD_CY - FIELD_RY)) / 2
_road_bottom = ((CY + (RING_RY - RIM_W)) + (FIELD_CY + FIELD_RY)) / 2
ROAD_MID_CY = (_road_top + _road_bottom) / 2
ROAD_MID_RY = (_road_bottom - _road_top) / 2
DASH_GAP = 9.0                         # road units of clear road between the lettering and the dashes
TITLE_ROOM_UNITS = 225.0               # usable arc length before the dashes begin (238 minus margin)
TITLE_SIZES = [22, 21, 20, 19]         # 19 is the smallest that keeps letters >= 1.8 mm tall
MIN_SQUEEZE = 0.82                     # last resort: condense a long title up to 18%
YEAR_SIZE = 19
YEAR_RANGE_SIZE = 16                    # "2021–2024" for multi-year construction badges
ICON_BOX = 124.0                       # icons are drawn on a 200 x 200 grid, scaled to this
ART_DIR = os.path.join(os.path.dirname(__file__), "art")
# V2 paintings arrive as 1024 x 688 ovals with their own dark frame and red line; this is the part
# inside the red line, as fractions of the image, which is laid into the orange center.
ART_CROP = (62 / 1024, 44 / 688, 962 / 1024, 650 / 688)
MIN_ART_DPI = 300                      # source pixels per printed inch across the center, at least

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


def _arc(rx, ry, top=True):
    """Half-ellipse path on the road's middle, left to right, over the top or under the bottom."""
    sweep = 1 if top else 0
    return (f"M {ROAD_MID_CX - rx:.2f} {ROAD_MID_CY:.2f} A {rx:.2f} {ry:.2f} 0 0 {sweep} "
            f"{ROAD_MID_CX + rx:.2f} {ROAD_MID_CY:.2f}")


def _angle_for_arc_length(rx, ry, length, start_deg):
    """Walk along an ellipse from start_deg until 'length' road units are covered; return degrees."""
    t, done, step = math.radians(start_deg), 0.0, math.radians(0.1)
    while done < length:
        dx, dy = -rx * math.sin(t), ry * math.cos(t)
        done += math.hypot(dx, dy) * step
        t += step
    return math.degrees(t) - start_deg


def road_dashes(title_w, title_r_scale, year_w, year_r_scale):
    """Dash runs that start the same distance past the end of the title and the year on both
    sides: a short title gets long runs, a long title short ones. Each side's run begins at the
    title, so the two sides mirror each other."""
    rx, ry = ROAD_MID_RX, ROAD_MID_RY
    a_t = _angle_for_arc_length(rx, ry, title_w / 2 * title_r_scale + DASH_GAP, -90.0)
    a_y = _angle_for_arc_length(rx, ry, year_w / 2 * year_r_scale + DASH_GAP, 90.0)

    def run(t0, t1):
        n = max(2, int(abs(t1 - t0) / 1.0))
        pts = [(ROAD_MID_CX + rx * math.cos(math.radians(t0 + (t1 - t0) * i / n)),
                ROAD_MID_CY + ry * math.sin(math.radians(t0 + (t1 - t0) * i / n))) for i in range(n + 1)]
        return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts)
    right = run(-90.0 + a_t, 90.0 - a_y)          # down the right side, from the title to the year
    left = run(-90.0 - a_t, -270.0 + a_y)         # down the left side, the same way round
    return right + " " + left


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


def art_image(art_png):
    """The painting's inside, cropped, as (base64 PNG, width px, height px)."""
    import io
    with Image.open(art_png) as im:
        im = im.convert("RGB")
        w, h = im.size
        box = (round(ART_CROP[0] * w), round(ART_CROP[1] * h), round(ART_CROP[2] * w), round(ART_CROP[3] * h))
        crop = im.crop(box)
    buf = io.BytesIO()
    crop.save(buf, "PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode(), crop.width, crop.height


def build_svg(hook, icon_inner, cfg, art_png=None):
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
    from .icons import ACCENT_FOR
    accent = ACCENT_FOR.get(getattr(hook, "icon_key", None), pal["highlight"]) if pal.get("outline") else pal["highlight"]
    from .icons import HOUSE_COLORS
    tok = dict(HOUSE_COLORS, paper=pal["icon"], accent=accent, ink=pal["field"])
    icon = re.sub(r'"(paper|accent|ink|white|orange|road)"', lambda m: f'"{tok[m.group(1)]}"', icon_inner)
    group_svg = group_circle(getattr(hook, "group", ""), pal) if pal.get("outline") else ""
    rim = (f'<ellipse cx="{CX}" cy="{CY}" rx="{RING_RX - 2.2}" ry="{RING_RY - 2.2}" fill="none" '
           f'stroke="{pal["rim"]}" stroke-width="{RIM_W}"/>' if pal.get("rim") else "")
    # Centering: measure what the picture actually covers, then put the middle of that (or of its
    # most interesting part, if the icon names one) exactly on the middle of the field.
    from .icons import FOCUS, SCENES, SCENE_BOX
    scene = SCENES.get(getattr(hook, "icon_key", None)) if icon_inner == SCENES.get(
        getattr(hook, "icon_key", None), {}).get("art") else None
    focus = FOCUS.get(getattr(hook, "icon_key", None))
    art = art_image(art_png) if art_png else None
    if art:     # a painting: fills the center edge to edge (cropped to fit), no shading
        fx, fy = FIELD_CX - FIELD_RX, FIELD_CY - FIELD_RY
        icon_transform = "translate(0 0)"
        icon_art, icon_defs = (f'<image href="data:image/png;base64,{art[0]}" x="{fx}" y="{fy}" '
                               f'width="{2 * FIELD_RX}" height="{2 * FIELD_RY}" preserveAspectRatio="xMidYMid slice"/>'), ""
    else:
        if scene:   # camera shot: the scene's frame maps onto the whole picture, edges and all
            box, k = SCENE_BOX, (2 * FIELD_RX) / (SCENE_BOX[2] - SCENE_BOX[0])
        else:
            box = focus or icon_bbox(icon)
            k = fit_scale(box, cropped=bool(focus))
        bx, by = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        icon_transform = f"translate({FIELD_CX} {FIELD_CY}) scale({k:.4f}) translate({-bx:.2f} {-by:.2f})"
    if art:
        pass   # a painting is used as it is
    elif scene:
        from .toon import shade
        icon_art, icon_defs = shade(icon, None, k, light_deg=pal.get("light_deg", 135.0), band=scene["band"],
                                    lift=scene["lift"], drop=scene["drop"])
    elif pal.get("outline"):
        from .toon import shade
        icon_art, icon_defs = shade(icon, pal["outline"], k, light_deg=pal.get("light_deg", 135.0),
                                    hole_color=pal["field"])
    else:
        icon_art, icon_defs = icon, ""

    # Title and year sit centered across the road's thickness: the baseline is moved half a capital
    # letter's height in from the road's middle (the title's letters grow outward, the year's inward).
    year_text = str(hook.year).replace("-", "\u2013")
    year_size = YEAR_SIZE if len(str(hook.year)) <= 4 else YEAR_RANGE_SIZE
    year_ls = 3 if len(str(hook.year)) <= 4 else 1.5
    t_half = _cap_height_units(font_path, size) / 2
    y_half = _cap_height_units(font_path, year_size) / 2
    title_arc = _arc(ROAD_MID_RX - t_half, ROAD_MID_RY - t_half, top=True)
    year_arc = _arc(ROAD_MID_RX + y_half, ROAD_MID_RY + y_half, top=False)
    year_w = _text_width_units(font_path, year_text, year_size, year_ls)
    dashes = road_dashes(width_units, ROAD_MID_RY / (ROAD_MID_RY - t_half), year_w, ROAD_MID_RY / (ROAD_MID_RY + y_half))

    cut = f"M {CX - CUT_RX} {CY} A {CUT_RX} {CUT_RY} 0 1 0 {CX + CUT_RX} {CY} A {CUT_RX} {CUT_RY} 0 1 0 {CX - CUT_RX} {CY} Z"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{vw * unit_in:.4f}in" height="{vh * unit_in:.4f}in" viewBox="{vx:.2f} {vy:.2f} {vw:.2f} {vh:.2f}">
<defs><style>@font-face{{font-family:PatchFont;src:url(data:font/ttf;base64,{font_b64});font-weight:700;}}</style>
<path id="tarc" d="{title_arc}"/><path id="yarc" d="{year_arc}"/>
<clipPath id="field"><ellipse cx="{FIELD_CX}" cy="{FIELD_CY}" rx="{FIELD_RX}" ry="{FIELD_RY}"/></clipPath>{icon_defs}</defs>
<rect id="bleed" x="{vx:.2f}" y="{vy:.2f}" width="{vw:.2f}" height="{vh:.2f}" fill="{pal['edge']}"/>
<ellipse cx="{CX}" cy="{CY}" rx="{CUT_RX}" ry="{CUT_RY}" fill="{pal['edge']}"/>
<ellipse cx="{CX}" cy="{CY}" rx="{RING_RX}" ry="{RING_RY}" fill="{pal['ring']}"/>
<ellipse cx="{FIELD_CX}" cy="{FIELD_CY}" rx="{FIELD_RX}" ry="{FIELD_RY}" fill="{pal['field']}"/>
{rim}<g clip-path="url(#field)"><g transform="{icon_transform}">{icon_art}</g></g>
<path d="{dashes}" fill="none" stroke="{pal.get('dashes', pal['text'])}" stroke-width="3.5" stroke-dasharray="12 9" stroke-linecap="butt"/>
{group_svg}
<text font-family="PatchFont" font-weight="700" font-size="{size}" letter-spacing="1" fill="{pal['text']}"><textPath href="#tarc" startOffset="50%" text-anchor="middle"{fit_attr}>{_esc(title)}</textPath></text>
<text font-family="PatchFont" font-weight="700" font-size="{year_size}" letter-spacing="{year_ls}" fill="{pal['text']}"><textPath href="#yarc" startOffset="50%" text-anchor="middle">{_esc(year_text)}</textPath></text>
</svg>"""
    cutline = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{vw * unit_in:.4f}in" height="{vh * unit_in:.4f}in" '
               f'viewBox="{vx:.2f} {vy:.2f} {vw:.2f} {vh:.2f}"><path d="{cut}" fill="none" stroke="#FF00FF" stroke-width="0.5"/></svg>')
    geo = dict(squeeze=round(squeeze, 3), unit_in=unit_in, vx=vx, vy=vy, vw=vw, vh=vh, size=size, width_units=width_units,
               cap_units=_cap_height_units(font_path, size), font=os.path.basename(font_path),
               art_px=(art[1], art[2]) if art else None)
    return svg, cutline, geo


def _flat(fid, color):
    return (f'<filter id="{fid}" x="-20%" y="-20%" width="140%" height="140%"><feFlood flood-color="{color}"/>'
            f'<feComposite in2="SourceAlpha" operator="in"/></filter>')


def _illustrate(icon, pal, shift=7, outline_px=5):
    """Illustrator look, as if lit from the upper left: a dark outline around the whole picture,
    a lighter rim along its upper-left edges and a darker rim along its lower-right edges.
    Edges come from the picture's own silhouette shifted against itself."""
    defs = (f'<g id="ic">{icon}</g>'
            f'<filter id="olf" x="-20%" y="-20%" width="140%" height="140%">'
            f'<feMorphology in="SourceAlpha" operator="dilate" radius="{outline_px}" result="d"/>'
            f'<feFlood flood-color="{pal["outline"]}"/><feComposite in2="d" operator="in" result="o"/>'
            f'<feMerge><feMergeNode in="o"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
            + _flat("wf", "#FFFFFF") + _flat("kf", "#000000")
            + _flat("hlf", pal["light"]) + _flat("shf", pal["shade"])
            + f'<mask id="hlm" maskUnits="userSpaceOnUse" x="-50" y="-50" width="300" height="300">'
              f'<use href="#ic" filter="url(#wf)"/><use href="#ic" filter="url(#kf)" transform="translate({shift} {shift})"/></mask>'
            + f'<mask id="shm" maskUnits="userSpaceOnUse" x="-50" y="-50" width="300" height="300">'
              f'<use href="#ic" filter="url(#wf)"/><use href="#ic" filter="url(#kf)" transform="translate({-shift} {-shift})"/></mask>')
    art = ('<use href="#ic" filter="url(#olf)"/>'
           '<g mask="url(#shm)"><use href="#ic" filter="url(#shf)"/></g>'
           '<g mask="url(#hlm)" opacity="0.9"><use href="#ic" filter="url(#hlf)"/></g>')
    return art, defs


# The group circle: one small round mark per badge, saying which group it belongs to (a city,
# or a kind of event such as construction). Same size and place on every badge, overlapping the
# lower-right edge of the picture, line art only.
GROUP_R = 23.0
GROUP_ANGLE = 38.0          # degrees below horizontal, on the picture's edge
GROUP_INSET = 0.80          # 1.0 = centered on the picture's edge; smaller = further inside


def group_circle(group, pal):
    from .icons import GROUPS
    art = GROUPS.get(group)
    if not art:
        return ""
    a = math.radians(GROUP_ANGLE)
    gx = FIELD_CX + FIELD_RX * GROUP_INSET * math.cos(a)
    gy = FIELD_CY + FIELD_RY * GROUP_INSET * math.sin(a)
    k = (GROUP_R * 2 * 0.72) / 100.0            # line art sits on a 100-unit grid, 72% of the circle
    line = pal.get("group_line", "#FFFFFF")
    return (f'<circle cx="{gx:.2f}" cy="{gy:.2f}" r="{GROUP_R + 2.2}" fill="{pal["outline"]}"/>'
            f'<circle cx="{gx:.2f}" cy="{gy:.2f}" r="{GROUP_R}" fill="{pal["ring"]}" stroke="{pal["rim"]}" stroke-width="2.2"/>'
            f'<g transform="translate({gx - 50 * k:.2f} {gy - 50 * k:.2f}) scale({k:.4f})" fill="none" '
            f'stroke="{line}" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round">'
            f'{art.replace("LINE", line)}</g>')


ICON_MARGIN = 9.0       # badge units kept clear inside the field when the whole picture shows
_BBOX_CACHE = {}


def fit_scale(box, cropped=False):
    """Largest scale at which the box fits inside the field ellipse (less a margin). A cropped
    focus box gets a smaller margin: the rest of the picture is allowed to run off the edge."""
    w, h = box[2] - box[0], box[3] - box[1]
    m = ICON_MARGIN * (0.4 if cropped else 1.0)
    rx, ry = FIELD_RX - m, FIELD_RY - m
    return 1.0 / math.sqrt((w / 2 / rx) ** 2 + (h / 2 / ry) ** 2)


def icon_bbox(icon):
    """What the picture really covers, in its 200-unit grid, strokes included: rendered once
    and measured from the pixels, so centering never depends on how the icon was written."""
    key = hashlib.sha1(icon.encode()).hexdigest()
    if key in _BBOX_CACHE:
        return _BBOX_CACHE[key]
    import tempfile
    px = 3.0
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" viewBox="-200 -200 600 600">'
           f'{icon}</svg>')
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "b.png")
        render_png(svg, out, 600 * px, 600 * px, dpi=72)
        with Image.open(out) as im:
            bb = im.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
    box = (-200 + bb[0] / px, -200 + bb[1] / px, -200 + bb[2] / px, -200 + bb[3] / px) if bb else (0, 0, 200, 200)
    _BBOX_CACHE[key] = box
    return box


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


def make_badge(hook, icon_inner, cfg, out_dir, art_png=None):
    os.makedirs(out_dir, exist_ok=True)
    svg, cutline, g = build_svg(hook, icon_inner, cfg, art_png)
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
    if g["art_px"]:   # a painting has no single picture color; check its sharpness instead
        del checks["contrast_icon_vs_field"]
        field_in = 2 * FIELD_RX * g["unit_in"]
        # the picture is cropped to fill the center, so the narrower source side sets the sharpness
        checks["art_dpi"] = round(min(g["art_px"][0] / field_in, g["art_px"][1] / (2 * FIELD_RY * g["unit_in"])))
        checks["picture"] = "painting"
    failures = []
    if checks["print_dpi"] != 300:
        failures.append("print file is not 300 dpi at full size")
    if cfg.bleed_mm < 3.0:
        failures.append("bleed under 3 mm")
    if checks["road_band_mm"] < 3.0:
        failures.append("road ring under 3 mm: picture too close to the cut")
    if checks["title_cap_height_mm"] < cfg.min_cap_height_mm:
        failures.append(f"title letters {checks['title_cap_height_mm']} mm tall < {cfg.min_cap_height_mm} mm")
    if checks.get("art_dpi", MIN_ART_DPI) < MIN_ART_DPI:
        failures.append(f"picture only {checks['art_dpi']} dpi in print < {MIN_ART_DPI}")
    for k, need in (("contrast_text_vs_ring", cfg.min_contrast), ("contrast_icon_vs_field", cfg.min_icon_contrast)):
        if k in checks and checks[k] < need:
            failures.append(f"{k} {checks[k]} < {need}")
    return BadgeResult(files, checks, not failures, failures)
