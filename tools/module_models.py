#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""A 3-D model of every module drawn in a mechanical drawing: <module>/MECHANICAL/<Mxxx>.model.json (and, made from
it by tools/stl/make_stl.mjs, <Mxxx>.stl), and the site's copy 2026/_catalog/models/<Mxxx>.json + index.json that
2026/stl.html views and generates STLs from.

A module is taken when its MECHANICAL folder holds a traced mechanical drawing ("(traced).json"), an AutoCAD file,
or its front panel was drawn from one (make_panels.py kinds cad / traced / layout / drawing): 194 modules.

The model (format "wbs-model/1", mm, x right / y up from the panel's lower-left corner, z out of the face):
  size      w x h of the front panel, d behind it: the module's own TECHNICAL DATA "Dimensions" (Specifications.json)
            when it prints them, else the drawing sheet's scale (a 1:1 drawing), else 41 mm wide (1.6", the common
            module) and the drawn panel's proportions; "size_from" says which
  panel     t (3.2 mm, 1/8" aluminium)
  holes     what the front panel drawing draws as closed shapes, found by rendering the panel SVG
            (<Mxxx> - front panel.svg) and taking the white regions enclosed by ink, and the solid ink dots:
              circle  d <= 12.7 mm  -> a through hole (jack, lamp, switch, screw)
              circle  d >  12.7 mm  -> a control: a 9.5 mm (3/8") bushing hole and a knob of the drawn size
              rect    >= 3 mm a side -> a cut-out (meter window, key, display)
  knobs     the controls above, {x, y, r}
  body      "card" (a PC card 1.6 mm thick down the middle, the module's depth) or "chassis" (a box behind a panel
            wider than 100 mm: rack units)
A module whose front panel is not drawn anywhere (only its cover plate, brackets, ...) gets the panel blank.
Nothing is drawn that the drawing does not draw; the panel picture (from) and what was found are kept in the JSON.

    python3 tools/module_models.py [Mxxx ...]       then   node tools/stl/make_stl.mjs
"""
import glob
import io
import json
import math
import os
import re
import sys

import cairosvg
import cv2
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLONES = os.path.join(ROOT, 'WBSps.ca', 'Github.WardBeckSystems')
SITE = os.path.join(ROOT, '2026', '_catalog', 'models')
OWNER = 'WardBeckSystems'
DRAWN = {'cad', 'traced', 'layout', 'drawing'}
PX_MM = 6.0             # raster: px per mm of panel
T_PANEL = 3.2
KNOB_MIN = 12.7         # a drawn circle wider than 1/2" is a control's knob, not a hole
BUSHING = 9.5
DEFAULT_W, DEFAULT_D = 41.0, 165.0


def module_code(repo):
    m = re.match(r'MODULES\.[^.]+\.([A-Z]{0,3}[0-9][0-9A-Z]*?)(?:-|$)', repo)
    return m.group(1) if m else None


def taken(d):
    mech = os.path.join(d, 'MECHANICAL')
    if not os.path.isdir(mech):
        return None, None
    panel = glob.glob(os.path.join(mech, '* - front panel.svg'))
    kind = None
    if panel:
        m = re.search(r'data-kind="(\w+)"', open(panel[0], encoding='utf-8', errors='replace').read(600))
        kind = m.group(1) if m else None
    drawings = sorted(glob.glob(os.path.join(mech, '*(traced).json')) + glob.glob(os.path.join(mech, '*.[dD][wW][gG]')))
    if drawings or kind in DRAWN:
        return (panel[0] if panel else None), kind
    return None, None


# --- size -------------------------------------------------------------------------------------------------------

def spec_size(d):
    """(w, h, d) mm from the TECHNICAL DATA "Dimensions" line, and the text it was read from."""
    f = os.path.join(d, 'Specifications.json')
    if not os.path.exists(f):
        return None, None
    try:
        data = json.load(open(f, encoding='utf-8'))
    except ValueError:
        return None, None
    lines = []

    def walk(x):
        if isinstance(x, dict):
            if str(x.get('name', '')).lower().startswith('dimension') and x.get('text'):
                lines.append(x['text'])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(data)
    for text in lines:
        t = text.replace(',', '.').replace('Mm', 'mm').replace('MM', 'mm')
        # "(41 mm X 178 mm X 165 mm)": three millimetre figures in a row
        mm = [float(v) for v in re.findall(r'(\d+(?:\.\d+)?)\s*m(?:m|im)\b', t)]
        if len(mm) >= 3 and all(5 <= v <= 700 for v in mm[:3]):
            w, h, dp = mm[:3]
            return (w, h, dp), text
        # inches: "1.6\" wide X 7\" high X 6.5\" deep", "1.58W X 6.625L X 6D", "3.4W X 3.4H X 13.70"
        got = {}
        for v, word in re.findall(r'(\d+(?:\.\d+)?)\s*(?:"\d?|ins?\.?|inches)?\s*(wide|w(?:1de|ide)?|high|h|deep|d|l)\b', t, re.I):
            k = {'w': 'w', 'h': 'h', 'l': 'h', 'd': 'd'}[word[0].lower()]
            got.setdefault(k, float(v) * 25.4)
        if 'w' in got and 'h' in got and all(5 <= v <= 700 for v in got.values()):
            return (got['w'], got['h'], got.get('d', DEFAULT_D)), text
    return None, None


# --- the panel drawing -----------------------------------------------------------------------------------------

def render(svg_path, height_px):
    s = open(svg_path, encoding='utf-8', errors='replace').read()
    png = cairosvg.svg2png(bytestring=s.encode('utf-8'), output_height=int(height_px), background_color='white')
    g = np.array(Image.open(io.BytesIO(png)).convert('L'))
    return g < 140, s


def panel_box(ink):
    """The panel inside the picture: the largest white region enclosed by ink, if it is most of the picture."""
    H, W = ink.shape
    n, lab, st, _ = cv2.connectedComponentsWithStats((~ink).astype(np.uint8), connectivity=4)
    best = None
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if x == 0 or y == 0 or x + w >= W or y + h >= H:
            continue
        if w * h > 0.35 * W * H and (best is None or a > st[best][4]):
            best = i
    if best is None:
        return (0, 0, W, H), None
    x, y, w, h, _ = st[best]
    return (x, y, w, h), best


def shapes(ink, box, scale):
    """Closed shapes inside the panel box: [(kind, cx, cy, a, b)] in px (circle: a = b = radius; rect: w, h)."""
    bx, by, bw, bh = box
    found = []
    for mask, solid in (((~ink).astype(np.uint8), False), (ink.astype(np.uint8), True)):
        cs, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        for c in cs:
            x, y, w, h = cv2.boundingRect(c)
            if x <= bx + 1 or y <= by + 1 or x + w >= bx + bw - 1 or y + h >= by + bh - 1:
                continue
            if w > 0.9 * bw and h > 0.3 * bh:
                continue
            a = cv2.contourArea(c)
            if a < 4:
                continue
            per = cv2.arcLength(c, True) or 1
            circ = 4 * math.pi * a / per ** 2
            wmm, hmm = w / scale, h / scale
            if solid:
                # a solid ink dot: a screw or lamp drawn filled
                if circ > 0.78 and 0.8 < w / h < 1.25 and 2.0 <= wmm <= 8.0:
                    filled = cv2.countNonZero(mask[y:y + h, x:x + w]) / (w * h)
                    if filled > 0.65:
                        found.append(('circle', x + w / 2, y + h / 2, (w + h) / 4, (w + h) / 4))
                continue
            small = wmm < 5.0      # a letter's loop (O, 6, 8, 0) is small and seldom quite round
            if (circ > (0.86 if small else 0.78) and (0.9 if small else 0.8) < w / h < (1.11 if small else 1.25)
                    and 2.8 <= wmm <= 45):
                found.append(('circle', x + w / 2, y + h / 2, (w + h) / 4, (w + h) / 4))
            elif a / (w * h) > 0.88 and wmm >= 3 and hmm >= 3 and wmm < 0.95 * bw / scale:
                found.append(('rect', x + w / 2, y + h / 2, w, h))
    return found


def features(found, box, scale, H_mm, sx, sy):
    """Holes and knobs in mm (panel lower-left origin, y up), overlaps resolved."""
    bx, by, bw, bh = box
    circles, rects = [], []
    for k, cx, cy, a, b in found:
        x, y = (cx - bx) * sx, H_mm - (cy - by) * sy
        if k == 'circle':
            circles.append([x, y, a * (sx + sy) / 2])
        else:
            rects.append([x, y, a * sx, b * sy])
    # concentric circles are one feature: the outer edge, and the smallest inner one
    circles.sort(key=lambda c: -c[2])
    groups = []
    for c in circles:
        for g in groups:
            if math.hypot(c[0] - g['x'], c[1] - g['y']) < max(1.5, 0.25 * g['r']):
                g['inner'] = min(g['inner'], c[2])
                break
        else:
            groups.append({'x': c[0], 'y': c[1], 'r': c[2], 'inner': c[2]})
    holes, knobs = [], []
    for g in groups:
        if 2 * g['r'] > KNOB_MIN:
            hr = g['inner'] if 2 * g['inner'] <= KNOB_MIN else BUSHING / 2
            knobs.append({'x': round(g['x'], 2), 'y': round(g['y'], 2), 'r': round(g['r'], 2)})
            holes.append({'shape': 'circle', 'x': round(g['x'], 2), 'y': round(g['y'], 2), 'r': round(hr, 2)})
        else:
            holes.append({'shape': 'circle', 'x': round(g['x'], 2), 'y': round(g['y'], 2), 'r': round(g['r'], 2)})
    for x, y, w, h in rects:
        holes.append({'shape': 'rect', 'x': round(x, 2), 'y': round(y, 2), 'w': round(w, 2), 'h': round(h, 2)})
    return holes, knobs


def extent(h):
    if h['shape'] == 'circle':
        return h['x'] - h['r'], h['y'] - h['r'], h['x'] + h['r'], h['y'] + h['r']
    return h['x'] - h['w'] / 2, h['y'] - h['h'] / 2, h['x'] + h['w'] / 2, h['y'] + h['h'] / 2


def tidy(holes, W, H, edge=1.0):
    """Holes wholly inside the panel and apart from each other (bigger first): the plate stays one piece."""
    keep = []
    for h in sorted(holes, key=lambda h: -(h.get('r', 0) ** 2 * math.pi or h.get('w', 0) * h.get('h', 0))):
        x0, y0, x1, y1 = extent(h)
        if x0 < edge or y0 < edge or x1 > W - edge or y1 > H - edge:
            continue
        clash = False
        for k in keep:
            a0, b0, a1, b1 = extent(k)
            if h['shape'] == k['shape'] == 'circle':
                clash = math.hypot(h['x'] - k['x'], h['y'] - k['y']) < h['r'] + k['r'] + 0.6
            else:
                clash = not (x1 + 0.6 < a0 or a1 + 0.6 < x0 or y1 + 0.6 < b0 or b1 + 0.6 < y0)
            if clash:
                break
        if not clash:
            keep.append(h)
    return keep


def sheet_scale(d, svg_text):
    """mm per SVG unit when the panel was cut from a traced sheet (tracer px * the sheet's mm_per_px)."""
    m = re.search(r'data-from="([^"]*)"', svg_text)
    if not m:
        return None
    src = os.path.basename(m.group(1))
    stem = os.path.splitext(src)[0]
    j = os.path.join(d, 'MECHANICAL', stem + ' (traced).json')
    if os.path.exists(j):
        try:
            return json.load(open(j, encoding='utf-8'))['sheet']['mm_per_px']
        except (ValueError, KeyError):
            return None
    return None


DEBUG = None


def dbg(ink, box, found, out):
    im = cv2.cvtColor(np.where(ink, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    x, y, w, h = box
    cv2.rectangle(im, (x, y), (x + w, y + h), (255, 0, 0), 2)
    for k, cx, cy, a, b in found:
        if k == 'circle':
            cv2.circle(im, (int(cx), int(cy)), int(a), (0, 0, 255), 2)
        else:
            cv2.rectangle(im, (int(cx - a / 2), int(cy - b / 2)), (int(cx + a / 2), int(cy + b / 2)), (0, 160, 0), 2)
    cv2.imwrite(out, im)


def build(d):
    repo = os.path.basename(d)
    code = module_code(repo)
    panel_svg, kind = taken(d)
    if code is None or (panel_svg is None and kind is None and not glob.glob(os.path.join(d, 'MECHANICAL', '*(traced).json'))
                        and not glob.glob(os.path.join(d, 'MECHANICAL', '*.[dD][wW][gG]'))):
        return None
    size, size_text = spec_size(d)
    notes = []
    holes, knobs = [], []
    drawn = panel_svg and kind in DRAWN
    view = None
    if drawn:
        s = open(panel_svg, encoding='utf-8', errors='replace').read()
        view = [float(v) for v in re.search(r'viewBox="([^"]*)"', s).group(1).split()]
        vw, vh = view[2], view[3]
    if size:
        W, H, D = size
        size_from = f'TECHNICAL DATA: {size_text.strip()[:160]}'
    elif drawn and (mpp := sheet_scale(d, s)) and 15 <= vw * mpp <= 500 and 40 <= vh * mpp <= 600:
        W, H, D = vw * mpp, vh * mpp, DEFAULT_D
        size_from = 'the drawing sheet, taken as drawn 1:1'
    elif drawn and kind == 'cad' and abs(max(vw, vh) * 0.254 / 482.6 - 1) < 0.03:
        # AutoCAD panel art drawn in hundredths of an inch: a 19" rack panel
        W, H, D = max(vw, vh) * 0.254, min(vw, vh) * 0.254, DEFAULT_D
        size_from = 'the AutoCAD drawing (hundredths of an inch: a 19" rack panel)'
    elif drawn:
        W, H, D = DEFAULT_W, DEFAULT_W * vh / vw, DEFAULT_D
        size_from = f'assumed {DEFAULT_W:g} mm wide (1.6"), the drawn panel\'s proportions'
    else:
        W, H, D = DEFAULT_W, 178.0, DEFAULT_D
        size_from = 'assumed: 1.6" x 7" x 6.5", the common module'
    landscape = W > H
    if drawn:
        ink, _ = render(panel_svg, PX_MM * max(W, H) * 1.15)
        if landscape:   # make_panels.py stood a wide panel up (a quarter turn left): lay it back down
            ink = np.ascontiguousarray(np.rot90(ink, -1))
        box, _ = panel_box(ink)
        bw, bh = box[2], box[3]
        sx, sy = W / bw, H / bh
        if abs(math.log(sx / sy)) > math.log(1.15):
            notes.append(f'the drawn panel is {bw / bh:.2f} wide to high, the size {W / H:.2f}: '
                         'placed by its height')
            sx = sy
        found = shapes(ink, box, (bw / W + bh / H) / 2)
        if DEBUG:
            dbg(ink, box, found, os.path.join(DEBUG, code + '.png'))
        holes, knobs = features(found, box, (bw / W + bh / H) / 2, H, sx, sy)
        holes = tidy(holes, W, H)
        keepc = {(h['x'], h['y']) for h in holes if h['shape'] == 'circle'}
        knobs = [k for k in knobs if (k['x'], k['y']) in keepc]
    else:
        notes.append('no drawing of the front panel: the panel is blank')
    rel = lambda p: os.path.relpath(p, d).replace(os.sep, '/') if p else None
    return {
        'format': 'wbs-model/1',
        'module': code,
        'repo': repo,
        'title': repo.split('.', 2)[2].split('-', 1)[1].replace('-', ' ') if '-' in repo.split('.', 2)[2] else code,
        'category': repo.split('.')[1],
        'units': 'mm; x right, y up from the front panel\'s lower-left corner, z out of the face',
        'size': {'w': round(W, 2), 'h': round(H, 2), 'd': round(D, 2)},
        'size_from': size_from,
        'panel': {'t': T_PANEL, 'drawing': rel(panel_svg), 'kind': kind},
        'body': 'chassis' if W > 100 else 'card',
        'holes': holes,
        'knobs': knobs,
        'drawings': [rel(p) for p in sorted(glob.glob(os.path.join(d, 'MECHANICAL', '*(traced).json')))],
        'notes': notes,
        'stl': f'MECHANICAL/{code}.stl',
    }


SITE_URL = 'https://wardbecksystems.github.io/WBSps.ca/2026/stl.html'


def readme_section(d, m):
    """The README's "3-D model" section, rewritten in place (after the Mechanical section)."""
    f = os.path.join(d, 'README.md')
    if not os.path.exists(f):
        return
    code, sz = m['module'], m['size']
    lines = ['## 3-D model', '',
             f'[`MECHANICAL/{code}.stl`](MECHANICAL/{code}.stl) (GitHub turns it in 3-D) · '
             f'[view, change and generate it on WBSps.ca]({SITE_URL}?m={code})', '',
             f'- **Size:** {sz["w"]:g} × {sz["h"]:g} mm panel, {sz["d"]:g} mm deep, {m["panel"]["t"]:g} mm plate '
             f'({m["size_from"]})',
             f'- **From the drawing:** {len(m["holes"])} holes and cut-outs, {len(m["knobs"])} knobs'
             + (f' (front panel: `{m["panel"]["drawing"]}`)' if m['panel']['drawing'] else '')]
    lines += [f'- {n}' for n in m['notes']]
    lines += [f'- Made by `tools/module_models.py` (→ `MECHANICAL/{code}.model.json`) and `tools/stl/make_stl.mjs` in '
              '[WBSps.ca](https://github.com/WardBeckSystems/WBSps.ca); the site makes the same STL from the same JSON.', '']
    new = '\n'.join(lines)
    text = open(f, encoding='utf-8').read()
    hit = re.search(r'^## 3-D model\n.*?(?=^## |^---$|\Z)', text, re.S | re.M)
    if hit:
        text = text[:hit.start()] + new + '\n' + text[hit.end():]
    else:
        mech = re.search(r'^## Mechanical\n.*?(?=^## |^---$|\Z)', text, re.S | re.M)
        at = mech.end() if mech else (re.search(r'^---$', text, re.M).start() if re.search(r'^---$', text, re.M) else len(text))
        text = text[:at] + new + '\n' + text[at:]
    open(f, 'w', encoding='utf-8').write(re.sub(r'\n{3,}', '\n\n', text))


def main():
    global DEBUG
    if '--debug' in sys.argv:
        DEBUG = sys.argv[sys.argv.index('--debug') + 1]
        os.makedirs(DEBUG, exist_ok=True)
        sys.argv.remove(DEBUG)
    want = set(a for a in sys.argv[1:] if not a.startswith('-'))
    os.makedirs(SITE, exist_ok=True)
    index = []
    for d in sorted(glob.glob(os.path.join(CLONES, 'MODULES.*'))):
        code = module_code(os.path.basename(d))
        if want and code not in want:
            continue
        try:
            m = build(d)
        except Exception as e:   # one bad drawing never stops the rest
            print(f'{os.path.basename(d)}: {e}', file=sys.stderr)
            continue
        if not m:
            continue
        out = os.path.join(d, 'MECHANICAL', f'{code}.model.json')
        json.dump(m, open(out, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
        readme_section(d, m)
        site_name = m['repo'][len('MODULES.'):] + '.json'
        json.dump(m, open(os.path.join(SITE, site_name), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
        index.append({'module': code, 'repo': m['repo'], 'title': m['title'], 'category': m['category'],
                      'size': m['size'], 'holes': len(m['holes']), 'knobs': len(m['knobs']),
                      'kind': m['panel']['kind'], 'model': site_name,
                      'stl': f'https://raw.githubusercontent.com/{OWNER}/{m["repo"]}/main/MECHANICAL/{code}.stl',
                      'panel': (f'https://raw.githubusercontent.com/{OWNER}/{m["repo"]}/main/'
                                + m['panel']['drawing'].replace(' ', '%20')) if m['panel']['drawing'] else None})
        print(f'{code:8} {m["panel"]["kind"] or "-":8} {m["size"]["w"]:6.1f} x {m["size"]["h"]:6.1f} x {m["size"]["d"]:6.1f}'
              f'  holes {len(m["holes"]):3}  knobs {len(m["knobs"]):2}  {m["size_from"][:40]}')
    if not want:
        json.dump({'format': 'wbs-model-index/1', 'models': index}, open(os.path.join(SITE, 'index.json'), 'w',
                  encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f'{len(index)} models')


if __name__ == '__main__':
    main()
