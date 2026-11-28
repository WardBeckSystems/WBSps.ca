#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Move modules to another category: the GitHub repo, its clone, the submodule, and the text that names the category.

    python3 tools/recategorize_modules.py [--dry-run] [CODE ...]     # rows of tools/module_categories.tsv

Each row (code, from, to) of tools/module_categories.tsv:
  rename  (no `to` repo yet): GitHub repo MODULES.<from>.<M>-<Fn> renamed MODULES.<to>.<M>-<Fn> (GitHub redirects the old
          name), the clone renamed, origin URL, gitlink and .gitmodules moved, "(<from>)" / Category-<from> /
          Modules/<from>/<M> in its pages and its GitHub description changed, committed and pushed.
  merge   (a `to` repo exists, the same module twice): every file only the <from> copy has (README.md and index.html
          are rebuilt, not copied) goes into the <to> repo, committed and pushed; a file both have but different is kept
          as the <to> one and listed; the <from> repo is archived on GitHub, its submodule removed, its clone trashed.
Writes tools/module_category_moves.tsv (file paths, 2026-relative, for tools/apply_module_moves.py --moves) and
tools/submodule_moves.json (clone paths, for tools/move_relink.py). Then run: modules_home.py, apply_module_moves.py,
move_relink.py, make_category_pages.py.
"""
import csv, filecmp, glob, json, os, re, shutil, subprocess, sys

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TOP, 'tools'))
import modules_home  # noqa: E402

OWNER = 'WardBeckSystems'
REL = 'WBSps.ca/Github.WardBeckSystems'
HOME = os.path.join(TOP, REL)
PLAN = os.path.join(TOP, 'tools', 'module_categories.tsv')
FILE_MOVES = os.path.join(TOP, 'tools', 'module_category_moves.tsv')
CLONE_MOVES = os.path.join(TOP, 'tools', 'submodule_moves.json')
TRASH_LOG = os.path.join(TOP, 'tools', 'trash_log.csv')
DRIVE = os.path.join(TOP, '2026', '_catalog', 'drive')
REBUILT = re.compile(r'(^|/)(README\.md|index\.html)$')
TRAILER = '\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
DRY = '--dry-run' in sys.argv


def run(*a, cwd=TOP, check=True):
    r = subprocess.run(list(a), cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f'{" ".join(a)} (in {cwd}): {r.stderr.strip() or r.stdout.strip()}')
    return r.stdout


def git(d, *a, check=True):
    return run('git', '-C', d, *a, check=check)


def tracked(d):
    return [f for f in git(d, 'ls-files', '-z').split('\0') if f]


def push(d):
    git(d, 'pull', '-q', '--rebase', 'origin', 'main')
    git(d, 'push', '-q', 'origin', 'HEAD:main')


def drive_keys(prefix):
    out = []
    for f in glob.glob(os.path.join(DRIVE, '*.json')):
        out += [k for k in json.load(open(f, encoding='utf-8')) if k.startswith(prefix)]
    return out


def set_category_text(d, code, old, new):
    """The category named in the module's own pages: its title, the category link, the Modules/<CAT>/<M> label."""
    subs = [(f'({old})', f'({new})'), (f'Category-{old}.', f'Category-{new}.'), (f'>{old}</a>', f'>{new}</a>'),
            (f'Modules/{old}/{code}', f'Modules/{new}/{code}'), (f'MODULES.{old}.{code}', f'MODULES.{new}.{code}')]
    n = 0
    for rel in tracked(d):
        if not rel.endswith(('.md', '.html', '.json')):
            continue
        p = os.path.join(d, rel)
        try:
            s = open(p, encoding='utf-8').read()
        except (UnicodeDecodeError, OSError):
            continue
        t = s
        for a, b in subs:
            t = t.replace(a, b)
        if t != s:
            open(p, 'w', encoding='utf-8').write(t)
            n += 1
    return n


def gitmodules_edit(old_path, new_path=None, new_url=None):
    f = os.path.join(TOP, '.gitmodules')
    blocks = re.split(r'(?=^\[submodule )', open(f).read(), flags=re.M)
    out = []
    for b in blocks:
        if re.search(rf'^\s*path = {re.escape(old_path)}$', b, re.M):
            if new_path is None:
                continue   # removed
            b = re.sub(r'^\[submodule "[^"]*"\]', f'[submodule "{new_path}"]', b, flags=re.M)
            b = re.sub(rf'^(\s*path = ){re.escape(old_path)}$', lambda m: m.group(1) + new_path, b, flags=re.M)
            b = re.sub(r'^(\s*url = ).*$', lambda m: m.group(1) + new_url, b, flags=re.M)
        out.append(b)
    open(f, 'w').write(''.join(out))


def main():
    only = {a for a in sys.argv[1:] if not a.startswith('--')}
    rows = [r for r in csv.reader(open(PLAN, encoding='utf-8'), delimiter='\t') if r and not r[0].startswith('#')]
    clones = {(c, m): d for c, m, d in modules_home.modules()}
    file_moves, clone_moves, conflicts, report = [], {}, [], []
    for code, frm, to, *_ in rows:
        if only and code not in only:
            continue
        src = clones.get((frm, code))
        if not src:
            report.append(f'{code}: no {frm} clone registered, skipped'); continue
        dst = clones.get((to, code))
        base = os.path.basename(src)
        old_repo = git(src, 'remote', 'get-url', 'origin').strip().rstrip('/').split('/')[-1].removesuffix('.git')
        prefix_old, prefix_new = f'Modules/{frm}/{code}/', f'Modules/{to}/{code}/'
        files = tracked(src)
        for k in sorted(set(files) | {k[len(prefix_old):] for k in drive_keys(prefix_old)}):
            file_moves.append((prefix_old + k, prefix_new + k))
        try:
            one(code, frm, to, src, dst, base, old_repo, files, report, conflicts, clone_moves)
        except Exception as e:   # keep going: the logs below still record what moved
            report.append(f'{code}: FAILED {e}')
    finish(report, conflicts, file_moves, clone_moves)


def one(code, frm, to, src, dst, base, old_repo, files, report, conflicts, clone_moves):
        if dst is None:   # ---- rename
            new_base = base.replace(f'MODULES.{frm}.', f'MODULES.{to}.', 1)
            new_dir = os.path.join(HOME, new_base)
            report.append(f'{code}: rename {base} -> {new_base}')
            clone_moves[f'{REL}/{base}'] = f'{REL}/{new_base}'
            if DRY:
                return
            run('gh', 'repo', 'rename', new_base, '-R', f'{OWNER}/{old_repo}', '--yes')
            os.rename(src, new_dir)
            url = f'https://github.com/{OWNER}/{new_base}.git'
            git(new_dir, 'remote', 'set-url', 'origin', url)
            set_category_text(new_dir, code, frm, to)
            git(new_dir, 'add', '-A')
            if git(new_dir, 'status', '--porcelain', '-uno').strip():
                git(new_dir, 'commit', '-qm', f'{code}: category {frm} -> {to} (repo renamed {new_base}){TRAILER}')
            push(new_dir)
            desc = json.loads(run('gh', 'repo', 'view', f'{OWNER}/{new_base}', '--json', 'description'))['description'] or ''
            if f'({frm})' in desc:
                run('gh', 'repo', 'edit', f'{OWNER}/{new_base}', '--description', desc.replace(f'({frm})', f'({to})'))
            head = git(new_dir, 'rev-parse', 'HEAD').strip()
            git(TOP, 'update-index', '--force-remove', f'{REL}/{base}')
            git(TOP, 'update-index', '--add', '--cacheinfo', f'160000,{head},{REL}/{new_base}')
            gitmodules_edit(f'{REL}/{base}', f'{REL}/{new_base}', url)
        else:   # ---- merge
            dbase = os.path.basename(dst)
            have = set(tracked(dst))
            copy = [f for f in files if not REBUILT.search(f) and f not in have]
            diff = [f for f in files if not REBUILT.search(f) and f in have
                    and not filecmp.cmp(os.path.join(src, f), os.path.join(dst, f), shallow=False)]
            conflicts += [(code, f, base, dbase) for f in diff]
            report.append(f'{code}: merge {base} -> {dbase}: {len(copy)} files copied, {len(diff)} differ (kept {to})')
            clone_moves[f'{REL}/{base}'] = f'{REL}/{dbase}'
            if DRY:
                return
            for f in copy:
                os.makedirs(os.path.dirname(os.path.join(dst, f)) or dst, exist_ok=True)
                shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
            if copy:
                git(dst, 'add', '--', *copy)
                git(dst, 'commit', '-qm', f'{code}: merged the {frm} copy ({old_repo}, now archived): {len(copy)} files only it had{TRAILER}')
                push(dst)
            run('gh', 'repo', 'edit', f'{OWNER}/{old_repo}', '--description', f'Merged into {dbase} (archived)')
            run('gh', 'repo', 'archive', f'{OWNER}/{old_repo}', '--yes')
            head = git(dst, 'rev-parse', 'HEAD').strip()
            git(TOP, 'update-index', '--force-remove', f'{REL}/{base}')
            git(TOP, 'update-index', '--add', '--cacheinfo', f'160000,{head},{REL}/{dbase}')
            gitmodules_edit(f'{REL}/{base}')
            run('gio', 'trash', src)
            with open(TRASH_LOG, 'a', encoding='utf-8') as fh:
                fh.write(f'2026-11-27,{REL}/{base},duplicate of {code} in {to}; its {len(copy)} unique files merged first; repo archived,{REL}/{dbase}\n')


def finish(report, conflicts, file_moves, clone_moves):
    for r in report:
        print(r)
    for c in conflicts:
        print('DIFFERS (kept the target copy):', *c, sep='\t')
    if not DRY:
        run('git', 'add', '.gitmodules')
        with open(FILE_MOVES, 'a', encoding='utf-8') as fh:
            fh.writelines(f'{a}\t{b}\n' for a, b in file_moves)
        prev = json.load(open(CLONE_MOVES)) if os.path.exists(CLONE_MOVES) else {}
        prev.update(clone_moves)
        json.dump(prev, open(CLONE_MOVES, 'w'), indent=1, sort_keys=True)
    print(f'{len(report)} modules, {len(file_moves)} file paths' + (' (dry run)' if DRY else ''))


if __name__ == '__main__':
    main()
