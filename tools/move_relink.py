#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""After a folder of the site moved (OLD -> NEW, paths from the WBSps.ca root), fix every link the move broke.

    python3 tools/move_relink.py OLD NEW [OLD NEW ...] [--map MAP.json] [--in DIR ...] [--dry-run]

OLD NEW pairs are moves that happened: a page now under NEW was under OLD, and links to OLD/... go to NEW/....
--map MAP.json  {old: new} links only (nothing moved; e.g. a wiki page that now lives in its device's folder, or
                "2026": "" for the published copy at the root); a new ending in "/" links the folder.
--in DIR        also read the pages inside DIR (a submodule or a folder of submodules: Products/Modules); their
                changes are left for each repository to commit.

Every page (.html .md .js .json .css .svg) is read; each relative link (href= src= "...", markdown ](...),
viewer.html?f=...) is resolved from where the page was before the move. If its target moved, or the page did,
the link is written again relative to where the page is now. Absolute site URLs (wbsps.ca/…,
wardbecksystems.github.io/WBSps.ca/…) are mapped too. A link whose new target does not exist is left as it was.
"""
import json, os, re, subprocess, sys
from urllib.parse import quote, unquote

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = {'.html', '.md', '.js', '.json', '.css', '.svg'}
SITES = ['https://wbsps.ca/', 'https://WBSps.ca/', 'https://wardbecksystems.github.io/WBSps.ca/']
LINK = re.compile(r'''(?P<pre>(?:href|src)\s*=\s*["']|\]\()(?P<url>[^"'()\s<>#?]+)''')
# viewer.html?f=<path from the viewer's own folder>
VIEW = re.compile(r'''(?P<pre>(?:href|src)\s*=\s*["']|\]\()(?P<viewer>[^"'()\s<>#?]*viewer\.html)\?f=(?P<f>[^"'()\s<>&#]+)''')
SAFE = "/%:@&=+$,;!*~"


def norm(p):
    p = os.path.normpath(p).replace(os.sep, '/')
    return '' if p == '.' else p


def under(path, old):
    return old == '' or path == old or path.startswith(old + '/')


def remap(path, pairs, exact):
    """path -> its new place (exact maps first, then the longest prefix)."""
    if path in exact:
        return exact[path]
    for old, new in pairs:
        if under(path, old):
            rest = path[len(old):].lstrip('/') if old else path
            return '/'.join(x for x in (new.rstrip('/'), rest) if x) + ('/' if new.endswith('/') and not rest else '')
    return path


def tracked(args):
    return [f for f in subprocess.run(['git', '-C', TOP, *args], capture_output=True, text=True).stdout.split('\0') if f]


def main():
    argv = sys.argv[1:]
    dry = '--dry-run' in argv
    argv = [x for x in argv if x != '--dry-run']
    mapfile, ins, pos = None, [], []
    i = 0
    while i < len(argv):
        if argv[i] == '--map':
            mapfile = argv[i + 1]; i += 2
        elif argv[i] == '--in':
            ins.append(norm(argv[i + 1])); i += 2
        else:
            pos.append(argv[i]); i += 1
    moves = [(norm(pos[i]), norm(pos[i + 1])) for i in range(0, len(pos), 2)]
    extra = json.load(open(mapfile)) if mapfile else {}
    exact = {norm(k): v if v.endswith('/') else norm(v) for k, v in extra.items() if os.path.splitext(k)[1]}
    pairs = sorted(moves + [(norm(k), v) for k, v in extra.items() if not os.path.splitext(k)[1]],
                   key=lambda x: -len(x[0]))
    back = sorted(((n, o) for o, n in moves), key=lambda x: -len(x[0]))   # where a page was before
    exists = lambda p: os.path.exists(os.path.join(TOP, p.rstrip('/')) or TOP)

    files = tracked(['ls-files', '-z', '--cached', '--others', '--exclude-standard'])
    links_s = tracked(['ls-files', '-z', '-s'])
    gitlinks = {l.split('\t', 1)[1] for l in subprocess.run(['git', '-C', TOP, 'ls-files', '-s'], capture_output=True,
                text=True).stdout.splitlines() if l.startswith('160000')}
    for d in ins:   # pages inside submodules
        for g in sorted(x for x in gitlinks if under(x, d)):
            files += [g + '/' + f for f in subprocess.run(['git', '-C', os.path.join(TOP, g), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                      capture_output=True, text=True).stdout.split('\0') if f]
    pages = changed = links = 0
    touched = set()
    for rel in files:
        if os.path.splitext(rel)[1].lower() not in EXT or rel in gitlinks:
            continue
        p = os.path.join(TOP, rel)
        if not os.path.isfile(p) or os.path.islink(p):
            continue
        try:
            t = open(p, encoding='utf-8').read()
        except UnicodeDecodeError:
            continue
        origin = rel
        for n, o in back:
            if under(rel, n):
                origin = (o + '/' + rel[len(n):].lstrip('/')).lstrip('/')
                break
        here_new, here_old = os.path.dirname(rel), os.path.dirname(origin)

        def fix(m):
            nonlocal links
            url, pre = m.group('url'), m.group('pre')
            for s in SITES:
                if url.startswith(s):
                    path = unquote(url[len(s):])
                    new = remap(path, pairs, exact)
                    if new != path:
                        links += 1
                        return pre + s + quote(new, safe=SAFE)
                    return m.group(0)
            if re.match(r'^[a-z][a-z0-9+.-]*:', url, re.I) or url.startswith(('/', '#', 'data:')):
                return m.group(0)
            if url.endswith('viewer.html') and m.string.startswith('?f=', m.end()):
                return m.group(0)   # done by view()
            target = norm(os.path.join(here_old, unquote(url)))
            if target.startswith('..'):
                return m.group(0)
            new_target = remap(target, pairs, exact)
            if new_target == target and here_new == here_old:
                return m.group(0)
            if not exists(new_target):
                return m.group(0)
            r = os.path.relpath(new_target.rstrip('/') or '.', here_new or '.').replace(os.sep, '/')
            if (url.endswith('/') or new_target.endswith('/')) and not r.endswith('/'):
                r += '/'
            if r == unquote(url):
                return m.group(0)
            links += 1
            return pre + quote(r, safe=SAFE)

        def view(m):
            nonlocal links
            pre, viewer, f = m.group('pre'), m.group('viewer'), m.group('f')
            if re.match(r'^[a-z][a-z0-9+.-]*:', viewer, re.I) or viewer.startswith('/'):
                return m.group(0)
            v_old = norm(os.path.join(here_old, unquote(viewer)))   # the viewer, as the page reached it before
            if v_old.startswith('..'):
                return m.group(0)
            v_new = remap(v_old, pairs, exact)
            vb_old, vb_new = os.path.dirname(v_old), os.path.dirname(v_new)
            target = norm(os.path.join(vb_old, unquote(f)))
            new_target = remap(target, pairs, exact)
            if new_target == target and v_new == v_old and here_new == here_old:
                return m.group(0)
            if not exists(new_target):
                return m.group(0)
            nv = os.path.relpath(v_new, here_new or '.').replace(os.sep, '/')
            nf = os.path.relpath(new_target.rstrip('/') or '.', vb_new or '.').replace(os.sep, '/')
            out = pre + quote(nv, safe=SAFE) + '?f=' + quote(nf, safe=SAFE)
            if out != m.group(0):
                links += 1
            return out

        s = LINK.sub(fix, VIEW.sub(view, t))
        pages += 1
        if s != t:
            changed += 1
            touched.add(rel)
            if not dry:
                open(p, 'w', encoding='utf-8').write(s)
    print(f'{pages} pages read, {changed} changed, {links} links rewritten' + (' (dry run)' if dry else ''))
    subs = sorted({g for g in gitlinks for r in touched if r.startswith(g + '/')})
    if subs:
        print(f'{len(subs)} submodules have changed pages (commit them in each repository)')


if __name__ == '__main__':
    main()
