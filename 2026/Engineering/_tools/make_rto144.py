"""RTO-144 connection sheets for every module in the jumper calculator.

Usage: python3 make_rto144.py <jumper calculator .xlsx> <output folder> [--pdf]

For each module row in the Database tab this writes <output>/<CODE>/:
  <CODE> - RTO-144 Connections.html   drawing sheet: rear connector, I/O diagram, tables
  <CODE> - RTO-144 Connections.pdf    the same, printed (with --pdf, needs google-chrome)
  connector.svg, io.svg               the two drawings on their own
  <CODE>.rto144.json / .yaml / .md    the data
and <output>/index.html listing all modules.
"""
import datetime, html, json, os, re, subprocess, sys

from urllib.parse import quote

import openpyxl
import yaml

XLSX, OUT = sys.argv[1], os.path.abspath(sys.argv[2])
PDF = '--pdf' in sys.argv
LETTERS = list('ABCDEFHJKLMNPRSTUVWXYZ')  # edge-connector letters: no G, I, O, Q
e = html.escape

# ---------------------------------------------------------------- read the sheet

rows = list(openpyxl.load_workbook(XLSX, read_only=True, data_only=True)['Database'].iter_rows(values_only=True))
BUS_NAMES = [rows[5][52 + 3 * k] for k in range(20)]


def pin(v):
    """'P2-19' -> ('P2', '19'); 1.0 -> ('', '1'); 'y' -> ('', 'Y')"""
    if v is None or v == '':
        return None
    if isinstance(v, float):
        v = int(v)
    s = str(v).strip().upper()
    m = re.match(r'^(P\d+)-(.+)$', s)
    return (m.group(1), m.group(2)) if m else ('', s)


def num(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def direction(name):
    n = name.upper()
    if re.search(r'\b(IN|INPUT|RETURN|RTN)\b|MIC|LINE.?IN|-IN\b', n):
        return 'in'
    if re.search(r'OUT|SEND', n):
        return 'out'
    return 'io'


def parse(r):
    mod = {'code': r[0], 'series': r[1], 'type': r[2], 'row_count': num(r[4]),
           'impedance': {k: num(v) for k, v in (('line_in', r[5]), ('mic_in', r[6]), ('out', r[7])) if v},
           'note': r[9], 'audio': [], 'bus_out': [], 'bus_in': [], 'power': [], 'jumpers': [], 'logic': []}
    for side, start in (('A', 11), ('B', 32)):
        for k in range(4):
            b = start + 5 * k
            if r[b]:
                mod['audio'].append({'port': f'{side}{k + 1}', 'signal': str(r[b]), 'dir': direction(str(r[b])),
                                     'pos': pin(r[b + 1]), 'neg': pin(r[b + 2]), 'pad_pos': r[b + 3], 'pad_neg': r[b + 4]})
    for key, start in (('bus_out', 52), ('bus_in', 112)):
        for k in range(20):
            b = start + 3 * k
            if r[b] or r[b + 1]:
                mod[key].append({'bus': BUS_NAMES[k], 'signal': str(r[b] or BUS_NAMES[k]),
                                 'pos': pin(r[b + 1]), 'neg': pin(r[b + 2])})
    if r[173] is not None:
        mod['chassis'] = pin(r[173])
    for b in (175, 183, 191, 199, 207, 215):
        if r[b] and (r[b + 2] is not None or r[b + 4] is not None):
            mod['power'].append({'rail': r[b], 'style': r[b + 1], 'volts': num(r[b + 2]), 'max_a': num(r[b + 3]),
                                 'supply': pin(r[b + 4]), 'ground': pin(r[b + 5]), 'link': num(r[b + 6])})
    for b in range(223, 259, 4):
        if r[b + 2] or r[b + 3]:
            mod['jumpers'].append({'function': r[b], 'designation': r[b + 1], 'from': pin(r[b + 2]), 'to': pin(r[b + 3])})
    if r[261] is not None:
        mod['logic'].append({'signal': r[260], 'pin': pin(r[261])})
    attach_bare_pins(mod)
    return mod


def attach_bare_pins(mod):
    """A module with P1-/P2- pins sometimes lists a ground or chassis pin without the prefix;
    put it on its supply's connector, else on the most used connector."""
    used = [p[0] for a in mod['audio'] for p in (a['pos'], a['neg']) if p]
    used += [p[0] for x in mod['power'] for p in (x['supply'], x['ground']) if p]
    named = [c for c in used if c]
    if not named:
        return
    main = max(set(named), key=named.count)
    fix = lambda p, home=main: (home, p[1]) if p and not p[0] else p
    for x in mod['power']:
        home = x['supply'][0] if x['supply'] and x['supply'][0] else main
        x['supply'], x['ground'] = fix(x['supply']), fix(x['ground'], home)
    for a in mod['audio']:
        a['pos'], a['neg'] = fix(a['pos']), fix(a['neg'])
    for key in ('bus_out', 'bus_in'):
        for b in mod[key]:
            b['pos'], b['neg'] = fix(b['pos']), fix(b['neg'])
    for j in mod['jumpers']:
        j['from'], j['to'] = fix(j['from']), fix(j['to'])
    if mod.get('chassis'):
        mod['chassis'] = fix(mod['chassis'])


modules, seen = {}, set()
for r in rows[6:]:
    if not r[0] or not isinstance(r[0], str) or not re.match(r'^[A-Z]{1,3}\d', r[0].strip()):
        continue  # blank, header or note rows
    key = tuple(r)
    if key in seen:  # exact duplicate rows
        continue
    seen.add(key)
    code = r[0].strip()
    while code in modules:
        code += "'"
    modules[code] = parse(r)

# Pinouts read from the original drawings replace the calculator row (rto144_verified.yaml).
VERIFIED = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rto144_verified.yaml')))
for code, v in VERIFIED.items():
    pp = lambda x: pin(x) if x is not None else None
    modules[code] = {
        'code': code, 'series': (modules.get(code) or {}).get('series'), 'type': v['type'], 'row_count': v['row_count'],
        'impedance': {}, 'note': None, 'connector': v.get('connector'), 'verified': v['source'],
        'audio': [{'port': a['port'], 'signal': a['signal'], 'dir': a['dir'], 'pos': pp(a.get('pos')), 'neg': pp(a.get('neg')),
                   'pad_pos': None, 'pad_neg': None, 'note': a.get('note')} for a in v.get('audio', [])],
        'bus_out': [], 'bus_in': [],
        'power': [{'rail': x['rail'], 'style': None, 'volts': x['volts'], 'max_a': None, 'supply': pp(x['supply']),
                   'ground': pp(x.get('ground')), 'link': None} for x in v.get('power', [])],
        'jumpers': [{'function': j['function'], 'designation': j['designation'], 'from': pp(j['from']), 'to': pp(j['to'])}
                    for j in v.get('jumpers', [])],
        'logic': [],
        'other': [{'signal': o['signal'], 'role': o['role'], 'pins': [pin(x) for x in o['pins']]} for o in v.get('other', [])]}

# Rows that only carry the calculator's 44-contact P2 power/jumper template (no audio) are placeholders.
TEMPLATE = {'JMP.Z.W', 'JMP.X.18', 'JMP.Y.21', 'JMP.3', 'JMP.22.21', 'JMP.Z.Y', 'JMP.20.19', 'JMP.X.W'}
for m in modules.values():
    jset = {str(j['designation']).strip().replace('JMP.20.18', 'JMP.3') for j in m['jumpers']}  # the same 20-18 link
    if not m.get('verified') and not m['audio'] and jset == TEMPLATE:
        m['unverified'] = ('Placeholder data: this row of the jumper calculator holds only the 44-contact P2 power and '
                           'jumper template, with no audio connections. Not checked against a drawing; do not wire from it.')

# ---------------------------------------------------------------- pin roles

ROLE_STYLE = {'in': ('#2a5ea0', 'Input'), 'out': ('#a3352b', 'Output'), 'io': ('#6b4f8a', 'Input / output'),
              'bus': ('#2f6b45', 'Bus'), 'power': ('#b06d12', 'Power'), 'ground': ('#1c1c1c', 'Ground / chassis'),
              'jumper': ('#4f7f8a', 'Jumper'), 'logic': ('#6b6b2f', 'Logic'), 'nc': ('#9a978c', 'Not connected')}


def pin_roles(m):
    roles = {}

    def add(p, role, label):
        if p:
            roles.setdefault(p, []).append((role, label))
    for a in m['audio']:
        add(a['pos'], a['dir'], f"{a['signal']} +")
        add(a['neg'], a['dir'], f"{a['signal']} −")
    for b in m['bus_out'] + m['bus_in']:
        add(b['pos'], 'bus', f"{b['bus']} +")
        add(b['neg'], 'bus', f"{b['bus']} −")
    for p in m['power']:
        add(p['supply'], 'power', f"{p['rail']} {p['volts']:+}V" if isinstance(p['volts'], (int, float)) else p['rail'])
        add(p['ground'], 'ground', f"{p['rail']} GND")
    add(m.get('chassis'), 'ground', 'CHASSIS')
    for j in m['jumpers']:  # only label a jumper on pins that carry nothing else
        for p in (j['from'], j['to']):
            if p and p not in roles:
                add(p, 'jumper', j['designation'] or 'JMP')
    for g in m['logic']:
        add(g['pin'], 'logic', str(g['signal']))
    for o in m.get('other', []):
        for p in o['pins']:
            add(p, o['role'], o['signal'])
    return roles


def connectors(m, roles):
    """[(name, rows)] where rows is [[pin ids top], [pin ids bottom]] or [[pin ids]]"""
    out = []
    for c in sorted({p[0] for p in roles}):
        pins = [p[1] for p in roles if p[0] == c]
        lettered = any(not p.isdigit() for p in pins)
        rc = m['row_count'] if isinstance(m['row_count'], int) else None
        if rc and rc < 44 and (lettered or max(int(p) for p in pins if p.isdigit()) > rc if pins else False):
            print(f"warning: {m['code']}: pins {sorted(pins)} do not fit a {rc}-contact connector", file=sys.stderr)
        if lettered or rc == 44:
            out.append((c, [[str(i) for i in range(1, 23)], LETTERS]))
        else:
            n = max([m['row_count'] if isinstance(m['row_count'], int) else 0] + [int(p) for p in pins])
            out.append((c, [[str(i) for i in range(1, n + 1)]]))
    return out

# ---------------------------------------------------------------- drawings


def svg_connector(m, roles):
    """Rear view of the card edge: numbered side on top, lettered side below, leaders to each used pin."""
    conns = connectors(m, roles)
    W, finger, gap = 1100, 38, 8
    parts, y = [], 20
    for name, prow in conns:
        n = len(prow[0])
        x0 = (W - n * (finger + gap)) / 2
        lab_h = 175
        top = y + lab_h
        board_h = 70 if len(prow) == 2 else 44
        title = f'{name} — ' if name else ''
        size = f'{len(prow) * n} CONTACTS' if len(prow) == 2 or isinstance(m['row_count'], int) else f'CONTACTS 1-{n} SHOWN'
        parts.append(f'<text x="{W / 2}" y="{y + 4}" class="h" text-anchor="middle">{e(title)}REAR VIEW · CARD EDGE · {size}</text>')
        # board and edge
        parts.append(f'<rect x="{x0 - 30}" y="{top}" width="{n * (finger + gap) + 52}" height="{board_h}" class="board"/>')
        for ri, row in enumerate(prow):
            fy = top + 6 if ri == 0 else top + board_h - 30
            for i, p in enumerate(row):
                fx = x0 + i * (finger + gap)
                rl = roles.get((name, p))
                color = ROLE_STYLE[rl[0][0]][0] if rl else 'none'
                parts.append(f'<rect x="{fx}" y="{fy}" width="{finger}" height="24" class="finger" style="fill:{color};fill-opacity:{.85 if rl else 0}"/>')
                parts.append(f'<text x="{fx + finger / 2}" y="{fy + 17}" text-anchor="middle" class="pin{" on" if rl else ""}">{p}</text>')
                if rl:
                    label = 'GND' if all(r == 'ground' for r, _ in rl) and len(rl) > 1 else \
                        ' / '.join(dict.fromkeys(l for _, l in rl))[:24]
                    cx = fx + finger / 2
                    if ri == 0:
                        parts.append(f'<line x1="{cx}" y1="{fy}" x2="{cx}" y2="{fy - 14}" class="lead"/>')
                        parts.append(f'<text transform="translate({cx + 4},{fy - 18}) rotate(-62)" class="sig" style="fill:{color}">{e(label)}</text>')
                    else:
                        parts.append(f'<line x1="{cx}" y1="{fy + 24}" x2="{cx}" y2="{fy + 38}" class="lead"/>')
                        parts.append(f'<text transform="translate({cx + 4},{fy + 44}) rotate(62)" class="sig" style="fill:{color}">{e(label)}</text>')
        if len(prow) == 2:
            parts.append(f'<text x="{W / 2}" y="{y + 24}" text-anchor="middle" class="side">TOP ROW 1-22: COMPONENT SIDE · BOTTOM ROW A-Z: SOLDER SIDE</text>')
        y = top + board_h + (lab_h if len(prow) == 2 else 30)
    used = sorted({r for rl in roles.values() for r, _ in rl}, key=list(ROLE_STYLE).index)
    lx = 20
    for r in used:
        c, label = ROLE_STYLE[r]
        parts.append(f'<rect x="{lx}" y="{y}" width="14" height="14" style="fill:{c}"/><text x="{lx + 20}" y="{y + 12}" class="leg">{label}</text>')
        lx += 30 + 8.5 * len(label)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {y + 30}" class="drawing">{"".join(parts)}</svg>'


def pins_txt(p, q=None):
    f = lambda x: (f'{x[0]}-' if x and x[0] else '') + (x[1] if x else '?')
    return f'{f(p)} / {f(q)}' if q else f(p)


def svg_io(m):
    """Block diagram: inputs left, outputs right, power below, jumpers on the block."""
    ins = [(a['signal'], f"{a['port']}  {pins_txt(a['pos'], a['neg'])}") for a in m['audio'] if a['dir'] == 'in']
    ins += [(f"{b['bus']} bus", pins_txt(b['pos'], b['neg'])) for b in m['bus_in']]
    outs = [(a['signal'], f"{a['port']}  {pins_txt(a['pos'], a['neg'])}") for a in m['audio'] if a['dir'] == 'out']
    outs += [(f"{b['bus']} bus", pins_txt(b['pos'], b['neg'])) for b in m['bus_out']]
    both = [(a['signal'], f"{a['port']}  {pins_txt(a['pos'], a['neg'])}") for a in m['audio'] if a['dir'] == 'io']
    power = [(f"{p['rail']}", f"{p['volts']} V  {pins_txt(p['supply'])} / GND {pins_txt(p['ground'])}") for p in m['power']]
    if m.get('chassis'):
        power.append(('CHASSIS', pins_txt(m['chassis'])))
    W = 1100
    rows = max(len(ins) + len(both), len(outs), 2)
    bx, bw, by = 400, 300, 40
    bh = max(120, rows * 46 + 30)
    P = [f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" class="block"/>',
         f'<text x="{bx + bw / 2}" y="{by + bh / 2 - 6}" text-anchor="middle" class="code">{e(m["code"])}</text>',
         f'<text x="{bx + bw / 2}" y="{by + bh / 2 + 20}" text-anchor="middle" class="kind">{e(str(m["type"] or "")[:34])}</text>']

    def side(items, left, arrow_in, start_y, color):
        for i, (sig, pins) in enumerate(items):
            yy = start_y + i * 46
            x1, x2 = (60, bx) if left else (bx + bw, W - 60)
            P.append(f'<line x1="{x1}" y1="{yy}" x2="{x2}" y2="{yy}" class="wire" style="stroke:{color}"/>')
            tip = x2 if arrow_in else x1
            d = -1 if arrow_in else 1
            if not left:
                tip, d = (x2, -1) if not arrow_in else (x1, 1)
            P.append(f'<path d="M{tip},{yy} l{d * 12},-6 v12 z" style="fill:{color}"/>')
            tx = x1 + 4 if left else x2 - 4
            anchor = 'start' if left else 'end'
            P.append(f'<text x="{tx}" y="{yy - 8}" text-anchor="{anchor}" class="sig2">{e(sig)}</text>')
            P.append(f'<text x="{tx}" y="{yy + 18}" text-anchor="{anchor}" class="pins">{e(pins)}</text>')

    side(ins, True, True, by + 34, ROLE_STYLE['in'][0])
    side(both, True, True, by + 34 + len(ins) * 46, ROLE_STYLE['io'][0])
    side(outs, False, False, by + 34, ROLE_STYLE['out'][0])
    P.append(f'<text x="60" y="{by - 14}" class="h">INPUTS</text><text x="{W - 60}" y="{by - 14}" text-anchor="end" class="h">OUTPUTS</text>')
    y = by + bh
    for i, (rail, txt) in enumerate(power):
        xx = bx + 30 + i * (bw - 60) / max(1, len(power) - 1) if len(power) > 1 else bx + bw / 2
        P.append(f'<line x1="{xx}" y1="{y}" x2="{xx}" y2="{y + 40}" class="wire" style="stroke:{ROLE_STYLE["power"][0]}"/>')
        P.append(f'<text x="{xx}" y="{y + 56 + (i % 2) * 34}" text-anchor="middle" class="sig2">{e(rail)}</text>')
        P.append(f'<text x="{xx}" y="{y + 74 + (i % 2) * 34}" text-anchor="middle" class="pins">{e(txt)}</text>')
    for i, j in enumerate(m['jumpers']):
        jy = by + 18 + i * 22
        P.append(f'<text x="{bx + 12}" y="{jy}" class="jmp">⌒ {e(str(j["designation"]))} {pins_txt(j["from"])}↔{pins_txt(j["to"])}</text>')
    H = y + (120 if power else 30)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" class="drawing">{"".join(P)}</svg>'


SVG_STYLE = '''
.drawing { width: 100%; height: auto; font-family: "Overpass", "Helvetica Neue", Arial, sans-serif }
.drawing .h { font: 700 15px "Overpass", Arial, sans-serif; letter-spacing: .12em; fill: #1c1c1c }
.drawing .board { fill: #e7e2c9; stroke: #1c1c1c; stroke-width: 2 }
.drawing .finger { stroke: #1c1c1c; stroke-width: 1.4 }
.drawing .pin { font: 600 13px "Overpass Mono", monospace; fill: #555 }
.drawing .pin.on { fill: #fff }
.drawing .lead { stroke: #1c1c1c; stroke-width: 1 }
.drawing .sig { font: 600 12px "Overpass", Arial, sans-serif; text-transform: uppercase }
.drawing .side, .drawing .leg { font: 600 11px "Overpass Mono", monospace; fill: #1c1c1c; letter-spacing: .06em }
.drawing .block { fill: #faf8ef; stroke: #1c1c1c; stroke-width: 2.5 }
.drawing .code { font: 800 34px "Overpass", Arial, sans-serif; fill: #1c1c1c }
.drawing .kind { font: 600 13px "Overpass", Arial, sans-serif; fill: #555; text-transform: uppercase; letter-spacing: .06em }
.drawing .wire { stroke-width: 2.2 }
.drawing .sig2 { font: 700 14px "Overpass", Arial, sans-serif; fill: #1c1c1c; text-transform: uppercase }
.drawing .pins { font: 13px "Overpass Mono", monospace; fill: #444 }
.drawing .jmp { font: 12px "Overpass Mono", monospace; fill: #4f7f8a }
'''

# ---------------------------------------------------------------- sheet

PAGE_CSS = '''
/* Layout: a WBS B-size drawing sheet - border frame, drawings in the field, typed tables, title block. Single look by design. */
:root { --paper: #f7f6ef; --ink: #1c1c1c; --faint: #66635c; --rule: #1c1c1c;
  --letter: "Overpass", "Helvetica Neue", Arial, sans-serif; --typed: "Courier Prime", "Courier New", monospace; color-scheme: light }
* { box-sizing: border-box }
body { margin: 0; background: #d9d6ca; color: var(--ink); font: 14px/1.45 var(--letter);
  padding-block: 20px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)) }
.sheet { position: relative; max-width: 1180px; margin: 0 auto 24px; background: var(--paper); border: 2px solid var(--rule);
  outline: 10px solid var(--paper); padding: 22px 26px; box-shadow: 0 0 0 11px #b9b5a6; overflow: hidden }
h1 { font: 800 22px var(--letter); letter-spacing: .08em; text-transform: uppercase; margin: 0 0 4px }
h2 { font: 700 13px var(--letter); letter-spacing: .14em; text-transform: uppercase; margin: 22px 0 8px; border-bottom: 1.5px solid var(--rule); padding-bottom: 3px }
.sub { color: var(--faint); margin: 0 }
.fig { overflow-x: auto }
table { border-collapse: collapse; font: 13px var(--typed); width: 100% }
th { text-align: left; font: 700 11px var(--letter); letter-spacing: .1em; text-transform: uppercase; border-bottom: 1.5px solid var(--rule); padding: 4px 8px }
td { padding: 3px 8px; border-bottom: 1px dotted #b8b4a6; font-variant-numeric: tabular-nums }
.tables { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 480px), 1fr)); gap: 0 30px }
.tables > div { min-width: 0; overflow-x: auto }
.foot { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 18px; align-items: end; margin-top: 26px }
.warn { border: 2px solid #a3352b; color: #a3352b; padding: 8px 12px; font-weight: 700; max-width: 80ch }
.note { max-width: 60ch; color: var(--faint); font: 12px var(--typed) }
.tb { border: 2px solid var(--rule); display: grid; grid-template-columns: 90px 1fr 90px 1fr; font: 11px var(--letter); text-transform: uppercase; min-width: min(100%, 520px) }
.tb > div { border-top: 1px solid var(--rule); border-right: 1px solid var(--rule); padding: 3px 6px }
.tb .co { grid-column: 1 / -1; border-top: 0; font: 800 15px var(--letter); letter-spacing: .06em; display: flex; gap: 10px; align-items: center }
.tb .co i { font-style: normal; border: 2px solid; border-radius: 9px; padding: 0 7px }
.tb .wide { grid-column: span 3 }
.toner, .scan { position: absolute; pointer-events: none }
.toner { inset: 0; opacity: .06; background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2'/><feColorMatrix values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -1.4 .62'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>") }
.scan { left: 0; right: 0; height: 120px; top: -130px; background: linear-gradient(to bottom, transparent, rgba(150,210,255,.18) 75%, rgba(225,245,255,.6) 94%, transparent) }
@media screen and (prefers-reduced-motion: no-preference) {
  .drawing line, .drawing rect, .drawing path { animation: pencil 2.4s ease-out both }
  .toner { animation: toner 2.4s 1.2s ease-out both }
  .scan { animation: scan 1.6s 2.2s ease-in both }
}
@keyframes pencil { 0% { opacity: .35; filter: grayscale(1) blur(.3px) } 50% { opacity: .6; filter: grayscale(1) } 100% { opacity: 1; filter: none } }
@keyframes toner { 0% { opacity: 0 } 35% { opacity: .3 } 100% { opacity: .06 } }
@keyframes scan { to { top: 100% } }
@page { size: 17in 11in; margin: .35in }
@media print { body { background: none; padding: 0 } .sheet { box-shadow: none; outline: 0; margin: 0; max-width: none } .toner, .scan { display: none } }
'''


def table(head, rows):
    if not rows:
        return ''
    th = ''.join(f'<th>{e(h)}</th>' for h in head)
    tr = ''.join('<tr>' + ''.join(f'<td>{e(str(c)) if c not in (None, "") else "—"}</td>' for c in r) + '</tr>' for r in rows)
    return f'<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'


def sheet_html(m, conn_svg, io_svg, safe=None):
    if safe is None:
        safe = m["code"].replace('/', '-')
    p = lambda x: pins_txt(x) if x else ''
    audio = table(['Port', 'Signal', 'Dir', 'Pin +', 'Pin −', 'Pad +', 'Pad −'],
                  [[a['port'], a['signal'], a['dir'], p(a['pos']), p(a['neg']), a['pad_pos'], a['pad_neg']] for a in m['audio']])
    busses = table(['Bus', 'Dir', 'Signal', 'Pin +', 'Pin −'],
                   [[b['bus'], 'out', b['signal'], p(b['pos']), p(b['neg'])] for b in m['bus_out']] +
                   [[b['bus'], 'in', b['signal'], p(b['pos']), p(b['neg'])] for b in m['bus_in']])
    power = table(['Rail', 'Style', 'Volts', 'Max A', 'Supply', 'Ground', 'Link'],
                  [[x['rail'], x['style'], x['volts'], x['max_a'], p(x['supply']), p(x['ground']), x['link']] for x in m['power']])
    jumpers = table(['Function', 'Designation', 'From', 'To'],
                    [[j['function'], j['designation'], p(j['from']), p(j['to'])] for j in m['jumpers']])
    other = table(['Signal', 'Pins'], [[o['signal'], ', '.join(p(x) for x in o['pins'])] for o in m.get('other', [])])
    if any(a.get('note') for a in m['audio']):
        audio = table(['Port', 'Signal', 'Dir', 'Pin +', 'Pin −', 'Note'],
                      [[a['port'], a['signal'], a['dir'], p(a['pos']), p(a['neg']), a.get('note')] for a in m['audio']])
    blocks = ''.join(f'<div><h2>{t}</h2>{h}</div>' for t, h in (('Audio connections · RTO-144 A / B', audio),
                     ('Bus connections', busses), ('Power · bench PSU', power), ('Jumpers', jumpers),
                     ('Other pins', other)) if h)
    source = (f'Source: Ward-Beck drawing {m["verified"]}. Verify against the module before wiring.' if m.get('verified') else
              'Source: Ward-Beck Systems - Module RTO-144 Jumper calculator.xlsx (Database tab). Pin direction is inferred '
              'from the signal name. Verify against the module schematic before wiring.')
    warn = f'<p class="warn">{e(m["unverified"])}</p>' if m.get('unverified') else ''
    imp = ', '.join(f'{k.replace("_", " ")} {v} Ω' for k, v in m['impedance'].items())
    today = datetime.date.today()
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(m["code"])} RTO-144 Connections</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Overpass:wght@400;600;700;800&family=Overpass+Mono:wght@400;600&family=Courier+Prime:wght@400;700&display=swap">
<style>{PAGE_CSS}{SVG_STYLE}</style></head>
<body><main class="sheet">
<div class="toner" aria-hidden="true"></div><div class="scan" aria-hidden="true"></div>
<h1>{e(m["code"])} · RTO-144 Connections</h1>
<p class="sub">{e(str(m["type"] or ""))}{" · series " + e(str(m["series"])) if m["series"] else ""}{" · " + imp if imp else ""}{" · " + e(m["connector"]) if m.get("connector") else ""}</p>
<div style="margin: 10px 0 16px; display: flex; gap: 12px; align-items: center; font-size: 13px; background: #efe9d2; padding: 6px 12px; border: 1px solid #cfcabc;">
  <span style="font-weight: 700;">KiCad:</span>
  <a href="../../kicad.html?m={quote(m['code'])}" style="color: #1f3f6b; font-weight: 700;">⚡ Open in KiCad Library Generator</a> ·
  <a href="{quote(safe)}.kicad_sym" download style="color: #1f3f6b;">📥 Download {e(safe)}.kicad_sym</a>
</div>
{warn}
<h2>Rear connector</h2><div class="fig">{conn_svg}</div>
<h2>Inputs and outputs</h2><div class="fig">{io_svg}</div>
<div class="tables">{blocks}</div>
<div class="foot">
  <p class="note">{e(source)}</p>
  <div class="tb"><div class="co"><i>WBS</i> Ward-Beck Systems Ltd.</div>
    <div>Title</div><div class="wide">{e(m["code"])} RTO-144 connections</div>
    <div>Drn.</div><div>make_rto144.py</div><div>Date</div><div>{today:%b %d %Y}</div></div>
</div>
</main></body></html>'''


def md(m):
    p = lambda x: pins_txt(x) if x else ''
    L = [f'# {m["code"]} · RTO-144 Connections', '', f'{m["type"] or ""}' + (f' · {m["connector"]}' if m.get('connector') else ''), '']
    if m.get('unverified'):
        L += [f'> **{m["unverified"]}**', '']
    L += [
         '![Rear connector](connector.svg)', '', '![Inputs and outputs](io.svg)', '']
    if m['audio']:
        L += ['## Audio connections', '', '| Port | Signal | Dir | Pin + | Pin − |', '|---|---|---|---|---|']
        L += [f'| {a["port"]} | {a["signal"]} | {a["dir"]} | {p(a["pos"])} | {p(a["neg"])} |' for a in m['audio']] + ['']
    if m['bus_out'] or m['bus_in']:
        L += ['## Bus connections', '', '| Bus | Dir | Pin + | Pin − |', '|---|---|---|---|']
        L += [f'| {b["bus"]} | out | {p(b["pos"])} | {p(b["neg"])} |' for b in m['bus_out']]
        L += [f'| {b["bus"]} | in | {p(b["pos"])} | {p(b["neg"])} |' for b in m['bus_in']] + ['']
    if m['power']:
        L += ['## Power', '', '| Rail | Volts | Max A | Supply | Ground |', '|---|---|---|---|---|']
        L += [f'| {x["rail"]} | {x["volts"]} | {x["max_a"] if x["max_a"] is not None else ""} | {p(x["supply"])} | {p(x["ground"])} |' for x in m['power']] + ['']
    if m['jumpers']:
        L += ['## Jumpers', '', '| Function | Designation | From | To |', '|---|---|---|---|']
        L += [f'| {j["function"]} | {j["designation"]} | {p(j["from"])} | {p(j["to"])} |' for j in m['jumpers']] + ['']
    if m.get('other'):
        L += ['## Other pins', '', '| Signal | Pins |', '|---|---|']
        L += [f'| {o["signal"]} | {", ".join(p(x) for x in o["pins"])} |' for o in m['other']] + ['']
    L += [f'_Source: Ward-Beck drawing {m["verified"]}. Verify against the module before wiring._' if m.get('verified') else
          '_Source: Module RTO-144 Jumper calculator.xlsx (Database tab). Verify against the module schematic before wiring._', '']
    return '\n'.join(L)


def plain(m):
    """JSON/YAML-friendly copy: pins as 'P2-19' / '19' strings"""
    def fix(v):
        if isinstance(v, tuple):
            return pins_txt(v)
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        if isinstance(v, list):
            return [fix(x) for x in v]
        return v
    return fix(m)

# ---------------------------------------------------------------- KiCad symbols

PIN_TYPE = {'in': 'input', 'out': 'output', 'io': 'bidirectional', 'power': 'power_in', 'ground': 'power_in',
            'jumper': 'passive', 'logic': 'bidirectional', 'nc': 'no_connect'}


def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def contact_order(p):
    c, n = p
    return c, (int(n) if n.isdigit() else 100 + LETTERS.index(n) if n in LETTERS else 999)


def kicad_symbol(m, roles, name):
    """One symbol per module: each used edge contact is a pin, numbered as on the connector.
    Inputs left, outputs right, supplies on top, grounds below."""
    bus_in = {p for b in m['bus_in'] for p in (b['pos'], b['neg']) if p}
    sides = {'L': [], 'R': [], 'T': [], 'B': []}
    for p in roles:  # signal order: each + pin next to its − pin
        rl = roles[p]
        role = rl[0][0]
        if role == 'bus':
            side, etype = ('L', 'input') if p in bus_in else ('R', 'output')
        else:
            side, etype = {'out': 'R', 'power': 'T', 'ground': 'B'}.get(role, 'L'), PIN_TYPE[role]
        label = ' / '.join(dict.fromkeys(l for _, l in rl)).replace('−', '-')
        sides[side].append((pins_txt(p), label, etype))
    g = 2.54
    rows = max(len(sides['L']), len(sides['R']), 2)
    cols = max(len(sides['T']), len(sides['B']), 1)
    longest = max([len(l) for _, l, _ in sides['L'] + sides['R']] + [0])
    half_w = round(max(10 * g, cols * 2 * g, 0.65 * longest * g) / g) * g
    half_h = round((rows + 1) / 2) * g + g
    pins = []

    def add(etype, x, y, ang, label, num):
        pins.append(f'      (pin {etype} line (at {x:.2f} {y:.2f} {ang}) (length 5.08)'
                    f' (name {q(label)} (effects (font (size 1.27 1.27))))'
                    f' (number {q(num)} (effects (font (size 1.27 1.27)))))')
    for i, (num, label, et) in enumerate(sides['L']):
        add(et, -half_w - 5.08, half_h - (i + 1) * g, 0, label, num)
    for i, (num, label, et) in enumerate(sides['R']):
        add(et, half_w + 5.08, half_h - (i + 1) * g, 180, label, num)
    for side, y, ang in (('T', half_h + 5.08, 270), ('B', -half_h - 5.08, 90)):
        n = len(sides[side])
        for i, (num, label, et) in enumerate(sides[side]):
            add(et, (i - (n - 1) / 2) * 4 * g, y, ang, label, num)
    font = '(effects (font (size 1.27 1.27)))'
    hidden = '(effects (font (size 1.27 1.27)) hide)'
    desc = f'{m["code"]} {m["type"] or ""}: ' + (m['verified'] if m.get('verified') else 'edge connector pin-out from the RTO-144 jumper calculator')
    return '\n'.join([
        f'  (symbol {q(name)} (pin_names (offset 1.016)) (exclude_from_sim yes) (in_bom yes) (on_board yes)',
        f'    (property "Reference" "U" (at 0 {half_h + 2 * g:.2f} 0) {font})',
        f'    (property "Value" {q(m["code"])} (at 0 {-half_h - 2 * g:.2f} 0) {font})',
        f'    (property "Footprint" "" (at 0 0 0) {hidden})',
        f'    (property "Datasheet" "" (at 0 0 0) {hidden})',
        f'    (property "Description" {q(desc)} (at 0 0 0) {hidden})',
        f'    (property "ki_keywords" {q("Ward-Beck WBS module RTO-144 " + str(m["series"] or ""))} (at 0 0 0) {hidden})',
        f'    (symbol {q(name + "_0_1")} (rectangle (start {-half_w:.2f} {half_h:.2f}) (end {half_w:.2f} {-half_h:.2f})'
        f' (stroke (width 0.254) (type default)) (fill (type background))))',
        f'    (symbol {q(name + "_1_1")}',
        *pins,
        '    )',
        '  )', ''])


def kicad_lib(symbols):
    return '(kicad_symbol_lib (version 20231120) (generator "make_rto144") (generator_version "1.0")\n' + ''.join(symbols) + ')\n'

# ---------------------------------------------------------------- write

os.makedirs(OUT, exist_ok=True)
index_rows = []
all_symbols = []
for code, m in modules.items():
    roles = pin_roles(m)
    safe = code.replace('/', '-')
    d = os.path.join(OUT, safe)
    os.makedirs(d, exist_ok=True)
    conn, io = svg_connector(m, roles), svg_io(m)
    for name, svg in (('connector.svg', conn), ('io.svg', io)):
        with open(os.path.join(d, name), 'w') as f:
            f.write(svg.replace('class="drawing">', f'class="drawing"><style>{SVG_STYLE}</style>', 1))
    base = f'{safe} - RTO-144 Connections'
    with open(os.path.join(d, base + '.html'), 'w') as f:
        f.write(sheet_html(m, conn, io, safe))
    data = plain(m)
    with open(os.path.join(d, f'{safe}.rto144.json'), 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    with open(os.path.join(d, f'{safe}.rto144.yaml'), 'w') as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    with open(os.path.join(d, f'{safe}.rto144.md'), 'w') as f:
        f.write(md(m))
    if PDF:
        subprocess.run(['google-chrome', '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
                        '--virtual-time-budget=4000', f'--print-to-pdf={os.path.join(d, base + ".pdf")}',
                        'file://' + os.path.join(d, base + '.html')], capture_output=True, timeout=120)
    symbol = kicad_symbol(m, roles, safe.replace("'", '_alt'))
    all_symbols.append(symbol)
    with open(os.path.join(d, f'{safe}.kicad_sym'), 'w') as f:
        f.write(kicad_lib([symbol]))
    index_rows.append((code, safe, m, len(roles)))

with open(os.path.join(OUT, 'WBS_Modules.kicad_sym'), 'w') as f:
    f.write(kicad_lib(all_symbols))
items = ''.join(
    f'<tr><td><a href="{quote(s)}/{quote(s + " - RTO-144 Connections.html")}">{e(c)}</a></td><td>{e(str(m["type"] or ""))}</td>'
    f'<td>{len(m["audio"])}</td><td>{len(m["bus_out"]) + len(m["bus_in"])}</td><td>{len(m["power"])}</td><td>{n}</td>'
    f'<td><a href="../../kicad.html?m={quote(s)}">Generator</a> · <a href="{quote(s)}/{quote(s)}.kicad_sym" download>.kicad_sym</a></td></tr>'
    for c, s, m, n in sorted(index_rows))
with open(os.path.join(OUT, 'index.html'), 'w') as f:
    f.write(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>RTO-144 Connections</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Overpass:wght@400;700;800&family=Courier+Prime&display=swap">
<style>{PAGE_CSS}</style></head><body><main class="sheet">
<h1>RTO-144 Connections · all modules</h1><p class="sub">{len(index_rows)} modules from the jumper calculator. Each sheet shows the rear connector, the inputs and outputs, and the pin tables.</p>
<div style="display:flex; flex-wrap:wrap; gap:10px 14px; margin:14px 0 20px; align-items:center;">
<a href="../../kicad.html" style="background:#2a5ea0; color:#fff; text-decoration:none; padding:6px 14px; font-weight:700; font-size:13px; border-radius:3px;">⚡ KiCad Library Generator (Interactive)</a>
<a href="../KICAD/WBS_All_Modules.kicad_sym" download style="background:#2e6b34; color:#fff; text-decoration:none; padding:6px 14px; font-weight:700; font-size:13px; border-radius:3px;">📦 Export All 526 Symbols (.kicad_sym)</a>
<a href="WBS_Modules.kicad_sym" download style="background:#ece7d5; border:1px solid #1c1c1c; color:#1c1c1c; text-decoration:none; padding:6px 14px; font-weight:700; font-size:13px;">📦 Download {len(index_rows)} RTO Symbols (.kicad_sym)</a>
<a href="../KICAD/" style="background:#f5f2e6; border:1px solid #1c1c1c; color:#1c1c1c; text-decoration:none; padding:6px 14px; font-weight:700; font-size:13px;">📂 23 Category Libraries</a>
</div>
<h2>Modules</h2><div class="tables" style="grid-template-columns:1fr"><div>
<table><thead><tr><th>Module</th><th>Type</th><th>Audio ports</th><th>Buses</th><th>Rails</th><th>Pins used</th><th>KiCad Symbol</th></tr></thead><tbody>{items}</tbody></table>
</div></div></main></body></html>''')
print(f'{len(index_rows)} modules written to {OUT}' + (' (with PDFs)' if PDF else ''))
