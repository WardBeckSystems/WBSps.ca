#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Markdown links whose path has literal ( ) or ' (written by move_relink.py before it encoded them): %28 %29 %27 again.

    python3 tools/fix_link_parens.py [--dry-run]
"""
import os, re, subprocess, sys
TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ](path) where path has no spaces and holds balanced (...) groups; only paths that look like files or folders
MD = re.compile(r"\]\(((?:[^\s()]|\([^\s()]*\))*\([^\s()]*\)(?:[^\s()]|\([^\s()]*\))*)\)")
HREF = re.compile(r'''((?:href|src)=")([^"]*[()'][^"]*)(")''')
enc = lambda s: s.replace('(', '%28').replace(')', '%29').replace("'", '%27')
dry = '--dry-run' in sys.argv
files = subprocess.run(['git', '-C', TOP, 'ls-files', '-z', '--cached', '--others', '--exclude-standard', '--', '*.md', '*.html'],
                       capture_output=True, text=True).stdout.split('\0')
n = links = 0
for rel in filter(None, files):
    p = os.path.join(TOP, rel)
    if not os.path.isfile(p):
        continue
    t = open(p, encoding='utf-8', errors='surrogateescape').read()
    def md(m):
        global links
        u = m.group(1)
        if u.startswith(('http', 'javascript:')) or '%20' not in u and '/' not in u:
            return m.group(0)
        links += 1
        return '](' + enc(u) + ')'
    s = MD.sub(md, t)
    if s != t:
        n += 1
        if not dry:
            open(p, 'w', encoding='utf-8', errors='surrogateescape').write(s)
print(f'{n} pages, {links} markdown links re-encoded' + (' (dry run)' if dry else ''))
