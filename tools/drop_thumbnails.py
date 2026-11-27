#!/usr/bin/env python3
"""Take web thumbnails ('<name>_small.jpg') off the wiki pages when the full-size '<name>' is on the same page.

    python3 tools/drop_thumbnails.py [PAGES/M466.html ...]     # default: every PAGES/*.html and *.md

The _small copies were the old website's thumbnails of the pictures beside them. A thumbnail that is the only copy
of its picture stays. On .html pages it removes the gallery tile and the file-table row; on .md pages the table row.
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = r'\.(?:jpe?g|png|gif|webp|tiff?|bmp)'
NAME = re.compile(r'>([^<>]+?' + EXT + r')</a>', re.I)            # link text of a file
MDNAME = re.compile(r'\[([^\]]+?' + EXT + r')\]\(', re.I)
SMALL = re.compile(r'^(.*)_small(' + EXT + r')$', re.I)


def thumbs(names):
    """The _small names whose full-size picture (any extension) is also listed."""
    stems = {os.path.splitext(n)[0].lower() for n in names}
    return {n for n in names if (m := SMALL.match(n)) and m.group(1).lower() in stems}


def clean_html(s):
    drop = thumbs(set(NAME.findall(s)))
    if not drop:
        return s, 0
    alt = '|'.join(re.escape(n) for n in sorted(drop, key=len, reverse=True))
    tile = re.compile(r'<a href="[^"]*"><img [^>]*>(?:' + alt + r')</a>')
    row = re.compile(r'<tr>\n(?:<td>[^\n]*</td>\n)*?<td><a href="[^"]*">(?:' + alt + r')</a></td>\n(?:<td>[^\n]*</td>\n)*</tr>\n')
    s, a = tile.subn('', s)
    s, b = row.subn('', s)
    return s, a + b


def clean_md(s):
    drop = thumbs(set(MDNAME.findall(s)))
    if not drop:
        return s, 0
    out, n = [], 0
    for line in s.split('\n'):
        m = MDNAME.search(line) if line.startswith('|') else None
        if m and m.group(1) in drop:
            n += 1
            continue
        out.append(line)
    return '\n'.join(out), n


def main():
    files = sys.argv[1:] or sorted(glob.glob(os.path.join(ROOT, 'PAGES', '*.html')) + glob.glob(os.path.join(ROOT, 'PAGES', '*.md')))
    pages = total = 0
    for f in files:
        s = open(f, encoding='utf-8').read()
        t, n = (clean_md if f.endswith('.md') else clean_html)(s)
        if n:
            open(f, 'w', encoding='utf-8').write(t)
            pages += 1
            total += n
    print(f'{total} thumbnail entries removed from {pages} pages')


if __name__ == '__main__':
    main()
