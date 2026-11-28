#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""ADVERTISEMENTS: the ads, brochures and press as their own repo (WardBeckSystems/ADVERTISEMENTS), each picture
with its note beside it (the site's scrubbed note when there is one). Banned / private files are left out
(make_site.py's list). Hard links: no extra disk.

    python3 -I tools/make_advertisements_repo.py
"""
import os, shutil, sys
TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.argv = ['make_site.py', os.path.join(TOP, '2026'), os.path.join(TOP, 'site')]
sys.path.insert(0, os.path.join(TOP, '2026', 'timelines'))
import make_site as M  # noqa: E402
SRC, OUT = os.path.join(TOP, '2026', 'ADVERTISEMENTS'), os.path.join(TOP, 'WBSps.ca', 'Github.WardBeckSystems', 'ADVERTISEMENTS')
PIC = {'.jpg', '.jpeg', '.png', '.pdf', '.gif', '.tif', '.tiff'}
n = skipped = 0
for dp, dn, fn in os.walk(SRC):
    for f in fn:
        if os.path.splitext(f)[1].lower() not in PIC:
            continue
        rel = os.path.relpath(os.path.join(dp, f), os.path.join(TOP, '2026'))
        if M.is_banned(rel) or M.PRIVATE_SRC.search(rel):
            skipped += 1
            continue
        dst = os.path.join(OUT, os.path.relpath(os.path.join(dp, f), SRC))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            try:
                os.link(os.path.join(dp, f), dst)
            except OSError:
                shutil.copy2(os.path.join(dp, f), dst)
        for note in (os.path.join(TOP, rel + '.md'), os.path.join(TOP, '2026', rel + '.md')):
            if os.path.isfile(note):
                t = M.scrub(open(note, encoding='utf-8', errors='replace').read())
                open(dst + '.md', 'w', encoding='utf-8').write(t)
                break
        n += 1
open(os.path.join(OUT, 'README.md'), 'w').write(
    '# Ward-Beck Systems advertisements\n\nThe ads, brochures and press coverage of Ward-Beck Systems, each picture with '
    'its note (date, where it ran, the text read from it). The timeline of them is on '
    '[WBSps.ca](https://wardbecksystems.github.io/WBSps.ca/ADVERTISEMENTS/).\n\n---\n'
    '© Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca) · archive by Anthony Peter Kuzub · '
    '[WBSps.ca](https://WBSps.ca) · [WBSps.Kuzub.com](https://WBSps.Kuzub.com)\n')
shutil.copy2(os.path.join(TOP, 'tools', 'module.gitignore'), os.path.join(OUT, '.gitignore'))
print(f'{n} pictures with their notes, {skipped} banned/private left out -> {OUT}')
