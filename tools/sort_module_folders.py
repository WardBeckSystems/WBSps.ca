#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Sort each module folder into SCHEMATICS/ MANUALS/ PHOTOS/ SOFTWARE/ OCR/ (see module_layout.py).

Moves the files (git mv inside a module repo for tracked files, plain rename for the media the repos ignore), puts each
.md note in OCR/, fixes the relative links inside the notes, and writes moves.tsv (old -> new, relative to 2026/) so the
database and the site can follow (tools/apply_module_moves.py).

    python3 tools/sort_module_folders.py                 # dry run: counts and samples
    python3 tools/sort_module_folders.py --apply [2026/Modules/CAT/M ...]
"""
import glob
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from urllib.parse import quote, unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from module_layout import KINDS, TOP, is_note, kind_of, origin_of  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modules_home  # noqa: E402  the module folders (2026/Modules/<CAT>/<M> -> clones)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Y2026 = os.path.join(ROOT, '2026')
MOVES = os.path.join(ROOT, 'tools', 'module_moves.tsv')
LINK = re.compile(r'\]\(([^)\s]+)\)')


def plan(moddir):
    names = [n for n in os.listdir(moddir) if not n.startswith('.')]
    files = [n for n in names if n not in TOP and n not in KINDS and not is_note(n)]
    notes = [n for n in names if is_note(n)]
    out = []
    for n in files:
        note = n + '.md'
        k = kind_of(n, origin_of(os.path.join(moddir, note)) if note in notes else '', names, os.path.join(moddir, n))
        out.append((n, f'{k}/{n}'))
    out += [(n, f'OCR/{n}') for n in notes]
    return out


def fix_links(text, old_dir, new_dir, newpath_of):
    """Relative links in a note moved from old_dir to new_dir; links to moved siblings point at their new place."""
    def sub(m):
        url = m.group(1)
        if re.match(r'^[a-z]+:|^#|^/', url):
            return m.group(0)
        target = os.path.normpath(os.path.join(old_dir, unquote(url)))
        target = newpath_of.get(target, target)
        rel = os.path.relpath(target, new_dir).replace(os.sep, '/')
        return '](' + quote(rel, safe='/#()') + ')'
    return LINK.sub(sub, text)


ABOUT = {
    'SCHEMATICS': 'Electrical drawings: schematics (-02-), functional diagrams (-01-), component layouts (-06-), wiring (-09-), '
                  'PCB files (.pcb .dsn), and beside each scan its `(EXTRACTED).svg`: the vectors traced from it.',
    'MECHANICAL': 'Mechanical drawings: front panels, cover plates, metalwork and hardware (-03- drawings), AutoCAD files, '
                  'each with its `(EXTRACTED).svg` vectors; `<module> - front panel.svg` is the front panel as vectors.',
    'PINOUTS': 'Pinouts: the RTO-144 edge connector (connection sheets, connector layouts and rear views, strapping), and '
               'the pinout / connections drawings made from them. The module root `RTO.json` lists every contact.',
    'KICAD': 'KiCad: a schematic (`.kicad_sch`) traced from each electrical drawing, the module symbol (`.kicad_sym`) and '
             'its PCB projects. Traced schematics are the line work only: redraw with symbols over them.',
    'MANUALS': 'Manuals and manual pages, price lists, RTO-144 connection sheets, brochures, ads and other document scans.',
    'PHOTOS': 'Photographs of the module itself: front, back, inside, racked.',
    'SOFTWARE': 'Program listings and firmware, and `plugin/`: the module as a Rust VST3 / CLAP plugin and Audio Tap insert, '
                'where there is one.',
    'OCR': 'The note of every file in this module, `<file name>.md`: its date and how it was dated, where it came from, '
           'its SHA-256, the title block, traced vectors and the text recovered by OCR.',
}


def tracked_files(moddir):
    """Paths git knows under moddir (the module's own repo, or WBSps.ca for a module not split off yet)."""
    out = subprocess.run(['git', '-C', moddir, 'ls-files', '-z', '--', '.'], capture_output=True, check=True).stdout
    return {p for p in out.decode('utf-8', 'surrogateescape').split('\0') if p}


def apply(moddir, moves):
    newpath_of = {os.path.join(moddir, a): os.path.join(moddir, b) for a, b in moves}
    for k in KINDS:
        os.makedirs(os.path.join(moddir, k), exist_ok=True)
        r = os.path.join(moddir, k, 'README.md')
        if not os.path.exists(r):
            with open(r, 'w', encoding='utf-8') as fh:
                fh.write(f'# {k}\n\n{ABOUT[k]}\n\nThe pictures are on Google Drive: see the module\'s README one folder up.\n')
    known = tracked_files(moddir)
    by_kind = {}
    for a, b in moves:
        if a in known or a + '/' in {p[:len(a) + 1] for p in known if p.startswith(a + '/')}:
            by_kind.setdefault(b.split('/')[0], []).append(a)
    for k, srcs in by_kind.items():   # tracked: git mv, in batches (one index write per batch)
        for i in range(0, len(srcs), 200):
            subprocess.run(['git', '-C', moddir, 'mv', '-k', '--', *srcs[i:i + 200], k + '/'], check=True)
    for a, b in moves:                # the rest (media the repos ignore): a plain rename, the hard link goes with it
        src, dst = os.path.join(moddir, a), os.path.join(moddir, b)
        if os.path.lexists(src) and not os.path.lexists(dst):
            os.rename(src, dst)
    for a, b in moves:
        dst = os.path.join(moddir, b)
        if b.startswith('OCR/'):
            with open(dst, encoding='utf-8') as fh:
                t = fh.read()
            n = fix_links(t, moddir, os.path.join(moddir, 'OCR'), newpath_of)
            if n != t:
                with open(dst, 'w', encoding='utf-8') as fh:
                    fh.write(n)
    rel = os.path.relpath(moddir, Y2026).replace(os.sep, '/')
    with open(MOVES, 'a', encoding='utf-8') as fh:
        for a, b in moves:
            fh.write(f'{rel}/{a}\t{rel}/{b}\n')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dirs = [os.path.abspath(a) for a in args] or modules_home.module_dirs()
    total, samples = Counter(), defaultdict(list)
    for d in dirs:
        moves = plan(d)
        for a, b in moves:
            k = b.split('/')[0]
            total[k] += 1
            if True:
                samples[k].append(f'{os.path.basename(d)}: {a}')
        if '--apply' in sys.argv and moves:
            apply(d, moves)
    print(dict(total))
    if '--apply' not in sys.argv:
        import random
        random.seed(1)
        for k, v in samples.items():
            print(f'\n== {k}')
            for s in random.sample(v, min(len(v), int(os.environ.get('N', 15)))):
                print('  ', s)


if __name__ == '__main__':
    main()
