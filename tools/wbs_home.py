#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Where each WardBeckSystems repository lives in the official local copy, WBSps.ca/Github.WardBeckSystems.

Names repeated ten or more times are kept in a folder (user, 2026-11-28): a family of ten or more repos sharing the part
of the name before the first dot gets a folder of that name, and inside it a group of ten or more sharing the next part
gets one too. The repo's own folder keeps the repo's full name, so it still matches GitHub:

    MODULES/AMPLIFIERS/MODULES.AMPLIFIERS.M124-Line-Amplifier     (MODULES: 349; MODULES.AMPLIFIERS: 62)
    MODULES/MODULES.COMPUTERS.M5200-…                             (MODULES.COMPUTERS: 5, under ten)
    CONSOLE/MODEL/CONSOLE.MODEL.L1202A                            CONSOLE/CONSOLE.730050
    SUBASSEMBLY/SUBASSEMBLY.SA14-293      INTERCOM/INTERCOM.…     PRODUCTS/PRODUCTS.PODS
    CONSOLE/Console, INTERCOM/Intercom    a family's index repo goes in its family's folder (Console and CONSOLE would clash
                                          where case does not count: macOS, Windows)
    Engineering, PHOTOS, Premote.WBSps.ca …  everything else at the top

    from wbs_home import HOME, repo_dir, nest, repos
    repo_dir('MODULES.AMPLIFIERS.M124-Line-Amplifier')  -> its folder (absolute), wherever it is now
    nest(name)                                          -> where a repo of that name belongs (relative to HOME)
"""
import os, re
from collections import Counter

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.join(TOP, 'WBSps.ca', 'Github.WardBeckSystems')
REPEAT = 10
_index = None


def _scan():
    """{repo name: absolute folder} of every clone under HOME (a folder holding .git), up to three levels down."""
    out = {}
    def walk(d, depth):
        try:
            names = sorted(os.listdir(d))
        except OSError:
            return
        for n in names:
            p = os.path.join(d, n)
            if n.startswith('.') or not os.path.isdir(p) or os.path.islink(p):
                continue
            if os.path.exists(os.path.join(p, '.git')):
                out.setdefault(n, p)
            elif depth < 3:
                walk(p, depth + 1)
    walk(HOME, 1)
    return out


def repos(refresh=False):
    """{repo name: absolute folder} of every clone (cached; refresh=True rescans)."""
    global _index
    if _index is None or refresh:
        _index = _scan()
    return _index


def repo_dir(name, refresh=False):
    """The folder of the repo called name (absolute); where it belongs (nest) when it is not cloned yet."""
    d = repos(refresh).get(name)
    return d or os.path.join(HOME, nest(name))


def nest(name, names=None):
    """Where a repo called name belongs, relative to HOME (names: every repo name; default: the clones present)."""
    names = list(names if names is not None else repos())
    if name not in names:
        names.append(name)
    fam = Counter(n.split('.')[0] for n in names if '.' in n)
    parts = name.split('.')
    if '.' not in name:   # a family's index repo (Console, Intercom) goes in its family's folder
        f = next((k for k, v in fam.items() if v >= REPEAT and k.lower() == name.lower()), None)
        return f'{f}/{name}' if f else name
    if fam[parts[0]] < REPEAT:
        return name
    sub = Counter(n.split('.')[1] for n in names if n.split('.')[0] == parts[0] and n.count('.') >= 2)
    if len(parts) >= 3 and sub[parts[1]] >= REPEAT:
        return f'{parts[0]}/{parts[1]}/{name}'
    return f'{parts[0]}/{name}'


def rel(name):
    """The repo's path from the WBSps.ca root, as the site and .gitmodules write it: WBSps.ca/Github.WardBeckSystems/…"""
    return os.path.relpath(repo_dir(name), TOP).replace(os.sep, '/')


def families(names=None):
    """The family folders (the names before the first dot repeated ten or more times)."""
    names = list(names if names is not None else repos())
    fam = Counter(n.split('.')[0] for n in names if '.' in n)
    return sorted(k for k, v in fam.items() if v >= REPEAT)


def path_re(fams=None):
    """A regex for code that reads paths: group 1 the repo, group 2 the path in it. A family folder, then maybe a group
    folder (capitals and hyphens, no dot), then the repo. Top-level repos named in capitals (PHOTOS, DOCUMENTS) are repos."""
    f = '|'.join(map(re.escape, fams if fams is not None else families()))
    return re.compile(r'Github\.WardBeckSystems/(?:(?:' + f + r')/(?:[A-Z][A-Z0-9-]*/)?)?([^/]+)/(.*)$')
