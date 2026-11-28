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

     KICAD/<M>.kicad_sym          the KiCad symbol (KiCad 8 and later)
     KICAD/<M>.pptx               beside it, a PowerPoint deck: the symbol, the front panel, the back panel (every shape editable)
     KICAD/<M>.vsdx               the same three pages for Visio
     KICAD/<M>-symbol.svg         the symbol as a picture (the site, the README); <M>-symbol.dxf for CAD (layers per kind of pin)
     KICAD/<M>-front-panel.svg    the best front panel the archive has (tools/make_panels.py: panel art, traced drawing, layout,
                                  photo), when there is one
     KICAD/<M>-back-panel.svg     the connectors as seen from the rear, every contact with its signal, coloured by kind: what
                                  to wire to

Every output says it was synthesized and from what; edit RTO.json (or the readings it is made from), never the outputs.
--check: report what would change, write nothing. A module with no pinout read anywhere gets no symbol (listed).
"""
import json, math, os, re, sys
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


def symbol_page(lay):
    """The symbol as page primitives (tools/symbol_sheets.py)."""
    x0, y0, x1, y1 = lay['body']
    P = [('rect', x0, y0, x1, y1, lay['fill'], lay['line'], 0.3, f'{lay["code"]} body')]
    for p in lay['pins']:
        if p.get('hide'):
            continue
        (ax, ay), (bx, by) = pin_end(p)
        P.append(('line', ax, ay, bx, by, p['colour'], 0.25, f'pin {p["num"]} {p["name"]}'))
        P.append(('circle', ax, ay, 0.35, '#ffffff', p['colour'], 0.15))
        nx, ny, anchor, rot = name_at(p)
        P.append(('text', nx, ny, p['name'], 1.7, '#1F1E1C', anchor, -rot, False))
        mx, my = (ax + bx) / 2, (ay + by) / 2
        P.append(('text', mx, my + 0.9, p['num'], 1.3, p['colour'], 'middle', 0, False) if p['rot'] in (0, 180)
                 else ('text', mx - 0.9, my, p['num'], 1.3, p['colour'], 'middle', 90, False))
    P.append(('text', lay['ref'][0], lay['ref'][1], lay['code'], 2.6, lay['line'], 'middle', 0, True))
    P.append(('text', lay['value'][0], lay['value'][1], f'{lay["cat"].title()}{" · " + lay["connector"] if lay["connector"] else ""}'
              ' · Ward-Beck Systems', 1.6, '#6D6A63', 'middle', 0, False))
    return P


EDGE = 'ABCDEFHJKLMNPRSTUVWXYZ'      # the letter side of a Ward-Beck edge connector (no G, I, O, Q): A is opposite 1


def back_page(lay, data):
    """The back panel: each connector as seen from the rear, every contact with its signal, coloured by kind — what to wire."""
    by_conn = {}
    for p in data['pins']:
        by_conn.setdefault(p.get('connector') or '', []).append(p)
    P, x, pitch = [], 0, 3.96
    for conn in sorted(by_conn, key=lambda c: (c == '', c)):
        pins = by_conn[conn]
        rows = {}
        for p in pins:
            n = str(p['pin'])
            if n.isdigit():
                rows.setdefault(int(n), [None, None])[0] = p
            elif n.upper() in EDGE:
                rows.setdefault(EDGE.index(n.upper()) + 1, [None, None])[1] = p
            else:
                rows.setdefault(1000 + len(rows), [None, None])[0] = p
        nrow = max(rows) if rows and max(rows) < 1000 else len(rows)
        lw = max([len(label(p)) for r in rows.values() for p in r if p] + [6]) * 1.7 * 0.6
        cx = x + lw + 12
        top = (nrow + 1) * pitch / 2
        P.append(('text', cx, top + 6, f'{conn or "Connector"} · rear view', 2.2, '#1F1E1C', 'middle', 0, True))
        P.append(('rect', cx - 7, -top - 1, cx + 7, top + 1, '#E9E4D4', '#6D6A63', 0.3, f'{conn} edge'))
        for i, r in enumerate(sorted(rows)):
            y = top - (i + 1) * pitch if max(rows) >= 1000 else top - r * pitch
            for side, p in zip((-1, 1), rows[r]):
                padx0, padx1 = (cx - 6, cx - 0.6) if side < 0 else (cx + 0.6, cx + 6)
                kind = COLOUR_OF.get((p or {}).get('kind'), 'other') if p and p.get('kind') not in ('nc', 'unread') else None
                fill = PIN_COLOURS[kind] if kind else '#FFFFFF'
                P.append(('rect', padx0, y - 1.4, padx1, y + 1.4, fill, '#6D6A63', 0.15, f'{conn}-{p["pin"] if p else ""}'))
                pin_name = (str(r) if side < 0 else (EDGE[r - 1] if r <= len(EDGE) else '')) if max(rows) < 1000 else str((p or {}).get('pin', ''))
                P.append(('text', (padx0 + padx1) / 2, y, pin_name, 1.5, '#FFFFFF' if kind else '#6D6A63', 'middle', 0, True))
                if p:
                    t = label(p) if p.get('kind') not in ('nc',) else 'N/C'
                    P.append(('text', padx0 - 1.2 if side < 0 else padx1 + 1.2, y, t, 1.7,
                              PIN_COLOURS[kind] if kind else '#999999', 'end' if side < 0 else 'start', 0, False))
        x = cx + 7 + lw + 14
    legend = [('input', 'in'), ('output', 'out'), ('power', 'power'), ('ground / shield', 'ground'), ('control', 'control'), ('other', 'other')]
    y0 = min(pp[2] for pp in P if pp[0] == 'rect') - 6
    for i, (t, k) in enumerate(legend):
        P.append(('rect', i * 24, y0 - 1.2, i * 24 + 2.4, y0 + 1.2, PIN_COLOURS[k], None, 0, ''))
        P.append(('text', i * 24 + 3.4, y0, t, 1.6, '#1F1E1C', 'start', 0, False))
    return P


def front_page(repo, code, work):
    """The front panel: the best picture of the module's face the archive has (tools/make_panels.py), or None."""
    src = os.path.join(repo, 'MECHANICAL', f'{code} - front panel.svg')
    if not os.path.exists(src):
        return None, None, None
    head = open(src, encoding='utf-8', errors='replace').read(2000)
    kind = (re.search(r'data-kind="([a-z]+)"', head) or [None, ''])[1]
    if kind in ('', 'none'):
        return None, None, None
    frm = (re.search(r'data-from="([^"]*)"', head) or [None, ''])[1]
    vb = [float(v) for v in (re.search(r'viewBox="([-\d. ]+)"', head) or [None, '0 0 100 600'])[1].split()]
    png = os.path.join(work, f'{code}-front.png')
    import subprocess
    subprocess.run(['inkscape', src, '--export-type=png', f'--export-filename={png}', '--export-height=2400',
                    '--export-background=#ffffff', '--export-background-opacity=1'], capture_output=True, timeout=180,
                   env={'HOME': os.environ.get('HOME', '/tmp'), 'PATH': '/usr/bin:/bin'})   # clean: a snap's libraries break it
    if not os.path.exists(png):
        return None, None, None
    H = 200.0
    W = H * vb[2] / vb[3]
    how = {'cad': 'the panel art', 'traced': 'a traced front-panel drawing', 'layout': 'the module layout drawing',
           'drawing': 'a front-panel drawing', 'photo': 'a photograph, squared up'}.get(kind, kind)
    P = [('image', png, -W / 2, -H / 2, W / 2, H / 2, f'{code} front panel'),
         ('rect', -W / 2, -H / 2, W / 2, H / 2, None, '#6D6A63', 0.3, 'outline'),
         ('text', 0, -H / 2 - 5, f'from {how}: {os.path.basename(frm)}'[:110], 1.8, '#6D6A63', 'middle', 0, False)]
    return P, src, kind


# ---------------------------------------------------------------- run --------------------------------------------------------

def title_of(repo, code):
    m = re.match(r'^MODULES\.[^.]+\.' + re.escape(code) + r'-(.+)$', os.path.basename(repo))
    return m.group(1).replace('-', ' ') if m else ''


OUTPUTS = ('{c}.kicad_sym', '{c}.pptx', '{c}.vsdx', '{c}-symbol.svg', '{c}-symbol.dxf', '{c}-front-panel.svg', '{c}-back-panel.svg')
OLD = ('{c}-symbol.pptx', '{c}-symbol.vsdx')       # the first outputs, folded into <M>.pptx / <M>.vsdx


def synth_one(code, cat, repo, data):
    """Every drawing of one module into its KICAD/ folder, from its RTO.json (data): the KiCad symbol, and beside it the same
    symbol with the module's front and back panels as a PowerPoint deck, a Visio document and SVGs, and the symbol as DXF.
    tools/pinout_build.py calls it too."""
    import shutil, tempfile
    import symbol_sheets as sh
    title = title_of(repo, code)
    lay = layout(code, cat, data, title)
    src = (data.get('built_from') or {}).get('synthesized') or 'tools/pinout_build.py, from the pinout pictures'
    meta = {'title': title, 'source': f'synthesized by tools/symbol_synth.py (WBSps.ca) from this repository\'s RTO.json ({src})',
            'description': f'{code} {title} ({cat.title()}), Ward-Beck Systems. Pinout from RTO.json.'}
    kd = os.path.join(repo, 'KICAD'); os.makedirs(kd, exist_ok=True)
    out = {o: os.path.join(kd, o.format(c=code)) for o in OUTPUTS}
    for p in list(out.values()) + [os.path.join(kd, o.format(c=code)) for o in OLD]:
        if os.path.islink(p) or (os.path.exists(p) and os.stat(p).st_nlink > 1) or any(p.endswith(o.format(c=code)) for o in OLD):
            if os.path.lexists(p):
                os.unlink(p)    # a link into Engineering becomes this module's own file; the first outputs' names go
    name = f'{code} {title}'.strip()
    foot = f'{code} · {cat.title()} · Ward-Beck Systems · synthesized from RTO.json'
    with tempfile.TemporaryDirectory() as work:
        sym = symbol_page(lay)
        back = back_page(lay, data)
        front, front_src, _ = front_page(repo, code, work)
        pages = [(f'{name} · symbol', sym)] + ([(f'{code} · front panel', front)] if front else []) + [(f'{code} · back panel: the connectors, rear view', back)]
        open(out['{c}.kicad_sym'], 'w').write(kicad_sym(lay, meta))
        sh.pptx(pages, out['{c}.pptx'], f'{code} symbol and panels', foot)
        sh.vsdx(pages, out['{c}.vsdx'], f'{code} symbol and panels')
        open(out['{c}-symbol.svg'], 'w').write(sh.svg(sym, f'{name}: symbol'))
        open(out['{c}-back-panel.svg'], 'w').write(sh.svg(back, f'{name}: back panel, rear view of the connectors'))
        if front_src:
            shutil.copyfile(front_src, out['{c}-front-panel.svg'])
        elif os.path.exists(out['{c}-front-panel.svg']):
            os.unlink(out['{c}-front-panel.svg'])
        dxf(lay, meta, out['{c}-symbol.dxf'])
    return [p for p in out.values() if os.path.exists(p)]


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
