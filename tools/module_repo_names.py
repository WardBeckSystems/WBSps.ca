#!/usr/bin/env python3
"""Module repo names: WardBeckSystems/MODULES.<CAT>.<M>-<Function-Words>.

The function of each module lives in tools/module_names.tsv (module<TAB>function, from the
manuals, title blocks, brochures and price lists). A module with no known function keeps the
bare MODULES.<CAT>.<M> name.

  python3 tools/module_repo_names.py            rename on GitHub + set descriptions (idempotent)
  python3 tools/module_repo_names.py --local    point .gitmodules and each submodule's origin at the new names
"""
import os, re, subprocess, sys, json, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER = 'WardBeckSystems'


def functions():
    out = {}
    for line in open(os.path.join(ROOT, 'tools', 'module_names.tsv'), encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        m, _, f = line.rstrip('\n').partition('\t')
        out[m.strip()] = f.strip()
    return out


def slug(text):
    return re.sub(r'[^A-Za-z0-9]+', '-', text).strip('-')


def repo_name(cat, mod, names=None):
    f = (names if names is not None else functions()).get(mod, '')
    return f'MODULES.{cat}.{mod}' + (f'-{slug(f)}' if f else '')


def title(mod, names=None):
    f = (names if names is not None else functions()).get(mod, '')
    return f'{mod} {f}'.strip()


def submodules():
    """(path, cat, mod, current repo name) for every 2026/Modules submodule in .gitmodules."""
    s = open(os.path.join(ROOT, '.gitmodules'), encoding='utf-8').read()
    for path, url in re.findall(r'path = (2026/Modules/[^\n]+)\n\s*url = (\S+)', s):
        _, _, cat, mod = path.split('/')
        yield path, cat, mod, url.rstrip('/').split('/')[-1].removesuffix('.git')


def gh(*args):
    return subprocess.run(['gh', *args], capture_output=True, text=True)


def rename_remote():
    names = functions()
    have = set(gh('repo', 'list', OWNER, '--limit', '2000', '--json', 'name', '-q', '.[].name').stdout.split())
    for path, cat, mod, _ in submodules():
        old, new = f'MODULES.{cat}.{mod}', repo_name(cat, mod, names)
        desc = f'Ward-Beck Systems {title(mod, names)} ({cat}) — module archive for WBSps.ca'
        src = new if new in have else old if old in have else None
        if not src:
            print('not on GitHub yet:', old); continue
        r = gh('api', '-X', 'PATCH', f'repos/{OWNER}/{src}', '-f', f'name={new}', '-f', f'description={desc}')
        print(('ok  ' if r.returncode == 0 else 'FAIL') + f' {src} -> {new}' + ('' if r.returncode == 0 else ' ' + r.stderr.strip()[:200]))
        time.sleep(0.5)


def point_local():
    gm = os.path.join(ROOT, '.gitmodules')
    s = open(gm, encoding='utf-8').read()
    names = functions()
    for path, cat, mod, cur in submodules():
        new = repo_name(cat, mod, names)
        if cur == new:
            continue
        url = f'https://github.com/{OWNER}/{new}.git'
        s = re.sub(rf'(path = {re.escape(path)}\n\s*url = )\S+', lambda m: m.group(1) + url, s)
        full = os.path.join(ROOT, path)
        if os.path.exists(os.path.join(full, '.git')):
            subprocess.run(['git', '-C', full, 'remote', 'set-url', 'origin', url])
        subprocess.run(['git', '-C', ROOT, 'config', f'submodule.{path}.url', url])
        print(path, '->', new)
    open(gm, 'w', encoding='utf-8').write(s)


if __name__ == '__main__':
    point_local() if '--local' in sys.argv else rename_remote()
