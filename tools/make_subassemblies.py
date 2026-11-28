#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Sub-assemblies: every SA14-nnn board assembly its own folder (then its own repo SUBASSEMBLY.SA14-nnn-<Title>),
in WBSps.ca/Github.WardBeckSystems beside the module repos.

    python3 tools/make_subassemblies.py [--dry-run]          folders + README (safe to rerun: README rewritten)
    python3 tools/make_subassemblies.py --populate [--dry-run]   move the boards in (see below)

Where the list comes from (all of it, so the picture is complete):
  PAGES/Register-Circuit-boards-SA14-nnn.md   the drawings' title blocks: title, year, the modules each board is used in
  Engineering/PCB/14-nnn*/board.json          the Tango / Eagle boards converted to KiCad; the folder the original
                                              file was found in names the module or product it was made for
  Engineering/ORCAD/*SA14-nnn*                OrCAD schematics, netlists and BOMs
One folder per base number: issues A, B ... (14-273A, 14-277B) are the same board and go inside it.

Each folder has the module kind folders (SCHEMATICS/ MECHANICAL/ KICAD/ OCR/ PHOTOS/ MANUALS/) and a README:
title, used in (modules / products), the drawings with links to where they are now, the boards. --populate moves
Engineering/PCB/14-nnn* into KICAD/<board>/ and Engineering/ORCAD SA14 sets into SCHEMATICS/ORCAD/<set>/ (the
published copies are moved; their 2026/ duplicates go to the Trash, logged in tools/trash_log.csv).
"""
import json, os, re, shutil, subprocess, sys
from collections import defaultdict
from datetime import date

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = os.path.join(TOP, 'WBSps.ca', 'Github.WardBeckSystems')
REG = os.path.join(TOP, 'PAGES', 'Register-Circuit-boards-SA14-nnn.md')
PCB = os.path.join(TOP, 'Engineering', 'PCB')
ORCAD = os.path.join(TOP, 'Engineering', 'ORCAD')
KINDS = ['SCHEMATICS', 'MECHANICAL', 'KICAD', 'MANUALS', 'PHOTOS', 'OCR']
SITE = 'https://wardbecksystems.github.io/WBSps.ca/'
OWNER = 'WardBeckSystems'
JUNK = re.compile(r'(?i)^(schematic$|all resistors are|ase noleh|last component|unless all|parts list|iii\)|\d+ p1 connector)')
PARENT = re.compile(r'\b(R?M\d{3,4}[A-Z]{0,3}|POD\s?\d+[A-Z]?|AP\d{5}|D\d{4}[A-Z]?|IKR-?\d+[A-Z]?|microCOM(?: II)?)\b')


def clean(s):
    s = re.sub(r'^B\s+14-\d+-\d+-\d+(?:-\d+)?\s*-\s*', '', s)
    s = re.sub(r'^(?:PARTS LIST\s+)?(SA)?14-\d+[A-Z]*\s*(?:/|-)?\s*', '', s, flags=re.I)
    s = re.sub(r'\s*(?:/\s*)?(SCHEMATIC|COMPONENT LAYOUT|FUNCTIONAL|LAYOUT)\s*-?\s*$', '', s, flags=re.I)
    s = re.sub(r'\s*-\s*ASSEMBLY\s*-?\s*$', ' ASSEMBLY', s, flags=re.I).strip(' -/;')
    s = re.sub(r'^(?:POD\s?\d+[A-Z]?|R?M\d{3,4}[A-Z]*)\s*-\s*', '', s).strip()   # the parent's name in front
    s = re.sub(r'(?i)\(orcad\)|^\d{2}-\d{3}(?:\s|$)|\b14-\d+[-_\d]*\b', '', s).strip(' -/;')
    return '' if JUNK.match(s) or re.fullmatch(r'(AP\d+|M\d+[A-Z]*|POD\s*\d+|\(ORCAD\).*)', s) else s


def title_case(s):
    small = {'and', 'or', 'of', 'to', 'the', 'a'}
    s = re.sub(r'(?i)\bpramplifier\b', 'Preamplifier', s)
    w = re.sub(r'\s+', ' ', s).strip().split(' ')
    return ' '.join(x if re.search(r'\d|^(VU|DC|AC|SR|PA|IKR|LED|PCB|CPU|SA|II|III)$', x) else
                    (x.lower() if x.lower() in small and i else x.capitalize()) for i, x in enumerate(w))


def gather():
    sa = defaultdict(lambda: dict(titles=[], used=set(), drawings=[], boards=[], orcad=[], years=set()))
    t = open(REG, encoding='utf-8').read()
    for blk in re.split(r'(?m)^<a id="[^"]+"></a>\s*$', t)[1:]:
        m = re.search(r'^### SA14-(\d+)[A-Z]* — (.*)$', blk, re.M)
        if not m:
            continue
        e = sa[m.group(1)]
        e['titles'].append(clean(m.group(2)))
        u = re.search(r'^Used in: (.*)$', blk, re.M)
        if u:
            e['used'] |= set(re.findall(r'\[([^\]]+)\]\([^)]+\.md\)', u.group(1)))
        y = re.search(r'\[(\d{4})\\?\|', blk)
        if y:
            e['years'].add(y.group(1))
        for name, href in re.findall(r'\[([^\]]+\.(?:jpg|png|pdf|tif|svg))\]\(([^)]+)\)', blk, re.I):
            e['drawings'].append((name, href))
    for d in sorted(os.listdir(PCB)):
        m = re.match(r'14-(\d+)([A-Z]*)\b(?:\s*-\s*(.*))?$', d)
        if not m or not os.path.isdir(os.path.join(PCB, d)):
            continue
        e = sa[m.group(1)]
        e['boards'].append(d)
        rest = re.sub(r'^SA14-\d+[A-Z]*\s*', '', m.group(3) or '')
        if rest:
            e['titles'].append(clean(rest))
            e['used'] |= set(PARENT.findall(rest))
        try:
            src = json.load(open(os.path.join(PCB, d, 'board.json'))).get('source', '')
        except (OSError, ValueError):
            src = ''
        e['used'] |= {p.replace(' ', '') for p in PARENT.findall(src.replace('_', ' '))}
    for d in sorted(os.listdir(ORCAD)):
        m = re.search(r'SA14-(\d+)', d)
        if m and os.path.isdir(os.path.join(ORCAD, d)):
            e = sa[m.group(1)]
            e['orcad'].append(d)
            try:
                e['titles'].append(clean(json.load(open(os.path.join(ORCAD, d, 'orcad.json'))).get('title', '')))
            except (OSError, ValueError):
                pass
    for n, e in sa.items():
        norm = {}
        for u in e['used']:
            k = re.sub(r'[\s-]', '', u).upper()
            norm.setdefault(k, u.replace(' ', ''))
        e['used'] = set(norm.values())   # "POD 7" and "POD7" are one
    for n, e in sa.items():   # M405P is matched into almost every register entry (a database mix-up): kept only alone
        if len(e['used']) > 1:
            e['used'].discard('M405P')
        e['titles'] = [x for x in e['titles'] if x]
        e['title'] = title_case(max(e['titles'], key=lambda x: (e['titles'].count(x), len(x)))) if e['titles'] else ''
    return dict(sorted(sa.items(), key=lambda x: int(x[0])))


def repo_name(n, e):
    slug = re.sub(r'[^A-Za-z0-9]+', '-', e['title']).strip('-')
    return f'SUBASSEMBLY.SA14-{n}' + (f'-{slug}' if slug else '')


def readme(n, e, name):
    rel = os.path.relpath(TOP, os.path.join(G, name))
    lines = [f'# SA14-{n}' + (f' · {e["title"]}' if e['title'] else ''), '',
             f'Ward-Beck Systems sub-assembly SA14-{n}' + (f', {", ".join(sorted(e["years"]))}' if e['years'] else '') +
             '. A circuit-board assembly used inside modules and products; issues A, B … are kept here together.', '']
    if e['used']:
        lines += ['## Used in', '', ' · '.join(f'[{u}]({SITE}PAGES/{u.replace(" ", "%20")}.html)' for u in sorted(e['used'])), '']
    what = {'SCHEMATICS': 'schematics, component layouts, OrCAD projects (SCHEMATICS/ORCAD)',
            'MECHANICAL': 'board outlines, brackets, assemblies',
            'KICAD': 'the board files converted to KiCad (one folder per board issue), top and bottom renders',
            'MANUALS': 'parts lists, manual pages', 'PHOTOS': 'photographs of the board', 'OCR': 'the note of every file'}
    here = os.path.join(G, name)
    full = [k for k in KINDS if os.path.isdir(os.path.join(here, k)) and any(os.scandir(os.path.join(here, k)))]
    if full:   # only the folders that hold something
        lines += ['| Folder | What is in it |', '|---|---|'] + [f'| [{k}/]({k}/) | {what[k]} |' for k in full] + ['']
    if e['boards']:
        lines += ['## Boards', ''] + [f'- `{b}`' for b in e['boards']] + ['']
    if e['orcad']:
        lines += ['## OrCAD', ''] + [f'- `{o}`' for o in e['orcad']] + ['']
    if e['drawings']:
        lines += ['## Drawings (in the module and console repos)', '']
        for name, href in e['drawings']:
            h = href if href.startswith('http') else SITE + os.path.normpath(os.path.join('PAGES', href)).replace(os.sep, '/')
            lines.append(f'- [{name}]({h})')
        lines.append('')
    lines += ['---', '© Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca) · archive by Anthony Peter Kuzub · '
              '[WBSps.ca](https://WBSps.ca) · [WBSps.Kuzub.com](https://WBSps.Kuzub.com)', '']
    return '\n'.join(lines)


def main():
    dry = '--dry-run' in sys.argv
    sa = gather()
    gi = open(os.path.join(TOP, 'tools', 'module.gitignore')).read() if os.path.exists(os.path.join(TOP, 'tools', 'module.gitignore')) else ''
    index = {}
    for n, e in sa.items():
        name = repo_name(n, e)
        index[name] = dict(sa=f'SA14-{n}', title=e['title'], used=sorted(e['used']), boards=e['boards'], orcad=e['orcad'])
        print(f'{name:60} used {",".join(sorted(e["used"]))[:40]:40} boards {len(e["boards"])} orcad {len(e["orcad"])} drawings {len(e["drawings"])}')
        if dry:
            continue
        d = os.path.join(G, name)
        old = [x for x in os.listdir(G) if x.startswith(f'SUBASSEMBLY.SA14-{n}') and x != name and
               re.match(rf'SUBASSEMBLY\.SA14-{n}(?:-|$)', x)]
        for o in old:   # renamed since the last run (a better title)
            os.rename(os.path.join(G, o), d) if not os.path.exists(d) else None
        os.makedirs(d, exist_ok=True)   # kind folders only when something goes in them (no empty folders)
        open(os.path.join(d, 'README.md'), 'w', encoding='utf-8').write(readme(n, e, name))
        if gi and not os.path.exists(os.path.join(d, '.gitignore')):
            open(os.path.join(d, '.gitignore'), 'w').write(gi)
    if not dry:
        json.dump(index, open(os.path.join(TOP, 'tools', 'subassemblies.json'), 'w'), indent=1)
    print(f'{len(sa)} sub-assemblies' + (' (dry run)' if dry else f' in {G}'))


if __name__ == '__main__':
    main()
