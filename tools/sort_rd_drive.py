#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Sort folders of the R&D drives (ENGINEERING.RD-H-Drive, ENGINEERING.RD-APK) into the repos they belong to.

    python3 tools/sort_rd_drive.py [--dry-run] [--rm] [NAME ...]     # NAME: a rule below (default: all)

Each rule: a source folder (in WBSps.ca/Github.WardBeckSystems) -> a repo and a folder in it. Generated folder pages
(index.html) are not copied; a file whose content the target repo already has anywhere is not copied again; a name
that is there with other content is listed and not copied. Copies are committed in each target repo (explicit
paths). --rm: git rm the source folder in its R&D repo once every file in it is in its target (nothing listed).
"""
import hashlib, os, re, shutil, subprocess, sys
from collections import defaultdict

import wbs_home

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.join(TOP, 'WBSps.ca', 'Github.WardBeckSystems')
H = 'ENGINEERING.RD-H-Drive'
A = 'ENGINEERING.RD-APK/WBS Engineering - APK'
REN = f'{H}/CONSOLES/REN TV Console'
TRAILER = '\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'


def ren_m920(rel):
    """The M920 folder of the REN TV drive also holds M921/M923/M927 working files: each to its own module."""
    top = rel.split('/')[0]
    if top in ('OLD',):
        return 'MODULES.RENAISSANCE.M920', 'SCHEMATICS/ORCAD/M920 - OLD/' + rel.split('/', 1)[1]
    m = re.match(r'(M92[0-9])', os.path.basename(rel).upper())
    code = m.group(1) if m else 'M920'
    return f'MODULES.RENAISSANCE.{code}', f'SCHEMATICS/ORCAD/{code}/' + rel


def sub(src_sub, repo, dest):
    return lambda rel: (repo, dest + rel)


def ren_m926(rel):
    top, _, rest = rel.partition('/')
    if top == 'OLD':
        return 'MODULES.RENAISSANCE.M926', 'SCHEMATICS/ORCAD/M926 - OLD/' + rest
    if top == 'OLD2':
        return 'MODULES.RENAISSANCE.M926', 'SCHEMATICS/ORCAD/M926 - OLD2/' + rest
    return 'MODULES.RENAISSANCE.M926', 'SCHEMATICS/ORCAD/M926/' + rel


RULES = {   # name: (source folder, rule(rel) -> (repo, path in repo), only these top-level names or None)
    'ren-m920': (f'{REN}/M920', ren_m920),
    'ren-m921': (f'{REN}/921', lambda rel: ('MODULES.RENAISSANCE.M921', 'SCHEMATICS/ORCAD/M921 - ' + rel)),
    'ren-m923': (f'{REN}/M923', lambda rel: ('MODULES.RENAISSANCE.M923', 'SCHEMATICS/ORCAD/M923 - ' + rel)),
    'ren-m926': (f'{REN}/M926', ren_m926),
    'ren-tvfunc': (REN, lambda rel: None if '/' in rel else
                   ('CONSOLE.MODEL.R-series-Renaissance', 'REN TV Console/' + rel)),
    'm703d': (f'{H}/M7XX/M703D', lambda rel: ('MODULES.COMMUNICATION.M703D-Intercom-Preamplifier', 'SCHEMATICS/' + rel)),
    'm719': (f'{H}/M7XX/M719', lambda rel: ('MODULES.COMMUNICATION.M719-Intercom-Module',
                                          'SCHEMATICS/ORCAD/M719/' + rel.split('/', 1)[-1] if rel.startswith('ORCAD/') else 'SCHEMATICS/ORCAD/M719/' + rel)),
    'm8205': (f'{H}/M82X_OLD/M8205', lambda rel: ('MODULES.AMPLIFIERS.M8205-Audio-Distribution-Amplifier', 'SCHEMATICS/ORCAD/M8205/' + rel)),
    'mcom325': (f'{H}/mcom325 Microcom software', lambda rel: ('Microcom', 'mcom325 Microcom software/' + rel)),
    'pod-old': (f'{H}/POD_OLD', lambda rel: ('PRODUCTS.PODS', (lambda top, rest: f'{top}/SCHEMATICS/ORCAD/{top}/{rest}'
                if re.fullmatch(r'POD\d+[A-Z]?', top) and rest else f'SERIES/SCHEMATICS/{rel}')(*(rel.split('/', 1) + [''])[:2]))),
    'd2000': (f'{H}/D2000 Digital rack', lambda rel: ('PRODUCTS.D2000', rel)),
    'd8212f': (f'{H}/D8212F', lambda rel: ('PRODUCTS.D8212F', rel)),
    'euro-mixer': (f'{A}/Console/Euro Rack Mixer', lambda rel: ('CONSOLE.EuroConsole', 'MECHANICAL/Euro Rack Mixer (2014-15, APK)/' + rel)),
    'euro-rack': (f'{A}/Console/Euro Rack', lambda rel: ('CONSOLE.EuroConsole', 'MECHANICAL/Euro Rack (2014-15, APK)/' + rel)),
    'rto-psu': (f'{A}/20140627 - RTO-PSU', lambda rel: ('Engineering', 'RTO-144/RTO-PSU (2014-06-27)/' + rel)),
    'brand': (f'{A}/BRAND ELEMENTS', lambda rel: ('ADVERTISEMENTS', 'BRAND ELEMENTS/' + rel)),
}
RM = {   # folders removed from the R&D repo once all their rules are clean
    f'{REN}': ['ren-m920', 'ren-m921', 'ren-m923', 'ren-m926', 'ren-tvfunc'],
    f'{H}/M7XX': ['m703d', 'm719'],
    f'{H}/M82X_OLD': ['m8205'],
    f'{H}/mcom325 Microcom software': ['mcom325'],
    f'{H}/POD_OLD': ['pod-old'],
    f'{H}/D2000 Digital rack': ['d2000'],
    f'{H}/D8212F': ['d8212f'],
    f'{A}/Console/Euro Rack Mixer': ['euro-mixer'],
    f'{A}/Console/Euro Rack': ['euro-rack'],
    f'{A}/20140627 - RTO-PSU': ['rto-psu'],
    f'{A}/BRAND ELEMENTS': ['brand'],
}


def at(path):
    """'<repo>/<path in it>' -> the absolute path, the repo's clone wherever its family folder is."""
    repo, _, rest = path.partition('/')
    return os.path.join(wbs_home.repo_dir(repo), rest) if rest else wbs_home.repo_dir(repo)


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def git(d, *a, check=True):
    r = subprocess.run(['git', '-C', d, *a], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f'git {" ".join(a)} in {d}: {r.stderr.strip()}')
    return r.stdout


def main():
    dry, rm = '--dry-run' in sys.argv, '--rm' in sys.argv
    names = [a for a in sys.argv[1:] if not a.startswith('--')] or list(RULES)
    hashes = {}

    def repo_hashes(repo):
        if repo not in hashes:
            d = wbs_home.repo_dir(repo)
            hashes[repo] = {md5(os.path.join(d, f)) for f in git(d, 'ls-files', '-z').split('\0') if f and os.path.isfile(os.path.join(d, f))}
        return hashes[repo]

    copies, clean = defaultdict(list), {}
    for name in names:
        src, rule = RULES[name]
        sd = at(src)
        n = dup = 0
        clash = []
        for r, ds, fs in os.walk(sd):
            ds[:] = [x for x in ds if x != '.git']
            for f in fs:
                rel = os.path.relpath(os.path.join(r, f), sd).replace(os.sep, '/')
                if f == 'index.html':
                    continue
                hit = rule(rel)
                if hit is None:
                    continue
                repo, dest = hit
                p = os.path.join(r, f)
                if md5(p) in repo_hashes(repo):
                    dup += 1; continue
                out = os.path.join(wbs_home.repo_dir(repo), dest)
                if os.path.exists(out):
                    clash.append(f'{repo}/{dest}'); continue
                copies[repo].append((p, dest)); n += 1
        clean[name] = not clash
        print(f'{name}: {n} to copy, {dup} already there, {len(clash)} name clashes')
        for c in clash:
            print('   CLASH', c)
    for repo, items in copies.items():
        d = wbs_home.repo_dir(repo)
        print(f'{repo}: {len(items)} files' + (' (dry run)' if dry else ''))
        if dry:
            continue
        remote = bool(git(d, 'remote').strip())
        if remote:
            git(d, 'fetch', '-q', 'origin')
        ahead = int(git(d, 'rev-list', '--count', '@{u}..HEAD', check=False).strip() or 0) if remote else 0
        for p, dest in items:
            os.makedirs(os.path.dirname(os.path.join(d, dest)), exist_ok=True)
            shutil.copy2(p, os.path.join(d, dest))
        paths = [dest for _, dest in items]
        git(d, 'add', '-f', '--', *paths)
        git(d, 'commit', '-qm', f'R&D drive: {len(items)} engineering files from ENGINEERING.RD-H-Drive / RD-APK sorted here (tools/sort_rd_drive.py){TRAILER}', '--', *paths)
        if not remote:
            print(f'   {repo}: committed, not pushed (no GitHub repo yet: tools/create_repos.py pushes it)'); continue
        if ahead:
            print(f'   {repo}: committed, NOT pushed ({ahead} earlier unpushed commits there are not mine)'); continue
        git(d, 'pull', '-q', '--rebase', 'origin', 'main')
        git(d, 'push', '-q', 'origin', 'HEAD:main')
    if rm and not dry:
        for folder, rules in RM.items():
            if not all(clean.get(x) for x in rules) or not all(x in names for x in rules):
                print(f'not removing {folder}: not every rule ran clean'); continue
            repo = folder.split('/')[0]
            rel = folder[len(repo) + 1:]
            git(wbs_home.repo_dir(repo), 'rm', '-r', '-q', '--', rel)
            git(wbs_home.repo_dir(repo), 'commit', '-qm', f'{rel}: sorted into its repos (tools/sort_rd_drive.py in WBSps.ca){TRAILER}', '--', rel)
            print(f'removed {folder} (committed in {repo}, not pushed)')


if __name__ == '__main__':
    main()
