#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""After sort_module_folders.py: every path that named a moved module file names its new place.

In:  tools/module_moves.tsv (old <TAB> new, relative to 2026/, e.g. Modules/FILTERS/M462/x.jpg -> Modules/FILTERS/M462/SCHEMATICS/x.jpg)
Fix: the timeline database (every text column that holds a path), 2026/_catalog (drive map re-sharded, everything.js,
     hotspots.js, folders/, rotation, traces …), and every .md / .html / .js / .json page under 2026 that links a module
     file, raw or URL-encoded (%20). Only exact, whole file names are replaced.

    python3 tools/apply_module_moves.py [--moves MOVES.tsv] [--db-only|--files-only] [--dry]
"""
import json
import os
import sqlite3
import sys
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Y2026 = os.path.join(ROOT, '2026')
DB = os.path.join(Y2026, 'timelines', 'wbs_timeline.db')
MOVES = (sys.argv[sys.argv.index('--moves') + 1] if '--moves' in sys.argv     # e.g. tools/module_category_moves.tsv
         else os.path.join(ROOT, 'tools', 'module_moves.tsv'))
DRY = '--dry' in sys.argv
TEXT_EXT = {'.md', '.html', '.js', '.json', '.csv', '.svg', '.txt'}
SKIP_DIRS = {'.git', 'node_modules', 'venv', 'venv-gpu', '__pycache__', 'extractors', '_packages', 'target', 'thumbs', 'pdfjs'}
DELIM = set('"\'\n\t`|)],;#?&<>') | {'\r'}


def load():
    raw, enc = {}, {}
    with open(MOVES, encoding='utf-8') as fh:
        for line in fh:
            a, b = line.rstrip('\n').split('\t')
            if a != b:
                raw[a] = b
                enc[quote(a, safe='/()')] = quote(b, safe='/()')
                enc[quote(a, safe='/')] = quote(b, safe='/')
                enc[a.replace(' ', '%20')] = b.replace(' ', '%20')
    return raw, enc


def remap(s, maps):
    """Replace every whole module path in s (raw or encoded) by its new path."""
    if 'Modules/' not in s:
        return s
    out, i = [], 0
    while True:
        j = s.find('Modules/', i)
        if j < 0:
            out.append(s[i:])
            break
        out.append(s[i:j])
        best = None
        # candidate ends: every delimiter (and the string end) within 400 characters; the first exact hit wins
        k = j + 8
        lim = min(len(s), j + 400)
        while k <= lim:
            if k == len(s) or s[k] in DELIM:
                cand = s[j:k]
                for m in maps:
                    if cand in m:
                        best = (k, m[cand])
                        break
                if best:
                    break
            k += 1
        if best:
            out.append(best[1])
            i = best[0]
        else:
            out.append('Modules/')
            i = j + 8
    return ''.join(out)


def fix_db(raw, enc):
    con = sqlite3.connect(DB)
    n = 0
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")') if (r[2] or '').upper() in ('TEXT', '')]
        for c in cols:
            rows = con.execute(f'SELECT rowid, "{c}" FROM "{t}" WHERE typeof("{c}")=\'text\' AND "{c}" LIKE \'%Modules/%\'').fetchall()
            ch = []
            for rid, v in rows:
                w = remap(v, (raw, enc))
                if w != v:
                    ch.append((w, rid))
            if ch:
                print(f'  db {t}.{c}: {len(ch)} rows')
                n += len(ch)
                if not DRY:
                    try:
                        con.executemany(f'UPDATE "{t}" SET "{c}"=? WHERE rowid=?', ch)
                    except sqlite3.IntegrityError:   # a primary key: one row at a time, keep the first
                        for w, rid in ch:
                            con.execute(f'UPDATE OR IGNORE "{t}" SET "{c}"=? WHERE rowid=?', (w, rid))
    if not DRY:
        con.commit()
    print(f'database: {n} values')


def fix_drive(which='drive'):
    """_catalog/drive/ and _catalog/traces/: maps keyed by 2026 path (traces also "<path>#p3"), in 256 slices by key."""
    d = os.path.join(Y2026, '_catalog', which)
    if not os.path.isdir(d):
        return
    raw, _ = load()
    m = {}
    for f in os.listdir(d):
        if f.endswith('.json'):
            with open(os.path.join(d, f), encoding='utf-8') as fh:
                m.update(json.load(fh))
    moved = 0
    out = {}
    for k, v in m.items():
        base, sep, frag = k.partition('#')
        nk = raw.get(base, base) + sep + frag
        moved += nk != k
        out[nk] = v
    print(f'{which} map: {moved} of {len(m)} keys moved')
    if DRY:
        return
    from collections import defaultdict
    h = lambda key: f'{_fnv(key) & 0xFF:02x}'
    shards = defaultdict(dict)
    for k, v in out.items():
        shards[h(k)][k] = v
    for f in os.listdir(d):
        if f.endswith('.json'):
            os.remove(os.path.join(d, f))
    for s, vals in shards.items():
        with open(os.path.join(d, s + '.json'), 'w', encoding='utf-8') as fh:
            json.dump(vals, fh, ensure_ascii=False, separators=(',', ':'))


def _fnv(key):   # make_drive_links.shard_of / drive_lookup.js
    x = 0x811C9DC5
    for b in key.encode('utf-8'):
        x = ((x ^ b) * 0x01000193) & 0xFFFFFFFF
    return x


def fix_files(raw, enc):
    n = 0
    for top, dirs, names in os.walk(Y2026):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith('_old_')]
        if os.path.relpath(top, Y2026).replace(os.sep, '/').startswith(('_catalog/drive', '_catalog/traces')):
            continue
        for name in names:
            if os.path.splitext(name)[1].lower() not in TEXT_EXT:
                continue
            p = os.path.join(top, name)
            try:
                if os.path.getsize(p) > 200_000_000:
                    continue
                with open(p, encoding='utf-8') as fh:
                    t = fh.read()
            except (UnicodeDecodeError, OSError):
                continue
            if 'Modules/' not in t:
                continue
            w = remap(t, (raw, enc))
            if w != t:
                n += 1
                if not DRY:
                    with open(p, 'w', encoding='utf-8') as fh:
                        fh.write(w)
    print(f'pages and catalogs: {n} files')


def main():
    raw, enc = load()
    print(f'{len(raw)} moves')
    if '--files-only' not in sys.argv:
        fix_db(raw, enc)
    if '--db-only' not in sys.argv:
        fix_drive('drive')
        fix_drive('traces')
        fix_files(raw, enc)


if __name__ == '__main__':
    main()
