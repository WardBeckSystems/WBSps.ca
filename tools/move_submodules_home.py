#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Register submodules at their clone in WBSps.ca/Github.WardBeckSystems/<repo> (the one local copy).

    python3 tools/move_submodules_home.py PREFIX [PREFIX ...] [--dry-run]     # e.g. Products/Modules Products/Console

For every submodule whose path is under a PREFIX: find its clone (the repo name, or the repo name plus its
-Function suffix after a GitHub rename), check the clone holds the submodule's recorded commit, then
  - the gitlink moves to WBSps.ca/Github.WardBeckSystems/<clone> at the clone's HEAD,
  - .gitmodules gets the new path and the clone's own origin URL.
The old checkout is left on disk (trash it after verifying: tools/trash_log.csv). Writes tools/submodule_moves.json
{old path: new path} for tools/move_relink.py.
"""
import json, os, re, subprocess, sys

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = 'WBSps.ca/Github.WardBeckSystems'


def git(d, *a, check=False):
    r = subprocess.run(['git', '-C', os.path.join(TOP, d), *a], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f'git {" ".join(a)} in {d}: {r.stderr}')
    return r


def main():
    dry = '--dry-run' in sys.argv
    prefixes = [p.rstrip('/') for p in sys.argv[1:] if p != '--dry-run']
    text = open(os.path.join(TOP, '.gitmodules')).read()
    blocks = re.split(r'(?=^\[submodule )', text, flags=re.M)
    clones = os.listdir(os.path.join(TOP, HOME))
    index = {l.split('\t', 1)[1]: l.split()[1] for l in git('.', 'ls-files', '-s').stdout.splitlines() if l.startswith('160000')}
    moves, out, problems = {}, [], []
    for b in blocks:
        m = re.search(r'^\s*path = (.*)$', b, re.M)
        u = re.search(r'^\s*url = (.*)$', b, re.M)
        if not m or not any(m.group(1) == p or m.group(1).startswith(p + '/') for p in prefixes):
            out.append(b); continue
        old = m.group(1)
        name = u.group(1).rstrip('/').split('/')[-1].removesuffix('.git')
        hit = [c for c in clones if c == name] or [c for c in clones if c.startswith(name + '-')]
        if len(hit) != 1:
            problems.append(f'{old}: clone of {name}: {hit or "none"}'); out.append(b); continue
        new = f'{HOME}/{hit[0]}'
        rec = index.get(old)
        head = git(new, 'rev-parse', 'HEAD').stdout.strip()
        if not rec or git(new, 'merge-base', '--is-ancestor', rec, head).returncode:
            problems.append(f'{old}: clone {hit[0]} HEAD {head[:9]} does not contain the recorded {str(rec)[:9]}'); out.append(b); continue
        if git(new, 'status', '--porcelain', '-uno', '--ignore-submodules=all').stdout.strip():
            problems.append(f'{old}: clone {hit[0]} has uncommitted changes'); out.append(b); continue
        origin = git(new, 'remote', 'get-url', 'origin').stdout.strip() or u.group(1)
        b = b.replace(m.group(0), m.group(0).replace(old, new)).replace(u.group(0), u.group(0).replace(u.group(1), origin))
        out.append(b)
        moves[old] = new
        if not dry:
            git('.', 'update-index', '--force-remove', old, check=True)
            git('.', 'update-index', '--add', '--cacheinfo', f'160000,{head},{new}', check=True)
    for p in problems:
        print('SKIP', p)
    print(f'{len(moves)} submodules {"would move" if dry else "moved"} to {HOME}/, {len(problems)} skipped')
    if not dry and moves:
        open(os.path.join(TOP, '.gitmodules'), 'w').write(''.join(out))
        git('.', 'add', '.gitmodules', check=True)
        f = os.path.join(TOP, 'tools', 'submodule_moves.json')
        prev = json.load(open(f)) if os.path.exists(f) else {}
        prev.update(moves)
        json.dump(prev, open(f, 'w'), indent=1, sort_keys=True)


if __name__ == '__main__':
    main()
