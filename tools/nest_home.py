#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Put every clone in WBSps.ca/Github.WardBeckSystems where tools/wbs_home.py says it belongs (names repeated ten or more
times in a folder), and keep WBSps.ca's submodules, .gitignore and links in step.

    python3 tools/nest_home.py [--dry-run]        then commit what it lists (it writes tools/nest_moves.json)

For each clone not where it belongs: the folder is moved; a registered submodule's gitlink is moved in the index
(update-index, the same commit) and its .gitmodules section renamed. .gitignore gets one `!` line per family folder and
names the unregistered (private) clones inside them. Links in WBSps.ca's own tracked text files that name a moved repo's
old folder (Github.WardBeckSystems/<repo>/… and its %2F-encoded form) are pointed at the new one.
"""
import json, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wbs_home as w

TOP = w.TOP
HOME_REL = 'WBSps.ca/Github.WardBeckSystems'
TEXT = re.compile(r'\.(html?|md|js|json|txt|csv|tsv|py|css|xml|svg|yml|yaml)$', re.I)


def git(*a, inp=None):
    r = subprocess.run(['git', '-C', TOP, *a], capture_output=True, text=True, input=inp)
    if r.returncode:
        raise RuntimeError(f'git {" ".join(a)}: {r.stderr.strip()}')
    return r.stdout


def main():
    dry = '--dry-run' in sys.argv
    clones = w.repos(refresh=True)
    names = list(clones)
    links = {}   # path -> sha of every gitlink under HOME
    for line in git('ls-files', '-s', '--', HOME_REL).splitlines():
        meta, path = line.split('\t', 1)
        if meta.startswith('160000'):
            links[path] = meta.split()[1]
    moves = []
    for name, d in sorted(clones.items()):
        old = os.path.relpath(d, TOP).replace(os.sep, '/')
        new = f'{HOME_REL}/{w.nest(name, names)}'
        if old != new:
            moves.append((name, old, new))
    print(f'{len(moves)} clones to move, {sum(o in links for _, o, _ in moves)} of them submodules')
    if dry:
        for m in moves[:12]:
            print('  ', m[1][len(HOME_REL) + 1:], '->', m[2][len(HOME_REL) + 1:])
        return
    gm_path = os.path.join(TOP, '.gitmodules')
    gm = open(gm_path).read()
    idx_in = []
    for name, old, new in moves:
        os.makedirs(os.path.dirname(os.path.join(TOP, new)), exist_ok=True)
        os.rename(os.path.join(TOP, old), os.path.join(TOP, new))
        if old in links:
            idx_in.append(f'0 {"0" * 40}\t{old}')                 # remove the old gitlink
            idx_in.append(f'160000 {links[old]}\t{new}')         # and record it at its new path
            gm = gm.replace(f'[submodule "{old}"]', f'[submodule "{new}"]').replace(f'\tpath = {old}\n', f'\tpath = {new}\n')
    if idx_in:
        git('update-index', '--index-info', inp='\n'.join(idx_in) + '\n')
    open(gm_path, 'w').write(gm)

    # .gitignore: the clones' folder is ignored; each family folder and each registered top-level repo is let through;
    # the unregistered (private) clones inside a family folder are named
    clones = w.repos(refresh=True)
    reg = set(re.findall(r'^\s*path = (.*)$', gm, re.M))
    fams = w.families(list(clones))
    top_reg = sorted(n for n, d in clones.items() if '/' not in os.path.relpath(d, w.HOME) and f'{HOME_REL}/{n}' in reg)
    private = sorted(os.path.relpath(d, TOP).replace(os.sep, '/') for n, d in clones.items()
                     if '/' in os.path.relpath(d, w.HOME) and os.path.relpath(d, TOP).replace(os.sep, '/') not in reg)
    block = ['# local clones of every WardBeckSystems repo: the one local copy, names repeated ten or more times in a folder',
             '# (tools/wbs_home.py, tools/nest_home.py). Registered ones are submodules; private clones stay ignored.',
             f'/{HOME_REL}/*'] + [f'!/{HOME_REL}/{f}/' for f in fams] + [f'!/{HOME_REL}/{n}' for n in top_reg] + \
            ['# private clones inside the family folders (never submodules: they break the Pages build)'] + [f'/{p}/' for p in private]
    gi_path = os.path.join(TOP, '.gitignore')
    gi = open(gi_path).read().split('\n')
    start = next(i for i, l in enumerate(gi) if l.startswith('# local clones of every WardBeckSystems repo'))
    end = next(i for i in range(start, len(gi)) if not gi[i].strip())   # the block runs to the first blank line
    gi = gi[:start] + block + [''] + gi[end:]
    open(gi_path, 'w').write('\n'.join(gi))

    # links: every tracked text file of WBSps.ca itself (not inside the submodules) that names an old folder
    moved = {name: (old, new) for name, old, new in moves}
    pat = re.compile(r'Github\.WardBeckSystems(/|%2F)(' + '|'.join(re.escape(n) for n in sorted(moved, key=len, reverse=True)) +
                     r')(?=/|%2F|["\'?#)<>\s\]]|$)')
    def sub(m):
        sep = m.group(1)
        new = moved[m.group(2)][1][len(HOME_REL) + 1:]
        return 'Github.WardBeckSystems' + sep + new.replace('/', sep)
    changed, refs = [], 0
    for f in git('ls-files', '-z').split('\0'):
        if not f or not TEXT.search(f) or f.startswith(HOME_REL + '/') or f in ('.gitmodules', '.gitignore'):
            continue
        p = os.path.join(TOP, f)
        if not os.path.isfile(p) or os.path.islink(p):
            continue
        try:
            s = open(p, encoding='utf-8').read()
        except (UnicodeDecodeError, OSError):
            continue
        if 'Github.WardBeckSystems' not in s:
            continue
        t, n = pat.subn(sub, s)
        if n:
            open(p, 'w', encoding='utf-8').write(t); changed.append(f); refs += n
    json.dump({'moves': moves, 'relinked_files': changed}, open(os.path.join(TOP, 'tools', 'nest_moves.json'), 'w'), indent=1)
    print(f'moved {len(moves)}; .gitignore: {len(fams)} family folders, {len(top_reg)} top-level, {len(private)} private clones named; '
          f'{refs} links in {len(changed)} files')


if __name__ == '__main__':
    main()
