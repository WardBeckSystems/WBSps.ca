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
MODULES.<CAT>.<M>-<Function> clones); 2026/Modules/<CAT>/<M> works too. --check: report only.
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
        if os.path.isdir(d):
            out.setdefault(code_of(d), d)
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
    if a in (None, 'other') or b in (None, 'other') or a == b:
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
    for code, d in mods.items():
        for r in readings(d):
            r['_src'] = f'{code}/{r["_file"]}'
            all_reads.setdefault(code, []).append(r)
    variants = {}
    for code, rs in all_reads.items():
        for r in rs:
            for other in set(r.get('applies_to') or []) - {code}:
                variants.setdefault(other, []).append(r)
    todo = a.codes or sorted(set(all_reads) | (set(variants) & set(mods)))
    total = {'modules': 0, 'pins': 0, 'conflicts': 0}
    for code in todo:
        d = mods.get(code)
        if not d:
            continue
        doc = build(code, all_reads.get(code, []), variants.get(code, []))
        if not doc:
            continue
        total['modules'] += 1
        total['pins'] += len(doc['pins'])
        total['conflicts'] += len(doc['conflicts'])
        print(f'{code}: {len(doc["pins"])} pins, {len(doc["ports"])} ports, {len(doc["inserts"])} inserts, '
              f'{len(doc["conflicts"])} conflicts, sheet agrees {doc["built_from"]["sheet_agrees"]}')
        if a.check:
            continue
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
    print(total)


if __name__ == '__main__':
    main()
