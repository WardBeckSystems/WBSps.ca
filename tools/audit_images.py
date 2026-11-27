#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Audit: thumbnails and duplicate pictures, and which copy wins (highest resolution, then the sharpest).

    audit_images.py OUT_DIR ROOT...

Every picture under the ROOTs (hard links count once) gets: its size in pixels, a 64-bit difference hash (dHash, of the
picture shrunk to 9x8 grey) and a sharpness score (variance of its edges at a common 512 px scale).
  exact      same bytes (sha256)
  same       the same picture: dHash within 6 bits and the same aspect ratio (±3 %): re-saves, resizes, thumbnails
  thumbnail  a member of a group that is at most a quarter of the winner's pixels, or named like one (_small, thumb,
             -150x150 ...)
Winner of each group: most pixels, then sharpest, then biggest file. Out: OUT_DIR/audit.json (every group, winner first),
OUT_DIR/losers.tsv (loser, winner, why, where), OUT_DIR/index.html (the report, thumbnails of each group side by side).
Pictures under 48 px either way (web bullets, spacers, icons) are counted but not grouped. Cache: OUT_DIR/cache.json.
"""
import base64
import hashlib
import html
import json
import os
import re
import sys
from collections import defaultdict
from multiprocessing import Pool
from urllib.parse import quote

from PIL import Image, ImageFilter, ImageStat

Image.MAX_IMAGE_PIXELS = None
EXT = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp'}
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', 'venv', 'venv-gpu', 'extractors', '_packages', 'dist', 'target',
             '_previews', '_catalog', '_traces', '_sidecars', 'thumbs'}   # the site's own generated previews
THUMB_NAME = re.compile(r'(?i)(^|[_\-. ])(small|thumb|thumbnail|thumbs|tn|sm|mini|preview)([_\-. ]|\d|$)|-\d{2,4}x\d{2,4}\.\w+$|^_?thumbs?/')
TINY = 48
DOXYGEN = re.compile(r'_8[ch](pp)?(_|\.)|cgraph|icgraph|__incl|__dep|inherit_graph|collaboration_graph|^form_\d+\.png$')


def walk(roots):
    seen, out = set(), []
    for root in roots:
        for r, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
            for f in files:
                if os.path.splitext(f)[1].lower() in EXT:
                    p = os.path.join(r, f)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    key = (st.st_dev, st.st_ino)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append((p, st.st_size, int(st.st_mtime)))
    return out


def measure(item):
    p, size, mtime = item
    try:
        with Image.open(p) as im:
            w, h = im.size
            if im.format == 'JPEG':
                im.draft('L', (max(512, w // 8), max(512, h // 8)))
            g = im.convert('L')
        dh = g.resize((9, 8), Image.LANCZOS)
        px = dh.tobytes()
        bits = 0
        for y in range(8):
            for x in range(8):
                bits = bits << 1 | (px[y * 9 + x] > px[y * 9 + x + 1])
        d16 = g.resize((17, 16), Image.LANCZOS).tobytes()
        big = 0
        for y in range(16):
            for x in range(16):
                big = big << 1 | (d16[y * 17 + x] > d16[y * 17 + x + 1])
        v32 = base64.b64encode(g.resize((32, 32), Image.LANCZOS).tobytes()).decode()
        s = g.copy()
        s.thumbnail((512, 512))
        sharp = ImageStat.Stat(s.filter(ImageFilter.FIND_EDGES)).var[0]
        return p, dict(w=w, h=h, d=bits, D=f'{big:064x}', v=v32, s=round(sharp, 1), b=size, t=mtime)
    except Exception as e:      # unreadable / truncated: reported, not grouped
        return p, dict(err=str(e)[:120], b=size, t=mtime)


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def where(p, roots):
    """The repo (clone folder) or source tree a file is in."""
    for root in roots:
        a = os.path.abspath(root)
        if os.path.abspath(p).startswith(a + os.sep):
            rel = os.path.relpath(p, a)
            top = rel.split(os.sep)[0]
            return (os.path.basename(a) + '/' + top) if os.path.basename(a) != 'Github.WardBeckSystems' else top
    return '?'


# a different shot or sheet even when it looks the same: camera frame numbers, drawing numbers, issues, sheets, pages
TOKENS = {
    'frame': re.compile(r'(?i)(?:IMG|DSC|DSCN|DSCF|PICT|MVC|P|CIMG|DCP|PANA)[_-]?(\d{3,8})|(\d{8}[_-]\d{6})'),
    'drawing': re.compile(r'(?<![\dA-Z])([A-D]? ?\d{1,6}-\d{1,4}-\d{1,4}(?:-\d{1,3})?)(?!\d)', re.I),
    'issue': re.compile(r'(?i)\biss(?:ue)?\.? ?(\d+)'),
    'sheet': re.compile(r'(?i)\b(?:sheet|sht|page|pg|p)\.? ?(\d+)(?: of \d+)?'),
    'module': re.compile(r'(?<![A-Z0-9])(M\d{3,4}[A-Z]?)(?![0-9])'),
    'figure': re.compile(r'(?i)\bfig(?:ure)?\.? ?(\d+)'),
    'part': re.compile(r'(?i)\((\d+)\)|[_ -](\d{1,3})\.\w+$'),
}


def tokens(path):
    n = os.path.basename(path)
    out = {}
    for k, rx in TOKENS.items():
        v = {''.join(x for x in (m if isinstance(m, tuple) else (m,)) if x) for m in rx.findall(n)}
        if v:
            out[k] = v
    return out


def distinct(a, b):
    """True when the names say these are different shots or sheets (both carry a token of a kind, values differ)."""
    ta, tb = tokens(a), tokens(b)
    return any(k in tb and ta[k] != tb[k] for k in ta if k != 'part') or \
        ('part' in ta and 'part' in tb and ta['part'] != tb['part'] and
         os.path.splitext(re.sub(r'\(\d+\)|[_ -]\d{1,3}(?=\.\w+$)', '', os.path.basename(a)))[0].strip().lower() ==
         os.path.splitext(re.sub(r'\(\d+\)|[_ -]\d{1,3}(?=\.\w+$)', '', os.path.basename(b)))[0].strip().lower())


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def main():
    out, roots = sys.argv[1], sys.argv[2:]
    os.makedirs(out, exist_ok=True)
    cache_f = os.path.join(out, 'cache.json')
    cache = json.load(open(cache_f)) if os.path.isfile(cache_f) else {}
    items = walk(roots)
    todo = [it for it in items if not (it[0] in cache and cache[it[0]].get('b') == it[1] and cache[it[0]].get('t') == it[2]
                                        and ('D' in cache[it[0]] or 'err' in cache[it[0]]))]
    print(f'{len(items)} pictures, {len(todo)} to measure', flush=True)
    with Pool(12) as pool:
        for i, (p, m) in enumerate(pool.imap_unordered(measure, todo, chunksize=64), 1):
            cache[p] = m
            if i % 5000 == 0:
                print(f'  {i}/{len(todo)}', flush=True)
                json.dump(cache, open(cache_f, 'w'))
    live = {p for p, _, _ in items}
    cache = {p: m for p, m in cache.items() if p in live}
    json.dump(cache, open(cache_f, 'w'))

    good = {p: m for p, m in cache.items() if 'err' not in m}
    errs = {p: m for p, m in cache.items() if 'err' in m}
    doxy = {p for p in good if DOXYGEN.search(os.path.basename(p))}
    big = {p: m for p, m in good.items() if min(m['w'], m['h']) >= TINY and p not in doxy}
    tiny = len(good) - len(big) - len(doxy)
    dsu = DSU()
    why = {}
    # exact: same size in bytes, then sha256
    by_size = defaultdict(list)
    for p, m in big.items():
        by_size[m['b']].append(p)
    for ps in by_size.values():
        if len(ps) > 1:
            hs = defaultdict(list)
            for p in ps:
                big[p]['sha'] = sha(p)
                hs[big[p]['sha']].append(p)
            for g in hs.values():
                for q in g[1:]:
                    dsu.union(q, g[0])
                    why[(q, g[0])] = 'exact'
    # same picture: dHash within 6 bits (pigeonhole: some byte equal), same aspect ratio
    buckets = defaultdict(list)
    for p, m in big.items():
        for k in range(8):
            buckets[(k, (m['d'] >> (8 * k)) & 255)].append(p)
    import numpy as np
    POP = np.array([bin(x).count('1') for x in range(256)], dtype=np.uint8)
    names = list(big)
    hashes = np.array([big[p]['d'] for p in names], dtype=np.uint64)
    ratio = np.array([big[p]['w'] / big[p]['h'] for p in names])
    flat = (hashes == 0) | (hashes == np.uint64((1 << 64) - 1))
    H256 = np.array([np.frombuffer(bytes.fromhex(big[p]['D']), dtype=np.uint8) for p in names])
    V = np.array([np.frombuffer(base64.b64decode(big[p]['v']), dtype=np.uint8) for p in names], dtype=np.float32)
    V = (V - V.mean(1, keepdims=True)) / (V.std(1, keepdims=True) + 1e-3)

    raw = np.array([np.frombuffer(base64.b64decode(big[p]['v']), dtype=np.uint8) for p in names], dtype=np.float32)
    blank = raw.std(1) < 6          # a nearly blank page: every blank page looks like every other

    def same(i, j):
        if blank[i] or blank[j]:
            return False
        if POP[H256[i] ^ H256[j]].sum() > 26:            # of 256 bits
            return False
        return float(np.abs(V[i] - V[j]).mean()) <= 0.25  # 32x32, brightness/contrast normalised
    index = {p: i for i, p in enumerate(names)}
    similar = set()
    for key, ps in buckets.items():
        if len(ps) < 2 or len(ps) > 4000:      # flat / blank pictures share hashes: too many to be meaningful
            continue
        idx = np.array([index[p] for p in ps])
        h, r = hashes[idx], ratio[idx]
        for a in range(len(idx) - 1):
            if flat[idx[a]]:
                continue
            x = (h[a + 1:] ^ h[a]).view(np.uint8).reshape(-1, 8)
            dist = POP[x].sum(1)
            ok = np.nonzero((dist <= 6) & (np.abs(r[a] / r[a + 1:] - 1) <= 0.03) & ~flat[idx[a + 1:]])[0]
            for b in ok:
                i, j = idx[a], idx[a + 1 + b]
                if same(i, j):
                    if distinct(names[i], names[j]):
                        similar.add((names[i], names[j]) if names[i] < names[j] else (names[j], names[i]))
                    else:
                        dsu.union(names[i], names[j])
    groups = defaultdict(list)
    for p in big:
        if p in dsu.p:
            groups[dsu.find(p)].append(p)
    rows, report = [], []
    for g in groups.values():
        if len(g) < 2:
            continue
        g.sort(key=lambda p: (-big[p]['w'] * big[p]['h'], -big[p]['s'], -big[p]['b'], len(p)))
        win = g[0]
        wm = big[win]
        members = []
        for p in g:
            m = big[p]
            if p == win:
                kind = 'winner'
            elif m.get('sha') and m.get('sha') == wm.get('sha'):
                kind = 'exact'
            elif m['w'] * m['h'] * 4 <= wm['w'] * wm['h'] or THUMB_NAME.search(os.path.basename(p)):
                kind = 'thumbnail'
            else:
                kind = 'same'
            members.append(dict(path=p, kind=kind, where=where(p, roots), **{k: m[k] for k in ('w', 'h', 's', 'b')}))
            if p != win:
                rows.append((p, win, kind, where(p, roots), where(win, roots)))
        report.append(members)
    report.sort(key=lambda g: -len(g))
    json.dump(dict(groups=report, unreadable=sorted(errs), tiny=tiny, pictures=len(cache)), open(os.path.join(out, 'audit.json'), 'w'), indent=0)
    with open(os.path.join(out, 'similar.tsv'), 'w') as f:
        f.write('a\tb\ta_in\tb_in\n')
        for x, y in sorted(similar):
            f.write(f'{x}\t{y}\t{where(x, roots)}\t{where(y, roots)}\n')
    with open(os.path.join(out, 'losers.tsv'), 'w') as f:
        f.write('loser\twinner\tkind\tloser_in\twinner_in\n')
        for r in rows:
            f.write('\t'.join(r) + '\n')
    kinds = defaultdict(int)
    kb = defaultdict(int)
    for g in report:
        for m in g[1:]:
            kinds[m['kind']] += 1
            kb[m['kind']] += m['b']
    cross = sum(1 for r in rows if r[3] != r[4])
    write_html(out, report, kinds, kb, cross, len(cache), tiny, errs)
    print(f'{len(cache)} pictures: {len(report)} groups; losers: ' +
          ', '.join(f'{k} {kinds[k]} ({kb[k] / 1e9:.2f} GB)' for k in ('exact', 'thumbnail', 'same')) +
          f'; {cross} losers are in another repo than their winner; {len(similar)} similar pairs (different shots/sheets, kept); {len(errs)} unreadable; {tiny} tiny, {len(doxy)} doxygen (not grouped)')


def write_html(out, report, kinds, kb, cross, n, tiny, errs):
    e = html.escape
    th = os.path.join(out, 'thumbs')
    os.makedirs(th, exist_ok=True)

    def thumb(p):
        t = os.path.join(th, hashlib.md5(p.encode()).hexdigest() + '.jpg')
        if not os.path.isfile(t):
            try:
                with Image.open(p) as im:
                    im.draft('RGB', (240, 240))
                    im = im.convert('RGB')
                    im.thumbnail((180, 180))
                    im.save(t, quality=70)
            except Exception:
                return ''
        return 'thumbs/' + os.path.basename(t)

    css = """:root{--bg:#f4f1ea;--fg:#1d1d1b;--mut:#6b675e;--card:#fff;--line:#d9d3c7;--win:#2e7d32;--thumb:#b26a00;--exact:#a12a2a;--same:#3b5f8a}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#ece8df;--mut:#9a958a;--card:#22211e;--line:#3a3833}}
body{background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif;margin:0;padding:16px}
h1{font-size:20px;margin:0 0 4px}.mut{color:var(--mut)}.g{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:12px 0;padding:10px;display:flex;flex-wrap:wrap;gap:10px}
.m{width:190px;font-size:11px;word-break:break-all}.m img{display:block;max-width:180px;max-height:180px;border-radius:4px;margin-bottom:4px}
.k{font-weight:600;text-transform:uppercase;font-size:10px;letter-spacing:.05em}.winner .k{color:var(--win)}.thumbnail .k{color:var(--thumb)}.exact .k{color:var(--exact)}.same .k{color:var(--same)}
.winner img{outline:3px solid var(--win)}table{border-collapse:collapse}td{padding:2px 10px 2px 0}"""
    parts = [f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Picture Audit</title><style>{css}</style>',
             '<h1>Picture audit: thumbnails and duplicates</h1>',
             f'<p class="mut">{n} pictures · {len(report)} groups · winner = highest resolution, then sharpest · {tiny} tiny pictures (&lt;48 px) not grouped · {len(errs)} unreadable</p>',
             '<table>' + ''.join(f'<tr><td class="k {k}">{k}</td><td>{kinds[k]} losers</td><td>{kb[k] / 1e9:.2f} GB</td></tr>' for k in ('exact', 'thumbnail', 'same')) +
             f'<tr><td>across repos</td><td>{cross} losers in another repo than their winner</td></tr></table>']
    for g in report[:1500]:
        parts.append('<div class="g">')
        for m in g:
            src = thumb(m['path'])
            parts.append(f'<div class="m {m["kind"]}"><img loading="lazy" src="{quote(src)}" alt=""><span class="k">{m["kind"]}</span> '
                         f'{m["w"]}×{m["h"]} · sharp {m["s"]:.0f} · {m["b"] / 1e6:.1f} MB<br><b>{e(m["where"])}</b><br>{e(os.path.basename(m["path"]))}</div>')
        parts.append('</div>')
    if len(report) > 1500:
        parts.append(f'<p class="mut">… {len(report) - 1500} more groups in audit.json / losers.tsv</p>')
    open(os.path.join(out, 'index.html'), 'w').write('\n'.join(parts))


if __name__ == '__main__':
    main()
