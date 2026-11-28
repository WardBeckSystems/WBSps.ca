#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Where the modules live: every module repo is a submodule in WBSps.ca/Github.WardBeckSystems/MODULES/ (its category's
folder when ten or more share it: MODULES/<CAT>/MODULES.<CAT>.<M>[-Function]; tools/wbs_home.py).

    python3 tools/modules_home.py          # (re)build the 2026/Modules/<CAT>/<M> links

The pipeline thinks in <CAT>/<M> (the catalog db stores 2026-relative dests like Modules/AMPLIFIERS/M124/...), so
2026/Modules is a gitignored folder of links, 2026/Modules/<CAT>/<M> -> the clone. Tools list modules with
module_dirs() (the link paths, so path[-2:] is (CAT, M)) and never glob Products/.
"""
import os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.join(ROOT, 'WBSps.ca', 'Github.WardBeckSystems')
FARM = os.path.join(ROOT, '2026', 'Modules')
NAME = re.compile(r'^MODULES\.([A-Z0-9-]+)\.(R?[A-Z]*\d+[A-Z0-9]*?)(?:-.+)?$')


def modules():
    """[(cat, code, clone dir)] for every module submodule in .gitmodules."""
    out = []
    for path in re.findall(r'^\s*path = (WBSps\.ca/Github\.WardBeckSystems/(?:[^\n]*/)?MODULES\.[^\n/]+)$', open(os.path.join(ROOT, '.gitmodules')).read(), re.M):
        m = NAME.match(os.path.basename(path))
        if m:
            out.append((m.group(1), m.group(2), os.path.join(ROOT, path)))
    return sorted(out)


def ensure_farm():
    want = {os.path.join(FARM, c, m): d for c, m, d in modules()}
    if os.path.islink(FARM):
        os.remove(FARM)
    for link, d in want.items():
        os.makedirs(os.path.dirname(link), exist_ok=True)
        target = os.path.relpath(d, os.path.dirname(link))
        if os.path.islink(link) and os.readlink(link) == target:
            continue
        if os.path.lexists(link):
            if not os.path.islink(link):
                raise SystemExit(f'{link} is a real folder, not a link: move it into its clone first')
            os.remove(link)
        os.symlink(target, link)
    for cat in os.listdir(FARM):   # links of modules no longer registered
        for m in os.listdir(os.path.join(FARM, cat)):
            p = os.path.join(FARM, cat, m)
            if os.path.islink(p) and p not in want:
                os.remove(p)
    return want


def module_dirs():
    """The module folders as 2026/Modules/<CAT>/<M> (links into the clones), sorted."""
    return sorted(ensure_farm())


def module_dir(code):
    return next((os.path.join(FARM, c, m) for c, m, _ in modules() if m == code), None)


if __name__ == '__main__':
    print(f'{len(ensure_farm())} module links in 2026/Modules')
