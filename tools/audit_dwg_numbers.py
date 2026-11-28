#!/usr/bin/env python3
"""Audit: does every schematic / mechanical drawing carry its drawing number
(##-###-##-###) in its file name as [DWG ##-###-##-###]?

Read-only. For every drawing file under WBSps.ca/Github.WardBeckSystems it
looks for the number in:
  name      the file name itself
  title     the sidecar's title block ("- **Drawing:**") / traced json sheet.number
  ocr       the sidecar's full OCR text, the traced json words
  content   text inside the file (PDF text, DXF TEXT/MTEXT, SVG <text>)

Writes tools/dwg_number_audit.tsv (one row per drawing) and
tools/DWG-NUMBER-AUDIT.md (summary + lists).

    python3 tools/audit_dwg_numbers.py
"""
import csv, json, os, re, subprocess, sys
from collections import Counter, defaultdict

import wbs_home

ROOT = wbs_home.HOME
REPO_RX = wbs_home.path_re()
OUT_TSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dwg_number_audit.tsv')
OUT_MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'DWG-NUMBER-AUDIT.md')

DRAW_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff', '.bmp', '.pdf',
            '.dwg', '.dxf', '.sch', '.schdoc', '.pcb', '.pcbdoc', '.cdr',
            '.svg', '.eps', '.kicad_sch', '.dsn'}
CAD_EXT = {'.dwg', '.dxf', '.sch', '.schdoc', '.pcb', '.pcbdoc', '.dsn', '.kicad_sch'}
DRAW_DIRS = {'SCHEMATICS', 'MECHANICAL', 'KICAD', 'ORCAD', 'DRAWINGS'}
SKIP_DIRS = {'.git', 'node_modules', '_traces', '__pycache__'}
DERIVED = re.compile(r'\((traced|EXTRACTED)\)', re.I)

SEP = r'\s*[-‐-―.]\s*'
# strict: 2-3-2-3 digits, not part of a longer run
STRICT = re.compile(r'(?<![\d])(\d{2})' + SEP + r'(\d{3})' + SEP + r'(\d{2})' + SEP + r'(\d{3})(?![\d])')
# the filename form the user wants
BRACKET = re.compile(r'\[DWG (\d{2}-\d{3}-\d{2}-\d{3})\]')
# near misses worth a human look: 5 digits run together (14701-02-101) or
# the 3-2-3 short form (701-02-101) or 1-3-2-3 (8-109-02-002)
NEAR = [
    ('joined',  re.compile(r'(?<![\d-])(\d{2})(\d{3})' + SEP + r'(\d{2})' + SEP + r'(\d{3})(?![\d])')),
    ('1-3-2-3', re.compile(r'(?<![\d-])(\d)' + SEP + r'(\d{3})' + SEP + r'(\d{2})' + SEP + r'(\d{3})(?![\d])')),
    ('3-2-3',   re.compile(r'(?<![\d-])(\d{3})' + SEP + r'(\d{2})' + SEP + r'(\d{3})(?![\d])')),
]


def norm(m):
    return '-'.join(m.groups())


def strict(text):
    return sorted({norm(m) for m in STRICT.finditer(text or '')})


def near(text):
    found = {}
    t = text or ''
    for kind, rx in NEAR:
        for m in rx.finditer(t):
            found.setdefault('-'.join(m.groups()), kind)
    return found


def walk():
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            yield dp, fn


def sidecar_for(dp, fn):
    """Sidecar .md beside the file, or in the repo's OCR/ folder."""
    c = [os.path.join(dp, fn + '.md')]
    p = dp
    while p.startswith(ROOT) and p != ROOT:
        c.append(os.path.join(p, 'OCR', fn + '.md'))
        p = os.path.dirname(p)
    return [x for x in c if os.path.isfile(x)]


def traced_json(dp, fn):
    stem = os.path.splitext(fn)[0]
    j = os.path.join(dp, stem + ' (traced).json')
    return j if os.path.isfile(j) else None


def read(p, limit=4_000_000):
    try:
        with open(p, 'r', errors='replace') as f:
            return f.read(limit)
    except OSError:
        return ''


def file_text(path, ext):
    if ext == '.pdf':
        try:
            r = subprocess.run(['pdftotext', '-l', '20', path, '-'], capture_output=True,
                               timeout=60)
            return r.stdout.decode('utf8', 'replace')
        except Exception:
            return ''
    if ext in ('.dxf', '.svg', '.sch', '.kicad_sch', '.dsn', '.eps'):
        return read(path)
    if ext in ('.dwg', '.schdoc', '.pcbdoc', '.pcb', '.cdr'):
        # binary: pull printable runs (DWG text is often UTF-16 in R2007+)
        try:
            b = open(path, 'rb').read(30_000_000)
        except OSError:
            return ''
        runs = re.findall(rb'[ -~]{6,}', b)
        u16 = re.findall(rb'(?:[ -~]\x00){6,}', b)
        return (b' '.join(runs).decode('ascii', 'replace') + ' ' +
                b' '.join(u16).decode('ascii', 'replace').replace('\x00', ''))
    return ''


def is_drawing(rel, dp, fn, ext, cars, tj):
    parts = set(rel.split(os.sep)[:-1])
    if parts & DRAW_DIRS:
        return True
    if ext in CAD_EXT:
        return True
    if tj:
        return True
    for c in cars:
        if '## Title block' in read(c, 20000):
            return True
    if STRICT.search(fn):
        return True
    return False


def main():
    rows = []
    for dp, fn in walk():
        ext = os.path.splitext(fn)[1].lower()
        if fn.lower().endswith('.kicad_sch'):
            ext = '.kicad_sch'
        if ext not in DRAW_EXT or DERIVED.search(fn):
            continue
        path = os.path.join(dp, fn)
        rel = os.path.relpath(path, ROOT)
        m = REPO_RX.search('Github.WardBeckSystems/' + rel.replace(os.sep, '/'))
        top = m.group(1) if m else rel.split(os.sep)[0]   # the repo, wherever its folder is
        if top in ('PHOTOS', 'YOU_TUBE', 'youtube-editor', 'XTM', 'WebRouter', 'Premote',
                   'Ward-Beck-Audio-Tap', 'Ward-Beck-Plugin-Core', 'Ward-Beck-Generators',
                   'Microcom-Simulator', 'Public_Page', '_stage', '_audit'):
            continue
        if any(seg in ('MANUALS', 'PHOTOS', 'OCR') for seg in rel.split(os.sep)[1:-1]):
            continue
        cars = sidecar_for(dp, fn)
        tj = traced_json(dp, fn)
        if not is_drawing(rel, dp, fn, ext, cars, tj):
            continue

        title_txt, ocr_txt = '', ''
        for c in cars:
            t = read(c)
            for line in t.splitlines():
                if line.startswith('- **Drawing:**') or line.startswith('- **Title:**'):
                    title_txt += line + '\n'
            ocr_txt += t
        if tj:
            try:
                d = json.load(open(tj))
                title_txt += str(d.get('sheet', {}).get('number', '')) + '\n'
                ocr_txt += json.dumps(d.get('text', {}).get('lines', []))
            except Exception:
                pass
        content = file_text(path, ext)

        name_n = strict(fn)
        bracket = BRACKET.findall(fn)
        title_n = strict(title_txt)
        ocr_n = strict(ocr_txt)
        cont_n = strict(content)
        allnums = sorted(set(name_n) | set(title_n) | set(ocr_n) | set(cont_n))
        near_all = {}
        for t in (fn, title_txt, ocr_txt, content):
            for k, v in near(t).items():
                near_all.setdefault(k, v)
        for n in allnums:  # drop near hits that are pieces of a strict hit
            near_all = {k: v for k, v in near_all.items() if k not in n}

        if bracket:
            status = 'OK-bracketed'
        elif allnums and name_n:
            status = 'in-name-not-bracketed'
        elif allnums:
            status = 'found-inside-not-in-name'
        elif near_all:
            status = 'near-miss-only'
        else:
            status = 'none-found'
        where = ','.join(k for k, v in (('name', name_n), ('title', title_n),
                                         ('ocr', ocr_n), ('content', cont_n)) if v)
        rows.append({
            'status': status, 'repo': top, 'ext': ext.lstrip('.'),
            'numbers': ' '.join(allnums), 'where': where,
            'near': ' '.join(f'{k}({v})' for k, v in sorted(near_all.items())[:6]),
            'sidecar': 'yes' if cars else '', 'path': rel,
        })

    rows.sort(key=lambda r: (r['status'], r['path']))
    with open(OUT_TSV, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter='\t')
        w.writeheader(); w.writerows(rows)

    st = Counter(r['status'] for r in rows)
    by_kind = defaultdict(Counter)
    for r in rows:
        kind = r['repo'].split('.')[0]
        by_kind[kind][r['status']] += 1
    nums = Counter(n for r in rows for n in r['numbers'].split())
    multi = [r for r in rows if len(r['numbers'].split()) > 1]
    cols = ['OK-bracketed', 'in-name-not-bracketed', 'found-inside-not-in-name',
            'near-miss-only', 'none-found']
    L = ['# Drawing-number audit — `[DWG ##-###-##-###]`', '',
         f'Drawings scanned: **{len(rows):,}** (schematic / mechanical / CAD files under '
         '`WBSps.ca/Github.WardBeckSystems`; traced/extracted derivatives, manuals and photos left out).', '',
         'Sources searched per drawing: file name, title-block sidecar (`- **Drawing:**`, traced json '
         '`sheet.number`), full OCR text, and text inside the file (PDF text, DXF/SVG text, DWG strings).', '',
         '| Status | Drawings | Meaning |', '|---|---:|---|',
         f"| OK-bracketed | {st['OK-bracketed']:,} | name already has `[DWG ##-###-##-###]` |",
         f"| in-name-not-bracketed | {st['in-name-not-bracketed']:,} | number is in the name, not in `[DWG …]` form |",
         f"| found-inside-not-in-name | {st['found-inside-not-in-name']:,} | number read on the drawing, missing from the name |",
         f"| near-miss-only | {st['near-miss-only']:,} | only a short/joined form (`701-02-101`, `8-109-02-002`, `14701-02-101`) |",
         f"| none-found | {st['none-found']:,} | no drawing number of this style anywhere |", '',
         '## By repo kind', '', '| Kind | ' + ' | '.join(cols) + ' |', '|---|' + '---:|' * len(cols)]
    for k in sorted(by_kind):
        L.append(f'| {k} | ' + ' | '.join(str(by_kind[k][c]) for c in cols) + ' |')
    L += ['', f'Distinct `##-###-##-###` numbers seen: **{len(nums):,}**. '
          f'Drawings showing more than one number (need a human pick): **{len(multi):,}**.', '',
          'Full row-per-drawing list: `tools/dwg_number_audit.tsv`.', '']
    for s in cols[1:4]:
        sub = [r for r in rows if r['status'] == s]
        L += [f'## {s} ({len(sub):,}) — first 60', '']
        for r in sub[:60]:
            L.append(f"- `{r['path']}` — {r['numbers'] or r['near']} ({r['where'] or 'near'})")
        L.append('')
    open(OUT_MD, 'w').write('\n'.join(L))
    print('\n'.join(L[:30]))


if __name__ == '__main__':
    main()
