#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""After a folder of the site moved (OLD -> NEW, paths from the WBSps.ca root), fix every link the move broke.

    python3 tools/move_relink.py OLD NEW [OLD NEW ...] [--dry-run]

Every tracked page (.html .md .js .json .css .svg, outside submodules) is read; each relative link (href= src=
"...", markdown ](...), viewer.html?f=...) is resolved from where the page was before the move (a page inside a
moved folder was at OLD/...). If that target moved, or the page itself moved, the link is written again,
relative to where the page is now, so it reaches the same file. Absolute site URLs (wbsps.ca/…,
wardbecksystems.github.io/WBSps.ca/…) into OLD are rewritten as well. Links that did not resolve before are left.
"""
import os, re, subprocess, sys
from urllib.parse import quote, unquote

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = {'.html', '.md', '.js', '.json', '.css', '.svg'}
SITES = ['https://wbsps.ca/', 'https://WBSps.ca/', 'https://wardbecksystems.github.io/WBSps.ca/']
LINK = re.compile(r'''(?P<pre>(?:href|src)\s*=\s*["']|\]\(|[?&]f=)(?P<url>[^"'()\s<>#?]+)''')


def norm(p):
    return os.path.normpath(p).replace(os.sep, '/')


def mapped(path, moves):
    for old, new in moves:
        if path == old or path.startswith(old + '/'):
            return new + path[len(old):]
    return path


def unmapped(path, moves):
    for old, new in moves:
        if path == new or path.startswith(new + '/'):
            return old + path[len(new):]
    return path


def main():
    a = [x for x in sys.argv[1:] if x != '--dry-run']
    dry = '--dry-run' in sys.argv
    moves = [(norm(a[i]).strip('/'), norm(a[i + 1]).strip('/')) for i in range(0, len(a), 2)]
    files = subprocess.run(['git', '-C', TOP, 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                           capture_output=True, text=True).stdout.split('\0')
    gitlinks = set(subprocess.run(['git', '-C', TOP, 'ls-files', '-s'], capture_output=True, text=True).stdout and
                   [l.split('\t')[1] for l in subprocess.run(['git', '-C', TOP, 'ls-files', '-s'], capture_output=True,
                    text=True).stdout.splitlines() if l.startswith('160000')])
    exists = lambda p: os.path.exists(os.path.join(TOP, p))
    pages = changed = links = 0
    for rel in filter(None, files):
        if os.path.splitext(rel)[1].lower() not in EXT or rel in gitlinks:
            continue
        p = os.path.join(TOP, rel)
        if not os.path.isfile(p):
            continue
        try:
            t = open(p, encoding='utf-8').read()
        except UnicodeDecodeError:
            continue
        here_new = os.path.dirname(rel)
        here_old = os.path.dirname(unmapped(rel, moves))
        page_moved = here_new != here_old

        def fix(m):
            nonlocal links
            url = m.group('url')
            pre = m.group('pre')
            for s in SITES:   # absolute site URLs
                if url.startswith(s):
                    path = unquote(url[len(s):])
                    new = mapped(path, moves)
                    if new != path:
                        links += 1
                        return pre + s + quote(new, safe="/%:@&=+$,;'()!*~")
                    return m.group(0)
            if re.match(r'^[a-z][a-z0-9+.-]*:', url, re.I) or url.startswith(('/', '#', 'data:')):
                return m.group(0)
            base = here_old
            if pre.endswith('f='):   # viewer.html?f=<path from the viewer's folder: the root, or 2026/ for 2026 pages>
                vb = '2026' if rel.startswith('2026/') else ''
                target = norm(os.path.join(vb, unquote(url)))
                new_target = mapped(target, moves)
                if new_target == target:
                    return m.group(0)
                links += 1
                return pre + quote(os.path.relpath(new_target, vb or '.').replace(os.sep, '/'), safe="/%:@&=+$,;'()!*~")
            target = norm(os.path.join(base, unquote(url)))
            if target.startswith('..'):
                return m.group(0)
            new_target = mapped(target, moves)
            if new_target == target and not page_moved:
                return m.group(0)
            if not exists(new_target) and not exists(target):
                return m.group(0)   # broken before: leave it
            r = os.path.relpath(new_target, here_new or '.').replace(os.sep, '/')
            if url.endswith('/') and not r.endswith('/'):
                r += '/'
            if r == url or unquote(url) == r:
                return m.group(0)
            links += 1
            return pre + quote(r, safe="/%:@&=+$,;'()!*~")

        s = LINK.sub(fix, t)
        pages += 1
        if s != t:
            changed += 1
            if not dry:
                open(p, 'w', encoding='utf-8').write(s)
    print(f'{pages} pages read, {changed} changed, {links} links rewritten' + (' (dry run)' if dry else ''))


if __name__ == '__main__':
    main()
