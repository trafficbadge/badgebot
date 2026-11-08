"""Center icons. Every icon is SVG on a 200x200 grid using only three colour tokens:
paper (the picture, prints black), accent (yellow details), ink (the orange background,
for cut-outs). badge.py swaps in the real palette. That keeps every badge in the
house style and guarantees the contrast check means something.

AI icons: when ANTHROPIC_API_KEY is set, Claude draws the icon as SVG under the same
rules, and sanitize() strips anything outside the allowlist before it is used.
"""
import re
import xml.etree.ElementTree as ET

import requests

LIBRARY = {
    "blueberry_truck": """
<g stroke-linejoin="round">
  <rect x="18" y="62" width="104" height="62" rx="6" fill="paper"/>
  <path d="M126 80 h30 l22 24 v20 h-52 z" fill="paper"/>
  <path d="M140 86 h14 l14 16 h-28 z" fill="ink"/>
  <rect x="14" y="124" width="168" height="8" rx="3" fill="paper"/>
  <circle cx="44" cy="140" r="15" fill="paper"/><circle cx="44" cy="140" r="6" fill="accent"/>
  <circle cx="92" cy="140" r="15" fill="paper"/><circle cx="92" cy="140" r="6" fill="accent"/>
  <circle cx="156" cy="140" r="15" fill="paper"/><circle cx="156" cy="140" r="6" fill="accent"/>
  <g fill="accent">
    <circle cx="14" cy="56" r="11"/><circle cx="34" cy="40" r="10"/><circle cx="8" cy="30" r="9"/>
    <circle cx="58" cy="30" r="12"/><circle cx="30" cy="16" r="8"/><circle cx="84" cy="44" r="9"/>
    <circle cx="100" cy="24" r="10"/>
  </g>
  <g fill="ink">
    <path d="M14 51 l2 4 4 1 -4 1 -2 4 -2 -4 -4 -1 4 -1z"/>
    <path d="M58 25 l2 4 4 1 -4 1 -2 4 -2 -4 -4 -1 4 -1z"/>
    <path d="M100 19 l2 4 4 1 -4 1 -2 4 -2 -4 -4 -1 4 -1z"/>
  </g>
</g>""",
    "snowflake": """
<g stroke="paper" stroke-width="14" stroke-linecap="round" fill="none">
  <line x1="100" y1="18" x2="100" y2="182"/>
  <line x1="29" y1="59" x2="171" y2="141"/>
  <line x1="29" y1="141" x2="171" y2="59"/>
  <path d="M78 34 l22 22 22 -22 M78 166 l22 -22 22 22"/>
  <path d="M35 85 l30 8 -8 -30 M165 115 l-30 -8 8 30"/>
  <path d="M35 115 l30 -8 -8 30 M165 85 l-30 8 8 -30"/>
</g>
<circle cx="100" cy="100" r="16" fill="accent"/>""",
    "motorcade": """
<g>
  <path d="M10 120 q6 -26 30 -28 h40 q16 0 26 16 l6 12 z" fill="paper"/>
  <rect x="8" y="118" width="108" height="18" rx="6" fill="paper"/>
  <circle cx="34" cy="140" r="11" fill="accent"/><circle cx="92" cy="140" r="11" fill="accent"/>
  <path d="M100 120 q6 -26 30 -28 h40 q16 0 26 16 l2 12 z" fill="paper" opacity="0.85"/>
  <rect x="98" y="118" width="96" height="18" rx="6" fill="paper" opacity="0.85"/>
  <circle cx="124" cy="140" r="11" fill="accent"/><circle cx="178" cy="140" r="11" fill="accent"/>
  <rect x="46" y="54" width="4" height="40" fill="paper"/>
  <path d="M50 54 h30 l-8 9 8 9 h-30 z" fill="accent"/>
</g>""",
    "bridge": """
<g fill="none" stroke="paper" stroke-width="10" stroke-linecap="round">
  <path d="M10 120 Q60 60 100 120 Q140 60 190 120"/>
  <line x1="10" y1="120" x2="190" y2="120"/>
  <line x1="55" y1="60" x2="55" y2="150"/><line x1="145" y1="60" x2="145" y2="150"/>
</g>
<path d="M0 160 q25 -12 50 0 t50 0 t50 0 t50 0" fill="none" stroke="accent" stroke-width="8"/>""",
    "cone": """
<path d="M100 20 L150 160 H50 Z" fill="accent"/>
<path d="M82 70 h36 l8 24 h-52 z M70 110 h60 l8 22 h-76 z" fill="paper"/>
<rect x="30" y="160" width="140" height="16" rx="4" fill="paper"/>""",
}
LIBRARY["crab"] = """
<g transform="translate(-20 -22)">
  <path d="M98 126 L82 106 M142 126 L158 106 M96 138 l-24 8 M98 148 l-20 14 M144 138 l24 8 M142 148 l20 14" fill="none" stroke="paper" stroke-width="8" stroke-linecap="round"/>
  <circle cx="78" cy="96" r="15" fill="paper"/><circle cx="162" cy="96" r="15" fill="paper"/>
  <path d="M78 96 L64 80 L60 94 Z M162 96 L176 80 L180 94 Z" fill="ink"/>
  <ellipse cx="120" cy="136" rx="32" ry="22" fill="paper"/>
  <circle cx="110" cy="112" r="5" fill="paper"/><circle cx="130" cy="112" r="5" fill="paper"/>
</g>"""
LIBRARY["bee_truck"] = """
<g transform="translate(-63 -13)">
  <g fill="paper">
    <rect x="78" y="112" width="30" height="24"/><rect x="112" y="112" width="30" height="24"/>
    <rect x="146" y="112" width="30" height="24"/><rect x="180" y="112" width="30" height="24"/>
    <rect x="96" y="84" width="30" height="24"/><rect x="130" y="84" width="30" height="24"/>
    <rect x="164" y="84" width="30" height="24"/><rect x="70" y="138" width="150" height="8"/>
    <path d="M222 146 V112 h20 l14 16 v18 Z"/>
    <circle cx="92" cy="156" r="9"/><circle cx="118" cy="156" r="9"/><circle cx="238" cy="156" r="9"/>
  </g>
  <path d="M70 146 h30 v6 q-3 4 -3 10 q0 4 -3 4 q-3 0 -3 -4 v-6 q-4 0 -5 8 q0 4 -3 4 q-3 0 -3 -4 v-12 h-10 Z" fill="accent"/>
  <g fill="accent"><circle cx="110" cy="68" r="4"/><circle cx="160" cy="62" r="4"/><circle cx="206" cy="74" r="4"/><circle cx="226" cy="96" r="4"/></g>
</g>"""
LIBRARY["gertie"] = """
<rect x="56" y="40" width="12" height="122" fill="paper"/><rect x="132" y="40" width="12" height="122" fill="paper"/>
<path d="M0 74 Q34 62 62 44 Q100 112 138 44 Q166 62 200 74" fill="none" stroke="paper" stroke-width="4"/>
<path d="M80 68 v34 M100 76 v32 M120 68 v36" stroke="paper" stroke-width="3"/>
<path d="M0 124 C30 94 62 154 100 120 S168 92 200 124" fill="none" stroke="paper" stroke-width="14" stroke-linecap="round"/>
<path d="M8 172 q15 -9 30 0 t30 0 t30 0 t30 0 t30 0 t30 0" fill="none" stroke="accent" stroke-width="6" stroke-linecap="round"/>"""
LIBRARY["crowd"] = """
<g fill="paper">
  <circle cx="44" cy="112" r="13"/><path d="M26 182 q0 -50 18 -52 q18 2 18 52 z"/>
  <circle cx="100" cy="104" r="14"/><path d="M80 182 q0 -56 20 -58 q20 2 20 58 z"/>
  <circle cx="156" cy="112" r="13"/><path d="M138 182 q0 -50 18 -52 q18 2 18 52 z"/>
  <rect x="52" y="40" width="8" height="74"/><rect x="108" y="30" width="8" height="78"/>
  <rect x="148" y="44" width="8" height="70"/>
</g>
<g fill="accent">
  <rect x="24" y="26" width="64" height="40" rx="3"/><rect x="84" y="14" width="56" height="38" rx="3"/>
  <rect x="134" y="30" width="56" height="38" rx="3"/>
</g>"""
LIBRARY["truck"] = LIBRARY["blueberry_truck"].split("<g fill=\"accent\">")[0] + "</g>"

ALLOWED_TAGS = {"svg", "g", "path", "circle", "ellipse", "rect", "polygon", "polyline", "line"}
ALLOWED_ATTRS = {"d", "cx", "cy", "r", "rx", "ry", "x", "y", "width", "height", "points",
                 "x1", "y1", "x2", "y2", "fill", "stroke", "stroke-width", "stroke-linecap",
                 "stroke-linejoin", "stroke-dasharray", "transform", "opacity", "viewBox", "xmlns"}
# named colors an icon may use: the palette three, plus fixed house colors for things that are
# always the same color in real life (snow and clouds, traffic cones, asphalt)
COLOR_TOKENS = {"paper", "accent", "ink", "none", "white", "orange", "road"}
HOUSE_COLORS = {"white": "#F3F5F9", "orange": "#F26B1D", "road": "#3B3B42"}


def sanitize(svg_text):
    """Return inner SVG markup if it obeys the house rules, else raise ValueError."""
    svg_text = re.sub(r"^.*?(<svg)", r"\1", svg_text, flags=re.S)
    svg_text = re.sub(r"(</svg>).*$", r"\1", svg_text, flags=re.S)
    root = ET.fromstring(svg_text)
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ALLOWED_TAGS:
            raise ValueError(f"disallowed element <{tag}>")
        for k, v in el.attrib.items():
            k = k.split("}")[-1]
            if k not in ALLOWED_ATTRS:
                raise ValueError(f"disallowed attribute {k}")
            if k in ("fill", "stroke") and v not in COLOR_TOKENS:
                raise ValueError(f"colour {v} not in palette tokens")
            if "url(" in v or "javascript" in v.lower():
                raise ValueError("external reference")
        if (el.text or "").strip():
            raise ValueError("icons may not contain text")
    inner = "".join(ET.tostring(c, encoding="unicode") for c in root)
    return re.sub(r'\sxmlns(:\w+)?="[^"]*"', "", inner).replace("ns0:", "")


ICON_PROMPT = """Draw a bold, simple sticker icon showing exactly: {subject}.
Draw the literal nouns, nothing symbolic: a crab with claws, bees on a truck, snow.
Output ONE <svg viewBox="0 0 200 200"> element and nothing else.
Rules: only g, path, circle, ellipse, rect, polygon, polyline, line elements.
Colours: fill/stroke values must be exactly "paper" (the main shape colour, prints
black), "accent" (small yellow details such as honey, sparks, lights), "ink" (cut-out
details in the background colour) or "none". The background is orange; do not draw one.
Keep the subject inside a 200 x 130 band centred vertically (the patch centre is a wide
oval). Thick shapes (strokes >= 8), at most 20 elements, no text, no faces, readable at 1 inch."""


def ai_icon(subject, cfg):
    body = {"model": cfg.anthropic_model, "max_tokens": 2000,
            "messages": [{"role": "user", "content": ICON_PROMPT.format(subject=subject)}]}
    r = requests.post("https://api.anthropic.com/v1/messages", json=body, timeout=90, headers={
        "x-api-key": cfg.anthropic_api_key, "anthropic-version": "2023-06-01"})
    r.raise_for_status()
    d = r.json()
    raw = "".join(b.get("text", "") for b in d.get("content", []))
    u = d.get("usage", {})
    cost = u.get("input_tokens", 0) * 3e-6 + u.get("output_tokens", 0) * 15e-6
    return sanitize(raw), cost


def get_icon(hook, cfg):
    """Returns (svg_inner, source, cost)."""
    if cfg.anthropic_api_key:
        try:
            svg, cost = ai_icon(hook.icon_subject, cfg)
            return svg, "claude", cost
        except Exception as e:  # fall back to the library, but say so in the log
            return LIBRARY.get(hook.icon_key, LIBRARY["cone"]), f"library (AI failed: {e})", 0.0
    return LIBRARY.get(hook.icon_key, LIBRARY["cone"]), "library", 0.0


# The most interesting part of a library picture, in its own 200-unit grid (x0, y0, x1, y1).
# The badge centers and fills the field with this part, even if the rest runs off the edge.
FOCUS = {
    "crab": (36, 50, 164, 116),              # the claws, with the face beneath them
    "bee_truck": (-10, 92, 96, 170),         # the honey dripping off the back of the truck
    "blueberry_truck": (-6, 2, 136, 150),    # berries spilling off the top
}


# The fourth color follows what's pictured (it fills the icon's "accent" parts). Anything not
# listed uses the palette's own accent.
ACCENT_FOR = {
    "blueberry_truck": "#6E4FC9",   # blueberry purple
    "bee_truck": "#F59E1B",         # honey amber
    "crab": "#D7263D",              # cooked-crab red
    "snowflake": "#FFFFFF",         # snow white
}


def lettering(text, font_path, fill="paper", tracking=0.04, stroke=None, stroke_w=0.0):
    """Text turned into shapes on the 200-unit icon grid, so it gets the same outline and toon
    shading as any picture (used for city marks like the stylized 206)."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont
    font = TTFont(font_path)
    gs, cmap, upm = font.getGlyphSet(), font.getBestCmap(), font["head"].unitsPerEm
    x, parts = 0.0, []
    for ch in text:
        name = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[name].draw(TransformPen(pen, (1, 0, 0, -1, x, 0)))   # flip: fonts draw y up
        parts.append(pen.getCommands())
        x += gs[name].width + tracking * upm
    width = x - tracking * upm
    cap = font["OS/2"].sCapHeight or upm * 0.7
    k = min(180 / width, 120 / cap)                                # fill the grid, keep proportions
    tx, ty = 100 - width * k / 2, 100 + cap * k / 2
    d = " ".join(parts)
    line = (f' stroke="{stroke}" stroke-width="{stroke_w / k:.1f}" stroke-linejoin="round"' if stroke else "")
    return f'<path transform="translate({tx:.2f} {ty:.2f}) scale({k:.5f})" d="{d}" fill="{fill}"{line}/>'


# ---- Icons from Elizabeth's Nov 6 sketches (200-unit grid) -----------------------------------
_W = "white"      # cloud white
_O = "orange"     # cone orange

SKETCHED = {
    # The gallop: two towers, sagging cables, and a deck that waves like it's mid-gallop.
    "gertie_gallop": (
        '<path d="M0,176 q10,-6 20,0 t20,0 t20,0 t20,0 t20,0 t20,0 t20,0 t20,0 t20,0 t20,0" fill="none" stroke="white" stroke-width="4"/>'
        '<path d="M0,96 Q24,70 50,38 Q100,118 150,38 Q176,70 200,96" fill="none" stroke="paper" stroke-width="3.5"/>'
        '<rect x="42" y="34" width="7" height="140" fill="paper"/><rect x="55" y="34" width="7" height="140" fill="paper"/>'
        '<rect x="42" y="58" width="20" height="6" fill="paper"/><rect x="42" y="96" width="20" height="6" fill="paper"/>'
        '<rect x="138" y="34" width="7" height="140" fill="paper"/><rect x="151" y="34" width="7" height="140" fill="paper"/>'
        '<rect x="138" y="58" width="20" height="6" fill="paper"/><rect x="138" y="96" width="20" height="6" fill="paper"/>'
        '<path d="M0,128 C22,108 38,150 62,130 S100,104 124,130 S166,152 200,118" fill="none" stroke="paper" stroke-width="10" stroke-linecap="round"/>'),
    # Cartoon clouds with sound waves rolling off them, and snowflakes of several sizes.
    "thunder_snow": (
        '<path d="M14,52 A26,26 0 0,1 34,26 M6,44 A38,38 0 0,1 34,14" fill="none" stroke="paper" stroke-width="4" stroke-linecap="round"/>'
        '<path d="M168,30 A26,26 0 0,1 190,54 M170,16 A40,40 0 0,1 198,48" fill="none" stroke="paper" stroke-width="4" stroke-linecap="round"/>'
        '<g fill="' + _W + '"><circle cx="38" cy="72" r="22"/><circle cx="66" cy="54" r="29"/><circle cx="96" cy="70" r="21"/>'
        '<rect x="18" y="68" width="98" height="26" rx="13"/></g>'
        '<g fill="' + _W + '"><circle cx="124" cy="62" r="18"/><circle cx="150" cy="46" r="25"/><circle cx="176" cy="62" r="18"/>'
        '<rect x="106" y="60" width="88" height="22" rx="11"/></g>'
        '<g fill="none" stroke="paper" stroke-width="6" stroke-linecap="round">'
        '<path d="M100,104 V176 M68,122 L132,158 M68,158 L132,122"/>'
        '<path d="M88,110 L100,120 L112,110 M88,170 L100,160 L112,170 M72,134 L86,134 M114,146 L128,146"/></g>'
        '<g fill="none" stroke="paper" stroke-width="4" stroke-linecap="round">'
        '<path d="M34,140 V168 M22,147 L46,161 M22,161 L46,147"/><path d="M166,136 V164 M154,143 L178,157 M154,157 L178,143"/></g>'),
    # Bird's-eye map: diagonal Madison St you can't use or cross, closed at each crossing, and
    # right-angle detours that double back and get nowhere.
    "madison_maze": (
        '<path d="M12,188 L188,12" stroke="road" stroke-width="36" fill="none"/>'
        '<path d="M12,188 L188,12" stroke="paper" stroke-width="3" stroke-dasharray="10 8" fill="none"/>'
        '<g stroke="accent" stroke-width="8" stroke-linecap="round" fill="none">'
        '<path d="M48,138 L76,166 M48,166 L76,138"/><path d="M86,100 L114,128 M86,128 L114,100"/>'
        '<path d="M124,62 L152,90 M124,90 L152,62"/></g>'
        '<g stroke="white" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" fill="none">'
        '<path d="M6,40 H40 V64 H18 V96 H46"/><path d="M60,10 V34 H90 V14 H112 V40"/>'
        '<path d="M196,120 H164 V96 H186 V70"/><path d="M120,196 V170 H150 V188 H176 V160"/></g>'
        '<g fill="white"><polygon points="46,90 58,96 46,102"/><polygon points="106,40 112,52 118,40"/>'
        '<polygon points="180,72 186,60 192,72"/><polygon points="170,162 176,150 182,162"/></g>'),
    # SR 520: a swoopy road closed with cones, on tall bridge supports standing in the water.
    "sr520_construction": (
        '<path d="M0,170 q10,-6 20,0 t20,0 t20,0 t20,0 t20,0 t20,0 t20,0 t20,0 t20,0 t20,0" fill="none" stroke="white" stroke-width="4"/>'
        '<g fill="paper"><rect x="34" y="108" width="10" height="64"/><rect x="76" y="84" width="10" height="88"/>'
        '<rect x="118" y="74" width="10" height="98"/><rect x="160" y="74" width="10" height="98"/></g>'
        '<path d="M-4,124 C40,122 60,78 104,74 S160,92 204,62" fill="none" stroke="paper" stroke-width="14"/>'
        '<g fill="' + _O + '"><polygon points="22,114 30,92 38,114"/><polygon points="64,98 72,76 80,98"/>'
        '<polygon points="108,70 116,48 124,70"/><polygon points="156,80 164,58 172,80"/></g>'
        '<g fill="white"><rect x="26" y="102" width="8" height="4"/><rect x="68" y="86" width="8" height="4"/>'
        '<rect x="112" y="58" width="8" height="4"/><rect x="160" y="68" width="8" height="4"/></g>'),
}
LIBRARY.update(SKETCHED)
ACCENT_FOR.update({"madison_maze": "#D7263D"})


# ---- Group circles (100-unit grid, line art only; "LINE" becomes the line color) -------------
def _numerals(text):
    import os
    from .config import FONT_DIR
    # outlined numerals: 200-grid lettering shown at half size, so a 10-unit line reads as 5
    return (f'<g transform="scale(0.5)">'
            f'{lettering(text, os.path.join(FONT_DIR, "Archivo-Black.ttf"), fill="none", stroke="LINE", stroke_w=10)}</g>')


GROUPS = {
    "seattle": _numerals("206"),
    "tacoma": _numerals("253"),
    "construction": ('<path d="M16,66 A34,34 0 0,1 84,66"/><path d="M8,68 H92"/>'
                     '<path d="M50,32 V52"/><path d="M34,40 L38,60"/><path d="M66,40 L62,60"/>'),
}


# ---- Scenes: framed like a camera shot, not a centered icon ---------------------------------
# A scene fills the whole picture and runs past its edges. It has a ground (the setting) and a
# figure (the subject), told apart by value. Drawn on the 200-unit grid where the visible picture
# is x 0..200, y 35.7..164.3; anything outside that is cut off by the frame, on purpose.
# Solid shapes only: no outlines. The shading bands come from one light (toon.shade).
SCENE_BOX = (0.0, 35.7, 200.0, 164.3)


def _flake(x, y, r, rot=0.0, tilt=1.0, w=None, color="#E8EDF4"):
    """A chunky six-armed snowflake: thick arms with a V of branches, round ends."""
    import math as _m
    w = w or max(4.0, r * 0.24)
    d = []
    for i in range(6):
        a = _m.radians(60 * i)
        ex, ey = r * _m.cos(a), r * _m.sin(a)
        d.append(f"M0,0 L{ex:.1f},{ey:.1f}")
        for side in (-1, 1):
            bx, by = 0.55 * ex, 0.55 * ey
            b = a + side * _m.radians(48)
            d.append(f"M{bx:.1f},{by:.1f} l{0.32 * r * _m.cos(b):.1f},{0.32 * r * _m.sin(b):.1f}")
    return (f'<g transform="translate({x} {y}) rotate({rot}) scale(1 {tilt})">'
            f'<path d="{" ".join(d)}" fill="none" stroke="{color}" stroke-width="{w:.1f}" '
            f'stroke-linecap="round" stroke-linejoin="round"/></g>')


def _cloud(x, y, puffs, color, belly=0.08):
    """One cartoon cloud as a single solid shape: round puffs of the given radii, left to right,
    each overlapping the next, over a gently rounded bottom starting at (x, y)."""
    chords = [1.6 * r for r in puffs]            # each puff shows a bit more than half a circle
    w = sum(chords)
    d = [f"M{x:.1f},{y:.1f} Q{x + w / 2:.1f},{y + w * belly:.1f} {x + w:.1f},{y:.1f}"]
    px = x + w
    for r, c in zip(reversed(puffs), reversed(chords)):
        nx = px - c
        d.append(f"A{r:.1f},{r:.1f} 0 1 0 {nx:.1f},{y:.1f}")
        px = nx
    return f'<path d="{" ".join(d)} Z" fill="{color}"/>'


def _waves(x, y, rot, color, n=3, gap=9, r0=12, w=4.5):
    arcs = "".join(f'<path d="M{-(r0 + i * gap) * 0.70:.1f},{(r0 + i * gap) * 0.70:.1f} '
                   f'A{r0 + i * gap},{r0 + i * gap} 0 0 1 {(r0 + i * gap) * 0.70:.1f},{-(r0 + i * gap) * 0.70:.1f}" '
                   f'fill="none" stroke="{color}" stroke-width="{w}" stroke-linecap="round"/>' for i in range(n))
    return f'<g transform="translate({x} {y}) rotate({rot})">{arcs}</g>'


_SKY, _BACK, _MID, _FRONT, _NOISE = "#2B344B", "#3F4B66", "#56637F", "#6E7C99", "#9EA9C0"

SCENES = {
    # Thunder Snow: the ground is a sky full of noisy storm clouds, the figure is the snow.
    "thunder_snow": {
        "art": (
            f'<rect x="-40" y="0" width="280" height="200" fill="{_SKY}"/>'
            # back: big puffs whose tops fill the upper frame, and a bank along the bottom
            + _cloud(-30, 100, [24, 32, 26], _BACK) + _cloud(62, 92, [26, 36, 28, 22], _BACK)
            + _cloud(168, 98, [24, 30, 22], _BACK)
            + _cloud(-24, 196, [30, 38, 30], _BACK) + _cloud(96, 200, [34, 28, 36], _BACK)
            # middle layer
            + _cloud(-36, 142, [18, 26, 20], _MID) + _cloud(56, 136, [20, 27, 19], _MID)
            + _cloud(136, 140, [22, 28, 18], _MID)
            # front puffs, low in the frame
            + _cloud(-20, 184, [17, 23], _FRONT) + _cloud(114, 188, [18, 25, 17], _FRONT)
            + _waves(62, 64, -20, _NOISE) + _waves(150, 118, 30, _NOISE) + _waves(26, 150, -60, _NOISE, n=2)
            + _flake(98, 104, 44, rot=8, tilt=0.86)                     # the hero flake, close to camera
            + _flake(30, 120, 26, rot=-14, tilt=0.92)
            + _flake(164, 66, 30, rot=22, tilt=0.80)
            + _flake(200, 126, 22, rot=5)                               # cut off by the right edge
            + _flake(-2, 58, 20, rot=30, tilt=0.9)                      # cut off by the left edge
            + _flake(150, 152, 14, rot=-20) + _flake(58, 46, 11, rot=12) + _flake(122, 40, 9, rot=-8)
            + _flake(78, 160, 12, rot=40, tilt=0.85)),
        "lift": 0.16, "drop": 0.22, "band": 2.6,
    },
}


# ---- More scenes (Nov 6): Gertie, 520, Madison St. ------------------------------------------
import math as _math

_GOLD = "#F2B705"
_STORM = "#33405A"          # wind-storm sky
_HAZE = "#4E6683"           # overcast lake sky
_WATER = "#1C3F63"
_SWELL = "#2A5682"
_CONE = "#F26B1D"


def _ribbon(x0, x1, y_of, t_of, color, n=80):
    """A solid band along a curve: centerline y_of(x), thickness t_of(x). Thicker = closer."""
    xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
    top = [(x, y_of(x) - t_of(x) / 2) for x in xs]
    bot = [(x, y_of(x) + t_of(x) / 2) for x in reversed(xs)]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in top + bot)
    return f'<polygon points="{pts}" fill="{color}"/>'


def _swells(y, color, amp=5, length=34, x0=-40, x1=240):
    """A band of water with a rolling top edge, from y down past the frame."""
    pts, x = [], x0
    while x <= x1:
        pts.append(f"{x:.1f},{y + amp * _math.sin(x / length * _math.pi * 2):.1f}")
        x += 4
    return f'<polygon points="{" ".join(pts)} {x1},240 {x0},240" fill="{color}"/>'


def _tower(x, base, top, w, color):
    """A suspension-bridge tower: two thick legs and two crossbars."""
    leg = w * 0.32
    return (f'<rect x="{x - w / 2:.1f}" y="{top}" width="{leg:.1f}" height="{base - top}" fill="{color}"/>'
            f'<rect x="{x + w / 2 - leg:.1f}" y="{top}" width="{leg:.1f}" height="{base - top}" fill="{color}"/>'
            f'<rect x="{x - w / 2:.1f}" y="{top + (base - top) * 0.18:.1f}" width="{w:.1f}" height="{leg * 0.8:.1f}" fill="{color}"/>'
            f'<rect x="{x - w / 2:.1f}" y="{top + (base - top) * 0.42:.1f}" width="{w:.1f}" height="{leg * 0.8:.1f}" fill="{color}"/>')


def _cone(x, base, h, color=_CONE):
    w = h * 0.62
    return (f'<polygon points="{x - w / 2:.1f},{base} {x:.1f},{base - h:.1f} {x + w / 2:.1f},{base}" fill="{color}"/>'
            f'<polygon points="{x - w * 0.29:.1f},{base - h * 0.42:.1f} {x + w * 0.29:.1f},{base - h * 0.42:.1f} '
            f'{x + w * 0.21:.1f},{base - h * 0.62:.1f} {x - w * 0.21:.1f},{base - h * 0.62:.1f}" fill="#F3F5F9"/>'
            f'<rect x="{x - w * 0.62:.1f}" y="{base - h * 0.08:.1f}" width="{w * 1.24:.1f}" height="{h * 0.12:.1f}" fill="{color}"/>')


# Galloping Gertie: the bridge is the figure, the Narrows (and a windy sky) the ground.
# Close camera: the near tower is big and cut off at the top, the far one smaller; the deck
# gallops, its waves biggest near the camera.
_deck_y = lambda x: 112 - 0.06 * x + (15 - 0.045 * x) * _math.sin(x / 200 * _math.pi * 3.2 + 0.4)
_deck_t = lambda x: 15 - 0.04 * x
SCENES["gertie_gallop"] = {
    "art": (
        f'<rect x="-40" y="0" width="280" height="240" fill="{_STORM}"/>'
        + _swells(132, _WATER, amp=3, length=26) + _swells(146, _SWELL, amp=4, length=30)
        + _swells(160, _WATER, amp=5, length=36)
        + _tower(158, 136, 52, 22, _GOLD)                                   # far tower
        + '<path d="M210,92 Q186,60 158,54 Q100,124 40,8 Q20,40 -30,70" fill="none" '
          f'stroke="{_GOLD}" stroke-width="5.5" stroke-linecap="round"/>'      # main cable, sagging
        + _ribbon(-30, 230, _deck_y, _deck_t, _GOLD)                         # the galloping deck
        + _tower(40, 180, 0, 32, _GOLD)),                                   # near tower, cut off
    "lift": 0.18, "drop": 0.24, "band": 2.6,
}

# SR 520: the bridge is the figure, the lake the ground. A swooping road on tall supports,
# closed with cones; it sweeps toward the camera, so it widens on the right.
_road_y = lambda x: 112 - 34 * _math.sin((x + 20) / 240 * _math.pi * 1.25) + 0.12 * x
_road_t = lambda x: 9 + 0.09 * (x + 30)
SCENES["sr520_construction"] = {
    "art": (
        f'<rect x="-40" y="0" width="280" height="240" fill="{_HAZE}"/>'
        + _swells(136, _WATER, amp=2.5, length=24) + _swells(150, _SWELL, amp=3.5, length=30)
        + _swells(164, _WATER, amp=4.5, length=36)
        + "".join(f'<rect x="{x - w / 2:.1f}" y="{_road_y(x):.1f}" width="{w:.1f}" height="{190 - _road_y(x):.1f}" fill="{_GOLD}"/>'
                  for x, w in ((-6, 7), (38, 8.5), (86, 10.5), (136, 13), (190, 16)))
        + _ribbon(-40, 240, _road_y, _road_t, _GOLD)
        + "".join(_cone(x, _road_y(x) - _road_t(x) / 2 + 1, h)
                  for x, h in ((8, 13), (52, 15), (100, 18), (150, 21), (198, 25)))),
    "lift": 0.18, "drop": 0.24, "band": 2.4,
}

# Madison St.: the exception, a bird's-eye map. The ground is the city grid; the figure is the
# drive: right angle after right angle along the side streets, doubling back, never crossing
# the closed diagonal, and ending up stuck against it.
_BLOCK, _STREET, _CLOSED = "#46536F", "#2B344B", "#F26B1D"
_blocks = "".join(f'<rect x="{-25 + 40 * i}" y="{-5 + 40 * j}" width="30" height="30" rx="3" fill="{_BLOCK}"/>'
                  for i in range(7) for j in range(6))
# every corner stays on the open side of the closed street; one leg doubles back down
_route = "M15,195 V175 H95 V135 H135 V95 H155 V117 H175 V75 H153"
SCENES["madison_maze"] = {
    "art": (
        f'<rect x="-40" y="-20" width="280" height="260" fill="{_STREET}"/>' + _blocks
        + f'<path d="M-30,206 L230,-14" stroke="{_CLOSED}" stroke-width="24" fill="none"/>'
        + '<path d="M-30,206 L230,-14" stroke="#F3F5F9" stroke-width="24" stroke-dasharray="7 9" fill="none"/>'
        + f'<path d="{_route}" stroke="{_GOLD}" stroke-width="8" fill="none" stroke-linejoin="round" stroke-linecap="round"/>'
        + f'<polygon points="154,65 140,75 154,85" fill="{_GOLD}"/>'),     # arrow jammed against the barrier
    "lift": 0.16, "drop": 0.24, "band": 2.2,
}


# ---- Scene kits (Nov 6, second pass) ----------------------------------------------------------
# Reusable pieces with settings, so a just-in-time badge can be composed from a kit (bridge,
# road closed, weather) rather than drawn from scratch.
_ASPHALT, _LANE, _CURB = "#3B3B42", "#F3F5F9", "#6B6F7A"


def _poly(pts, color):
    return f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="{color}"/>'


def kit_bridge_road(y_of, deck_of, x0=-40, x1=240, piers=(), cones=(), sky=_HAZE, water_y=134):
    """A road bridge seen from slightly above: asphalt top with lane lines, the gold girder
    edge below it, piers into the water. deck_of(x) is the asphalt's apparent depth (bigger =
    closer to the camera)."""
    n = 90
    xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
    top = [(x, y_of(x) - deck_of(x)) for x in xs]           # far edge of the road surface
    edge = [(x, y_of(x)) for x in xs]                       # near edge of the road surface
    girder = [(x, y_of(x) + deck_of(x) * 0.55) for x in xs]
    out = [f'<rect x="-40" y="0" width="280" height="240" fill="{sky}"/>',
           _swells(water_y, _WATER, amp=2.5, length=24), _swells(water_y + 14, _SWELL, amp=3.5, length=30),
           _swells(water_y + 28, _WATER, amp=4.5, length=36)]
    for x, w in piers:
        out.append(f'<rect x="{x - w / 2:.1f}" y="{y_of(x):.1f}" width="{w:.1f}" height="{230 - y_of(x):.1f}" fill="{_GOLD}"/>')
    out.append(_poly(edge + list(reversed(girder)), _GOLD))      # girder face
    out.append(_poly(top + list(reversed(edge)), _ASPHALT))      # road surface
    # center line: dashes laid along the middle of the surface, longer and wider up close
    mid = [(x, y_of(x) - deck_of(x) / 2) for x in xs]
    dashes = []
    for i in range(0, n, 6):
        (ax, ay), (bx, by) = mid[i], mid[min(i + 3, n)]
        w = max(1.2, deck_of(ax) * 0.12)
        dashes.append(_poly([(ax, ay - w / 2), (bx, by - w / 2), (bx, by + w / 2), (ax, ay + w / 2)], _LANE))
    out.extend(dashes)
    for x, h in cones:
        out.append(_cone(x, y_of(x) - deck_of(x) * 0.35, h))
    return "".join(out)


def kit_suspension(left_x, right_x, tower_top, deck_y, cable_low, gallop, sky=_STORM, water_y=140, tower_w=20,
                   road_depth=0.0):
    """A suspension bridge face-on: rigid towers and approaches, cables hanging in a calm curve,
    vertical hangers, and a deck that gallops only in the middle span (gallop = wave height)."""
    span = right_x - left_x
    mid = (left_x + right_x) / 2

    def deck(x):
        if left_x <= x <= right_x:
            env = _math.sin(_math.pi * (x - left_x) / span)          # still at the towers
            return deck_y + gallop * env * _math.sin(2 * _math.pi * (x - left_x) / span * 1.5)
        return deck_y

    def cable(x):
        return cable_low - (cable_low - tower_top) * ((x - mid) / (span / 2)) ** 2

    out = [f'<rect x="-40" y="0" width="280" height="240" fill="{sky}"/>',
           _swells(water_y, _WATER, amp=3, length=26), _swells(water_y + 14, _SWELL, amp=4, length=30),
           _swells(water_y + 28, _WATER, amp=5, length=36)]
    out.append(_tower(left_x, 230, tower_top - 6, tower_w, _GOLD))
    out.append(_tower(right_x, 230, tower_top - 6, tower_w, _GOLD))
    # hangers: straight down from the calm cable to the moving deck (to the road's far edge)
    x = left_x + 10
    while x < right_x - 6:
        bottom = deck(x) - road_depth
        out.append(f'<rect x="{x - 1.1:.1f}" y="{cable(x):.1f}" width="2.2" height="{bottom - cable(x):.1f}" fill="{_GOLD}"/>')
        x += 11
    # main cable: middle span, plus the side spans down to anchorages off the frame
    pts = " ".join(f"{xx:.1f},{cable(xx):.1f}" for xx in [left_x + span * i / 40 for i in range(41)])
    out.append(f'<polyline points="{pts}" fill="none" stroke="{_GOLD}" stroke-width="4.5" stroke-linecap="round"/>')
    out.append(f'<path d="M{left_x},{tower_top} Q{left_x - 40},{tower_top + 30} {left_x - 90},{deck_y - 4}" fill="none" stroke="{_GOLD}" stroke-width="4.5"/>')
    out.append(f'<path d="M{right_x},{tower_top} Q{right_x + 40},{tower_top + 30} {right_x + 90},{deck_y - 4}" fill="none" stroke="{_GOLD}" stroke-width="4.5"/>')
    if road_depth:   # the deck as a road seen from slightly above: asphalt and lane line over the girder
        xs = [-40 + 280 * i / 160 for i in range(161)]
        top = [(x, deck(x) - road_depth) for x in xs]
        edge = [(x, deck(x)) for x in xs]
        girder = [(x, deck(x) + 6) for x in xs]
        out.append(_poly(edge + list(reversed(girder)), _GOLD))
        out.append(_poly(top + list(reversed(edge)), _ASPHALT))
        for i in range(0, 160, 6):
            (ax, ay), (bx, by) = top[i], top[min(i + 3, 160)]
            ay, by = ay + road_depth / 2, by + road_depth / 2
            out.append(_poly([(ax, ay - 0.8), (bx, by - 0.8), (bx, by + 0.8), (ax, ay + 0.8)], _LANE))
    else:
        out.append(_ribbon(-40, 240, deck, lambda x: 9, _GOLD, n=120))
    return "".join(out)


def kit_road_closed(rise=0.62, sky=_HAZE, skyline=True, cones=((36, 160, 30), (166, 158, 27))):
    """Street-level shot of a closed road: the street climbs away to the horizon (rise = how
    steep it looks), torn up, with a striped Type III barricade across it and cones in front."""
    hz = 74 + 24 * (1 - rise)                                   # steeper street: horizon higher
    out = [f'<rect x="-40" y="0" width="280" height="240" fill="{sky}"/>']
    if skyline:   # generic towers on the hill, no landmark
        x, hs = -30, [30, 18, 40, 24, 46, 22, 34, 16, 38, 24, 28]
        for i, h in enumerate(hs):
            w = 18 + (i * 7) % 11
            out.append(f'<rect x="{x}" y="{hz - h:.1f}" width="{w}" height="{h + 4}" fill="{_STORM}"/>')
            x += w + 3
    out.append(_poly([(-40, hz + 2), (240, hz + 2), (240, 240), (-40, 240)], "#3E4A63"))      # hillside
    out.append(_poly([(90, hz), (110, hz), (240, 220), (-40, 220)], _ASPHALT))                # the street
    out.append(_poly([(84, hz), (90, hz), (-40, 220), (-60, 220)], _CURB))
    out.append(_poly([(110, hz), (116, hz), (260, 220), (240, 220)], _CURB))
    for (a, b, c, d) in ((0.25, 0.32, 0.30, 0.42), (0.55, 0.62, 0.48, 0.60)):                # torn-up plates
        def at(t, u):
            y = hz + (220 - hz) * t
            half = 10 + (140 - 10) * t
            return (100 - half + 2 * half * u, y)
        out.append(_poly([at(a, c), at(a, d), at(b, d), at(b, c)], "#5E606B"))
    # Type III barricade: two legs and three striped boards
    bx0, bx1 = 34, 166
    for lx in (bx0 + 10, bx1 - 14):
        out.append(f'<rect x="{lx}" y="104" width="6" height="66" fill="#E8EDF4"/>')
    for k, by in enumerate((106, 124, 142)):
        out.append(f'<rect x="{bx0}" y="{by}" width="{bx1 - bx0}" height="12" fill="#E8EDF4"/>')
        sx = bx0 - 8 + (k % 2) * 4
        while sx < bx1:
            a, b = max(bx0, sx), min(bx1, sx + 9)
            if b > a:
                out.append(_poly([(a, by + 12), (min(bx1, a + 6), by), (min(bx1, b + 6), by), (b, by + 12)], _CONE))
            sx += 18
    for x, base, h in cones:
        out.append(_cone(x, base, h))
    return "".join(out)


_r520_y = lambda x: 116 - 20 * _math.sin((x + 20) / 260 * _math.pi * 1.1) + 0.10 * x
_r520_d = lambda x: 6 + 0.10 * (x + 40)
SCENES["sr520_construction"] = {
    "art": kit_bridge_road(_r520_y, _r520_d, piers=((-4, 7), (44, 9), (96, 11), (150, 13), (204, 16)),
                           cones=((14, 12), (60, 14), (108, 17), (158, 20), (206, 24))),
    "lift": 0.18, "drop": 0.24, "band": 2.4,
}
SCENES["gertie_gallop"] = {
    # framed like Elizabeth's sketch: left tower left of center, right tower near the right edge,
    # both towers reaching the top of the frame, the bridge running off both sides, water low
    "art": kit_suspension(left_x=64, right_x=178, tower_top=34, deck_y=110, cable_low=84, gallop=13,
                          water_y=146, tower_w=22, road_depth=7),
    "lift": 0.18, "drop": 0.24, "band": 2.4,
}
SCENES["madison_closed"] = {
    "art": kit_road_closed(rise=0.62),
    "lift": 0.16, "drop": 0.24, "band": 2.2,
}


# ---- Scenes for the history set (Nov 7): built from the kits ---------------------------------
def snow_scene(waves=True, flakes=1.0):
    """The weather kit: storm clouds as the ground, snow as the figure; waves = thunder."""
    art = SCENES["thunder_snow"]["art"]
    if not waves:
        art = re.sub(r'<g transform="translate\([^)]*\) rotate\([^)]*\)"><path d="M-[^"]*A[^>]*/>(<path[^>]*/>)*</g>', "", art)
    return art


import re  # noqa: E402  (used by snow_scene)

_flat_y = lambda base, sway: (lambda x: base - sway * _math.sin((x + 40) / 280 * _math.pi))
SCENES["snowpocalypse"] = {"art": snow_scene(waves=False), "lift": 0.16, "drop": 0.22, "band": 2.6}
SCENES["ship_canal"] = {      # Revive I-5: the double-deck Ship Canal Bridge squeezed down with cones
    "art": kit_bridge_road(_flat_y(104, 6), lambda x: 8 + 0.06 * (x + 40),
                           piers=((10, 14), (100, 16), (190, 18)),
                           cones=((24, 13), (64, 15), (104, 17), (146, 20), (190, 23))),
    "lift": 0.18, "drop": 0.24, "band": 2.4}
SCENES["west_seattle"] = {    # the high bridge, closed: cones across the whole deck
    "art": kit_bridge_road(_flat_y(96, 14), lambda x: 7 + 0.07 * (x + 40), sky="#3F5470",
                           piers=((20, 12), (110, 15), (196, 18)),
                           cones=((36, 14), (76, 16), (118, 18), (160, 21))),
    "lift": 0.18, "drop": 0.24, "band": 2.4}
SCENES["i90_bridge"] = {      # the floating bridge, low on the water, its far end going under
    "art": kit_bridge_road(lambda x: 122 + 0.10 * max(0, 60 - x), lambda x: 5 + 0.05 * (x + 40),
                           water_y=128, cones=((120, 14), (170, 17))),
    "lift": 0.18, "drop": 0.24, "band": 2.4}
SCENES["hood_canal"] = {      # the floating bridge in a windstorm
    "art": kit_bridge_road(lambda x: 120 - 0.04 * x, lambda x: 5 + 0.05 * (x + 40), sky=_STORM,
                           water_y=124, cones=()),
    "lift": 0.18, "drop": 0.24, "band": 2.4}
SCENES["viadoom"] = {"art": kit_road_closed(rise=0.3, sky="#3F5470"), "lift": 0.16, "drop": 0.24, "band": 2.2}
