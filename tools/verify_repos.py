#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Is every file in its repository on GitHub? One line per clone in WBSps.ca/Github.WardBeckSystems, and what is still
left in the source folders.

    verify_repos.py [G_DIR] [--repos NAME...] [--out FILE.tsv]

Per repo: files in the folder · files in GitHub's main · untracked/modified (not committed) · commits not pushed ·
ignored files (kept on disk only) · LFS objects not uploaded. OK = everything in the folder is in GitHub's main
(GitHub refuses a push with missing content, so local HEAD == origin/main means GitHub holds every file).
"""
import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modules_home  # noqa: E402
import wbs_home  # noqa: E402

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = ['WBSps.ca/Github.WardBeckSystems', '2026/PHOTOS', '2026/DOCUMENTS', '2026/Engineering', 'Intercom', 'hard drive recovery',
           'WBSps.ca/Github.WardBeckSystems/_stage']


def git(repo, *a):
    r = subprocess.run(['git', '-C', repo, *a], capture_output=True, text=True,
                       env=dict(os.environ, GIT_LFS_SKIP_SMUDGE='1', GIT_TERMINAL_PROMPT='0'))
    return r.returncode, r.stdout


def busy(repo):
    """A distribute/build run is working in it right now."""
    r = subprocess.run(['pgrep', '-af', 'distribute_to_repo|make_project_repos|apply_audit|psd_sweep'],
                       capture_output=True, text=True).stdout
    return any(os.path.basename(repo) in line for line in r.splitlines()) or \
        os.path.exists(os.path.join(repo, '.git', 'index.lock'))


def check(repo):
    name = os.path.basename(repo)
    git(repo, 'fetch', '-q', 'origin')
    rc, br = git(repo, 'rev-parse', '--abbrev-ref', 'origin/HEAD')
    remote = br.strip() if not rc and br.strip() else 'origin/main'
    _, head = git(repo, 'rev-parse', 'HEAD')
    rc, rhead = git(repo, 'rev-parse', remote)
    _, tracked = git(repo, 'ls-files')
    rc2, on_gh = git(repo, 'ls-tree', '-r', '--name-only', remote)
    _, st = git(repo, 'status', '--porcelain')
    _, ign = git(repo, 'ls-files', '-o', '-i', '--exclude-standard')
    _, ahead = git(repo, 'rev-list', '--count', f'{remote}..HEAD') if not rc else (0, '?')
    lfs = ''
    if os.path.isfile(os.path.join(repo, '.gitattributes')) and 'lfs' in open(os.path.join(repo, '.gitattributes')).read():
        _, out = git(repo, 'lfs', 'push', '--dry-run', 'origin', 'HEAD')
        lfs = str(len([l for l in out.splitlines() if l.startswith('push ')]))
    files = sum(1 for r, ds, fs in os.walk(repo) if '/.git' not in r + '/' and not r.endswith('/.git')
                for f in fs) if True else 0
    n_st = len([l for l in st.splitlines() if l.strip()])
    n_ign = len([l for l in ign.splitlines() if l.strip()])
    gh = len(on_gh.splitlines()) if not rc2 else 0
    same = not rc and head.strip() == rhead.strip()
    ok = same and n_st == 0 and lfs in ('', '0')
    state = 'OK' if ok else ('BUSY' if busy(repo) else 'CHECK')
    return dict(repo=name, state=state, folder=files, github=gh, uncommitted=n_st, unpushed=ahead.strip() or '0',
                ignored=n_ign, lfs_unuploaded=lfs or '-', ignored_list=[l for l in ign.splitlines() if l.strip()][:5],
                status_list=st.splitlines()[:5])


def leftovers():
    out = []
    for s in SOURCES:
        p = os.path.join(TOP, s)
        if not os.path.isdir(p):
            continue
        if os.path.exists(os.path.join(p, '.git')) or s.startswith('2026/'):
            # a WBSps.ca tree or a checkout: what git there doesn't track (the media that should have moved)
            sub = subprocess.run(['git', '-C', p, 'ls-files', '-o', '-z'], capture_output=True).stdout
            rels = [x for x in sub.split(b'\0') if x and not x.endswith(b'index.html')]
            if s == 'WBSps.ca/Github.WardBeckSystems':   # every module is its own clone
                rels = []
                for d in [x for _, _, x in modules_home.modules()]:
                        if os.path.exists(os.path.join(d, '.git')):
                            r = subprocess.run(['git', '-C', d, 'ls-files', '-o', '-z'], capture_output=True).stdout
                            rels += [x for x in r.split(b'\0') if x and not x.endswith(b'index.html')]
            out.append((s, len(rels)))
        else:
            out.append((s, sum(len(fs) for _, _, fs in os.walk(p))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('g', nargs='?', default=wbs_home.HOME)
    ap.add_argument('--repos', nargs='*')
    ap.add_argument('--out')
    a = ap.parse_args()
    if os.path.abspath(a.g) == os.path.abspath(wbs_home.HOME):   # the clones, wherever their family folders are
        found = sorted(wbs_home.repos().items())
    else:
        found = [(d, os.path.join(a.g, d)) for d in os.listdir(a.g)]
    repos = [p for d, p in sorted(found)   # by repo name
             if not d.startswith('_') and os.path.isdir(os.path.join(p, '.git'))
             and (not a.repos or d in a.repos)]
    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(check, repos))
    cols = ['repo', 'state', 'folder', 'github', 'uncommitted', 'unpushed', 'ignored', 'lfs_unuploaded']
    if a.out:
        with open(a.out, 'w') as f:
            f.write('\t'.join(cols) + '\n')
            for r in rows:
                f.write('\t'.join(str(r[c]) for c in cols) + '\n')
    for st in ('CHECK', 'BUSY'):
        for r in rows:
            if r['state'] == st:
                print(f"{st:5} {r['repo'][:60]:60} folder {r['folder']:6} github {r['github']:6} uncommitted "
                      f"{r['uncommitted']:5} unpushed {r['unpushed']:>3} ignored {r['ignored']:4} lfs {r['lfs_unuploaded']}")
                for l in r['status_list'][:3]:
                    print('        ', l[:110])
    ok = [r for r in rows if r['state'] == 'OK']
    print(f"\n{len(ok)} of {len(rows)} repos OK (every file on GitHub); "
          f"{sum(r['state'] == 'BUSY' for r in rows)} busy (being filled now); {sum(r['state'] == 'CHECK' for r in rows)} to check")
    ig = [(r['repo'], r['ignored']) for r in rows if r['ignored']]
    if ig:
        print('kept on disk only (ignored):', ', '.join(f'{n} {c}' for n, c in ig[:15]), '…' if len(ig) > 15 else '')
    print('\nleft in the source folders (not yet in a repo):')
    for s, n in leftovers():
        print(f'  {n:7}  {s}')


if __name__ == '__main__':
    main()
