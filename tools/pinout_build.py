#!/usr/bin/env python3
"""RTO.json and the KiCad symbol of a module, from its pinout pictures.

Every pinout picture has a reading beside it, `<picture>.pinout.json` (tools/pinout_schema.md).
For each module this merges:

  1. the readings of its own pictures (PINOUTS/, then any other kind folder),
  2. the readings of other modules' pictures whose title names it (`applies_to`: a variant),
  3. the RTO-144 sheet (2026/Engineering/RTO-144/<code>/<code>.rto144.json), as a check only,

into `RTO.json` (every contact: connector, pin, signal, kind, port, polarity, which pictures
read it, whether the sheet agrees; the ports, the inserts as send / return pairs, the straps,
every disagreement) and `KICAD/<code>.kicad_sym`: inputs on the left, outputs on the right,
each insert a block of its own (send, then return, together), power on top, grounds at the
bottom. The symbol keeps the header (title, category, year …) of the one it replaces.

    python3 tools/pinout_build.py [--root DIR] [--check] [CODE ...]

--root: the folder holding the module repos (default: WBSps.ca/Github.WardBeckSystems, the
MODULES.<CAT>.<M>-<Function> clones); 2026/Modules/<CAT>/<M> (links to the clones) works too. --check: report only.
"""

import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ENG = os.path.join(REPO, '2026', 'Engineering')
CLONES = os.path.join(REPO, 'WBSps.ca', 'Github.WardBeckSystems')
KINDS = ('PINOUTS', 'MANUALS', 'SCHEMATICS', 'MECHANICAL', 'PHOTOS')
CONF = {'high': 3, 'medium': 2, 'low': 1}
LEFT = ('in', 'insert_return', 'control_in', 'bus', 'strap', 'other')
RIGHT = ('out', 'insert_send', 'control_out')
KICAD_TYPE = {'in': 'input', 'insert_return': 'input', 'control_in': 'input', 'out': 'output', 'insert_send': 'output',
              'control_out': 'output', 'power': 'power_in', 'ground': 'power_in', 'shield': 'passive', 'bus': 'bidirectional',
              'strap': 'passive', 'other': 'passive', 'nc': 'no_connect'}


def code_of(moddir):
    """MODULES.FILTERS.M462-Equalizer-Module -> M462; .../FILTERS/M462 -> M462."""
    b = os.path.basename(os.path.normpath(moddir))
    if b.startswith('MODULES.'):
        b = b.split('.', 2)[2]
        return b.split('-', 1)[0]
    return b


def module_dirs(root):
    out = {}
    for d in sorted(glob.glob(os.path.join(root, 'MODULES.*'))) + sorted(glob.glob(os.path.join(root, '*', 'M*'))):
        if os.path.isdir(d) and d not in out.get(code_of(d), []):
            out.setdefault(code_of(d), []).append(d)   # a code may have a repo in two categories
    return out


def readings(moddir):
    for k in KINDS:
        for f in sorted(glob.glob(os.path.join(moddir, k, '*.pinout.json'))):
            try:
                j = json.load(open(f, encoding='utf-8'))
            except (OSError, ValueError) as e:
                print(f'  ! {f}: {e}', file=sys.stderr)
                continue
            if j.get('schema') == 'wbs-pinout/1':
                j['_file'] = os.path.relpath(f, moddir)
                yield j


def norm_conn(c):
    c = (c or '').strip().upper().replace(' ', '')
    return c or 'P1'


def split_ref(ref):
    """"P1-17" -> ("P1", "17"); "4" -> ("P1", "4")."""
    ref = str(ref).strip()
    m = re.match(r'^([A-Z]+\d+)-(.+)$', ref, re.I)
    return (norm_conn(m.group(1)), m.group(2).strip().upper()) if m else ('P1', ref.upper())


def sheet_pins(code):
    """The RTO-144 sheet's contacts: {(conn, pin): (signal, kind)} and its facts."""
    f = os.path.join(ENG, 'RTO-144', code, f'{code}.rto144.json')
    if not os.path.exists(f):
        return {}, None
    s = json.load(open(f, encoding='utf-8'))
    pins = {}

    def put(ref, signal, kind):
        if ref:
            pins.setdefault(split_ref(ref), (signal, kind))
    for a in s.get('audio', []):
        d = {'in': 'in', 'out': 'out'}.get(a.get('dir'), 'other')
        put(a.get('pos'), f"{a.get('signal')} +", d)
        put(a.get('neg'), f"{a.get('signal')} -", d)
    for b in s.get('bus_out', []):
        put(b.get('pos'), f"{b.get('signal')} +", 'out')
        put(b.get('neg'), f"{b.get('signal')} -", 'out')
    for b in s.get('bus_in', []):
        put(b.get('pos'), f"{b.get('signal')} +", 'in')
        put(b.get('neg'), f"{b.get('signal')} -", 'in')
    for p in s.get('power', []):
        put(p.get('supply'), p.get('rail'), 'power')
        put(p.get('ground'), 'GND', 'ground')
    for j in s.get('jumpers', []):
        put(j.get('from'), j.get('designation'), 'strap')
        put(j.get('to'), j.get('designation'), 'strap')
    for o in s.get('other', []):
        role = {'ground': 'ground', 'nc': 'nc', 'jumper': 'strap'}.get(o.get('role'), 'other')
        for p in o.get('pins', []):
            put(p, o.get('signal'), role)
    if s.get('chassis'):
        put(s['chassis'], 'CHASSIS', 'ground')
    return pins, s


def same_kind(a, b):
    """Do two readings of a contact agree? A bus contact is fed or read (in or out), and
    "other" (the sheet's catch-all) or no kind fits anything."""
    g = lambda k: {'shield': 'ground', 'insert_send': 'out', 'insert_return': 'in', 'control_in': 'in',
                   'control_out': 'out'}.get(k, k)
    a, b = g(a), g(b)
    # A strap (a frame jumper) rides on a contact that also carries its signal
    if a in (None, 'other', 'strap') or b in (None, 'other', 'strap') or a == b:
        return True
    return 'bus' in (a, b) and {a, b} <= {'bus', 'in', 'out'}


def build(code, own, variants):
    """The RTO.json document of `code` from its readings (own first) and the sheet."""
    names = lambda r: {x.strip().upper() for x in (r.get('applies_to') or [])}
    reads = [(r, True) for r in own if r.get('pinout', True) and (not names(r) or code in names(r))]
    reads += [(r, True) for r in variants if r.get("pinout", True)]   # its title names this module: its own drawing, wherever filed
    if not reads:
        return None
    sheet, facts = sheet_pins(code)
    pic_conns = {norm_conn(p.get('connector')) for r, _ in reads for p in r.get('pins', [])}
    sheet_conns = {c for c, _ in sheet}
    # One connector each side under different names (a drawing that names none is read as P1,
    # the sheet may call it P2): the same connector
    if len(pic_conns) == 1 and len(sheet_conns) == 1 and pic_conns != sheet_conns:
        (pc,), (sc,) = pic_conns, sheet_conns
        sheet = {(pc, pin): v for (_, pin), v in sheet.items()}
    single = len(pic_conns) <= 1
    cands = {}
    for r, mine in reads:
        rank = (1 if mine else 0, CONF.get(r.get('confidence'), 1))
        for p in r.get('pins', []):
            if not p.get('pin'):
                continue
            key = (norm_conn(p.get('connector')), str(p['pin']).strip().upper())
            cands.setdefault(key, []).append((rank, p, r['_src']))
            # A row drawn "A | 1" with one label: the opposite contact carries it too
            # (unless the reading lists that contact itself)
            also = str(p.get('also') or '').strip().upper()
            if also and also != key[1]:
                listed = any(norm_conn(o.get('connector')) == key[0] and str(o.get('pin') or '').strip().upper() == also
                             for o in r.get('pins', []))
                if not listed:
                    cands.setdefault((key[0], also), []).append((rank, {**p, 'pin': also, 'also': key[1], '_row': True}, r['_src']))
    pins, conflicts = [], []
    for key in sorted(cands, key=lambda k: (k[0], (0, int(k[1])) if k[1].isdigit() else (1, k[1]))):
        cs = sorted(cands[key], key=lambda c: c[0], reverse=True)
        best = cs[0][1]
        for _, p, src in cs[1:]:
            if not same_kind(p.get('kind'), best.get('kind')):
                conflicts.append({'pin': '-'.join(key), 'kept': f"{best.get('signal')} ({best.get('kind')})",
                                  'other': f"{p.get('signal')} ({p.get('kind')})", 'from': src})
        sh = sheet.get(key)
        agrees = None if sh is None else same_kind(sh[1], best.get('kind'))
        if agrees is False:
            conflicts.append({'pin': '-'.join(key), 'kept': f"{best.get('signal')} ({best.get('kind')})",
                              'other': f'{sh[0]} ({sh[1]})', 'from': 'RTO-144 sheet'})
        pins.append({
            'connector': key[0], 'pin': key[1], 'ref': key[1] if single else f'{key[0]}-{key[1]}',
            'also': best.get('also'), 'same_row': bool(best.get('_row')) or None,
            'signal': best.get('signal'), 'kind': best.get('kind'),
            'port': best.get('port'), 'polarity': best.get('polarity'),
            'confidence': 'variant' if cs[0][0][0] == 0 else {3: 'high', 2: 'medium', 1: 'low'}[cs[0][0][1]],
            'read_from': sorted({src for _, _, src in cs}),
            'sheet': None if sh is None else {'signal': sh[0], 'kind': sh[1], 'agrees': agrees},
        })
    # Ports, inserts and straps: the best own reading first, then any the others add by name
    ports, inserts, straps, seen = [], [], [], set()
    for r, _ in sorted(reads, key=lambda x: (x[1], CONF.get(x[0].get('confidence'), 1)), reverse=True):
        for p in r.get('ports', []):
            if p.get('name') and p['name'] not in seen:
                seen.add(p['name'])
                ports.append(p)
        for i in r.get('inserts', []):
            if i.get('name') and all(i['name'] != x['name'] for x in inserts):
                inserts.append(i)
        for s in r.get('straps', []):
            if s.get('name') and all(s['name'] != x['name'] for x in straps):
                straps.append(s)
    # The sheet's frame straps too (jumpers between contacts)
    for j in (facts or {}).get('jumpers', []):
        name = (j.get('designation') or '').strip()
        if name and all(name != x.get('name') for x in straps):
            straps.append({'name': name, 'pins': [j.get('from'), j.get('to')], 'note': (j.get('function') or '').strip(),
                           'from': 'RTO-144 sheet'})
    # An insert is always a pair: every insert port in the pins belongs to one
    names = {p['port'] for p in pins if p['kind'] in ('insert_send', 'insert_return') and p.get('port')}
    paired = {x for i in inserts for x in (i.get('send'), i.get('return'))}
    for n in sorted(names - paired):
        conflicts.append({'pin': n, 'kept': 'insert port', 'other': 'no partner (send / return) named', 'from': 'inserts'})
    connectors, cseen = [], set()
    for r, _ in reads:
        for c in r.get('connectors', []):
            n = norm_conn(c.get('name'))
            if n not in cseen:
                cseen.add(n)
                connectors.append({**c, 'name': n})
    agree = [p for p in pins if p['sheet'] is not None]
    to_check = [{'what': 'disagree', 'pin': c['pin'], 'detail': f"kept {c['kept']}; {c['from']} says {c['other']}"} for c in conflicts]
    for r, _ in reads:
        for k, detail in guesses(r):
            to_check.append({'what': k, 'pin': None, 'detail': f"{detail} ({r['_src'].split('/', 1)[0]}: {r.get('picture')})"})
    return {
        'code': code,
        'connector': 'RTO-144',
        'type': (facts or {}).get('type'),
        'series': (facts or {}).get('series'),
        'connectors': connectors,
        'verified': (facts or {}).get('verified'),
        'built_from': {
            'pictures': sorted({r['_src'] for r, _ in reads}),
            'sheet': f'Engineering/RTO-144/{code}/{code}.rto144.json' if facts else None,
            'sheet_agrees': f'{sum(1 for p in agree if p["sheet"]["agrees"])} of {len(agree)}' if agree else None,
        },
        'pins': pins,
        'ports': ports,
        'inserts': inserts,
        'straps': straps,
        'conflicts': conflicts,
        'to_check': to_check,
    }


# ---- KiCad symbol ----

def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def pin_line(kind, x, y, rot, name, number, stacked=False):
    """One pin; `stacked`: a second contact of the same row at the same place (KiCad stacked pin)."""
    t = 'passive' if stacked else KICAD_TYPE.get(kind, 'passive')
    hide = ' hide' if stacked else ''
    return (f'      (pin {t} line (at {x:.2f} {y:.2f} {rot}) (length 5.08){hide} (name {q(name)} (effects (font (size 1.27 1.27)))) '
            f'(number {q(number)} (effects (font (size 1.27 1.27)))))')


def symbol(code, doc, old):
    """The symbol library text: the old header (properties) kept, pins and body new."""
    pins = [p for p in doc['pins'] if p['kind'] != 'nc']
    by_ref, uniq, stack = {}, [], {}
    refs = {p['ref'] for p in pins}
    for p in pins:   # one KiCad pin per contact; a same-row twin is stacked under its partner
        if p['ref'] in by_ref:
            continue
        by_ref[p['ref']] = p
        twin = p['ref'][:-len(p['pin'])] + str(p.get('also') or '') if p.get('also') else None
        if p.get('same_row') and twin in refs:
            stack.setdefault(twin, []).append(p)
            continue
        uniq.append(p)
    port_of = lambda p: p.get('port') or p['signal']
    insert_ports = {}
    for i in doc['inserts']:
        insert_ports[i.get('send')] = (i['name'], 0)
        insert_ports[i.get('return')] = (i['name'], 1)
    # An insert port named in the pins but missing from `inserts` still goes with the inserts
    for p in uniq:
        if p['kind'] in ('insert_send', 'insert_return') and port_of(p) not in insert_ports:
            insert_ports[port_of(p)] = (port_of(p), 0 if p['kind'] == 'insert_send' else 1)
    left, right, top, bottom, ins = [], [], [], [], {}
    for p in uniq:
        if port_of(p) in insert_ports and p['kind'] in ('insert_send', 'insert_return', 'in', 'out', 'shield'):
            name, k = insert_ports[port_of(p)]
            ins.setdefault(name, ([], []))[k].append(p)
        elif p['kind'] == 'power':
            top.append(p)
        elif p['kind'] in ('ground',) or (p['kind'] == 'shield' and not p.get('port')):
            bottom.append(p)
        elif p['kind'] in RIGHT:
            right.append(p)
        else:
            left.append(p)

    def grouped(ps):
        """Pins in port order, a blank row between ports."""
        out, last = [], object()
        for p in sorted(ps, key=lambda p: (LEFT.index(p['kind']) if p['kind'] in LEFT else RIGHT.index(p['kind']) if p['kind'] in RIGHT else 9,
                                           port_of(p))):
            if out and port_of(p) != last:
                out.append(None)
            out.append(p)
            last = port_of(p)
        return out
    L, R = grouped(left), grouped(right)
    blocks = []   # inserts: below the outputs, send then return, a label above each
    for name, (send, ret) in ins.items():
        blocks.append(('label', name))
        blocks += [('pin', p) for p in send] + [('pin', p) for p in ret]
    if blocks and R:
        R.append(None)
    rows = max(len(L), len(R) + sum(1 for b in blocks), 2)
    width_chars = max([len(p['signal'] or '') for p in uniq] + [8])
    half = max(15.24, round((width_chars * 1.27 * 0.9 + 5.08) / 2.54) * 2.54)
    top_y = round((rows * 2.54) / 2 / 2.54 + 1) * 2.54
    lines, texts = [], []

    def place(p, x, y, rot):
        lines.append(pin_line(p['kind'], x, y, rot, p['signal'], p['ref']))
        for s in stack.get(p['ref'], []):
            lines.append(pin_line(s['kind'], x, y, rot, s['signal'], s['ref'], stacked=True))
    y = top_y - 2.54
    for p in L:
        if p:
            place(p, -half - 5.08, y, 0)
        y -= 2.54
    y = top_y - 2.54
    for p in R:
        if p:
            place(p, half + 5.08, y, 180)
        y -= 2.54
    for kind, v in blocks:
        if kind == 'label':
            texts.append(f'    (text {q(v + " (send / return)")} (at {half - 1.27:.2f} {y:.2f} 0) (effects (font (size 1.016 1.016) italic) (justify right)))')
        else:
            place(v, half + 5.08, y, 180)
        y -= 2.54
    if blocks:
        bw = max(len(b[1]['signal'] or '') for b in blocks if b[0] == 'pin') * 1.27 * 0.75 + 3.81
        bw = max(bw, max(len(b[1]) for b in blocks if b[0] == 'label') * 1.016 * 0.75 + 15)
        texts.append(f'    (rectangle (start {half - bw:.2f} {y + 2.54 * (len(blocks) + 0.5):.2f}) (end {half:.2f} {y + 1.27:.2f}) '
                     f'(stroke (width 0.1524) (type dash)) (fill (type none)))')
    bot_y = top_y - (rows + 1) * 2.54   # below the longer of the two sides
    # Room for the power / ground names, drawn upright inside the body
    span = lambda ps: (round((max([len(p['signal'] or '') for p in ps] + [0]) * 1.27 * 0.8 + 1.27) / 2.54) * 2.54) if ps else 0
    top_y += span(top)
    bot_y -= span(bottom)
    for side, ps, yy, rot in ((top, top, top_y + 5.08, 270), (bottom, bottom, bot_y - 5.08, 90)):
        n = len(ps)
        for k, p in enumerate(ps):
            x = (k - (n - 1) / 2) * 5.08
            place(p, x, yy, rot)
    half_w = max(half, (max(len(top), len(bottom)) * 5.08) / 2 + 2.54)
    header = []
    if old:
        for ln in old.splitlines():
            if re.match(rf'\s*\(symbol {re.escape(q(code + "_0_1"))}', ln):
                break
            if ln.lstrip().startswith(';;') or '(property "Pinout_Pictures"' in ln:
                continue   # KiCad 9 loads no file with ";;" comments
            header.append(ln)
        header = [re.sub(r'\(property "Reference" "U" \(at [^)]*\)', f'(property "Reference" "U" (at 0 {top_y + 7.62:.2f} 0)', h) for h in header]
        header = [re.sub(r'\(property "Value" "([^"]*)" \(at [^)]*\)', rf'(property "Value" "\1" (at 0 {bot_y - 7.62:.2f} 0)', h) for h in header]
    else:
        header = [f'(kicad_symbol_lib (version 20231120) (generator "WBSps KiCad - {code}") (generator_version "2.0")',
                  f'  (symbol {q(code)} (pin_names (offset 1.016)) (exclude_from_sim yes) (in_bom yes) (on_board yes)',
                  f'    (property "Reference" "U" (at 0 {top_y + 7.62:.2f} 0) (effects (font (size 1.27 1.27))))',
                  f'    (property "Value" {q(code)} (at 0 {bot_y - 7.62:.2f} 0) (effects (font (size 1.27 1.27))))',
                  '    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
                  f'    (property "Datasheet" "https://wbsps.ca/PAGES/{code}.html" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
                  '    (property "Manufacturer" "Ward-Beck Systems Ltd." (at 0 0 0) (effects (font (size 1.27 1.27)) hide))']
    pics = '; '.join(doc['built_from']['pictures'])
    at = next((i for i, h in enumerate(header) if '(property "Manufacturer"' in h), len(header) - 1) + 1
    header.insert(at, f'    (property "Pinout_Pictures" {q(pics)} (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')
    body = [f'    (symbol {q(code + "_0_1")}',
            f'      (rectangle (start {-half_w:.2f} {top_y:.2f}) (end {half_w:.2f} {bot_y:.2f}) '
            '(stroke (width 0.254) (type default)) (fill (type background)))']
    body += ['  ' + t for t in texts] + ['    )']   # the insert blocks: a dashed box and a label each
    body += [f'    (symbol {q(code + "_1_1")}'] + lines + ['    )', '  )', ')']
    return '\n'.join(header + body) + '\n'


GUESS = re.compile(r'guess|assum|infer|my reading|not drawn|not stated|not marked|not shown|not labell?ed|does not say|unclear|is not explained', re.I)


def guesses(r):
    """What a reading says it had to guess: which insert contact sends and which returns, and
    polarity put on contacts the drawing marks no + / − for."""
    out = []
    texts = ' '.join([r.get('notes') or ''] + [str(u) for u in r.get('unread') or []] + [str(i.get('note') or '') for i in r.get('inserts') or []])
    sentences = re.split(r'(?<=[.;])\s+|(?<=[a-z0-9)])\s+(?=[A-Z][a-z]+ )', texts)
    if r.get('inserts'):
        hit = [s for s in sentences if re.search(r'insert|send|return|source|destination', s, re.I) and GUESS.search(s)]
        empty = [i for i in r['inserts'] if not i.get('send') or not i.get('return')]
        if hit or empty:
            out.append(('insert guessed', (hit[0].strip()[:220] if hit else 'an insert without its send or return named')))
    # Polarity put on a contact whose label carries no + / − (nor RD / BK, HI / LO)
    mark = re.compile(r'[+\-−]|\b(PLUS|MINUS|POS|NEG|HI|LO|HIGH|LOW|RD|BK|RED|BLACK|TIP|RING)\b', re.I)
    assumed = [p for p in r.get('pins') or [] if p.get('polarity') in ('+', '-') and p.get('kind') not in ('power',)
               and not mark.search(str(p.get('as_drawn') or ''))]
    if assumed:
        out.append(('polarity assumed', f"{len(assumed)} contacts given + / − that the drawing does not mark "
                                        f"(e.g. {assumed[0].get('connector') or 'P1'}-{assumed[0].get('pin')} {assumed[0].get('signal')})"))
    return out


DOC_MD = os.path.join(ENG, 'PINOUTS.md')
DOC_HTML = os.path.join(ENG, 'PINOUTS.html')
DOC_URL = 'https://github.com/WardBeckSystems/WBSps.ca/blob/main/2026/Engineering/PINOUTS.md'

TREE = """flowchart TD
  P[Pinout picture in a module folder] --> R[Read by eye into its own .pinout.json]
  R --> Q1{Is it a pinout?}
  Q1 -- no --> X[pinout: false · kept, not used · listed below]
  Q1 -- yes --> Q2{Does the title block name models?}
  Q2 -- yes --> N[Counts for every model it names, wherever it is filed]
  Q2 -- no --> F[Counts for the module whose folder holds it]
  N --> Q3{Filed under a model it does not name?}
  Q3 -- yes --> M[Misfiled · listed below]
  Q3 -- no --> C
  M --> C
  F --> C
  C{A row drawn A pipe 1} -- one label --> S[Both contacts carry it · one stacked pin on the symbol]
  C -- a label each side --> T[Two contacts of their own]
  S --> K
  T --> K
  K{Connector named?} -- no --> P1[Called P1 · the sheet's single connector is the same one]
  K -- yes --> AS[As drawn]
  P1 --> POL
  AS --> POL
  POL{+ / − drawn?} -- yes --> PY[Polarity as drawn]
  POL -- no --> PN[Polarity null · or assumed and listed below]
  PY --> INS
  PN --> INS
  INS{Insert?} -- send and return labelled --> IP[One insert: send = out, return = in, a pair]
  INS -- only INSERT written --> IG[Pair split by row order · listed below]
  INS -- none --> MG
  IP --> MG
  IG --> MG
  MG[Merge per contact: own drawing first, then high · medium · low confidence] --> SH{RTO-144 sheet says the same kind?}
  SH -- yes, or bus = in/out, or strap / other --> OK[Agrees]
  SH -- no --> CF[Picture kept · conflict listed below]
  OK --> OUT[RTO.json + KICAD symbol]
  CF --> OUT
  OUT --> SYM[Symbol: inputs left · outputs right · each insert a send / return block · power top · grounds bottom · N/C not drawn]"""

RULES = [
    ('Which module a picture belongs to', 'The models named in its title block (`applies_to`), wherever the file sits. A picture whose title names none counts for the folder it is in. A picture filed under a model it does not name is listed as misfiled; it still counts for the models it names.'),
    ('Two-sided edge connectors', 'A row drawn "A | 1" with one label: both contacts carry it, and the symbol shows them as one stacked pin (the letter hidden under the number). A row with a label on each side: two contacts of their own.'),
    ('Connector names', 'A drawing that names no connector is read as P1. When the RTO-144 sheet has a single connector of another name (often P2) it is the same connector.'),
    ('Polarity', 'Only as drawn. Most WBS rear views mark no + / −: polarity is null and the port\'s contacts are keyed a / b. A reading that assumed polarity says so in its notes and is listed below.'),
    ('Inserts', 'Always a pair: the send is the module\'s output to the outboard gear (`insert_send`), the return its input back (`insert_return`). Insert out / in, send / return, pre-fader out / fader return, EQ / compressor inserts count. Where a drawing writes only "INSERT" on several contacts the split into send and return is a guess from row order, listed below.'),
    ('Straps', 'Jumpers and strap options from the picture, plus the RTO-144 sheet\'s frame straps. A strap rides on a contact that also carries a signal, so it never disagrees with it.'),
    ('Merging readings', 'Per contact: a module\'s own drawing before a variant\'s, then high before medium before low confidence. A second reading of another kind is a conflict.'),
    ('The RTO-144 sheet', 'A check only, never the source. Same kind = agrees (a bus contact is fed or read, so bus matches in and out; "other" fits anything). Otherwise the picture is kept and the disagreement listed.'),
    ('The symbol', 'Inputs, control inputs, straps and others on the left; outputs and control outputs on the right; each insert a dashed send / return block of its own under the outputs; power on top; grounds, chassis and loose shields at the bottom; N/C contacts not drawn. The old symbol\'s properties (title, category, year …) are kept; no ";;" comments (KiCad 9 will not load them).'),
]


def write_docs(docs, all_reads, mods):
    """2026/Engineering/PINOUTS.md (+ .html): how a picture becomes RTO.json and the symbol, and what to check."""
    names = lambda r: {x.strip().upper() for x in (r.get('applies_to') or [])}
    notp, misfiled, unbuilt = [], [], []
    for code, rs in sorted(all_reads.items()):
        for r in rs:
            if r.get('pinout') is False:
                notp.append((code, r.get('picture'), (r.get('notes') or '').split('. ')[0]))
            elif names(r) and code not in names(r):
                misfiled.append((code, r.get('picture'), ', '.join(sorted(names(r)))))
        if code not in docs:
            unbuilt.append((code, ', '.join(sorted({n for r in rs for n in names(r)} - {code})) or '-'))
    md = ['# Pinouts: from the pictures to RTO.json and the KiCad symbol', '',
          'Every pinout picture of a module (connector layouts, rear views, pin-out pages, plug connections, strapping) is read '
          'by eye into `<picture>.pinout.json` beside it (format: [`tools/pinout_schema.md`](../../tools/pinout_schema.md)). '
          '[`tools/pinout_build.py`](../../tools/pinout_build.py) merges them into each module\'s `RTO.json` and '
          '`KICAD/<code>.kicad_sym`, and writes this page.', '',
          f'**{sum(len(v) for v in all_reads.values())} pictures read · {len(docs)} modules built · '
          f'{sum(len(d["pins"]) for d in docs.values())} contacts · {sum(len(d["inserts"]) for d in docs.values())} inserts · '
          f'{sum(len(d["to_check"]) for d in docs.values())} things to check**', '',
          '## Decision tree', '', '```mermaid', TREE.replace('&lt;', '<').replace('&gt;', '>'), '```', '', '## Rules', '']
    for k, v in RULES:
        md += [f'- **{k}.** {v}']
    md += ['', '## To check', '', 'Where a reading had to guess, or two sources disagree. Each module\'s `RTO.json` carries its own list (`to_check`).', '']
    for code, d in sorted(docs.items()):
        if not d['to_check']:
            continue
        md += [f'### {code}', '']
        md += [f"- **{c['what']}**{' ' + c['pin'] if c.get('pin') else ''}: {c['detail']}" for c in d['to_check']]
        md += ['']
    md += ['## Misfiled pictures', '', 'Filed under a model their title block does not name; they count for the models they name.', '',
           '| Folder | Picture | Title names |', '|---|---|---|'] + [f'| {a} | {b} | {c} |' for a, b, c in misfiled]
    md += ['', '## Not pinouts', '', 'Read and kept (`"pinout": false`), not used.', '', '| Folder | Picture | What it is |', '|---|---|---|']
    md += [f'| {a} | {b} | {c} |' for a, b, c in notp]
    md += ['', '## Modules with pictures but no pinout of their own', '',
           'Their pictures name other models only; RTO.json and the symbol stay as they were.', '', '| Module | Its pictures name |', '|---|---|']
    md += [f'| {a} | {b} |' for a, b in unbuilt]
    md += ['', '---', 'Archive: Anthony Peter Kuzub · [WBSps.ca](https://WBSps.ca) · [WBSps.Kuzub.com](https://WBSps.Kuzub.com)', '']
    with open(DOC_MD, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(md))
    with open(DOC_HTML, 'w', encoding='utf-8') as fh:
        fh.write(md_html('\n'.join(md)))


def md_html(md):
    """The page as HTML for the Pages site: the archive's paper look, the tree drawn by Mermaid."""
    import html as H
    out, table, code = [], None, None
    inline = lambda s: re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: f'<a href="{H.escape(m.group(2).replace(".md", ".md"))}">{m.group(1)}</a>',
                              re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', re.sub(r'`([^`]+)`', r'<code>\1</code>', H.escape(s, quote=False))))
    for ln in md.split('\n'):
        if code is not None:
            if ln.startswith('```'):
                out.append(f'<pre class="mermaid">{H.escape(chr(10).join(code))}</pre>')
                code = None
            else:
                code.append(ln)
            continue
        if ln.startswith('```'):
            code = []
            continue
        if ln.startswith('|'):
            cells = [c.strip() for c in ln.strip('|').split('|')]
            if set(''.join(cells)) <= set('-: '):
                continue
            if table is None:
                table = []
                out.append('<table><tr>' + ''.join(f'<th>{inline(c)}</th>' for c in cells) + '</tr>')
            else:
                out.append('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in cells) + '</tr>')
            continue
        if table is not None:
            out.append('</table>')
            table = None
        m = re.match(r'^(#{1,3}) (.*)', ln)
        if m:
            n = len(m.group(1))
            out.append(f'<h{n}>{inline(m.group(2))}</h{n}>')
        elif ln.startswith('- '):
            out.append(f'<p class="li">{inline(ln[2:])}</p>')
        elif ln == '---':
            out.append('<hr>')
        elif ln.strip():
            out.append(f'<p>{inline(ln)}</p>')
    if table is not None:
        out.append('</table>')
    body = '\n'.join(out)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pinouts decision tree</title>
<style>
:root {{ --desk:#2b2a27; --paper:#fbfaf4; --ink:#1f1e1c; --faint:#6d6a63; --rule:#cfcabc; --link:#1f3f6b; --hl:#efe9d2; }}
@media (prefers-color-scheme: dark) {{ :root {{ --desk:#141412; --paper:#22211e; --ink:#e9e5d8; --faint:#a29d90; --rule:#4a473f; --link:#9cc0f0; --hl:#3a372e; }} }}
* {{ box-sizing:border-box }} html {{ background:var(--desk) }}
body {{ margin:0; padding:28px 16px 60px; color:var(--ink); background:var(--desk); font:15px/1.55 "Courier Prime","Courier New",Courier,monospace }}
.sheet {{ max-width:9.5in; margin:0 auto; background:var(--paper); padding:clamp(20px,5vw,56px) clamp(16px,5vw,64px) 48px; box-shadow:0 18px 40px rgba(0,0,0,.5) }}
a {{ color:var(--link) }} h1 {{ font-size:20px; text-transform:uppercase; text-decoration:underline }} h2 {{ font-size:16px; text-transform:uppercase; margin-top:28px }}
h3 {{ font-size:15px; margin:18px 0 4px }} p.li {{ margin:4px 0 4px 1.2em; text-indent:-1.2em }} p.li::before {{ content:"– " }}
table {{ border-collapse:collapse; width:100%; margin:8px 0; font-size:13px; display:block; overflow-x:auto }}
th, td {{ border:1px solid var(--rule); padding:3px 6px; text-align:left; vertical-align:top }}
code {{ background:var(--hl); padding:0 3px }} pre.mermaid {{ background:#fff; color:#000; padding:12px; overflow-x:auto }}
</style></head><body><div class="sheet">
{body}
</div>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{ startOnLoad: true, theme: 'neutral', flowchart: {{ useMaxWidth: true }} }});</script>
</body></html>
"""


def readme_section(moddir):
    """The README's "RTO-144 pinout" section, rewritten in place from the new RTO.json."""
    f = os.path.join(moddir, 'README.md')
    if not os.path.exists(f):
        return
    sys.path.insert(0, HERE)
    from make_module_readmes import pin_table
    text = open(f, encoding='utf-8').read()
    new = '\n'.join(pin_table(moddir))
    m = re.search(r'^## RTO-144 pinout\n.*?(?=^## |^---$|\Z)', text, re.S | re.M)
    if m:
        text = text[:m.start()] + new + '\n' + text[m.end():]
    else:   # before the KiCad section (or the footer)
        m = re.search(r'^## KiCad|^---$', text, re.M)
        at = m.start() if m else len(text)
        text = text[:at] + new + '\n' + text[at:]
    open(f, 'w', encoding='utf-8').write(re.sub(r'\n{3,}', '\n\n', text))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=CLONES)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('codes', nargs='*')
    a = ap.parse_args()
    mods = module_dirs(a.root)
    all_reads = {}
    for code, ds in mods.items():
        for d in ds:
            for r in readings(d):
                r['_src'] = f'{code}/{r["_file"]}'
                all_reads.setdefault(code, []).append(r)
    variants = {}
    for code, rs in all_reads.items():
        for r in rs:
            for other in set(r.get('applies_to') or []) - {code}:
                variants.setdefault(other, []).append(r)
    todo = a.codes or sorted(set(all_reads) | (set(variants) & set(mods)))
    total = {'modules': 0, 'pins': 0, 'conflicts': 0, 'to_check': 0}
    docs = {}
    for code in todo:
        ds = mods.get(code)
        if not ds:
            continue
        doc = build(code, all_reads.get(code, []), variants.get(code, []))
        if not doc:
            continue
        total['modules'] += 1
        total['pins'] += len(doc['pins'])
        total['conflicts'] += len(doc['conflicts'])
        total['to_check'] += len(doc['to_check'])
        docs[code] = doc
        print(f'{code}: {len(doc["pins"])} pins, {len(doc["ports"])} ports, {len(doc["inserts"])} inserts, '
              f'{len(doc["conflicts"])} conflicts, sheet agrees {doc["built_from"]["sheet_agrees"]}')
        if a.check:
            continue
        for d in ds:
            write_module(d, code, doc)
    if not a.check and not a.codes:
        write_docs(docs, all_reads, mods)
    print(total)


def write_module(d, code, doc):
    """RTO.json, the README section and the symbol into one module repo."""
    with open(os.path.join(d, 'RTO.json'), 'w', encoding='utf-8') as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=1) + '\n')
    sym = os.path.join(d, 'KICAD', f'{code}.kicad_sym')
    old = open(sym, encoding='utf-8').read() if os.path.exists(sym) else None
    if old is None:
        src = os.path.join(ENG, 'RTO-144', code, f'{code}.kicad_sym')
        old = open(src, encoding='utf-8').read() if os.path.exists(src) else None
    readme_section(d)
    os.makedirs(os.path.dirname(sym), exist_ok=True)
    if os.path.islink(sym) or (os.path.exists(sym) and os.stat(sym).st_nlink > 1):
        os.unlink(sym)   # a hard link into Engineering: this module's own symbol now
    with open(sym, 'w', encoding='utf-8') as fh:
        fh.write(symbol(code, doc, old))


if __name__ == '__main__':
    main()
