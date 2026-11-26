#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""A front panel as vectors for every module: 2026/_catalog/panels/<Mxxx>.svg (module_extras.py links each one to
<module>/MECHANICAL/<Mxxx> - front panel.svg).

Each panel comes from the best thing in the archive that shows the module's face, in this order:
  cad       CorelDRAW / CAD panel art (tools/panels.json "cad": an SVG already converted from the .cdr / .dwg)
  traced    a front-panel drawing the drawing tracer turned into vectors ("<drawing> (EXTRACTED).svg": FRONT PANEL,
            ESCUTCHEON, FACE PLATE, SILK, PANEL LAYOUT): its line work and lettering, cropped to the panel
  layout    a -04- module layout (or other mechanical drawing) that draws the front panel, cropped the same way
  drawing   such a drawing not traced yet: the crop traced here (timelines/trace_svg.cjs, the tracer's line-art preset)
  photo     a front photo or data-sheet picture: the face squared up from four corners (tools/panels.json "quad") and
            traced from its light/dark edges
  none      nothing in the archive shows the panel: a plain outline, marked data-from="none", with a small note
The crop is found by shape: two long parallel edges closed top and bottom, tall and narrow (a module), with the
most drawn parts (knobs, keys, meters, lettering) inside. tools/panels.json overrides any module: a source file, a
box (fractions of the upright sheet), four corners of a photo, panel art, or "none" with the reason; "long" draws
a whole-console sheet larger so the one strip cut out of it keeps its detail, "note" is kept as data-note (a variant
sharing another's panel, a strip of a console layout).
Console modules (the M900 series, built into Renaissance consoles) are drawn under the console job's number, not the
module's, so the console folders are searched too: 2026/Consoles drawings whose title names the module (console_drawings)
and the "layouts" tools/m900_series.json lists for it.
Every panel is portrait (tall, one module wide); a panel drawn sideways is stood up. <svg data-from="<2026 path>"
data-kind="<kind>"> records where it came from. Never draws a control or legend that is not in the source.

    python3 -I tools/make_panels.py [Mxxx ...] [--list] [--sheet out.png] [--report out.tsv]
"""
import glob
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from html import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Y2026 = os.path.join(ROOT, '2026')
MODULES = os.path.join(Y2026, 'Modules')
OUT = os.path.join(Y2026, '_catalog', 'panels')
DB = os.path.join(Y2026, 'timelines', 'wbs_timeline.db')
TRACER = os.path.join(Y2026, 'timelines', 'trace_svg.cjs')
CONF = os.path.join(ROOT, 'tools', 'panels.json')
CONSOLES = os.path.join(Y2026, 'Consoles')
SERIES = os.path.join(ROOT, 'tools', 'm900_series.json')   # console modules: code -> function, consoles, drawings
LONG = 2000                     # the tracer's sheet: long side in px
MIN_SCORE = 4                   # a crop with less in it (about one knob and a few marks) is not taken as a panel
MIN_LAYOUT = 10                 # on a sheet not named for the front panel, a crop needs a few controls in it
INK = '#1c1c1c'
PICS = ('.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff', '.bmp')
SKIP_KINDS = {'OCR', 'KICAD', 'PINOUTS', 'SOFTWARE'}
FRONT = re.compile(r'FRONT\s*PANEL|FRONT\s*PNL|ESCUTCHEON|FACE\s*PLATE|FACEPLATE|SILK|PANEL\s*LAYOU|FRONT\s*&\s*REAR\s*LAYOUT', re.I)
NOT_FRONT = re.compile(r'REAR PANEL|DISPLAY SCREEN|LOCK LATCH|MTG PLATE|MOUNTING PLATE|SCHEMATIC|wbsps - (promo|module)', re.I)
LAYOUT = re.compile(r'(?<![0-9])\d{2,4}-04-\d{3}')
JOB_DRAWING = re.compile(r'(?<![0-9])\d{3,6}-0[34]-\d{3}')     # a console job's layout (-04-) or metalwork (-03-)
NOT_FACE = re.compile(r'TOP PLATE|BOTTOM PLATE|BACKPLANE|COVER|BRACKET|BOARD|COMPONENT LAYOUT|CONNECTOR', re.I)
CODE_OCR = re.compile(r'\bM([0-9IGQ])([0-9OIL])([0-9OILSBG])([A-Z]{0,3})\b')


# ---------------------------------------------------------------- sources

def module_dirs():
    """{code: [module dir, ...]} (a code filed under two categories pools both folders)."""
    out = {}
    for d in sorted(glob.glob(os.path.join(MODULES, '*', '*'))):
        if os.path.isdir(d) and not os.path.basename(d).startswith(('.', '_')):
            out.setdefault(os.path.basename(d), []).append(d)
    return out


def rel(p):
    return os.path.relpath(p, Y2026).replace(os.sep, '/')


def extracted(p):
    s = os.path.splitext(p)[0] + ' (EXTRACTED).svg'
    return s if os.path.exists(s) else None


def candidates(dirs):
    """Drawings that may show the front panel, best first: [(rank, path)]."""
    out = []
    for d in dirs:
        for kind in sorted(os.listdir(d)):
            kd = os.path.join(d, kind)
            if kind in SKIP_KINDS or not os.path.isdir(kd):
                continue
            for f in sorted(os.listdir(kd)):
                if not f.lower().endswith(PICS) or '_small' in f:
                    continue
                p = os.path.join(kd, f)
                if FRONT.search(f) and not (NOT_FRONT.search(f) and not re.search('FRONT', f, re.I)) and 'wbsps' not in f:
                    out.append((0 if extracted(p) else 2, p))
                elif LAYOUT.search(f) and kind == 'MECHANICAL':
                    out.append((1 if extracted(p) else 3, p))
    return sorted(out)


def ocr_code(s):
    """The module codes a drawing title names, with the scanner's misreadings put right (MIOINW -> M901NW, MIOSNW ->
    M905NW, M9O1CY -> M901CY): {code}."""
    first, second, third = str.maketrans('IGQ', '999'), str.maketrans('OIL', '011'), str.maketrans('OILSBG', '011589')
    return {f'M{a.translate(first)}{b.translate(second)}{c.translate(third)}{x}'
            for a, b, c, x in CODE_OCR.findall(s.upper())}


_console = None


def console_drawings():
    """{code: [path]}: the console folders' drawings of one module's face. A console job draws its modules under the
    job number, not the module's (940238-04-003 M901NW STEREO LINE INPUT MODULE LAYOUT, 940444-03-006 M901BY/CY
    CUSTOM INPUT MODULES), so a module folder never holds them. Taken: a -04- layout or a -03- module drawing whose
    title (file name, else the title block in its .md note) names one module, or two sharing the sheet (BY/CY); and
    every drawing tools/m900_series.json lists as a module's "layouts". A whole-console layout (one strip per module,
    many codes) is not taken here: tools/panels.json crops a strip out of it by hand."""
    global _console
    if _console is not None:
        return _console
    _console = {}
    for root, dirs, files in os.walk(CONSOLES):
        dirs[:] = [d for d in dirs if not d.startswith(('.', '_'))]
        for f in files:
            if not f.lower().endswith(PICS) or '_small' in f or not JOB_DRAWING.search(f):
                continue
            p = os.path.join(root, f)
            title = f
            md = p + '.md'
            if os.path.exists(md):
                m = re.search(r'"title_block":\[(.*?)\]', open(md, encoding='utf-8', errors='ignore').read())
                title += ' ' + (m.group(1) if m else '')
            if not (re.search(r'LAYOUT|MODULE', title, re.I) or FRONT.search(title)) or NOT_FRONT.search(f) or \
                    NOT_FACE.search(title):
                continue
            title = re.sub(r'\b(M\w+)/([A-Z]{1,2})\b', r'\1 \1/\2', title.upper())    # M901BY/CY: both
            codes = ocr_code(title)
            codes |= {re.sub(r'[A-Z]+$', '', c) + s for c in codes for s in re.findall(r'/([A-Z]{1,2})\b', title)}
            if 1 <= len(codes) <= 2:
                for c in codes:
                    _console.setdefault(c, []).append(p)
    try:
        series = json.load(open(SERIES, encoding='utf-8')).get('modules', {})
    except (OSError, ValueError):
        series = {}
    for code, m in series.items():
        for s in m.get('drawings', {}).get('layouts', []):
            p = os.path.join(Y2026, s)
            if os.path.exists(p) and p not in _console.get(code, []):
                _console.setdefault(code, []).append(p)
    return _console


def console_candidates(code):
    """The console drawings of one module, as candidates(): a layout (-04-) ranks with a module's own layouts."""
    return sorted((1 if extracted(p) else 3, p) for p in console_drawings().get(code, []))


# ---------------------------------------------------------------- sheets

_rot = None


def rotation(p):
    """The turn that stands a scan upright (the rotation audit, else the tracer's)."""
    global _rot
    if _rot is None:
        _rot = {}
        try:
            con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
            _rot.update(dict(con.execute('SELECT dest, rotate FROM traces')))
            _rot.update(dict(con.execute('SELECT dest, rotate FROM rotation')))
        except sqlite3.Error:
            pass
    return _rot.get(rel(p)) or 0


def picture(p, deg=None, long=None):
    """The picture upright, long side LONG (or long: a whole console sheet, where one module is a narrow strip), as an
    RGB PIL image."""
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = None
    long = long or LONG
    im = Image.open(p)
    im.draft('RGB', (long * 2, long * 2))
    im = ImageOps.exif_transpose(im).convert('RGB')
    deg = rotation(p) if deg is None else deg
    if deg:
        im = im.rotate(deg, expand=True, fillcolor='white')
    s = long / max(im.size)
    return im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)


def ink_of(im):
    """Ink (True) on paper, as the tracer sees a drawing; the scanner's dark edges cleared."""
    import numpy as np
    a = np.asarray(im.convert('L'), dtype=np.int16)
    ink = a < a.mean() - 40
    H, W = ink.shape
    for rng, axis in ((range(H // 4), 1), (range(H - 1, H * 3 // 4, -1), 1), (range(W // 4), 0), (range(W - 1, W * 3 // 4, -1), 0)):
        for i in rng:
            line = ink[i, :] if axis == 1 else ink[:, i]
            if line.mean() <= .5:
                break
            line[:] = False
    return ink


def trace_parts(svg_path):
    """(viewBox w, h, [(class, subpath, bbox)]) of a tracer SVG: line work and lettering, not the title block."""
    t = open(svg_path, encoding='utf-8').read()
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', t).group(1).split()]
    parts = []
    for cls, d in re.findall(r'<path class="(line|text|tb)" d="([^"]+)"', t):
        for sub in re.split(r'(?=M)', d):
            nums = [float(v) for v in re.findall(r'-?\d+\.?\d*', sub)]
            if len(nums) < 4:
                continue
            xs, ys = nums[0::2], nums[1::2]
            parts.append((cls, sub, (min(xs), min(ys), max(xs), max(ys))))
    return vb[2], vb[3], parts


def ink_of_trace(w, h, parts):
    """The traced outlines filled back into ink, on the sheet's own pixels (curves by their end points)."""
    import numpy as np
    import cv2
    img = np.zeros((int(round(h)) + 1, int(round(w)) + 1), np.uint8)
    polys = []
    for _, sub, _ in parts:
        nums = [float(v) for v in re.findall(r'-?\d+\.?\d*', sub)]
        pts = np.array(nums[:len(nums) // 2 * 2], np.float32).reshape(-1, 2)
        if len(pts) >= 2:
            polys.append(np.round(pts).astype(np.int32))
    for q in polys:   # even-odd, as the SVG draws a ring (outline and hole) and a letter's counters
        x, y, w2, h2 = cv2.boundingRect(q)
        if w2 <= 0 or h2 <= 0:
            continue
        loc = np.zeros((h2 + 1, w2 + 1), np.uint8)
        cv2.fillPoly(loc, [q - (x, y)], 1)
        cv2.polylines(loc, [q - (x, y)], True, 1, 1)
        sub = img[y:y + h2 + 1, x:x + w2 + 1]
        sub ^= loc[:sub.shape[0], :sub.shape[1]]
    return img > 0


def circles_of(ink):
    """Round things drawn on a sheet (knobs, jacks, keys, lamps, screw holes): [(cx, cy, diameter)]."""
    import numpy as np
    import cv2
    cs, _ = cv2.findContours(ink.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    out, seen = [], set()
    for c in cs:
        x, y, w, h = cv2.boundingRect(c)
        if w < 8 or h < 8 or not .75 <= w / h <= 1.33:
            continue
        per = cv2.arcLength(c, True)
        area = cv2.contourArea(c)
        if per == 0 or 4 * np.pi * area / per ** 2 < .7:
            continue
        key = (round((x + w / 2) / 6), round((y + h / 2) / 6))
        if key in seen:
            continue
        seen.add(key)
        out.append((x + w / 2, y + h / 2, (w + h) / 2))
    return np.array(out).reshape(-1, 3)


def find_panel(ink):
    f = find_panels(ink, 1)
    return f[0] if f else None


def find_panels(ink, k=1):
    """(x0, y0, x1, y1, score) of the module panel on a sheet, or None: a pair of long parallel edges, closed at both
    ends, tall and narrow (or wide and short: drawn sideways), holding the most knobs, jacks and keys (round things the
    size of a control), then the most other drawn parts. Callout boxes of lettering and title blocks score little."""
    import numpy as np
    import cv2
    H, W = ink.shape
    L = max(H, W)
    a = cv2.dilate(ink.astype(np.uint8) * 255, np.ones((3, 3), np.uint8))
    _, _, st, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    comp = st[1:]
    comp = comp[(comp[:, 4] >= 8)]
    circ = circles_of(ink)
    found = []
    for turned in (False, True):
        b = np.ascontiguousarray(a.T) if turned else a
        h, w = b.shape
        kl = max(40, int(.08 * L))
        v = cv2.morphologyEx(b, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 15)))   # broken lines
        v = cv2.morphologyEx(v, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, kl)))
        _, _, vs, _ = cv2.connectedComponentsWithStats(v)
        segs = sorted((x + ww / 2, y, y + hh) for x, y, ww, hh, _ in vs[1:] if ww <= .012 * L)
        for i, (xa, ya0, ya1) in enumerate(segs):
            for xb, yb0, yb1 in segs[i + 1:]:
                wd = xb - xa
                if wd < .015 * L:
                    continue
                y0, y1 = max(ya0, yb0), min(ya1, yb1)
                ln = y1 - y0
                if ln <= 0 or ln < .75 * min(ya1 - ya0, yb1 - yb0) or not 2.2 <= ln / wd <= 16:
                    continue
                if xa < .005 * w or xb > .995 * w:
                    continue
                band = max(3, int(.012 * L))
                ends = []
                for yy in (y0, y1):
                    r0, r1 = max(0, int(yy) - band), min(h, int(yy) + band + 1)
                    rows = b[r0:r1, int(xa):int(xb) + 1] > 0
                    ends.append(rows.mean(axis=1).max() if rows.size else 0)
                if max(ends) < .6:   # closed at one end at least (a traced line can break)
                    continue
                # a table (title block, connector list) is ruled right across: a panel is not, inside its ends
                inner = b[int(y0 + band * 2):int(y1 - band * 2), int(xa + band):int(xb - band)] > 0
                if inner.size == 0 or inner.mean() > .5:
                    continue
                full = inner.mean(axis=1) > .97
                rules = int(np.count_nonzero(full[1:] & ~full[:-1]))
                if rules > 4:
                    continue
                X0, Y0, X1, Y1 = (y0, xa, y1, xb) if turned else (xa, y0, xb, y1)
                inside = comp[(comp[:, 0] >= X0 + 1) & (comp[:, 1] >= Y0 + 1) & (comp[:, 0] + comp[:, 2] <= X1 - 1) &
                              (comp[:, 1] + comp[:, 3] <= Y1 - 1)]
                short = min(X1 - X0, Y1 - Y0)
                knobs = circ[(circ[:, 0] > X0) & (circ[:, 0] < X1) & (circ[:, 1] > Y0) & (circ[:, 1] < Y1) &
                             (circ[:, 2] >= .2 * short) & (circ[:, 2] <= .95 * short)] if len(circ) else circ
                score = 3 * len(knobs) + min(len(inside), 40) * .2
                found.append(((score, (X1 - X0) * (Y1 - Y0)), (X0, Y0, X1, Y1, score)))
    out = []
    for _, f in sorted(found, reverse=True):   # the best, then others that are not the same box again
        if all(overlap(f, g) < .6 for g in out):
            out.append(f)
        if len(out) >= k:
            break
    return out


def overlap(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy / min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))


# ---------------------------------------------------------------- writing

def pad_box(x0, y0, x1, y1, w, h, pad=.03):
    p = pad * max(x1 - x0, y1 - y0)
    return max(0, x0 - p), max(0, y0 - p), min(w, x1 + p), min(h, y1 + p)


def wrap(body, w, h, src, kind, extra=''):
    """The panel SVG: portrait; a wide crop is stood up (turned a quarter to the left)."""
    if w > h:
        body = f'<g transform="translate(0 {w:.0f}) rotate(-90)">{body}</g>'
        w, h = h, w
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" data-from="{escape(src)}" '
            f'data-kind="{kind}"{extra}>{body}</svg>')


def from_trace(svg_path, box=None):
    w, h, parts = trace_parts(svg_path)
    if box is None:
        f = find_panel(ink_of_trace(w, h, parts))
        if not f:
            return None
        x0, y0, x1, y1 = pad_box(*f[:4], w, h)
        score = f[4]
    else:
        x0, y0, x1, y1 = box[0] * w, box[1] * h, box[2] * w, box[3] * h
        score = None
    keep = {'line': [], 'text': [], 'tb': []}
    for cls, sub, (a, b, c, d) in parts:
        if c >= x0 and a <= x1 and d >= y0 and b <= y1:
            keep[cls].append(sub)
    cw, ch = x1 - x0, y1 - y0
    body = (f'<defs><clipPath id="c"><rect width="{cw:.0f}" height="{ch:.0f}"/></clipPath></defs>'
            f'<g clip-path="url(#c)"><g transform="translate({-x0:.0f} {-y0:.0f})" fill="{INK}">' +
            ''.join(f'<path class="{c}" d="{"".join(ds)}"/>' for c, ds in keep.items() if ds) + '</g></g>')
    return body, cw, ch, score


def trace_ink(ink):
    """Vectors of an ink mask by the drawing tracer's line-art preset (timelines/trace_svg.cjs): path data."""
    import numpy as np
    h, w = ink.shape
    raw = np.where(ink, 0, 255).astype(np.uint8)
    with tempfile.TemporaryDirectory() as td:
        rp, op = os.path.join(td, 'x.raw'), os.path.join(td, 'x.svg')
        raw.tofile(rp)
        job = {'raw': rp, 'w': w, 'h': h, 'out': op, 'dtype': '04', 'text': [], 'title_block': None}
        r = subprocess.run(['node', TRACER], input=json.dumps(job) + '\n', capture_output=True, text=True, timeout=600)
        if not os.path.exists(op):
            raise RuntimeError(r.stdout + r.stderr)
        t = open(op, encoding='utf-8').read()
    return ''.join(re.findall(r'<path class="[a-z]+" d="([^"]+)"', t))


def from_picture(p, box=None, deg=None, long=None):
    im = picture(p, deg, long)
    ink = ink_of(im)
    H, W = ink.shape
    if box is None:
        f = find_panel(ink)
        if not f:
            return None
        x0, y0, x1, y1 = pad_box(*f[:4], W, H)
        score = f[4]
    else:
        x0, y0, x1, y1 = box[0] * W, box[1] * H, box[2] * W, box[3] * H
        score = None
    x0, y0, x1, y1 = (int(round(v)) for v in (x0, y0, x1, y1))
    d = trace_ink(ink[y0:y1, x0:x1].copy())
    return f'<path class="line" fill="{INK}" d="{d}"/>', x1 - x0, y1 - y0, score


def from_photo(p, quad, deg=None, invert=None, scale=1.0):
    """A photo's panel face squared up from its four corners (fractions, TL TR BR BL) and traced from its edges."""
    import numpy as np
    import cv2
    im = picture(p, deg)
    a = np.asarray(im.convert('L'))
    H, W = a.shape
    q = np.float32([[x * W, y * H] for x, y in quad])
    wd = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    ht = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    s = 1600 / max(wd, ht) * scale
    wd, ht = int(wd * s), int(ht * s)
    M = cv2.getPerspectiveTransform(q, np.float32([[0, 0], [wd, 0], [wd, ht], [0, ht]]))
    face = cv2.warpPerspective(a, M, (wd, ht), borderValue=255)
    face = cv2.GaussianBlur(face, (3, 3), 0)
    dark = face.mean() < 128 if invert is None else invert
    # legends, knobs and holes: what stands out from the panel's own tone around it
    if dark:   # light legends and knob edges on a dark panel: brighter than the panel around them
        ink = cv2.adaptiveThreshold(face, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, -18) > 0
    else:
        ink = cv2.adaptiveThreshold(face, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 41, 12) > 0
    ink = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) > 0
    d = trace_ink(ink)
    body = (f'<rect class="outline" x="1" y="1" width="{wd - 2}" height="{ht - 2}" fill="none" stroke="{INK}" stroke-width="3"/>'
            f'<path class="line" fill="{INK}" d="{d}"/>')
    return body, wd, ht


def from_cad(svg_path, colours=None):
    """Panel art already converted to SVG (CorelDRAW / CAD): drawn in ink on the panel, inside its outline."""
    t = open(svg_path, encoding='utf-8').read()
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', t).group(1).split()]
    inner = re.sub(r'^.*?<svg[^>]*>|</svg>\s*$', '', t, flags=re.S)
    for c in (colours or []):
        inner = inner.replace(c, INK)
    w, h = vb[2], vb[3]
    body = (f'<g transform="translate({-vb[0]:g} {-vb[1]:g})">{inner}</g>'
            f'<rect class="outline" x=".5" y=".5" width="{w - 1:g}" height="{h - 1:g}" fill="none" stroke="{INK}" stroke-width="1"/>')
    return body, w, h


def blank(code, why='no front-panel art in the archive'):
    w, h = 120, 720
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" data-from="none" data-kind="none">'
            f'<rect class="outline" x="2" y="2" width="{w - 4}" height="{h - 4}" fill="none" stroke="#9a9a9a" '
            f'stroke-width="2" stroke-dasharray="8 6"/>'
            f'<text x="{w / 2}" y="{h / 2}" fill="#9a9a9a" font-family="sans-serif" font-size="9" text-anchor="middle" '
            f'transform="rotate(-90 {w / 2} {h / 2})">{escape(code)}: {escape(why)}</text></svg>')


# ---------------------------------------------------------------- main

def make(code, dirs, conf):
    """(svg text, kind, source) for one module."""
    c = conf.get(code, {})
    if 'none' in c:
        return blank(code, c['none'] or 'no front-panel art in the archive'), 'none', c['none']
    if 'cad' in c:
        body, w, h = from_cad(os.path.join(Y2026, c['cad']), c.get('colours'))
        return wrap(body, w, h, c['from'], 'cad'), 'cad', c['from']
    if 'src' in c:
        p = os.path.join(Y2026, c['src'])
        if 'quad' in c:
            body, w, h = from_photo(p, c['quad'], c.get('rot'), c.get('invert'))
            kind = 'photo'
        elif extracted(p) and c.get('rot') is None and not c.get('long'):
            body, w, h, _ = from_trace(extracted(p), c.get('box'))
            kind = c.get('kind', 'traced' if FRONT.search(os.path.basename(p)) else 'layout')
        else:
            r = from_picture(p, c.get('box'), c.get('rot'), c.get('long'))
            if not r:
                raise RuntimeError(f'{code}: no panel found in {c["src"]}')
            body, w, h, _ = r
            kind = c.get('kind', 'drawing')
        note = f' data-note="{escape(c["note"])}"' if c.get('note') else ''
        return wrap(body, w, h, rel(p), kind, note), kind, rel(p)
    skip = set(c.get('skip', []))
    found = []
    for rank, p in sorted(candidates(dirs) + console_candidates(code)):
        if rel(p) in skip:
            continue
        ex = extracted(p)
        try:
            r = from_trace(ex) if ex else from_picture(p)
        except Exception as e:   # a picture that will not open
            print(f'  {code}: {rel(p)}: {e}', file=sys.stderr)
            continue
        if r and r[3] >= (MIN_SCORE if rank % 2 == 0 else MIN_LAYOUT):
            # a drawing named for the front panel first, then the most controls found, a traced one before a scan
            found.append(((rank % 2, -r[3], rank // 2), rank, p, r))
    if found:
        _, rank, p, (body, w, h, _) = min(found, key=lambda f: f[0])
        kind = ('traced', 'layout', 'drawing', 'drawing')[rank]
        return wrap(body, w, h, rel(p), kind), kind, rel(p)
    return blank(code), 'none', ''


def sheet(codes, out):
    """A contact sheet of the panels (for looking at them)."""
    try:
        import cairosvg
    except ImportError:   # run with -I: the user's site packages
        import site
        sys.path.insert(0, site.getusersitepackages())
        import cairosvg
    from PIL import Image, ImageDraw
    cells = []
    for code in codes:
        t = open(os.path.join(OUT, code + '.svg'), encoding='utf-8').read().replace('<svg ', '<svg style="background:white" ', 1)
        try:
            im = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=t.encode(), output_height=360))).convert('RGBA')
        except Exception:
            im = Image.new('RGBA', (60, 360), 'red')
        if im.width > 200:
            im = im.resize((200, max(1, int(im.height * 200 / im.width))))
        cell = Image.new('RGB', (206, 384), 'white')
        cell.paste(im, (3, 3), im)
        ImageDraw.Draw(cell).text((3, 368), code, fill='black')
        cells.append(cell)
    cols = 16
    for k in range(0, len(cells), cols * 3):
        ch = cells[k:k + cols * 3]
        s = Image.new('RGB', (cols * 206, ((len(ch) + cols - 1) // cols) * 384), '#ccc')
        for i, c in enumerate(ch):
            s.paste(c, ((i % cols) * 206, (i // cols) * 384))
        p = out.replace('.png', f'_{k // (cols * 3):02d}.png')
        s.save(p)
        print(p)


def propose(codes, mods, out):
    """For choosing by eye: every candidate sheet of each module with its best boxes drawn and numbered
    (<out>_NN.png) and <out>.json: {"<code> <letter><n>": {"src": ..., "box": [...]}} ready for tools/panels.json."""
    import numpy as np
    from PIL import Image, ImageDraw
    cells, table = [], {}
    for code in codes:
        for i, (rank, p) in enumerate(sorted(candidates(mods[code]) + console_candidates(code))[:8]):
            letter = 'abcdefgh'[i]
            ex = extracted(p)
            try:
                if ex:
                    w, h, parts = trace_parts(ex)
                    ink = ink_of_trace(w, h, parts)
                    im = Image.fromarray(np.where(ink_of_trace(w, h, parts), 0, 255).astype(np.uint8)).convert('RGB')
                else:
                    im = picture(p)
                    ink = ink_of(im)
            except Exception as e:
                print(code, rel(p), e, file=sys.stderr)
                continue
            H, W = ink.shape
            boxes = find_panels(ink, 6)
            s = 520 / max(W, H)
            im = im.resize((max(1, int(W * s)), max(1, int(H * s))))
            d = ImageDraw.Draw(im)
            for g in range(1, 20):   # a grid in twentieths, to read a box off by eye
                c = (150, 150, 150) if g % 2 else (90, 90, 90)
                d.line([(im.width * g / 20, 0), (im.width * g / 20, im.height)], fill=c, width=1 if g % 2 else 2)
                d.line([(0, im.height * g / 20), (im.width, im.height * g / 20)], fill=c, width=1 if g % 2 else 2)
            for n, (x0, y0, x1, y1, sc) in enumerate(boxes):
                col = ['red', 'blue', 'green', 'magenta', 'orange', 'cyan'][n]
                d.rectangle([x0 * s, y0 * s, x1 * s, y1 * s], outline=col, width=2)
                d.text((x0 * s + 2, y0 * s + 2), str(n), fill=col)
                table[f'{code} {letter}{n}'] = {'src': rel(p), 'box': [round(v, 4) for v in pad_box(x0, y0, x1, y1, W, H)
                                                                         [:2] + pad_box(x0, y0, x1, y1, W, H)[2:]],
                                                 'score': round(sc, 1)}
                bx = pad_box(x0, y0, x1, y1, W, H)
                table[f'{code} {letter}{n}']['box'] = [round(bx[0] / W, 4), round(bx[1] / H, 4), round(bx[2] / W, 4), round(bx[3] / H, 4)]
            cell = Image.new('RGB', (526, 548), 'white')
            cell.paste(im, (3, 3))
            ImageDraw.Draw(cell).text((3, 530), f'{code} {letter} {"T" if ex else "R"} {os.path.basename(p)[:70]}', fill='black')
            cells.append(cell)
    cols = 5
    for k in range(0, len(cells), cols * 3):
        ch = cells[k:k + cols * 3]
        sh = Image.new('RGB', (cols * 526, ((len(ch) + cols - 1) // cols) * 548), '#bbb')
        for i, c in enumerate(ch):
            sh.paste(c, ((i % cols) * 526, (i // cols) * 548))
        sh.save(f'{out}_{k // (cols * 3):02d}.png')
        print(f'{out}_{k // (cols * 3):02d}.png')
    json.dump(table, open(out + '.json', 'w'), indent=0)


def main():
    args = sys.argv[1:]
    opt = lambda k: args[args.index(k) + 1] if k in args else None
    sheet_out, report = opt('--sheet'), opt('--report')
    codes = [a for a in args if re.match(r'^R?M\w+$', a)]
    conf = json.load(open(CONF, encoding='utf-8')) if os.path.exists(CONF) else {}
    conf = {k: v for k, v in conf.items() if not k.startswith('_')}
    mods = module_dirs()
    if opt('--propose'):
        propose(codes or sorted(c for c in mods if candidates(mods[c])), mods, opt('--propose'))
        return
    if '--list' in args:
        for code in codes or mods:
            for rank, p in sorted(candidates(mods[code]) + console_candidates(code)):
                print(code, rank, rel(p))
        return
    os.makedirs(OUT, exist_ok=True)
    rows, count = [], {}
    for code in codes or sorted(mods):
        try:
            svg, kind, src = make(code, mods[code], conf)
        except Exception as e:
            print(f'{code}: {e}', file=sys.stderr)
            svg, kind, src = blank(code), 'none', ''
        p = os.path.join(OUT, code + '.svg')
        if not os.path.exists(p) or open(p, encoding='utf-8').read() != svg:
            with open(p, 'w', encoding='utf-8') as fh:
                fh.write(svg)
        count[kind] = count.get(kind, 0) + 1
        rows.append((code, kind, src))
        print(f'{code}\t{kind}\t{src}', flush=True)
    print(f'{len(rows)} panels: ' + ', '.join(f'{k} {v}' for k, v in sorted(count.items())))
    if report:
        with open(report, 'w', encoding='utf-8') as fh:
            fh.write('code\tkind\tsource\n' + ''.join(f'{c}\t{k}\t{s}\n' for c, k, s in rows))
    if sheet_out:
        sheet([r[0] for r in rows], sheet_out)


if __name__ == '__main__':
    main()
