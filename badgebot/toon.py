"""Toon shading for badge icons, like a toon shader in a 3D app.

One invisible light (cfg.light_deg, default from the upper left) lights every shape in the
picture on its own: each shape gets a lighter band on the edges facing the light and a darker
band on the edges facing away, worked out from that shape's own color. A dark outline then goes
around the whole picture.

The bands come from each shape's own silhouette shifted toward and away from the light:
    highlight = shape minus (shape shifted away from the light)
    shadow    = shape minus (shape shifted toward the light)
so they follow any shape, including strokes, without hand-drawn shading.
"""
import math
import re
import xml.etree.ElementTree as ET

INHERIT = ("fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin")
SHAPES = {"path", "rect", "circle", "ellipse", "polygon", "polyline", "line"}


def _hex(c):
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _mix(c, other, t):
    a, b = _hex(c), _hex(other)
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def tones(color, lift=0.45, drop=0.30):
    """(light, shadow) for one base color: same hue, a step lighter and a step darker than that
    shape's own normal. Light and dark are only ever relative to the shape's base."""
    return _mix(color, "#FFFFFF", lift), _mix(color, "#000000", drop)


def flatten(icon_svg):
    """Leaf shapes with their inherited colors and the full chain of transforms above them."""
    root = ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg">{icon_svg}</svg>')
    out = []

    def walk(el, inherited, transforms):
        attrs = dict(inherited)
        for k in INHERIT:
            if el.get(k) is not None:
                attrs[k] = el.get(k)
        tr = transforms + ([el.get("transform")] if el.get("transform") else [])
        tag = el.tag.split("}")[-1]
        if tag in SHAPES:
            a = {k: v for k, v in el.attrib.items() if k not in INHERIT and k != "transform"}
            a.update({k: v for k, v in attrs.items()})
            if "fill" not in a and tag not in ("line", "polyline"):
                a["fill"] = "#000000"
            if tr:
                a["transform"] = " ".join(tr)
            out.append((tag, a))
        for child in el:
            walk(child, attrs, tr)

    for child in root:
        walk(child, {}, [])
    return out


def _attrs(a):
    return " ".join(f'{k}="{v}"' for k, v in a.items())


# Filters measured in the picture's own units, not its box: a perfectly straight line has a box
# with zero width, and a box-relative filter would then draw nothing.
FREGION = 'filterUnits="userSpaceOnUse" x="-400" y="-400" width="1000" height="1000"'


def _flat(fid, color):
    return (f'<filter id="{fid}" {FREGION} color-interpolation-filters="sRGB">'
            f'<feFlood flood-color="{color}"/><feComposite in2="SourceAlpha" operator="in"/></filter>')


def shade(icon_svg, outline, scale, light_deg=135.0, band=2.0, outline_w=1.5, hole_color=None,
          lift=0.45, drop=0.30):
    """Returns (art, defs) in the icon's own 200-unit coordinates.
    band and outline_w are in badge units; scale converts them to icon units.
    Shapes painted in hole_color (the field) are gaps, like the opening in a claw: they cut
    through the picture and its outline instead of being drawn, shaded or outlined themselves."""
    leaves = flatten(icon_svg)
    norm = lambda c: (c or "").strip().upper()
    holes = [(t, a) for t, a in leaves if hole_color and norm(a.get("fill")) == norm(hole_color)]
    leaves = [(t, a) for t, a in leaves if not (hole_color and norm(a.get("fill")) == norm(hole_color))]
    rad = math.radians(light_deg)
    d = band / scale
    lx, ly = math.cos(rad) * d, -math.sin(rad) * d     # toward the light (y grows downward)
    defs, art, filters = [], [], {}

    def flat_id(color):
        if color not in filters:
            filters[color] = f"fl{len(filters)}"
            defs.append(_flat(filters[color], color))
        return filters[color]

    wf = flat_id("#FFFFFF")
    region = 'maskUnits="userSpaceOnUse" x="-400" y="-400" width="1000" height="1000"'
    cut = ""
    if holes:
        gaps = "".join(f'<{t} {_attrs(dict(a, fill="#000000", stroke="none"))}/>' for t, a in holes)
        defs.append(f'<mask id="holes" {region}><rect x="-400" y="-400" width="1000" height="1000" fill="#FFFFFF"/>'
                    f'{gaps}</mask>')
        cut = 'mask="url(#holes)"'
    whole = []
    for i, (tag, a) in enumerate(leaves):
        base = a.get("fill") if a.get("fill") not in (None, "none") else a.get("stroke")
        sid = f"s{i}"
        defs.append(f'<{tag} id="{sid}" {_attrs(a)}/>')
        whole.append(f'<use href="#{sid}"/>')
        if not base or not base.startswith("#"):
            art.append(f'<use href="#{sid}"/>')
            continue
        light, dark = tones(base, lift, drop)
        # the shape's silhouette with the gaps already cut out, so bands follow the gap edges too
        defs.append(f'<mask id="m{i}" {region}><g {cut}><use href="#{sid}" filter="url(#{wf})"/></g></mask>')
        defs.append(f'<mask id="t{i}" {region}><g transform="translate({lx:.2f} {ly:.2f})"><g {cut}>'
                    f'<use href="#{sid}" filter="url(#{wf})"/></g></g></mask>')
        art.append(
            f'<g mask="url(#m{i})">'
            f'<use href="#{sid}" filter="url(#{flat_id(light)})"/>'                       # lit everywhere...
            f'<use href="#{sid}" filter="url(#{flat_id(dark)})" transform="translate({-lx:.2f} {-ly:.2f})"/>'
            f'<g mask="url(#t{i})"><use href="#{sid}" transform="translate({-lx:.2f} {-ly:.2f})"/></g>'
            f'</g>')                                  # ...then shadow away from the light, base in the middle
    ow = outline_w / scale
    # the outline: the whole picture's silhouette, grown and filled dark, under everything
    defs.append(f'<filter id="olf" {FREGION} color-interpolation-filters="sRGB">'
                f'<feMorphology in="SourceAlpha" operator="dilate" radius="{ow:.2f}" result="g"/>'
                f'<feFlood flood-color="{outline}"/><feComposite in2="g" operator="in"/></filter>')
    # outline grown from the silhouette after the gaps are cut, so gaps get an outline too;
    # outline=None is the solid-object look: no outline, only the light's own bands
    body = (f'<g filter="url(#olf)"><g {cut}>{"".join(whole)}</g></g>' if outline else "") + "".join(art)
    return body, "".join(defs)
