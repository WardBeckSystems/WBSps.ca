#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""What the pipeline knows about a module, filed into its own folder (Products/Modules/<CATEGORY>/<Mxxx>/):

  <drawing> (EXTRACTED).svg   beside every traced scan (and "<pdf> p<N> (EXTRACTED).svg" beside a traced PDF):
                              the tracer's vectors (_traces/<sha16>.svg: line work, lettering, title block, centre lines)
  KICAD/<drawing>.kicad_sch   a KiCad schematic from each extracted electrical drawing (-01- functional, -02- schematic,
                              -09- wiring), made by timelines/trace_cad.cjs; <Mxxx>.kicad_sym, the module's symbol;
                              PCB <board>/ the module's KiCad PCB projects from Engineering/PCB
  MECHANICAL/<Mxxx> - front panel.svg   the front panel as vectors (_catalog/panels), where one has been drawn
  PINOUTS/                    the RTO-144 connector and connections drawings (Engineering/RTO-144, Engineering/IO)
  RTO.json                    the RTO-144 edge connector pin by pin: signal, kind, pair and polarity, how sure, where read

Files are hard links to the pipeline's copies (one set of bytes); run again after a rebuild, it only adds what changed.

    python3 tools/module_extras.py [Products/Modules/CAT/M ...]
"""
import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Y2026 = os.path.join(ROOT, '2026')
ENG = os.path.join(Y2026, 'Engineering')
DB = os.path.join(Y2026, 'timelines', 'wbs_timeline.db')
TRACES = os.path.join(Y2026, '_traces')
CAD = os.path.join(Y2026, 'timelines', 'trace_cad.cjs')
ELECTRICAL = {'01', '02', '09'}
DTYPE = re.compile(rb'data-dtype="(\d\d)"')


def link(src, dst):
    """dst becomes a hard link to src (a copy where linking fails); nothing done when it already is."""
    try:
        if os.path.exists(dst) and os.path.samefile(src, dst):
            return False
        if os.path.lexists(dst):
            os.remove(dst)
    except OSError:
        pass
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)
    return True


def traces_by_module(con):
    """{module dir (relative to 2026): [(2026 path of the scan, page or None, traced svg)]}

    A trace is kept by the scan's sha256 under the path it was traced at (traces.dest); every filed copy with the same
    bytes (table files: a module's kind folders, other modules, moved files) gets it too."""
    out = {}
    copies = {}
    for dest, h in con.execute("SELECT dest, sha256 FROM files WHERE dest LIKE 'Modules/%'"):
        copies.setdefault(h, []).append(dest)
    rows = []
    for h, d, i in con.execute("SELECT sha256, dest, info FROM traces WHERE made != ''"):
        rows += [(c, None, i) for c in set(copies.get(h, [])) | ({d} if d.startswith('Modules/') else set())]
    for h, p, d, i in con.execute("SELECT sha256, page, dest, info FROM trace_pages WHERE made != ''"):
        rows += [(c, p, i) for c in set(copies.get(h, [])) | ({d} if d.startswith('Modules/') else set())]
    for dest, page, info in rows:
        try:
            svg = json.loads(info).get('out') or ''
        except ValueError:
            continue
        svg = os.path.join(TRACES, os.path.basename(svg))
        if not os.path.exists(svg):
            continue
        mod = '/'.join(dest.split('/')[:3])
        out.setdefault(mod, []).append((dest, page, svg))
    return out


def pins_doc(code):
    """RTO.json for a module: Engineering/IO/<code>.pins.json (every contact, merged from all its documents) with the
    RTO-144 sheet's straps, power and connector facts (Engineering/RTO-144/<code>/<code>.rto144.json)."""
    pins_f = os.path.join(ENG, 'IO', f'{code}.pins.json')
    sheet_f = os.path.join(ENG, 'RTO-144', code, f'{code}.rto144.json')
    pins = json.load(open(pins_f, encoding='utf-8')) if os.path.exists(pins_f) else None
    sheet = json.load(open(sheet_f, encoding='utf-8')) if os.path.exists(sheet_f) else None
    if not pins and not sheet:
        return None
    doc = {'code': code, 'connector': 'RTO-144',
           'type': (sheet or {}).get('type') or (pins or {}).get('name'),
           'series': (sheet or {}).get('series'),
           'contacts': (sheet or {}).get('connector') or ', '.join(
               f'{c.get("rows")} contacts' + (f' ({c["name"]})' if c.get('name') else '') for c in (pins or {}).get('connectors', [])),
           'verified': (sheet or {}).get('verified'),
           'derived': bool((pins or {}).get('derived')) and not sheet,
           'variant_of': (pins or {}).get('variant_of'),
           'pins': [], 'straps': (sheet or {}).get('jumpers', []), 'power': (sheet or {}).get('power', []),
           'sources': []}
    for p in (pins or {}).get('pins', []):
        doc['pins'].append({'pin': p.get('pin'), 'signal': p.get('signal'), 'kind': p.get('kind'), 'pair': p.get('pair'),
                            'polarity': p.get('pol'), 'confidence': p.get('conf'), 'read_from': p.get('how'),
                            'file': (p.get('src') or {}).get('file'), 'page': (p.get('src') or {}).get('page')})
    if not doc['pins'] and sheet:   # the sheet alone: its ports as contacts
        for a in sheet.get('audio', []):
            for pol, k in (('+', 'pos'), ('-', 'neg')):
                if a.get(k):
                    doc['pins'].append({'pin': a[k], 'signal': a.get('signal'), 'kind': a.get('dir'), 'pair': a.get('port'),
                                        'polarity': pol, 'confidence': 'high', 'read_from': 'rto-144'})
        for o in sheet.get('other', []):
            for pin in o.get('pins', []):
                doc['pins'].append({'pin': pin, 'signal': o.get('signal'), 'kind': o.get('role'), 'confidence': 'high',
                                    'read_from': 'rto-144'})

    def order(p):
        s = str(p.get('pin') or '')
        return (0, int(s)) if s.isdigit() else (1, s)
    doc['pins'].sort(key=order)
    doc['sources'] = sorted({p['file'] for p in doc['pins'] if p.get('file')} |
                            ({os.path.relpath(sheet_f, Y2026)} if sheet else set()))
    return doc


def pcb_projects(code):
    """Engineering/PCB/<board> - <code>/ folders that hold a KiCad project."""
    out = []
    for d in sorted(glob.glob(os.path.join(ENG, 'PCB', '*'))):
        name = os.path.basename(d)
        if os.path.isdir(d) and re.search(r'(^|\s-\s)' + re.escape(code) + r'$', name) and glob.glob(os.path.join(d, '*.kicad_pcb')):
            out.append(d)
    return out


def extras(moddir, traced, pairs):
    rel = os.path.relpath(moddir, Y2026).replace(os.sep, '/')
    code = os.path.basename(moddir)
    n = {'svg': 0, 'kicad': 0, 'pinouts': 0, 'rto': 0, 'panel': 0}
    # EXTRACTED svgs beside their scans; KiCad schematics of the electrical ones
    for dest, page, svg in traced.get(rel, []):
        scan = os.path.join(Y2026, dest)
        if not os.path.exists(scan):
            continue
        stem = os.path.splitext(os.path.basename(scan))[0] + (f' p{page}' if page else '')
        n['svg'] += link(svg, os.path.join(os.path.dirname(scan), f'{stem} (EXTRACTED).svg'))
        with open(svg, 'rb') as fh:
            m = DTYPE.search(fh.read(400))
        if m and m.group(1).decode() in ELECTRICAL:
            pairs.append([svg, os.path.join(moddir, 'KICAD', f'{stem}.kicad_sch')])
    # Pinout pictures read into <picture>.pinout.json: RTO.json and the symbol come from
    # them (tools/pinout_build.py), not from Engineering/IO and the RTO-144 sheet alone
    from_pictures = bool(glob.glob(os.path.join(moddir, '*', '*.pinout.json')))
    # the module symbol, its PCB projects
    for sym in [] if from_pictures else (os.path.join(ENG, 'RTO-144', code, f'{code}.kicad_sym'), os.path.join(ENG, 'KICAD', f'{code}.kicad_sym')):
        if os.path.exists(sym):
            n['kicad'] += link(sym, os.path.join(moddir, 'KICAD', f'{code}.kicad_sym'))
            break
    for d in pcb_projects(code):
        for f in os.listdir(d):
            if f.endswith(('.kicad_pcb', '.kicad_pro', '.kicad_prl', '.kicad_sch', '.svg', '.json')) or f == 'README.md':
                n['kicad'] += link(os.path.join(d, f), os.path.join(moddir, 'KICAD', 'PCB ' + os.path.basename(d), f))
    # the front panel as vectors (_catalog/panels: lifted from its front-panel drawing)
    panel = os.path.join(Y2026, '_catalog', 'panels', f'{code}.svg')
    if os.path.exists(panel):
        n['panel'] = link(panel, os.path.join(moddir, 'MECHANICAL', f'{code} - front panel.svg'))
    # pinout drawings
    for src, name in ((os.path.join(ENG, 'RTO-144', code, 'connector.svg'), f'{code} - RTO-144 connector.svg'),
                      (os.path.join(ENG, 'RTO-144', code, 'io.svg'), f'{code} - RTO-144 inputs and outputs.svg'),
                      (os.path.join(ENG, 'RTO-144', code, f'{code} - RTO-144 Connections.pdf'), f'{code} - RTO-144 Connections.pdf'),
                      (os.path.join(ENG, 'IO', f'{code}.pinout.svg'), f'{code} - pinout.svg'),
                      (os.path.join(ENG, 'IO', f'{code}.connections.svg'), f'{code} - connections.svg')):
        if os.path.exists(src) and not os.path.exists(os.path.join(moddir, name)):   # a top-level copy counts too
            n['pinouts'] += link(src, os.path.join(moddir, 'PINOUTS', name))
    doc = None if from_pictures else pins_doc(code)
    if doc:
        t = json.dumps(doc, ensure_ascii=False, indent=1) + '\n'
        p = os.path.join(moddir, 'RTO.json')
        if not os.path.exists(p) or open(p, encoding='utf-8').read() != t:
            with open(p, 'w', encoding='utf-8') as fh:
                fh.write(t)
            n['rto'] = 1
    return n


def main():
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    traced = traces_by_module(con)
    dirs = [os.path.abspath(a) for a in sys.argv[1:]] or sorted(
        p for p in glob.glob(os.path.join(ROOT, 'Products', 'Modules', '*', '*')) if os.path.isdir(p))
    pairs, tot = [], {}
    for d in dirs:
        for k, v in extras(d, traced, pairs).items():
            tot[k] = tot.get(k, 0) + v
    if pairs:
        for _, out in pairs:
            os.makedirs(os.path.dirname(out), exist_ok=True)
        pf = os.path.join(Y2026, 'timelines', 'logs', 'kicad_pairs.json')
        os.makedirs(os.path.dirname(pf), exist_ok=True)
        with open(pf, 'w', encoding='utf-8') as fh:
            json.dump(pairs, fh)
        r = subprocess.run(['node', CAD, '--pairs', pf], capture_output=True, text=True)
        print(r.stdout.strip() or r.stderr.strip())
    print(f'{len(dirs)} modules: {tot}; {len(pairs)} electrical drawings for KiCad')


if __name__ == '__main__':
    main()
