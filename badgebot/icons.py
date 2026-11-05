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
                 "stroke-linejoin", "transform", "opacity", "viewBox", "xmlns"}
COLOR_TOKENS = {"paper", "accent", "ink", "none"}


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
