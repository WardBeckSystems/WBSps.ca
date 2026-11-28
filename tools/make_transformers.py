#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Transformers: one repo (WardBeckSystems/Transformers) for every Ward-Beck transformer, a folder per type.

    python3 tools/make_transformers.py [--dry-run]

  Transformers/60-n Input/60-14/       each type: its drawings (picture + its .md note beside it) and a README
  Transformers/70-n Output/70-8/       (title, year, drawn by, the modules it is used in)
  Transformers/80-n Power/80-10/
  Transformers/FOOTPRINTS/             PCB pad footprints for the transformers
From the registers (PAGES/Register-*-transformers-*.md); the pictures from the PHOTOS repo clone
(Github.WardBeckSystems/PHOTOS), their notes from the site's PHOTOS/. Copied, not moved: the originals are
retired once the repo is on GitHub (then the site links point here). No empty folders.
"""
import os, re, shutil, sys
from urllib.parse import unquote

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = os.path.join(TOP, 'WBSps.ca', 'Github.WardBeckSystems')
OUT = os.path.join(G, 'Transformers')
SITE = 'https://wardbecksystems.github.io/WBSps.ca/'
GROUPS = [('Input-transformers-60-n', '60-n Input', 'input transformers'),
          ('Output-transformers-70-n', '70-n Output', 'output transformers'),
          ('Power-transformers-80-n', '80-n Power', 'power transformers')]
FOOT = os.path.join(TOP, '2026', 'PARTS', 'Footprints', 'Transformer #footprint')


def find_picture(rel):
    """A register link (from PAGES/) -> the picture's file now: the repo clone first, then the site."""
    p = os.path.normpath(os.path.join('PAGES', unquote(rel))).replace(os.sep, '/')
    for c in (os.path.join(G, p), os.path.join(TOP, p), os.path.join(TOP, '2026', p)):
        if os.path.isfile(c):
            return c, p
    return None, p


def main():
    dry = '--dry-run' in sys.argv
    top = ['# Transformers', '', "Ward-Beck Systems' own transformers: 60-n input, 70-n output and 80-n power types, "
           'their drawings and the modules each is used in. One folder per type.', '']
    total = pics = 0
    for reg, folder, what in GROUPS:
        t = open(os.path.join(TOP, 'PAGES', f'Register-{reg}.md'), encoding='utf-8').read()
        top += [f'## {folder} ({what})', '', '| Type | Title | Year | Used in |', '|---|---|---|---|']
        for blk in re.split(r'(?m)^<a id="[^"]+"></a>\s*$', t)[1:]:
            m = re.search(r'^### (\d\d-\w+) — (.*)$', blk, re.M)
            if not m:
                continue
            typ, title = m.group(1), m.group(2)
            title = re.sub(rf'^{re.escape(typ)}\s*/?\s*|\s*/\s*TYPE\s+{re.escape(typ)}$|\s+{re.escape(typ)}\b', ' ', title).strip(' /')
            year = (re.search(r'\[(\d{4})\\?\|', blk) or [None, ''])[1]
            drawn = ', '.join(re.findall(r'drawn \[([^\]]+)\]', blk))
            used = re.findall(r'\[([^\]]+)\]\([^)]+\.md\)', (re.search(r'^Used in: (.*)$', blk, re.M) or [None, ''])[1])
            d = os.path.join(OUT, folder, typ)
            files = []
            for name, href in re.findall(r'\[([^\]]+\.(?:jpg|jpeg|png|pdf|tif|tiff))\]\(([^)]+)\)', blk, re.I):
                src, p = find_picture(href)
                if src:
                    files.append((name, src, p))
            total += 1
            top.append(f'| [{typ}]({quote_path(folder)}/{typ}/) | {title.title()} | {year} | {", ".join(used)} |')
            if dry:
                print(f'{folder}/{typ}: {title} · {len(files)} drawings · used in {",".join(used)[:50]}')
                continue
            os.makedirs(d, exist_ok=True)
            lines = [f'# {typ} · {title.title()}', '', f'Ward-Beck Systems {what[:-1]} type {typ}' +
                     (f', {year}' if year else '') + (f', drawn by {drawn}' if drawn else '') + '.', '']
            if used:
                lines += ['## Used in', '', ' · '.join(f'[{u}]({SITE}PAGES/{u}.html)' for u in used), '']
            if files:
                lines += ['## Drawings', '']
            for name, src, p in files:
                dst = os.path.join(d, name)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    pics += 1
                for note in (os.path.join(TOP, p + '.md'), os.path.join(TOP, '2026', p + '.md')):   # its note beside it
                    if os.path.isfile(note) and not os.path.exists(dst + '.md'):
                        shutil.copy2(note, dst + '.md')
                        break
                lines.append(f'![{name}]({quote_path(name)})  ')
                lines.append(f'[{name}]({quote_path(name)}) · [note]({quote_path(name)}.md)' if os.path.exists(dst + '.md') else '')
            open(os.path.join(d, 'README.md'), 'w', encoding='utf-8').write('\n'.join(lines + ['']))
        top.append('')
    if os.path.isdir(FOOT) and not dry:
        dst = os.path.join(OUT, 'FOOTPRINTS')
        os.makedirs(dst, exist_ok=True)
        for f in os.listdir(FOOT):
            if f != 'index.html' and os.path.isfile(os.path.join(FOOT, f)):
                shutil.copy2(os.path.join(FOOT, f), dst)
        top += ['## Footprints', '', '[FOOTPRINTS/](FOOTPRINTS/): PCB pad footprints for the transformers.', '']
    top += ['---', '© Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca) · archive by Anthony Peter Kuzub · '
            '[WBSps.ca](https://WBSps.ca) · [WBSps.Kuzub.com](https://WBSps.Kuzub.com)', '']
    if not dry:
        open(os.path.join(OUT, 'README.md'), 'w', encoding='utf-8').write('\n'.join(top))
        gi = os.path.join(TOP, 'tools', 'module.gitignore')
        if os.path.exists(gi) and not os.path.exists(os.path.join(OUT, '.gitignore')):
            shutil.copy2(gi, os.path.join(OUT, '.gitignore'))
    print(f'{total} transformer types, {pics} drawings copied' + (' (dry run)' if dry else f' -> {OUT}'))


def quote_path(s):
    return s.replace(' ', '%20').replace('(', '%28').replace(')', '%29')


if __name__ == '__main__':
    main()
