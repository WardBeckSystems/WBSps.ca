#!/usr/bin/env python3
"""Write README.md in each module folder (Products/Modules/<CATEGORY>/<Mxxx>): every image shown, each one linked
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modules_home  # noqa: E402  the module folders (2026/Modules/<CAT>/<M> -> clones)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Y2026 = os.path.join(ROOT, '2026')
SITE = 'https://wardbecksystems.github.io/WBSps.ca'
IMG = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff', '.bmp')
COLS = 3
SMALL = re.compile(r'_small$', re.I)


def thumbnail_of_shown(name, names):
    """A '<x>_small' copy whose full-size '<x>' is also in the folder: a web thumbnail, not shown."""
    stem = os.path.splitext(name)[0]
    base = SMALL.sub('', stem)
    return base != stem and any(os.path.splitext(n)[0] == base for n in names)


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
    if d.get('built_from'):
        return pin_table_pictures(d)
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


def pin_table_pictures(d):
    """RTO.json built from the pinout pictures (tools/pinout_build.py)."""
    b = d['built_from']
    n = len(b.get('pictures') or [])
    line = f'Read from {n} pinout picture{"s" if n != 1 else ""} (each its own `.pinout.json` beside it)'
    if b.get('sheet_agrees'):
        line += f'; the RTO-144 sheet agrees on {b["sheet_agrees"]} contacts'
    if d.get('conflicts'):
        line += f'; {len(d["conflicts"])} to check (`conflicts`)'
    out = ['## RTO-144 pinout', '', line + '. Every contact, with where it was read: [`RTO.json`](RTO.json). How a picture '
           'becomes this table: [the pinout decision tree](https://github.com/WardBeckSystems/WBSps.ca/blob/main/2026/Engineering/PINOUTS.md).', '']
    if d.get('to_check'):
        out += ['**To check:**', ''] + [f"- {esc(c['what'])}{' ' + esc(c['pin']) if c.get('pin') else ''}: {esc(c['detail'])}"
                                        for c in d['to_check']] + ['']
    if d.get('inserts'):
        out += ['**Inserts:** ' + ' · '.join(f'{esc(i.get("name") or "")}: {esc(i.get("send") or "?")} → {esc(i.get("return") or "?")}'
                                             for i in d['inserts']), '']
    out += ['| Pin | Signal | Kind | Port | Confidence |', '|---|---|---|---|---|']
    for p in d.get('pins', []):
        port = (p.get('port') or '') + (f' {p["polarity"]}' if p.get('polarity') else '')
        out.append(f'| {p.get("ref") or p.get("pin") or ""} | {esc(p.get("signal") or "")} | {p.get("kind") or ""} | '
                   f'{esc(port.strip())} | {p.get("confidence") or ""} |')
    if d.get('straps'):
        out += ['', '**Straps:** ' + ' · '.join(f'{esc(s.get("name") or "")}: {" ".join(s.get("pins") or [])}' for s in d['straps'])]
    return out + ['']


def spec_section(moddir):
    """Specifications.json (tools/module_specs.py) as a table: the technical data sheet, line by line."""
    f = os.path.join(moddir, 'Specifications.json')
    if not os.path.exists(f):
        return []
    d = json.load(open(f, encoding='utf-8'))
    src = d['source']
    out = ['## Specifications', '',
           f'From the technical data sheet: [{esc(os.path.basename(src["file"]))}]({rel_url(src["file"])}) page {src["page"]} '
           f'(read by OCR; check against the page). As data: [`Specifications.json`](Specifications.json).', '',
           '| | |', '|---|---|']
    for x in d['specifications']:
        cell = lambda t: esc(t).replace('|', '\\|')
        out.append(f'| **{cell(x["name"])}** | {cell(x.get("text", ""))} |')
        for it in x.get('items', []):
            out.append(f'| &nbsp;&nbsp;{cell(it["name"])} | {cell(it.get("text", ""))} |')
    return out + ['']


def circuit_section(moddir):
    """CircuitDescription.json (tools/module_specs.py): the manual's circuit description, folded."""
    f = os.path.join(moddir, 'CircuitDescription.json')
    if not os.path.exists(f):
        return []
    d = json.load(open(f, encoding='utf-8'))
    src = d['source']
    pages = src['pages']
    pg = f'pages {pages[0]}-{pages[-1]}' if len(pages) > 1 else f'page {pages[0]}'
    out = ['## Circuit description', '',
           f'From [{esc(os.path.basename(src["file"]))}]({rel_url(src["file"])}) {pg} (read by OCR; check against the pages). '
           f'As data: [`CircuitDescription.json`](CircuitDescription.json).', '', '<details><summary>Read it</summary>', '']
    for sec in d['sections']:
        if sec.get('heading'):
            out += [f'**{esc(sec["heading"])}**', '']
        out += [esc(p) + '\n' for p in sec['paragraphs']]
    return out + ['</details>', '']


def forum_line(moddir):
    f = os.path.join(moddir, 'FORUM.md')
    if not os.path.exists(f):
        return []
    n = sum(1 for l in open(f, encoding='utf-8') if l.startswith('## '))
    return [f'**On the WBSps forum (2006|39 - 2014|47):** [{n} topic{"s" * (n != 1)}](FORUM.md): what owners and technicians said about it.', '']


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
        if n:   # an empty folder is not data: only the folders that hold something
            out.append(f'| [{k}/]({k}/) | {SHORT[k]} | {n} |')
    out.append('')
    block = forum_line(moddir) + spec_section(moddir) + circuit_section(moddir)
    out += ([BEGIN, ''] + block + [END, ''] if block else [])
    total = missing = 0
    for k, title in SECTIONS:
        names = {n for kk, n, _ in files if kk == k}
        shown = sorted((n, p) for kk, n, p in files if kk == k and os.path.splitext(n)[1].lower() in SHOWN
                       and '(traced)' not in n and not thumbnail_of_shown(n, names))
        if not shown:
            continue
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


BEGIN, END = '<!-- module data: tools/module_specs.py, tools/forum_quotes.py -->', '<!-- /module data -->'


def insert_data(moddir):
    """Put the forum line, Specifications and Circuit description into a README that is already there (a repo clone
    whose files no longer sit in 2026): after the folder table, between markers, replacing what a run put there before."""
    f = os.path.join(moddir, 'README.md')
    if not os.path.exists(f):
        return False
    text = open(f, encoding='utf-8').read()
    text = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END) + r'\n*', '', text, flags=re.S)
    block = forum_line(moddir) + spec_section(moddir) + circuit_section(moddir)
    if block:
        lines = text.split('\n')
        at = next((i for i, l in enumerate(lines) if l.startswith('| [OCR/]')), None)
        at = at + 1 if at is not None else next((i for i, l in enumerate(lines) if l.startswith('## ')), len(lines))
        lines[at:at] = ['', BEGIN, ''] + block + [END, '']
        text = '\n'.join(lines)
    open(f, 'w', encoding='utf-8').write(re.sub(r'\n{3,}', '\n\n', text))
    return bool(block)


def main():
    if sys.argv[1:2] == ['--insert']:   # tools/make_module_readmes.py --insert <clone> ...
        n = sum(insert_data(os.path.abspath(d)) for d in sys.argv[2:])
        print(f'{n} READMEs given their data')
        return
    drive = load_drive()
    dirs = [os.path.abspath(a) for a in sys.argv[1:]] or modules_home.module_dirs()
    for d in dirs:
        n, miss = readme(d, drive)
        print(f'{os.path.relpath(d, ROOT)}: {n} images, {miss} not on Drive')


if __name__ == '__main__':
    main()
