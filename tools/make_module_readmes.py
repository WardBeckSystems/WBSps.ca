#!/usr/bin/env python3
"""Write README.md in each module folder (2026/Modules/<CATEGORY>/<Mxxx>): every image shown, each one linked
to its Google Drive copy (from 2026/_catalog/drive, made by make_drive_links.py).

    python3 tools/make_module_readmes.py                      # every module
    python3 tools/make_module_readmes.py 2026/Modules/AMPLIFIERS/M124 ...
"""
import glob
import json
import os
import re
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import module_repo_names
from module_layout import KINDS, module_files  # noqa: E402
from sort_module_folders import ABOUT  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Y2026 = os.path.join(ROOT, '2026')
SITE = 'https://wardbecksystems.github.io/WBSps.ca'
IMG = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff', '.bmp')
COLS = 3


def load_drive():
    m = {}
    for f in glob.glob(os.path.join(Y2026, '_catalog', 'drive', '*.json')):
        with open(f, encoding='utf-8') as fh:
            m.update(json.load(fh))
    return m


def year_tag(y):
    return f'{y}|{int(y) - 1967}'   # house style: YYYY|n, n counted from 1967


def drive_view(d):
    url = f'https://drive.google.com/file/d/{d[0]}/view'
    return url + (f'?resourcekey={quote(d[1])}' if len(d) > 1 and d[1] else '')


def drive_thumb(d):
    url = f'https://drive.google.com/thumbnail?sz=w480&id={d[0]}'
    return url + (f'&resourcekey={quote(d[1])}' if len(d) > 1 and d[1] else '')


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def caption(name, module):
    stem = os.path.splitext(name)[0]
    m = re.match(r'^(\d{4}) - (.*)$', stem)
    year, rest = (m.group(1), m.group(2)) if m else (None, stem)
    rest = re.sub(r'^' + re.escape(module) + r' - ', '', rest)
    return (year_tag(year) + ' · ' if year else '') + rest


SECTIONS = (('PHOTOS', 'Photos'), ('MECHANICAL', 'Mechanical'), ('SCHEMATICS', 'Schematics'), ('PINOUTS', 'Pinouts'),
            ('MANUALS', 'Manuals and documents'))
SHOWN = IMG + ('.pdf',)
SHORT = {'SCHEMATICS': 'electrical drawings: schematics, functional diagrams, component layouts, wiring',
         'MECHANICAL': 'front panels, cover plates, metalwork, assemblies; the front panel as vectors',
         'PINOUTS': 'the RTO-144 connector: connection sheets, connector layouts, rear views',
         'MANUALS': 'manuals, manual pages, price lists, brochures, documents',
         'PHOTOS': 'photographs of the module',
         'SOFTWARE': 'program listings, firmware, the plugin',
         'KICAD': 'KiCad schematics traced from the drawings, the symbol, PCB projects',
         'OCR': 'the note of every file: date, origin, title block, OCR text'}


def grid(cells):
    out = ['<table>']
    for i in range(0, len(cells), COLS):
        out.append('<tr>' + ''.join(cells[i:i + COLS]) + '</tr>')
    return out + ['</table>', '']


def rel_url(path):
    return quote(path.replace(os.sep, '/'), safe='/()')


def pin_table(moddir):
    f = os.path.join(moddir, 'RTO.json')
    if not os.path.exists(f):
        return []
    d = json.load(open(f, encoding='utf-8'))
    out = ['## RTO-144 pinout', '',
           f'{d.get("contacts") or "RTO-144 edge connector"}' + (f'; checked against {d["verified"]}' if d.get('verified') else '') +
           ('. Read from the module\'s own documents (no RTO-144 sheet yet).' if d.get('derived') else '.') +
           ' Every contact, with where it was read: [`RTO.json`](RTO.json).', '',
           '| Pin | Signal | Kind | Pair | Confidence |', '|---|---|---|---|---|']
    for p in d.get('pins', []):
        pair = (p.get('pair') or '') + (f' {p["polarity"]}' if p.get('polarity') else '')
        out.append(f'| {p.get("pin") or ""} | {esc(p.get("signal") or "")} | {p.get("kind") or ""} | {pair.strip()} | '
                   f'{p.get("confidence") or ""} |')
    if d.get('straps'):
        out += ['', '**Straps:** ' + ' · '.join(f'{esc(j.get("function") or "")}: {j.get("designation") or ""}'
                                                 for j in d['straps'])]
    return out + ['']


def readme(moddir, drive):
    rel = os.path.relpath(moddir, Y2026)                 # Modules/<CAT>/<M>
    _, cat, mod = rel.split(os.sep)
    files = module_files(moddir)
    years = sorted({n[:4] for _, n, _ in files if re.match(r'^\d{4} - ', n)})
    out = [f'# {module_repo_names.title(mod)} · {cat.title().replace("-", " ")}', '']
    out.append(f'Ward-Beck Systems {mod}' + (f', {year_tag(years[0])}' if years else '') +
               f'. Wiki page: [{mod} on WBSps.ca]({SITE}/PAGES/{quote(mod)}.html)')
    out += ['', '| Folder | What is in it | Files |', '|---|---|---|']
    for k in KINDS:
        n = sum(1 for kk, _, _ in files if kk == k) if k != 'OCR' else \
            len([x for x in os.listdir(os.path.join(moddir, 'OCR')) if x.endswith('.md') and x != 'README.md']) \
            if os.path.isdir(os.path.join(moddir, 'OCR')) else 0
        out.append(f'| [{k}/]({k}/) | {SHORT[k]} | {n} |')
    out.append('')
    total = missing = 0
    for k, title in SECTIONS:
        shown = sorted((n, p) for kk, n, p in files if kk == k and os.path.splitext(n)[1].lower() in SHOWN
                       and '(traced)' not in n)
        if not shown:
            continue
        names = {n for kk, n, _ in files if kk == k}
        cells, private, miss = [], [], []
        for n, p in shown:
            d = drive.get(os.path.relpath(p, Y2026).replace(os.sep, '/'))
            stem = os.path.splitext(n)[0]
            vec = f'{stem} (EXTRACTED).svg'
            extra = f' · <a href="{rel_url(k + "/" + vec)}">vectors</a>' if vec in names else ''
            if not d:
                miss.append(n)
                continue
            if len(d) < 3 or not d[2]:
                private.append((n, d))
                continue
            cells.append(f'<td align="center" valign="top" width="33%"><a href="{drive_view(d)}" title="Open on Google Drive">'
                         f'<img src="{drive_thumb(d)}" width="240" alt="{esc(n)}"></a><br><sub>{esc(caption(n, mod))}{extra}</sub></td>')
        out += [f'## {title}', '', f'_{ABOUT[k]}_', '']
        if cells:
            out += grid(cells)
        if private:
            out += ['Shared privately on Google Drive (opens after sign-in): ' +
                    ' · '.join(f'[{esc(caption(n, mod))}]({drive_view(d)})' for n, d in private), '']
        if miss:
            out += ['Not on Google Drive yet: ' + ', '.join(f'`{m}`' for m in miss), '']
        total += len(cells)
        missing += len(miss)
        if k == 'PINOUTS':
            out += pin_table(moddir)
    if not any(k == 'PINOUTS' for k, _, _ in files):
        out += pin_table(moddir)
    kicad = sorted(n for k, n, _ in files if k == 'KICAD')
    if kicad:
        out += ['## KiCad', '', f'_{ABOUT["KICAD"]}_', ''] + [f'- [{esc(n)}]({rel_url("KICAD/" + n)})' for n in kicad] + ['']
    sw = sorted(n for k, n, _ in files if k == 'SOFTWARE')
    if sw:
        out += ['## Software', ''] + [f'- [{esc(n)}]({rel_url("SOFTWARE/" + n)})' +
                                      (': the Rust VST3 / CLAP plugin and Audio Tap insert' if n == 'plugin' else '')
                                      for n in sw] + ['']
    out += ['---', 'Archive: Anthony Peter Kuzub · [WBSps.ca](https://WBSps.ca) · [WBSps.Kuzub.com](https://WBSps.Kuzub.com)', '']
    with open(os.path.join(moddir, 'README.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(out))
    return total, missing


def main():
    drive = load_drive()
    dirs = [os.path.abspath(a) for a in sys.argv[1:]] or sorted(
        p for p in glob.glob(os.path.join(Y2026, 'Modules', '*', '*')) if os.path.isdir(p))
    for d in dirs:
        n, miss = readme(d, drive)
        print(f'{os.path.relpath(d, ROOT)}: {n} images, {miss} not on Drive')


if __name__ == '__main__':
    main()
