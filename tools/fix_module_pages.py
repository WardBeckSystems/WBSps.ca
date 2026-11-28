#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""The site's module pages after modules moved category (tools/module_categories.tsv) or moved into their clones.

    python3 tools/fix_module_pages.py [--dry-run]

- PAGES/<M>.md/.html: the category link, label and data-cat follow the module's category.
- PAGES/Category-<CAT>.md/.html: each module's row is on its category's page (a new category's page is made from
  another's); PAGES/Modules.md/.html list every category with its count.
- Products/Modules/index.html and Products/Modules/<CAT>/index.html: the front-panel cards, rebuilt from .gitmodules.
- Viewer links ?f=../Products/Modules/<CAT>/<M>/<file> (the old flat layout, gone) point at the file in the module's
  clone, found by name (the kind folder it was sorted into); one with no file of that name is left as it was.
"""
import csv, html, os, re, sys
from collections import defaultdict
from urllib.parse import quote, unquote

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TOP, 'tools'))
import modules_home  # noqa: E402

PAGES = os.path.join(TOP, 'PAGES')
PROD = os.path.join(TOP, 'Products', 'Modules')
DRY = '--dry-run' in sys.argv
SAFE = "/%:@&=+$,;!*~()"
e = html.escape


def rd(p):
    return open(p, encoding='utf-8').read()


def wr(p, s, changed):
    if os.path.exists(p) and rd(p) == s:
        return
    changed.append(os.path.relpath(p, TOP))
    if not DRY:
        open(p, 'w', encoding='utf-8').write(s)


def names():
    rows = rd(os.path.join(TOP, 'tools', 'module_names.tsv')).splitlines()
    return dict(r.split('\t', 1) for r in rows if '\t' in r and not r.startswith('#'))


def main():
    changed = []
    mods = modules_home.modules()
    cat_of = {m: c for c, m, _ in mods}
    clone_of = {m: d for c, m, d in mods}
    moved = [r for r in csv.reader(open(os.path.join(TOP, 'tools', 'module_categories.tsv'), encoding='utf-8'), delimiter='\t')
             if r and not r[0].startswith('#')]
    old_cat = defaultdict(set)
    for code, frm, to, *_ in moved:
        old_cat[code].add(frm)

    # 1. device pages: their category
    for code, frms in old_cat.items():
        to = cat_of.get(code)
        for ext in ('.md', '.html'):
            p = os.path.join(PAGES, code + ext)
            if not to or not os.path.exists(p):
                continue
            s = t = rd(p)
            for frm in frms:
                t = (t.replace(f'Category-{frm}.', f'Category-{to}.').replace(f'>{frm}</a>', f'>{to}</a>')
                      .replace(f'data-cat="{frm}"', f'data-cat="{to}"').replace(f'Modules/{frm}/{code}<', f'Modules/{to}/{code}<')
                      .replace(f'category: "{frm}"', f'category: "{to}"'))
            wr(p, t, changed)

    # 2. category tables: every row on its module's category page
    for ext, row_re in (('.md', re.compile(r'^\| \[(R?M[0-9A-Z]+)\]\(\1\.md\).*\n', re.M)),
                        ('.html', re.compile(r'<tr>\n<td><a href="(R?M[0-9A-Z]+)\.html">\1</a></td>\n(?:<td>.*</td>\n)*?</tr>\n'))):
        pages = {os.path.basename(p)[len('Category-'):-len(ext)]: p for p in
                 (os.path.join(PAGES, f) for f in os.listdir(PAGES) if f.startswith('Category-') and f.endswith(ext))}
        text = {c: rd(p) for c, p in pages.items()}
        rows = {}
        for c, s in text.items():
            for m in row_re.finditer(s):
                rows.setdefault(m.group(1), m.group(0))
        want = defaultdict(list)
        for code, row in rows.items():
            if code in cat_of:
                want[cat_of[code]].append((code, row))
            else:   # not a module repo (a product code): stays where it is
                want[next(c for c, s in text.items() if row in s)].append((code, row))
        tpl_cat = 'UNSORTED' if 'UNSORTED' in text else next(iter(text))
        for c in set(want) | set(text):
            s = text.get(c)
            if s is None:   # a new category: its page made from another's
                s = text[tpl_cat].replace(tpl_cat, c)
            found = list(row_re.finditer(s))
            body = ''.join(r for _, r in sorted(want.get(c, []), key=lambda x: x[0]))
            if found:
                s = s[:found[0].start()] + body + s[found[-1].end():]
            elif body:
                print(f'Category-{c}{ext}: no table to put {len(want[c])} rows in'); continue
            wr(os.path.join(PAGES, f'Category-{c}{ext}'), s, changed)
        # Modules.md / .html: one line per category with its count
        mp = os.path.join(PAGES, 'Modules' + ext)
        if os.path.exists(mp):
            s = rd(mp)
            count = {c: len(v) for c, v in want.items()}
            if ext == '.md':
                line = re.compile(r'^- \[([A-Z0-9-]+)\]\(Category-\1\.md\) — (\d+)(.*)$', re.M)
                fmt = lambda c, n: f'- [{c}](Category-{c}.md) — {n}'
            else:
                line = re.compile(r'^<li><a href="Category-([A-Z0-9-]+)\.html">\1</a> — (\d+)(.*)</li>$', re.M)
                fmt = lambda c, n: f'<li><a href="Category-{c}.html">{c}</a> — {n}</li>'
            found = list(line.finditer(s))
            if found:
                orig = {m.group(1): m.group(0) for m in found}
                out = [fmt(c, count[c]) if c in count else orig[c] for c in sorted(set(orig) | set(count))]
                keep = [l for l in s[found[0].start():found[-1].end()].split('\n') if l and not line.match(l)]
                out = sorted(out + keep, key=lambda l: re.sub(r'[^A-Z0-9]', '', l.upper().split('CATEGORY-')[-1]))
                s = s[:found[0].start()] + '\n'.join(out) + s[found[-1].end():]
                wr(mp, s, changed)

    # 3. Products/Modules card pages
    nm = names()
    by_cat = defaultdict(list)
    for c, m, d in mods:
        by_cat[c].append((m, d))

    def card(m, d, here):
        rel = os.path.relpath(d, here).replace(os.sep, '/')
        img = os.path.join(d, 'MECHANICAL', f'{m} - front panel.svg')
        pic = (f'<img loading="lazy" src="{quote(rel, safe=SAFE)}/MECHANICAL/{quote(m)}%20-%20front%20panel.svg" alt="{e(m)} front panel">'
               if os.path.exists(img) else '')
        return f'<a class="pc" href="{quote(rel, safe=SAFE)}/">{pic}<b>{e(m)}</b><small>{e(nm.get(m, ""))}</small></a>'

    def files_in(d):
        return sum(len(fs) for r, ds, fs in os.walk(d) if '.git' not in r.split(os.sep))

    tpl = rd(os.path.join(PROD, 'UNSORTED', 'index.html'))
    for c, ms in by_cat.items():
        here = os.path.join(PROD, c)
        p = os.path.join(here, 'index.html')
        s = rd(p) if os.path.exists(p) else tpl.replace('UNSORTED', c)
        i = s.index('<div class="pcs">') + len('<div class="pcs">')
        j = s.index('</div>', i)
        s = s[:i] + ''.join(card(m, d, here) for m, d in sorted(ms)) + s[j:]
        if not DRY:
            os.makedirs(here, exist_ok=True)
        wr(p, s, changed)
    for c in os.listdir(PROD):   # a category page with no modules left
        if os.path.isdir(os.path.join(PROD, c)) and c not in by_cat:
            print(f'Products/Modules/{c}: no modules left (left as it was)')
    p = os.path.join(PROD, 'index.html')
    s = rd(p)
    head = s[:s.index('<h2>')]
    tail = s[s.index('<div class="foot">'):]
    body = ''.join(f'<h2><a href="{quote(c)}/">{e(c)}</a> <small>{sum(files_in(d) for _, d in ms)} files</small></h2>'
                   f'<div class="pcs">{"".join(card(m, d, PROD) for m, d in sorted(ms))}</div>\n'
                   for c, ms in sorted(by_cat.items()))
    wr(p, head + body + tail, changed)

    # 4. viewer links into the old flat Products/Modules layout
    index = {}

    def find(code, name):
        d = clone_of.get(code)
        if not d:
            return None
        if d not in index:
            idx = defaultdict(list)
            for r, ds, fs in os.walk(d):
                ds[:] = [x for x in ds if x != '.git']
                for f in fs:
                    idx[f].append(os.path.relpath(os.path.join(r, f), d))
            index[d] = idx
        hits = index[d].get(name, [])
        return os.path.join(d, hits[0]) if len(hits) == 1 else None

    VIEW = re.compile(r'(?P<v>[^"\'\s()]*viewer\.html)\?f=(?P<f>(?:\.\./)*Products/Modules/(?P<cat>[A-Z0-9-]+)/(?P<m>R?M[0-9A-Z]+)/(?P<rest>[^"\'\s()<>&#]*))')
    fixed = left = 0
    for fn in sorted(os.listdir(PAGES)):
        if not fn.endswith(('.html', '.md')):
            continue
        p = os.path.join(PAGES, fn)
        s = rd(p)
        if 'Products/Modules/' not in s:
            continue

        def sub(mm):
            nonlocal fixed, left
            name = os.path.basename(unquote(mm.group('rest')))
            hit = find(mm.group('m'), name) if name else None
            if not hit:
                left += 1
                return mm.group(0)
            viewer = os.path.normpath(os.path.join(PAGES, unquote(mm.group('v'))))
            fixed += 1
            return (mm.group('v') + '?f=' +
                    quote(os.path.relpath(hit, os.path.dirname(viewer)).replace(os.sep, '/'), safe=SAFE))
        wr(p, VIEW.sub(sub, s), changed)
    print(f'viewer links: {fixed} pointed at the clones, {left} left (no single file of that name)')
    print(f'{len(changed)} pages {"would change" if DRY else "changed"}')


if __name__ == '__main__':
    main()
