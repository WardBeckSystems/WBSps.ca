#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""The symbol of every module, synthesized from its repository's own data: KiCad, SVG, DXF, PowerPoint and Visio.

    python3 tools/symbol_synth.py [--data-only] [--check] [CODE ...]

Two steps, both per module repository (WBSps.ca/Github.WardBeckSystems/MODULES.<CAT>.<M>-<Function>):

1. Data. RTO.json in the repo is the module's pinout. When it lacks a connector on its pins (the older, derived files) or the
   repo has none, it is filled from the archive's other readings of the same connector: the RTO-144 sheet
   (Engineering/RTO-144/<M>/<M>.rto144.json, checked against the schematics) and the I/O pin readings (Engineering/IO).
   Each pin then has connector, pin, signal, kind, port and polarity. A newer RTO.json (made by tools/pinout_build.py from
   the pinout pictures) is kept as it is: it is the best reading.
2. Symbols, from RTO.json alone, all from one layout (inputs left, outputs right, power top, grounds bottom, each port's
   + / - together, no-connects hidden), coloured by the module's category (CATEGORY_COLOURS):

     KICAD/<M>.kicad_sym        the KiCad symbol (KiCad 8 and later)
     KICAD/<M>-symbol.svg       a picture of it (the site, the README)
     KICAD/<M>-symbol.dxf       for CAD (layers per kind of pin)
     KICAD/<M>-symbol.pptx      a slide: the symbol drawn as shapes, to use in a schematic or a talk
     KICAD/<M>-symbol.vsdx      the same for Visio

Every output says it was synthesized and from what; edit RTO.json (or the readings it is made from), never the outputs.
--check: report what would change, write nothing. A module with no pinout read anywhere gets no symbol (listed).
"""
import json, math, os, re, sys, zipfile
from xml.sax.saxutils import escape as xesc

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.join(TOP, 'WBSps.ca', 'Github.WardBeckSystems')
ENG = os.path.join(HOME, 'Engineering')
G = 2.54                     # KiCad grid (mm)
CH = 1.05                    # width of one character of the 1.27 mm KiCad font, near enough
GEN = 'wbsps_symbol_synth'

# the module's kind, at a glance: body fill and line colour (light, dark)
CATEGORY_COLOURS = {
    'INPUT-PRE-AMPS': ('#E6F2E6', '#2E6B34'),   # green: where the signal comes in
    'AMPLIFIERS': ('#E3EEF9', '#1F5F8B'),       # blue
    'FILTERS': ('#FFF1D6', '#A86A00'),          # amber: equalizers and filters
    'DYNAMICS': ('#FBE4E1', '#A52A22'),         # red: compressors, limiters, gates
    'SUMMING': ('#EEE6F7', '#5B3A8C'),          # purple: buses and submasters
    'MONITORING': ('#E0F3F3', '#1E6E6E'),       # teal
    'METER': ('#FFF8CC', '#7A6800'),            # yellow
    'ROUTING': ('#F2E9DF', '#7A4E2A'),          # brown: switching and patching
    'COMMUNICATION': ('#E4EAF8', '#2A4E9A'),    # indigo: intercom
    'POWER': ('#F3E1E1', '#7A1F1F'),            # maroon
    'LOGIC': ('#E9EDF0', '#455A64'),            # slate
    'COMPUTERS': ('#E6E8F5', '#303F9F'),
    'RENAISSANCE': ('#F5ECDB', '#6B4E16'),      # bronze: the Renaissance console's own modules
    'UNSORTED': ('#F0F0F0', '#555555'),
}
PIN_COLOURS = {'in': '#2E6B34', 'out': '#1F5F8B', 'power': '#A52A22', 'ground': '#333333', 'control': '#7A4E2A', 'other': '#555555'}
SIDE = {'in': 'L', 'insert_return': 'L', 'control_in': 'L', 'bus_in': 'L', 'strap': 'L', 'other': 'L', 'audio': 'L', 'io': 'L',
        'unread': 'L', 'control': 'L', 'bus': 'R', 'out': 'R', 'insert_send': 'R', 'control_out': 'R',
        'power': 'T', 'ground': 'B', 'shield': 'B', 'nc': 'N'}
ETYPE = {'in': 'input', 'insert_return': 'input', 'control_in': 'input', 'bus_in': 'input', 'out': 'output', 'insert_send': 'output',
         'control_out': 'output', 'bus': 'output', 'power': 'power_in', 'ground': 'power_in', 'shield': 'passive', 'nc': 'no_connect',
         'control': 'bidirectional', 'io': 'bidirectional'}
COLOUR_OF = {'in': 'in', 'insert_return': 'in', 'control_in': 'control', 'bus_in': 'in', 'out': 'out', 'insert_send': 'out',
             'control_out': 'control', 'bus': 'out', 'power': 'power', 'ground': 'ground', 'shield': 'ground', 'control': 'control'}
CONF = {'high': 4, 'medium': 3, 'low': 2, 'variant': 1}


def modules():
    """[(code, category, repo dir)] of every module repository."""
    out = []
    for d in sorted(os.listdir(HOME)):
        m = re.match(r'^MODULES\.([A-Z0-9-]+)\.(R?[A-Z]*\d+[A-Z0-9]*?)(?:-.+)?$', d)
        if m and os.path.isdir(os.path.join(HOME, d, '.git')):
            out.append((m.group(2), m.group(1), os.path.join(HOME, d)))
    return out


def rel(repo):
    return os.path.relpath(repo, TOP).replace(os.sep, '/')


# ---------------------------------------------------------------- 1. the data -----------------------------------------------

def split_addr(a):
    """'P1-17' -> ('P1', '17'); '17' -> ('', '17')."""
    m = re.match(r'^([A-Z]+\d+)-(.+)$', str(a or '').strip())
    return (m.group(1), m.group(2)) if m else ('', str(a or '').strip())


def from_sheet(code):
    """Pins from the RTO-144 sheet: [(connector, pin, signal, kind, port, polarity)]."""
    p = os.path.join(ENG, 'RTO-144', code, code + '.rto144.json')
    if not os.path.exists(p):
        return None, None
    d = json.load(open(p))
    pins = []
    def add(addr, signal, kind, port=None, pol=None):
        if addr:
            c, n = split_addr(addr)
            pins.append({'connector': c, 'pin': n, 'signal': signal, 'kind': kind, 'port': port, 'polarity': pol})
    for a in d.get('audio') or []:
        kind = 'in' if a.get('dir') == 'in' else 'out'
        if re.search(r'INSERT', a.get('signal', ''), re.I):
            kind = 'insert_return' if a.get('dir') == 'in' else 'insert_send'
        add(a.get('pos'), a['signal'], kind, a.get('port'), '+'); add(a.get('neg'), a['signal'], kind, a.get('port'), '-')
    for b in (d.get('bus_out') or []) + (d.get('bus_in') or []):
        kind = 'bus' if b in (d.get('bus_out') or []) else 'bus_in'
        add(b.get('pos'), b['signal'], kind, b.get('bus'), '+'); add(b.get('neg'), b['signal'], kind, b.get('bus'), '-')
    for pw in d.get('power') or []:
        v = pw.get('volts')
        add(pw.get('supply'), f"{pw['rail']} {'+' if v and v > 0 else ''}{v} V" if v is not None else pw['rail'], 'power')
        add(pw.get('ground'), 'COMMON', 'ground')
    for lg in d.get('logic') or []:
        add(lg.get('pin'), lg['signal'], 'control')
    if d.get('chassis'):
        add(d['chassis'], 'CHASSIS', 'shield')
    for j in d.get('jumpers') or []:      # strap points not otherwise named
        for e in (j.get('from'), j.get('to')):
            add(e, j['designation'], 'strap')
    return pins, os.path.relpath(p, HOME).replace(os.sep, '/')


def from_io(code):
    p = os.path.join(ENG, 'IO', code + '.pins.json')
    if not os.path.exists(p):
        return None, None
    d = json.load(open(p))
    pins = []
    for x in d.get('pins', []):
        k = x.get('kind') or 'other'
        if k == 'audio':
            k = 'out' if re.search(r'\bOUT', x.get('signal') or '', re.I) else 'in'
        pins.append({'connector': x.get('conn') or '', 'pin': str(x.get('pin')), 'signal': x.get('signal') or '', 'kind': k,
                     'port': x.get('pair'), 'polarity': x.get('pol')})
    return pins, os.path.relpath(p, HOME).replace(os.sep, '/')


def merge(pins):
    """One reading per (connector, pin): a named signal over NC / unread, then the surer reading."""
    best = {}
    for p in pins:
        k = (p.get('connector') or '', str(p.get('pin')))
        score = (p.get('kind') not in ('nc', 'unread'), p.get('kind') != 'strap', CONF.get(p.get('confidence'), 3))
        if k not in best or score > best[k][0]:
            best[k] = (score, p)
    return [v[1] for v in best.values()]


def module_data(code, cat, repo):
    """(RTO.json dict to keep in the repo, changed?) — None when nothing about the module's pins is known."""
    path = os.path.join(repo, 'RTO.json')
    cur = json.load(open(path)) if os.path.exists(path) else None
    if cur and cur.get('connectors') and all(p.get('connector') is not None for p in cur.get('pins', [])):
        return cur, False          # pinout_build's reading of the pictures: kept
    sheet, sheet_src = from_sheet(code)
    io, io_src = from_io(code)
    if not sheet and cur and cur.get('variant_of'):
        sheet, sheet_src = from_sheet(cur['variant_of'])
    pins = sheet or io
    if not pins and cur and cur.get('pins'):
        # an older reading with no connectors: one connector named in "contacts" is assumed when every pin number is unique
        names = re.findall(r'\((\w+)\)', cur.get('contacts') or '')
        nums = [str(p.get('pin')) for p in cur['pins'] if p.get('kind') not in ('nc',)]
        conn = names[0] if len(set(names)) == 1 else ''
        pins = [dict(p, connector=conn) for p in cur['pins']] if conn or len(nums) == len(set(nums)) else None
    if not pins:
        return None, False
    base = {k: v for k, v in (cur or {}).items() if k not in ('pins',)}
    base.setdefault('code', code)
    base['pins'] = sorted(merge(pins), key=lambda p: (p.get('connector') or '', len(str(p['pin'])) > 2, pin_order(p['pin'])))
    base['built_from'] = dict(base.get('built_from') or {}, synthesized=f'tools/symbol_synth.py in WBSps.ca from '
                              + ', '.join(x for x in (sheet_src if sheet else None, io_src if (io and not sheet) else None,
                                                     'the older RTO.json' if not sheet and not io else None) if x))
    return base, json.dumps(base, sort_keys=True) != json.dumps(cur, sort_keys=True)


def pin_order(n):
    n = str(n)
    return (0, int(n), '') if n.isdigit() else (1, 0, n)


# ---------------------------------------------------------------- 2. the layout ---------------------------------------------

def label(p):
    # KiCad draws a space in a pin name as '_': words are joined by '-', the polarity follows straight on (MIC-IN+)
    s = re.sub(r'[\s_]+', '-', str(p.get('signal') or '').strip().upper()).strip('-') or '?'
    s = re.sub(r'-?([+-]?\d+(?:\.\d+)?)-V$', r'\1V', s)
    pol = p.get('polarity')
    return f'{s}{pol}' if pol in ('+', '-') and not s.endswith(('+', '-')) else s


def layout(code, cat, data, title=''):
    """Everything the writers draw, in mm, y up (KiCad's sense): body, pins, texts, colours."""
    pins = data['pins']
    multi = len({p.get('connector') or '' for p in pins}) > 1
    num = lambda p: (f"{p['connector']}-{p['pin']}" if multi and p.get('connector') else str(p['pin']))
    sides = {'L': [], 'R': [], 'T': [], 'B': [], 'N': []}
    for p in pins:
        sides[SIDE.get(p.get('kind'), 'L')].append(p)

    def rows(ps):                  # grouped by port, + then -, a blank row between groups
        groups = {}
        for p in ps:
            groups.setdefault((p.get('kind'), p.get('port') or p.get('signal')), []).append(p)
        order = sorted(groups.values(), key=lambda g: (list(SIDE).index(g[0].get('kind')) if g[0].get('kind') in SIDE else 99,
                                                       pin_order(g[0]['pin'])))
        out = []
        for g in order:
            if out:
                out.append(None)
            g = sorted(g, key=lambda p: (p.get('polarity') != '+', pin_order(p['pin'])))
            if len(g) > 1 and len({label(p) for p in g}) == 1:     # the two legs of a pair read with no polarity: A, B …
                g = [dict(p, signal=f"{p.get('signal') or ''}-{chr(65 + i)}") for i, p in enumerate(g)]
            out += g
        return out
    L, R = rows(sides['L']), rows(sides['R'])
    T = sorted(sides['T'], key=lambda p: label(p)); B = sorted(sides['B'], key=lambda p: label(p))
    # dedupe names that repeat on one side (two COMMON pins stay, KiCad stacks nothing)
    lw = max([len(label(p)) for p in L if p] + [4]) * CH
    rw = max([len(label(p)) for p in R if p] + [4]) * CH
    th = max([len(label(p)) for p in T] + [0]) * CH
    bh = max([len(label(p)) for p in B] + [0]) * CH
    n_side = max(len(L), len(R), 1)
    W = max(lw + rw + 3 * G, (max(len(T), len(B)) + 1) * G, len(code) * 2.2 + 2 * G)
    W = math.ceil(W / (2 * G)) * 2 * G
    H = (n_side + 1) * G + (th + G if T else 0) + (bh + G if B else 0)
    H = math.ceil(H / (2 * G)) * 2 * G
    x0, x1, y0, y1 = -W / 2, W / 2, -H / 2, H / 2
    PL = 2 * G if max([len(num(p)) for p in pins] + [1]) < 5 else 3 * G      # long enough for its number to sit on it
    fill, line = CATEGORY_COLOURS.get(cat, ('#F4F2EC', '#444444'))
    out = {'code': code, 'cat': cat, 'title': title, 'fill': fill, 'line': line, 'body': (x0, y0, x1, y1), 'pins': [], 'texts': []}
    ytop = y1 - (th + G if T else 0) - G
    for side, ps, x, rot in (('L', L, x0 - PL, 0), ('R', R, x1 + PL, 180)):
        for i, p in enumerate(ps):
            if p:
                out['pins'].append({'x': x, 'y': round((ytop - i * G) / G) * G, 'rot': rot, 'len': PL, 'name': label(p), 'num': num(p),
                                    'etype': ETYPE.get(p.get('kind'), 'passive'), 'colour': PIN_COLOURS[COLOUR_OF.get(p.get('kind'), 'other')]})
    for side, ps, y, rot in (('T', T, y1 + PL, 270), ('B', B, y0 - PL, 90)):
        start = -(len(ps) - 1) / 2 * G
        for i, p in enumerate(ps):
            out['pins'].append({'x': round((start + i * G) / G) * G, 'y': y, 'rot': rot, 'len': PL, 'name': label(p), 'num': num(p),
                                'etype': ETYPE.get(p.get('kind'), 'passive'), 'colour': PIN_COLOURS[COLOUR_OF.get(p.get('kind'), 'other')]})
    for p in sides['N']:            # no-connects: kept for the footprint, hidden, under the body's corner
        out['pins'].append({'x': x1 - G, 'y': y0 + G, 'rot': 0, 'len': 0, 'name': label(p), 'num': num(p), 'etype': 'no_connect',
                            'colour': '#999999', 'hide': True})
    out['ref'] = (0, y1 + PL + (4 * CH if T else 0) + G)
    out['value'] = (0, y0 - PL - (4 * CH if B else 0) - G)
    out['connector'] = data.get('connector') or ''
    return out


# ---------------------------------------------------------------- 3. the writers --------------------------------------------

def rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def kicad_sym(lay, meta):
    x0, y0, x1, y1 = lay['body']
    f, l = rgb(lay['fill']), rgb(lay['line'])
    hid = lambda k, v: f'    (property {q(k)} {q(v)} (at 0 0 0) (effects (font (size 1.27 1.27)) hide))'
    props = [f'    (property "Reference" "U" (at {lay["ref"][0]:.2f} {lay["ref"][1]:.2f} 0) (effects (font (size 1.27 1.27))))',
             f'    (property "Value" {q(lay["code"])} (at {lay["value"][0]:.2f} {lay["value"][1]:.2f} 0) (effects (font (size 1.27 1.27))))',
             hid('Footprint', ''), hid('Datasheet', f'https://wbsps.ca/PAGES/{lay["code"]}.html'),
             hid('Description', meta['description']), hid('ki_keywords', f'Ward-Beck WBS {lay["cat"]} {lay["code"]}'),
             hid('Manufacturer', 'Ward-Beck Systems Ltd.'), hid('Category', lay['cat']), hid('Connector', lay['connector']),
             hid('Synthesized', meta['source'])]
    pins = []
    for p in lay['pins']:
        pins.append(f'      (pin {p["etype"]} line (at {p["x"]:.2f} {p["y"]:.2f} {p["rot"]}) (length {p["len"]:.2f}){" hide" if p.get("hide") else ""}'
                    f' (name {q(p["name"])} (effects (font (size 1.27 1.27)))) (number {q(p["num"])} (effects (font (size 1.27 1.27)))))')
    c = lay['code']
    return '\n'.join([
        f'(kicad_symbol_lib (version 20231120) (generator {q(GEN)}) (generator_version "1")',
        f'  (symbol {q(c)} (pin_names (offset 0.762)) (exclude_from_sim yes) (in_bom yes) (on_board yes)', *props,
        f'    (symbol {q(c + "_0_1")}',
        f'      (rectangle (start {x0:.2f} {y1:.2f}) (end {x1:.2f} {y0:.2f}) (stroke (width 0.254) (type default) (color {l[0]} {l[1]} {l[2]} 1))'
        f' (fill (type color) (color {f[0]} {f[1]} {f[2]} 1)))',
        '    )', f'    (symbol {q(c + "_1_1")}', *pins, '    )', '  )', ')', ''])


def pin_end(p):
    """(x, y) of the pin's connection point and of where it meets the body."""
    a = math.radians(p['rot'])
    return (p['x'], p['y']), (p['x'] + math.cos(a) * p['len'], p['y'] + math.sin(a) * p['len'])


def name_at(p):
    """Where the pin's name goes inside the body, its anchor and rotation (degrees, SVG sense: clockwise)."""
    (_, _), (bx, by) = pin_end(p)
    off = 0.762
    return {0: (bx + off, by, 'start', 0), 180: (bx - off, by, 'end', 0),
            270: (bx, by - off, 'end', -90), 90: (bx, by + off, 'start', -90)}[p['rot']]


def svg(lay, meta):
    x0, y0, x1, y1 = lay['body']
    pad = 4 * G
    minx = min([x0] + [p['x'] for p in lay['pins']]) - pad - 6 * CH
    maxx = max([x1] + [p['x'] for p in lay['pins']]) + pad + 6 * CH
    miny = min(y0, lay['value'][1]) - pad
    maxy = max(y1, lay['ref'][1]) + pad
    k = 10                              # px per mm
    X = lambda x: (x - minx) * k
    Y = lambda y: (maxy - y) * k
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {(maxx - minx) * k:.0f} {(maxy - miny) * k:.0f}" '
         f'font-family="Overpass Mono, ui-monospace, monospace">',
         f'<title>{xesc(lay["code"])}: {xesc(meta["description"])}</title>',
         f'<rect width="100%" height="100%" fill="#ffffff"/>',
         f'<rect x="{X(x0):.1f}" y="{Y(y1):.1f}" width="{(x1 - x0) * k:.1f}" height="{(y1 - y0) * k:.1f}" fill="{lay["fill"]}" '
         f'stroke="{lay["line"]}" stroke-width="2.5"/>']
    for p in lay['pins']:
        if p.get('hide'):
            continue
        (ax, ay), (bx, by) = pin_end(p)
        o.append(f'<line x1="{X(ax):.1f}" y1="{Y(ay):.1f}" x2="{X(bx):.1f}" y2="{Y(by):.1f}" stroke="{p["colour"]}" stroke-width="2"/>')
        o.append(f'<circle cx="{X(ax):.1f}" cy="{Y(ay):.1f}" r="3" fill="#fff" stroke="{p["colour"]}" stroke-width="1.5"/>')
        nx, ny, anchor, rot = name_at(p)
        o.append(f'<text x="{X(nx):.1f}" y="{Y(ny):.1f}" font-size="12.7" dominant-baseline="middle" text-anchor="{anchor}" fill="#1f1e1c"'
                 + (f' transform="rotate({rot} {X(nx):.1f} {Y(ny):.1f})"' if rot else '') + f'>{xesc(p["name"])}</text>')
        mx, my = (ax + bx) / 2, (ay + by) / 2
        if p['rot'] in (0, 180):
            o.append(f'<text x="{X(mx):.1f}" y="{Y(my) - 4:.1f}" font-size="10" text-anchor="middle" fill="{p["colour"]}">{xesc(p["num"])}</text>')
        else:
            o.append(f'<text x="{X(mx) - 4:.1f}" y="{Y(my):.1f}" font-size="10" text-anchor="middle" fill="{p["colour"]}" '
                     f'transform="rotate(-90 {X(mx) - 4:.1f} {Y(my):.1f})">{xesc(p["num"])}</text>')
    o.append(f'<text x="{X(lay["ref"][0]):.1f}" y="{Y(lay["ref"][1]):.1f}" font-size="14" font-weight="700" text-anchor="middle" fill="{lay["line"]}">'
             f'{xesc(lay["code"])}</text>')
    o.append(f'<text x="{X(lay["value"][0]):.1f}" y="{Y(lay["value"][1]):.1f}" font-size="11" text-anchor="middle" fill="#6d6a63">'
             f'{xesc(lay["cat"].title())}{" · " + xesc(lay["connector"]) if lay["connector"] else ""} · Ward-Beck Systems</text>')
    o.append('</svg>')
    return '\n'.join(o)


def dxf(lay, meta, path):
    import ezdxf
    from ezdxf.enums import TextEntityAlignment
    doc = ezdxf.new('R2010', setup=True)
    doc.header['$INSUNITS'] = 4      # mm
    msp = doc.modelspace()
    for name, colour in (('BODY', lay['line']), ('PIN_IN', PIN_COLOURS['in']), ('PIN_OUT', PIN_COLOURS['out']),
                         ('PIN_POWER', PIN_COLOURS['power']), ('PIN_GROUND', PIN_COLOURS['ground']), ('PIN_CONTROL', PIN_COLOURS['control']),
                         ('PIN_OTHER', PIN_COLOURS['other']), ('TEXT', '#1F1E1C'), ('FILL', lay['fill'])):
        doc.layers.add(name).rgb = rgb(colour)
    x0, y0, x1, y1 = lay['body']
    hatch = msp.add_hatch(dxfattribs={'layer': 'FILL'}); hatch.rgb = rgb(lay['fill'])
    hatch.paths.add_polyline_path([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], is_closed=True)
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={'layer': 'BODY', 'lineweight': 25})
    layer_of = {v: 'PIN_' + k.upper() for k, v in PIN_COLOURS.items()}
    al = {'start': TextEntityAlignment.MIDDLE_LEFT, 'end': TextEntityAlignment.MIDDLE_RIGHT}
    for p in lay['pins']:
        if p.get('hide'):
            continue
        (ax, ay), (bx, by) = pin_end(p)
        lyr = layer_of.get(p['colour'], 'PIN_OTHER')
        msp.add_line((ax, ay), (bx, by), dxfattribs={'layer': lyr})
        msp.add_circle((ax, ay), 0.3, dxfattribs={'layer': lyr})
        nx, ny, anchor, rot = name_at(p)
        t = msp.add_text(p['name'], height=1.27, rotation=-rot, dxfattribs={'layer': 'TEXT'})
        t.set_placement((nx, ny), align=al[anchor])
        mx, my = (ax + bx) / 2, (ay + by) / 2
        t = msp.add_text(p['num'], height=1.0, rotation=-rot if p['rot'] in (90, 270) else 0, dxfattribs={'layer': lyr})
        t.set_placement((mx, my + (0.5 if p['rot'] in (0, 180) else 0)), align=TextEntityAlignment.BOTTOM_CENTER)
    t = msp.add_text(lay['code'], height=1.8, dxfattribs={'layer': 'TEXT'}); t.set_placement(lay['ref'], align=TextEntityAlignment.MIDDLE_CENTER)
    t = msp.add_text(f'{lay["cat"].title()} - Ward-Beck Systems', height=1.2, dxfattribs={'layer': 'TEXT'})
    t.set_placement(lay['value'], align=TextEntityAlignment.MIDDLE_CENTER)
    doc.set_modelspace_vport(height=(y1 - y0) * 1.6, center=(0, 0))
    doc.saveas(path)


def page_box(lay):
    x0, y0, x1, y1 = lay['body']
    xs = [x0, x1] + [p['x'] for p in lay['pins'] if not p.get('hide')]
    ys = [y0, y1, lay['ref'][1], lay['value'][1]] + [p['y'] for p in lay['pins'] if not p.get('hide')]
    return min(xs) - 12 * CH, max(xs) + 12 * CH, min(ys) - 2 * G, max(ys) + 2 * G


def pptx(lay, meta, path):
    from pptx import Presentation
    from pptx.util import Mm, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    minx, maxx, miny, maxy = page_box(lay)
    prs = Presentation()
    SW, SH = (338.7, 190.5) if (maxx - minx) > (maxy - miny) else (190.5, 338.7)   # 16:9, turned upright for a tall symbol
    prs.slide_width, prs.slide_height = Mm(SW), Mm(SH)
    s = min((SW - 20) / (maxx - minx), (SH - 30) / (maxy - miny))      # mm on the slide per symbol mm
    ox, oy = (SW - (maxx - minx) * s) / 2, 14 + (SH - 30 - (maxy - miny) * s) / 2
    X = lambda x: Mm(ox + (x - minx) * s)
    Y = lambda y: Mm(oy + (maxy - y) * s)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    col = lambda h: RGBColor(*rgb(h))
    tb = slide.shapes.add_textbox(Mm(10), Mm(4), Mm(SW - 20), Mm(10))
    tp = tb.text_frame.paragraphs[0]; tp.text = f'{lay["code"]} · {meta["title"] or lay["cat"].title()}'
    tp.runs[0].font.size, tp.runs[0].font.bold, tp.runs[0].font.color.rgb = Pt(20), True, col(lay['line'])
    x0, y0, x1, y1 = lay['body']
    body = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, X(x0), Y(y1), Mm((x1 - x0) * s), Mm((y1 - y0) * s))
    body.fill.solid(); body.fill.fore_color.rgb = col(lay['fill'])
    body.line.color.rgb, body.line.width = col(lay['line']), Pt(2)
    body.shadow.inherit = False
    body.name = f'{lay["code"]} body'
    fs = max(6, min(14, 1.27 * s * 3.3))     # the KiCad font's 1.27 mm, in points on the slide
    def text(t, x, y, w, h, size, colour, align=PP_ALIGN.LEFT, rot=0, bold=False):
        b = slide.shapes.add_textbox(x, y, w, h)
        tf = b.text_frame; tf.word_wrap = False; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        for m in ('margin_left', 'margin_right', 'margin_top', 'margin_bottom'):
            setattr(tf, m, 0)
        p = tf.paragraphs[0]; p.text = t; p.alignment = align
        p.runs[0].font.size, p.runs[0].font.color.rgb, p.runs[0].font.bold = Pt(size), col(colour), bold
        p.runs[0].font.name = 'Consolas'
        b.rotation = rot
        return b
    for p in lay['pins']:
        if p.get('hide'):
            continue
        (ax, ay), (bx, by) = pin_end(p)
        ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, X(ax), Y(ay), X(bx), Y(by))
        ln.line.color.rgb, ln.line.width = col(p['colour']), Pt(1.5)
        ln.name = f'pin {p["num"]} {p["name"]}'
        nx, ny, anchor, rot = name_at(p)
        tw = Mm(len(p['name']) * CH * s * 1.15 + 2)
        th = Mm(2.2 * s)
        if rot == 0:
            left = X(nx) if anchor == 'start' else X(nx) - tw
            text(p['name'], left, Y(ny) - th // 2, tw, th, fs, '#1F1E1C', PP_ALIGN.LEFT if anchor == 'start' else PP_ALIGN.RIGHT)
            text(p['num'], X(min(ax, bx)), Y(ay) - th, Mm(abs(bx - ax) * s), th, fs * .8, p['colour'], PP_ALIGN.CENTER)
        else:   # a vertical name: a box laid along the pin, turned a quarter
            cx, cy = X(nx), (Y(ny) + tw // 2 if anchor == 'end' else Y(ny) - tw // 2)
            text(p['name'], cx - tw // 2, cy - th // 2, tw, th, fs, '#1F1E1C',
                 PP_ALIGN.RIGHT if anchor == 'end' else PP_ALIGN.LEFT, rot=270)
    text(f'{lay["cat"].title()}{" · " + lay["connector"] if lay["connector"] else ""} · synthesized from RTO.json',
         Mm(10), Mm(SH - 12), Mm(SW - 20), Mm(8), 10, '#6D6A63', PP_ALIGN.CENTER)
    prs.core_properties.title = f'{lay["code"]} symbol'
    prs.core_properties.author = 'Ward-Beck Systems'
    prs.save(path)


def vsdx(lay, meta, path):
    """A Visio drawing (one page) written by hand: the OPC parts Visio 2013+ and LibreOffice read."""
    IN = 25.4
    minx, maxx, miny, maxy = page_box(lay)
    pw, ph = (maxx - minx) / IN, (maxy - miny) / IN + 0.6
    X = lambda x: (x - minx) / IN
    Y = lambda y: (y - miny) / IN
    NS = 'xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    shapes, sid = [], [0]
    def cells(**c):
        return ''.join(f'<Cell N="{k}" V="{v}"/>' for k, v in c.items())
    def shape(x, y, w, h, geom, text='', fill=None, line='#000000', weight=0.01, size=0.1, colour='#1F1E1C', align=0, angle=0, nofill=True, name=''):
        sid[0] += 1
        g = ''.join(f'<Row T="{t}" IX="{i + 1}"><Cell N="X" V="{gx}"/><Cell N="Y" V="{gy}"/></Row>' for i, (t, gx, gy) in enumerate(geom))
        f = cells(FillForegnd=fill, FillPattern=1) if fill else cells(FillPattern=0)
        txt = (f'<Section N="Character"><Row IX="0"><Cell N="Size" V="{size}" U="IN"/><Cell N="Color" V="{colour}"/><Cell N="Font" V="Consolas"/></Row></Section>'
               f'<Section N="Paragraph"><Row IX="0"><Cell N="HorzAlign" V="{align}"/></Row></Section><Text>{xesc(text)}</Text>') if text else ''
        shapes.append(f'<Shape ID="{sid[0]}" NameU="{xesc(name or "Shape" + str(sid[0]))}" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">'
                      + cells(PinX=f'{x + w / 2:.4f}', PinY=f'{y + h / 2:.4f}', Width=f'{w:.4f}', Height=f'{h:.4f}', LocPinX=f'{w / 2:.4f}',
                              LocPinY=f'{h / 2:.4f}', Angle=f'{angle:.6f}', LineColor=line, LineWeight=f'{weight}', VerticalAlign=1,
                              LeftMargin=0, RightMargin=0, TopMargin=0, BottomMargin=0)
                      + f + (f'<Section N="Geometry" IX="0">{cells(NoFill=1 if nofill else 0, NoLine=0 if geom else 1)}{g}</Section>' if geom else
                             f'<Section N="Geometry" IX="0">{cells(NoFill=1, NoLine=1)}</Section>') + txt + '</Shape>')
    x0, y0, x1, y1 = lay['body']
    w, h = (x1 - x0) / IN, (y1 - y0) / IN
    shape(X(x0), Y(y0), w, h, [('MoveTo', 0, 0), ('LineTo', w, 0), ('LineTo', w, h), ('LineTo', 0, h), ('LineTo', 0, 0)],
          fill=lay['fill'], line=lay['line'], weight=0.02, nofill=False, name=f'{lay["code"]} body')
    fs = 0.075                                   # inches: the KiCad font's 1.27 mm as Visio draws Consolas
    for p in lay['pins']:
        if p.get('hide'):
            continue
        (ax, ay), (bx, by) = pin_end(p)
        lx, ly, ww, hh = min(X(ax), X(bx)), min(Y(ay), Y(by)), abs(X(bx) - X(ax)) or 0.0001, abs(Y(by) - Y(ay)) or 0.0001
        geom = [('MoveTo', X(ax) - lx, Y(ay) - ly), ('LineTo', X(bx) - lx, Y(by) - ly)]
        shape(lx, ly, ww, hh, geom, line=p['colour'], weight=0.014, name=f'pin {p["num"]}')
        nx, ny, anchor, rot = name_at(p)
        tw, th = len(p['name']) * CH / IN * 1.1 + 0.05, 0.09
        if rot == 0:
            left = X(nx) if anchor == 'start' else X(nx) - tw
            shape(left, Y(ny) - th / 2, tw, th, [], p['name'], align=0 if anchor == 'start' else 2, size=fs)
            shape(lx, Y(ay) + 0.005, abs(X(bx) - X(ax)), th, [], p['num'], size=fs * .8, colour=p['colour'], align=1)
        else:
            cy = Y(ny) - tw / 2 if anchor == 'end' else Y(ny) + tw / 2
            shape(X(nx) - tw / 2, cy - th / 2, tw, th, [], p['name'], align=2 if anchor == 'end' else 0, size=fs, angle=math.pi / 2)
    shape(X(lay['ref'][0]) - 1, Y(lay['ref'][1]) - 0.1, 2, 0.2, [], lay['code'], size=0.09, colour=lay['line'], align=1)
    shape(X(lay['value'][0]) - 2, Y(lay['value'][1]) - 0.08, 4, 0.16, [], f'{lay["cat"].title()} · Ward-Beck Systems', size=0.06,
          colour='#6D6A63', align=1)
    parts = {
        '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>'
            '<Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>'
            '<Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>',
        '_rels/.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/document" Target="visio/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>',
        'docProps/core.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            f'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{xesc(lay["code"])} symbol</dc:title><dc:creator>Ward-Beck Systems</dc:creator></cp:coreProperties>',
        'docProps/app.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
            '<Application>Microsoft Visio</Application></Properties>',
        'visio/document.xml': f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><VisioDocument {NS}><DocumentSettings/><Colors/><FaceNames/>'
            '<StyleSheets><StyleSheet ID="0" NameU="No Style" Name="No Style">' + cells(LineWeight=0.01, LineColor='#000000', LinePattern=1,
            FillForegnd='#FFFFFF', FillPattern=1, VerticalAlign=1) + '<Section N="Character"><Row IX="0"><Cell N="Size" V="0.1"/><Cell N="Color" V="#000000"/>'
            '</Row></Section></StyleSheet></StyleSheets></VisioDocument>',
        'visio/_rels/document.xml.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/pages" Target="pages/pages.xml"/></Relationships>',
        'visio/pages/pages.xml': f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Pages {NS}><Page ID="0" NameU="{xesc(lay["code"])}" Name="{xesc(lay["code"])}">'
            f'<PageSheet>{cells(PageWidth=f"{pw:.4f}", PageHeight=f"{ph:.4f}", PageScale=1, DrawingScale=1)}</PageSheet><Rel r:id="rId1"/></Page></Pages>',
        'visio/pages/_rels/pages.xml.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/page" Target="page1.xml"/></Relationships>',
        'visio/pages/page1.xml': f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><PageContents {NS}><Shapes>{"".join(shapes)}</Shapes></PageContents>',
    }
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)), data)


# ---------------------------------------------------------------- run --------------------------------------------------------

def title_of(repo, code):
    m = re.match(r'^MODULES\.[^.]+\.' + re.escape(code) + r'-(.+)$', os.path.basename(repo))
    return m.group(1).replace('-', ' ') if m else ''


OUTPUTS = ('{c}.kicad_sym', '{c}-symbol.svg', '{c}-symbol.dxf', '{c}-symbol.pptx', '{c}-symbol.vsdx')


def synth_one(code, cat, repo, data):
    """Every symbol output of one module into its KICAD/ folder, from its RTO.json (data). tools/pinout_build.py calls it too."""
    title = title_of(repo, code)
    lay = layout(code, cat, data, title)
    src = (data.get('built_from') or {}).get('synthesized') or 'tools/pinout_build.py, from the pinout pictures'
    meta = {'title': title, 'source': f'synthesized by tools/symbol_synth.py (WBSps.ca) from this repository\'s RTO.json ({src})',
            'description': f'{code} {title} ({cat.title()}), Ward-Beck Systems. Pinout from RTO.json.'}
    kd = os.path.join(repo, 'KICAD'); os.makedirs(kd, exist_ok=True)
    paths = [os.path.join(kd, o.format(c=code)) for o in OUTPUTS]
    for p in paths:   # a hard link (or symlink) into Engineering: this module's own file from now on
        if os.path.islink(p) or (os.path.exists(p) and os.stat(p).st_nlink > 1):
            os.unlink(p)
    open(paths[0], 'w').write(kicad_sym(lay, meta))
    open(paths[1], 'w').write(svg(lay, meta))
    dxf(lay, meta, paths[2]); pptx(lay, meta, paths[3]); vsdx(lay, meta, paths[4])
    return paths


def category_of(repo):
    m = re.match(r'^MODULES\.([A-Z0-9-]+)\.', os.path.basename(os.path.normpath(repo)))
    return m.group(1) if m else 'UNSORTED'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    check, data_only = '--check' in sys.argv, '--data-only' in sys.argv
    done, nodata, data_changed = [], [], []
    for code, cat, repo in modules():
        if args and code not in args:
            continue
        data, changed = module_data(code, cat, repo)
        if not data:
            nodata.append(code); continue
        if changed:
            data_changed.append(code)
            if not check:
                with open(os.path.join(repo, 'RTO.json'), 'w') as fh:
                    json.dump(data, fh, indent=1, ensure_ascii=False); fh.write('\n')
        if data_only or check:
            done.append(code); continue
        synth_one(code, cat, repo, data)
        done.append(code)
    print(f'{len(done)} modules synthesized{" (data only)" if data_only else ""}{" (check: nothing written)" if check else ""}; '
          f'RTO.json filled in {len(data_changed)}; no pinout read anywhere for {len(nodata)}')
    if nodata:
        print('  no pinout data:', ' '.join(nodata))


if __name__ == '__main__':
    main()
