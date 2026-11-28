#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Put the drawing number in every drawing's file name as [DWG ##-###-##-###] — the sign that the file is a drawing.

    python3 tools/apply_dwg_names.py [--dry-run]

Reads tools/dwg_number_audit.tsv (tools/audit_dwg_numbers.py). For each drawing with one ##-###-##-### number:
  the number already in the name  -> replaced in place (with the size letter in front of it: "B 14-109-02-001",
                                     "B14-029-06-001" -> "[DWG 14-109-02-001]")
  the number only on the drawing  -> put in after the year and the model ("1985 - M462C - [DWG ...] - ...")
What was made from the drawing follows it: the (traced) / (EXTRACTED) files, the OCR note, the KiCad sheet.
Links and names in the repo's pages (.md .html .json .svg .kicad_sch) and in PAGES/ are rewritten.
Left alone (listed in the plan): CAD sources (OrCAD .SCH/.DSN, Tango .PCB, AutoCAD .DWG — other files point at
them by name), the raw Engineering/H drive copy, drawings showing two different numbers, OCR noise.
Plan: tools/dwg_renames.tsv.
"""
import csv, os, re, sys
from collections import defaultdict
from urllib.parse import quote

import wbs_home

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = wbs_home.HOME
AUDIT = os.path.join(TOP, 'tools', 'dwg_number_audit.tsv')
PLAN = os.path.join(TOP, 'tools', 'dwg_renames.tsv')
CAD = {'sch', 'dsn', 'pcb', 'dwg', 'schdoc', 'pcbdoc', 'dxf', 'cdr'}
SKIP_TOP = {'WBSps.ca', 'Intercom', 'Console', 'CONSOLES', '_audit', '_stage'}
NOISE = re.compile(r'^(0\d|80)-')       # 08-004-12-887 (OCR), 80-416-80-220 (Xilinx docs)
SEP = r'\s*[-‐-―.]\s*'
TEXT = ('.md', '.html', '.json', '.svg', '.kicad_sch', '.js', '.txt')
YEAR = re.compile(r'^(\d{4}|\d{2}xx|19xx|\d{4}-\d{4})$')


def num_rx(n):
    a, b, c, d = n.split('-')
    return re.compile(r'(?:(?<![A-Za-z0-9])(?:LB|[A-E])\s?)?(?<!\d)' + a + '(?:' + SEP + ')?' + b + SEP + c + SEP + d + r'(?!\d)')


def new_name(fn, n):
    stem, ext = os.path.splitext(fn)
    tag = f'[DWG {n}]'
    rx = num_rx(n)
    a, b, c, d = n.split('-')   # the short form on the older sheets: 066-06-001 for 14-066-06-001
    tail = re.compile(r'(?:(?<![A-Za-z0-9])(?:LB|[A-E])\s?)?(?<![\d-])' + b + SEP + c + SEP + d + r'(?!\d)')
    if not rx.search(stem) and tail.search(stem):
        rx = tail
    if rx.search(stem):
        s = rx.sub(tag, stem, count=1)
        s = re.sub(r'\]([a-z])\b', r'] \1', s)                  # 76-045-02-003c -> [DWG 76-045-02-003] c
        return s + ext
    parts = stem.split(' - ')
    if len(parts) == 1:
        return f'{tag} - {stem}{ext}'
    i = 0
    while i < len(parts) - 1 and YEAR.match(parts[i]):
        i += 1
    if i < len(parts) - 1 and re.fullmatch(r'[A-Z]{0,4}\d{2,6}[A-Z]{0,4}', parts[i]):
        i += 1
    return ' - '.join(parts[:i] + [tag] + parts[i:]) + ext


def repo_of(path):
    p = os.path.dirname(path)
    while p.startswith(G) and p != G:
        if os.path.exists(os.path.join(p, '.git')):
            return p
        p = os.path.dirname(p)
    return None


def companions(path, nfn):
    """(old, new) for the drawing's traced / extracted files, its OCR note and KiCad sheet."""
    dp, fn = os.path.split(path)
    stem, nstem = os.path.splitext(fn)[0], os.path.splitext(nfn)[0]
    out = []
    for x in os.listdir(dp):
        for suf in (' (traced)', ' (EXTRACTED)'):
            if x.startswith(stem + suf):
                out.append((os.path.join(dp, x), os.path.join(dp, nstem + x[len(stem):])))
        if x == fn + '.md':
            out.append((os.path.join(dp, x), os.path.join(dp, nfn + '.md')))
    repo = repo_of(path)
    for kind, a, b in (('OCR', fn + '.md', nfn + '.md'), ('KICAD', stem + '.kicad_sch', nstem + '.kicad_sch')):
        q = os.path.join(repo, kind, a)
        if os.path.isfile(q):
            out.append((q, os.path.join(repo, kind, b)))
    return out


def plan():
    rows = list(csv.DictReader(open(AUDIT, encoding='utf-8'), delimiter='\t'))
    moves, skipped = {}, []
    for r in rows:
        if r['status'] not in ('in-name-not-bracketed', 'found-inside-not-in-name'):
            continue
        path = os.path.join(G, r['path'])
        fn = os.path.basename(path)
        m = wbs_home.path_re().search('Github.WardBeckSystems/' + r['path'].replace(os.sep, '/'))
        top = m.group(1) if m else r['path'].split(os.sep)[0]   # the repo, wherever its folder is
        nums = [n for n in r['numbers'].split() if not NOISE.match(n)]
        in_name = [n for n in nums if num_rx(n).search(fn)]
        why = ('CAD source' if r['ext'].lower() in CAD else
               'raw H drive copy' if r['path'].startswith('Engineering/H drive') or top.startswith('ENGINEERING.') else
               'old site copy' if top in SKIP_TOP else
               'derived file' if re.search(r'\((traced|EXTRACTED)\)', fn) else
               'no number' if not nums else
               'two numbers' if len(in_name) != 1 and len(nums) > 1 else '')
        if why:
            skipped.append((why, r['numbers'], r['path']))
            continue
        n = in_name[0] if in_name else nums[0]
        if path in moves:
            continue
        nfn = new_name(fn, n)
        moves[path] = os.path.join(os.path.dirname(path), nfn)
        for a, b in companions(path, nfn):
            moves.setdefault(a, b)
    # a name the move would give that is already taken, or two files given one name: left alone
    seen = defaultdict(list)
    for a, b in moves.items():
        seen[b].append(a)
    for b, al in seen.items():
        if len(al) > 1 or (os.path.exists(b) and b not in moves):
            for a in al:
                skipped.append(('name taken', '', os.path.relpath(a, G)))
                moves.pop(a, None)
    return moves, skipped


TOUCHED = []   # every file the rename changed or wrote (each repo commits only these)
FORMS = [lambda x: x, quote, lambda x: quote(x, safe="/()"), lambda x: quote(x, safe="/()'"),
         lambda x: quote(x, safe="/%:@&=+$,;!*~()'"), lambda x: x.replace(' ', '%20'),
         lambda x: x.replace('&', '&amp;')]   # as written, and as links encode it


def rewrite(files, names):
    """Old file names -> new in the pages: whole names only (with what follows: .md, ' (traced).json' ...)."""
    pairs = {}
    for a, b in names.items():
        for f in FORMS:
            pairs.setdefault(f(a), f(b))
    pairs = [(a, b) for a, b in pairs.items() if a != b]
    pairs.sort(key=lambda p: -len(p[0]))
    if not pairs:
        return 0
    rx = re.compile(r'(?<![A-Za-z0-9 .\-])(' + '|'.join(re.escape(a) for a, _ in pairs) + ')')
    m = dict(pairs)
    changed = 0
    for f in files:
        try:
            t = open(f, encoding='utf-8').read()
        except (OSError, UnicodeDecodeError):
            continue
        u = rx.sub(lambda x: m[x.group(1)], t)
        if u != t:
            open(f, 'w', encoding='utf-8').write(u)
            TOUCHED.append(f)
            changed += 1
    return changed


def captions(files, stems):
    """The names shown without their extension (captions: '<sub>name · ', '<span>name</span>')."""
    pairs = sorted(((a, b) for a, b in stems.items() if a != b), key=lambda p: -len(p[0]))
    if not pairs:
        return 0
    rx = re.compile(r'(?:(?<=[>\[`"])|(?<=\| ))(' + '|'.join(re.escape(a) for a, _ in pairs) + r')(?=\s+·|<|`|"|\]|\s*\|)')
    m = dict(pairs)
    changed = 0
    for f in files:
        try:
            t = open(f, encoding='utf-8').read()
        except (OSError, UnicodeDecodeError):
            continue
        u = rx.sub(lambda x: m[x.group(1)], t)
        if u != t:
            open(f, 'w', encoding='utf-8').write(u)
            TOUCHED.append(f)
            changed += 1
    return changed


def text_files(root, top_only=False):
    for dp, dns, fns in os.walk(root):
        dns[:] = [] if top_only else [d for d in dns if d != '.git']
        for f in fns:
            if f.endswith(TEXT):
                yield os.path.join(dp, f)


def main():
    dry = '--dry-run' in sys.argv
    moves, skipped = plan()
    with open(PLAN, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t')
        w.writerow(['action', 'numbers', 'from', 'to'])
        for a, b in sorted(moves.items()):
            w.writerow(['rename', '', os.path.relpath(a, G), os.path.basename(b)])
        for why, nums, p in sorted(skipped):
            w.writerow([f'left: {why}', nums, p, ''])
    by = defaultdict(int)
    for why, _, _ in skipped:
        by[why] += 1
    print(f'{len(moves)} files to rename; left alone: ' + ', '.join(f'{k} {v}' for k, v in sorted(by.items())))
    if dry:
        return
    byrepo = defaultdict(dict)
    for a, b in moves.items():
        byrepo[repo_of(a)][os.path.basename(a)] = os.path.basename(b)
    for a, b in sorted(moves.items(), key=lambda x: -len(x[0])):
        os.rename(a, b)
        TOUCHED.extend([a, b])
    allnames = {}
    for r, names in byrepo.items():
        # a name also used by another file in the repo that is not renamed: only the rename's own pages change
        n = rewrite(text_files(r), names)
        allnames.update(names)
        print(f'  {os.path.basename(r)}: {len(names)} renamed, {n} pages rewritten')
    n = rewrite(list(text_files(os.path.join(TOP, 'PAGES'))), allnames)
    stems = {os.path.splitext(a)[0]: os.path.splitext(b)[0] for a, b in allnames.items() if '.' in a}
    n += captions([f for r in byrepo for f in text_files(r)] + list(text_files(os.path.join(TOP, 'PAGES'))), stems)
    print(f'  PAGES: {n} pages rewritten')
    open(os.path.join(TOP, 'tools', 'dwg_touched.txt'), 'w', encoding='utf-8').write('\n'.join(sorted(set(TOUCHED))) + '\n')


if __name__ == '__main__':
    main()
