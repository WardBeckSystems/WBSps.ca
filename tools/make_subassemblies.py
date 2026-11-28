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


# Drawing numbers 14-nnn-tt-sss: nnn the sub-assembly, tt the kind of drawing, sss the variant
# (001 = SA14-nnn, 002 = SA14-nnnA, 003 = SA14-nnnB ...): 109 = M527, 109A = M462C/M562C, 109B = M528.
DWG = re.compile(r'(?<![\d-])B?\s?14-(\d{3})-(\d{2})-(\d{3})(?![\d])')
SAN = re.compile(r'\bSA ?14-(\d{3})([A-Z]?)\b')
DTYPE = {'01': 'functional', '02': 'schematic', '03': 'assembly', '04': 'mechanical', '06': 'component layout'}
SKIP_TOP = {'Intercom', 'Console', 'CONSOLES', 'WBSps.ca', '_audit', '_stage', 'PHOTOS', 'DOCUMENTS'}
DERIVED = re.compile(r'\((traced|EXTRACTED)\)|\.(md|json|html|bak|kicad_sch|svg|dxf)$', re.I)
DRAWN = re.compile(r'\.(jpe?g|png|gif|tiff?|bmp|pdf|dwg)$', re.I)   # drawings; OrCAD sets go separately
AUDIT = os.path.join(TOP, 'tools', 'dwg_number_audit.tsv')


def variant(sss):
    k = int(sss) - 1
    return '' if k <= 0 else chr(ord('A') + k - 1) if k <= 26 else f'/{sss}'


def repo_of(path):
    p = os.path.dirname(path)
    while p.startswith(G) and p != G:
        if os.path.exists(os.path.join(p, '.git')):
            return p
        p = os.path.dirname(p)
    return None


def scan_variants():
    """{nnn: {variant letter: [(drawing number or '', repo, path in repo)]}} from the repo clones: the number in
    the file name, the number read off the drawing (tools/dwg_number_audit.tsv), or SA14-nnnX in the name."""
    inside = {}
    if os.path.exists(AUDIT):
        import csv
        for r in csv.DictReader(open(AUDIT, encoding='utf-8'), delimiter='\t'):
            nums = [n for n in r['numbers'].split() if n.startswith('14-')]
            if len(nums) == 1:
                inside[os.path.join(G, r['path'])] = nums[0]
    out = defaultdict(lambda: defaultdict(list))
    seen = set()
    for top in sorted(os.listdir(G)):
        if top in SKIP_TOP or top.startswith(('SUBASSEMBLY.', 'ENGINEERING.')) or not os.path.isdir(os.path.join(G, top)):
            continue
        for dp, dns, fns in os.walk(os.path.join(G, top)):
            dns[:] = [d for d in dns if d not in ('.git', 'OCR', '_traces')]
            for fn in fns:
                if DERIVED.search(fn) or not DRAWN.search(fn):
                    continue
                path = os.path.join(dp, fn)
                m, s = DWG.search(fn), SAN.search(fn)
                num = '-'.join(('14',) + m.groups()) if m else inside.get(path, '')
                if num:
                    nnn, letter = num.split('-')[1], variant(num.split('-')[3])
                elif s:
                    nnn, letter = s.group(1), s.group(2)
                else:
                    continue
                repo = repo_of(path)
                if not repo:
                    continue
                key = (os.path.basename(repo), os.path.relpath(path, repo))
                if key in seen:
                    continue
                seen.add(key)
                out[nnn].setdefault(letter, []).append((num,) + key)
    return out


ORCAD_EXT = re.compile(r'\.(DSN|SCH|PLT|BOM|NET|LIB|OLB|DBK|INF|INX|CFG|BCF|LST|TXT|LOG|DAT)$', re.I)
SANUM = re.compile(r'(?<![\dA-Z])(?:SA)?\s?14-?(\d{3})(?!\d)', re.I)


def sha(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def companions(path):
    """The drawing and what was made from it: (traced)/(EXTRACTED) siblings, the OCR note, the KiCad sheet."""
    dp, fn = os.path.split(path)
    stem = os.path.splitext(fn)[0]
    repo = repo_of(path)
    out = [(path, None)]
    for x in os.listdir(dp):
        if x != fn and (x.startswith(stem + ' (traced)') or x.startswith(stem + ' (EXTRACTED)') or x == fn + '.md'):
            out.append((os.path.join(dp, x), None))
    for kind, name in (('OCR', fn + '.md'), ('KICAD', stem + '.kicad_sch')):
        q = os.path.join(repo, kind, name)
        if os.path.isfile(q):
            out.append((q, kind))
    return out


def copy_in(src, dest_dir, have, log):
    """Copy src into dest_dir unless the same bytes are already anywhere in that sub-assembly repo (one copy of each
    file per repo); a different file of the same name gets (2)."""
    repo = os.path.join(G, os.path.relpath(dest_dir, G).split(os.sep)[0])
    if repo not in have:
        have[repo] = set()
        for dp, dns, fns in os.walk(repo):
            dns[:] = [d for d in dns if d != '.git']
            have[repo] |= {sha(os.path.join(dp, f)) for f in fns if f not in ('README.md', '.gitignore')}
    h = sha(src)
    if h in have[repo]:
        return
    os.makedirs(dest_dir, exist_ok=True)
    fn = os.path.basename(src)
    dst = os.path.join(dest_dir, fn)
    k = 2
    while os.path.exists(dst):
        b, e = os.path.splitext(fn)
        dst = os.path.join(dest_dir, f'{b} ({k}){e}')
        k += 1
    shutil.copy2(src, dst)
    have[repo].add(h)
    log.append((os.path.relpath(src, G), os.path.relpath(dst, G)))


def copy_drawings(sa, names, dry):
    """Every sub-assembly's drawings duplicated into its own repo from the repo they come from (originals stay):
    the variant drawings and their companions, and the OrCAD sets (SA14nnn / 14-nnn .DSN .SCH .PLT ...)."""
    log, have = [], {}
    vs = scan_variants()
    for nnn, byv in vs.items():
        name = names.get(nnn)
        if not name:
            continue
        for v, ds in byv.items():
            for num, repo, rel in ds:
                if repo.startswith('RECOVERY.'):
                    continue
                src = os.path.join(G, repo, rel)
                kind = rel.split(os.sep)[0] if os.sep in rel and rel.split(os.sep)[0] in KINDS else 'SCHEMATICS'
                for p, k in companions(src):
                    if not dry:
                        copy_in(p, os.path.join(G, name, k or kind), have, log)
                    else:
                        log.append((os.path.relpath(p, G), os.path.join(name, k or kind)))
    inside = {}
    if os.path.exists(AUDIT):
        import csv
        for r in csv.DictReader(open(AUDIT, encoding='utf-8'), delimiter='\t'):
            nums = {n.split('-')[1] for n in r['numbers'].split() if n.startswith('14-')}
            if len(nums) == 1:
                inside[os.path.join(G, r['path'])] = nums.pop()
    done = {os.path.join(G, f) for f, _ in log}
    generic = {'ORCAD', 'ORCADWIN', 'ACAD', 'TANGO', 'SCHEMATICS', 'MECHANICAL', 'MECHANIC', 'ISS1', 'ISS2', 'OLD', 'OBSOLETE', 'PCB'}
    for top in sorted(os.listdir(G)):   # OrCAD sets and AutoCAD drawings: Engineering and the module repos
        if top in SKIP_TOP or top.startswith(('SUBASSEMBLY.', 'RECOVERY.', 'ENGINEERING.')) or not os.path.isdir(os.path.join(G, top)):
            continue
        for dp, dns, fns in os.walk(os.path.join(G, top)):
            dns[:] = [d for d in dns if d not in ('.git', 'OCR', '_traces')]
            anc = []   # the SA14-nnn folder this is in (up to three levels up)
            q = dp
            for _ in range(3):
                m = SANUM.match(os.path.basename(q))
                if m:
                    anc = [m.group(1), os.path.basename(q)]
                    break
                q = os.path.dirname(q)
            for f in fns:
                cad = re.search(r'\.(dwg|dxf)$', f, re.I)
                if not (ORCAD_EXT.search(f) or cad) or DERIVED.search(f.replace('.dxf', '')) or '(traced)' in f:
                    continue
                path = os.path.join(dp, f)
                if path in done:
                    continue
                m = SANUM.search(f)
                nnn = m.group(1) if m else inside.get(path) or (anc[0] if anc else None)
                name = names.get(nnn)
                if not name:
                    continue
                label = anc[1] if anc and anc[0] == nnn else next(
                    (x for x in (os.path.basename(dp), os.path.basename(os.path.dirname(dp)))
                     if x.upper() not in generic), os.path.basename(dp))
                dest = os.path.join(G, name, 'MECHANICAL' if cad else 'SCHEMATICS', 'ACAD' if cad else 'ORCAD', label)
                if dry:
                    log.append((os.path.relpath(path, G), os.path.relpath(dest, G)))
                else:
                    copy_in(path, dest, have, log)
    import csv
    with open(os.path.join(TOP, 'tools', 'subassembly_copies.tsv'), 'w', newline='') as fh:
        w = csv.writer(fh, delimiter='\t'); w.writerow(['from', 'to']); w.writerows(log)
    print(f'{len(log)} files {"would be " if dry else ""}duplicated into the sub-assembly repos (tools/subassembly_copies.tsv)')


def gh(repo, rel):
    from urllib.parse import quote
    return f'https://github.com/{OWNER}/{repo}/blob/HEAD/{quote(rel)}'


def variants_md(n, vs):
    """The variants table and, per variant, its drawings (drawing-numbered first)."""
    if not vs:
        return []
    nnn = f'{int(n):03d}'
    lines = ['## Variants', '',
             f'Drawing numbers read `14-{nnn}-tt-sss`: tt the kind of drawing (02 schematic, 06 component layout …), '
             'sss the variant (001 this board, 002 A, 003 B …).', '',
             '| Variant | Drawing numbers | Used in |', '|---|---|---|']
    order = sorted(vs, key=lambda v: (len(v), v))
    for v in order:
        nums = sorted({d[0] for d in vs[v] if d[0]})
        used = sorted({re.sub(r'^(MODULES\.[A-Z-]+\.|CONSOLE\.(MODEL\.)?|INTERCOM\.|PRODUCTS\.|RECOVERY\.)', '', d[1]).split('-')[0]
                       for d in vs[v] if not d[1].startswith('RECOVERY.')})
        lines.append(f'| SA14-{nnn}{v} | ' + (' · '.join(f'{x} ({DTYPE.get(x.split("-")[2], "type " + x.split("-")[2])})'
                                                        for x in nums) or '—') + f' | {" · ".join(used)} |')
    lines.append('')
    for v in order:
        lines += [f'### SA14-{nnn}{v}', '']
        for num, repo, rel in sorted(vs[v], key=lambda d: (not d[0], d[0], d[1], d[2])):
            name = os.path.basename(rel)   # RECOVERY.* is private: named, not linked
            lines.append((f'- {name}' if repo.startswith('RECOVERY.') else f'- [{name}]({gh(repo, rel)})') + (f' — {num}' if num and num not in rel else '')
                         + f' · `{repo}`')
        lines.append('')
    return lines


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
    if e.get('variants'):   # the drawings found in the repo clones, by variant (replaces the old site links)
        lines += variants_md(n, e['variants'])
    elif e['drawings']:
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
    vs = scan_variants()
    for n, e in sa.items():
        e['variants'] = vs.get(f'{int(n):03d}', {})
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
    if '--copy-drawings' in sys.argv:
        copy_drawings(sa, {f'{int(n):03d}': repo_name(n, e) for n, e in sa.items()}, dry)
    if not dry:
        json.dump(index, open(os.path.join(TOP, 'tools', 'subassemblies.json'), 'w'), indent=1)
    print(f'{len(sa)} sub-assemblies' + (' (dry run)' if dry else f' in {G}'))


if __name__ == '__main__':
    main()
