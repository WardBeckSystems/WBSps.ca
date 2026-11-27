#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Every console and intercom project in 2026/Consoles as its own repository, like the MODULES.<CAT>.<M> repos.

    CONSOLE.<job>-<client>      a console job (YY####, as tools/make_job_repos.py numbers and merges them)
    INTERCOM.<job>-<client>     an intercom job (MicroCOM, MiniCOM, matrices, IFB)
    CONSOLE.MODEL.<model>       a console model (2026/Consoles/Models/<model>)
    CONSOLE.<name>              a project with no job number (WSVN, Red Deer WBS, 1968 - Little Green Giant...)

The photo piles (1960-1969/1967-1969, 1970-1979/1970-1979, 1980-1989/1980-1989, 1980-1989/1989-1999) were grouped into
project folders by camera metadata and by looking; each of those folders is a project too.

What may be public is what the site publishes: a note (.md) is taken from the site's scrubbed copy (WBSps.ca/Consoles), a
picture, PDF or drawing goes in when its note is on the site. Files are staged as hard links (no extra disk) and moved
into the clone in WBSps.ca/Github.WardBeckSystems by tools/distribute_to_repo.py (commit, push, blobless .git).
WardBeckSystems/Console and WardBeckSystems/Intercom then list every project as a submodule (gitlinks, nothing cloned).

usage: make_project_repos.py [--dry-run] [--only REPO ...] [--index]
"""
import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_job_repos as J  # noqa: E402

TOP = J.TOP
G = os.path.join(TOP, 'WBSps.ca', 'Github.WardBeckSystems')
OWNER = 'WardBeckSystems'
PILES = {('1960-1969', '1967-1969'), ('1970-1979', '1970-1979'), ('1980-1989', '1980-1989'), ('1980-1989', '1989-1999')}
STAGE = os.path.join(os.environ.get('STAGE_DIR', '/tmp'), 'project-stage')
STATE = os.path.join(TOP, 'tools', 'project_repos.json')   # repo name -> {kind, title, folders, sha}
TRAILER = '\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'


def slug(s):
    s = re.sub(r'[^A-Za-z0-9._-]+', '-', s).strip('-.')
    return re.sub(r'-{2,}', '-', s)


def projects():
    """[(repo, kind, title, job, year, [(dec, dir-relative-to-SRC)])]"""
    jobs, other, years = J.collect()
    out = []
    for no in sorted(jobs):
        folders = jobs[no]
        kind = J.kind_of(no, folders)
        names = [n for _, _, n in folders if n]
        what = max(names, key=lambda s: (sum(ch.isupper() for ch in s), len(s))) if names else ''
        year = years.get(no) or ('19' if no[:2] > '30' else '20') + no[:2]
        title = f'{no} - {what}' if what else no
        out.append((f'{kind.upper()}.{slug(title)}', kind, title, no, year, [(dec, d) for dec, d, _ in folders]))
    # collect() skips a folder named like its decade (1970-1979/1970-1979): those are photo piles, add them
    other = list(other) + [(dec, d) for dec, d in sorted(PILES) if dec == d and (dec, d) not in other]
    for dec, d in other:
        if dec == 'Models':
            out.append((f'CONSOLE.MODEL.{slug(d)}', 'console', f'{d} (model)', '', '', [(dec, d)]))
        elif (dec, d) in PILES:
            pile = os.path.join(J.SRC, dec, d)
            for p in sorted(os.listdir(pile)):
                if os.path.isdir(os.path.join(pile, p)):
                    out.append((f'CONSOLE.{slug(p)}', 'console', p, '', '', [(dec, f'{d}/{p}')]))
        else:
            out.append((f'CONSOLE.{slug(d)}', 'console', d, '', dec, [(dec, d)]))
    seen = {}
    for i, (repo, *rest) in enumerate(out):
        n = repo[:100]
        while n in seen:
            n = f'{repo[:96]}-{len(seen)}'
        seen[n] = 1
        out[i] = (n, *rest)
    return out


_BY_NAME = None


def by_name(name):
    """The site's note of that name anywhere in its Consoles copy (files were regrouped into projects since)."""
    global _BY_NAME
    if _BY_NAME is None:
        _BY_NAME = {}
        for r, _, fs in os.walk(J.PUBLISHED):
            for f in fs:
                if f.endswith('.md'):
                    _BY_NAME.setdefault(f, os.path.join(r, f))
    return _BY_NAME.get(name)


def published(dec, rel):
    """Its note on the site, or None: rel is a file inside 2026/Consoles/<dec>/..."""
    p = os.path.join(J.PUBLISHED, dec, rel)
    name = os.path.basename(rel)
    if rel.endswith('.md'):
        return p if os.path.isfile(p) else by_name(name)
    base = re.sub(r' \(traced\)\.(dxf|json|svg)$', '', name)
    for cand in (name + '.md', base + '.jpg.md', base + '.png.md', base + '.pdf.md', base + '.JPG.md'):
        q = os.path.join(os.path.dirname(p), cand)
        if os.path.isfile(q):
            return q
        q = by_name(cand)
        if q:
            return q
    return None


def readme(title, kind, no, year, folders, files):
    what = f'Ward-Beck Systems job **{no}**' + (f', {J.yr(year)}' if year and year.isdigit() else '') if no else \
        f'Ward-Beck Systems {"console model" if title.endswith("(model)") else "project"}'
    lines = [f'# {title}', '', f'{what} ({kind}).', '',
             'In the archive: ' + ', '.join(f'[{dec}/{d}]({J.page(dec, d)})' for dec, d in folders), '',
             'Photos, scans, PDFs and drawings are here with their notes (`.md`: date, origin and the text read '
             'from each page).', '', f'## {len(files)} files', '']
    lines += [f'- [{f}]({quote(f)})' for f in files if not f.endswith('.md')][:2000]
    lines += ['', '---', '© Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca) · archive by Anthony Peter Kuzub · '
              '[WBSps.ca](https://WBSps.ca) · [WBSps.Kuzub.com](https://WBSps.Kuzub.com)', '']
    return '\n'.join(lines)


def stage(p):
    repo, kind, title, no, year, folders = p
    dst = os.path.join(STAGE, repo)
    shutil.rmtree(dst, ignore_errors=True)
    kept, left = [], 0
    for dec, d in folders:
        src = os.path.join(J.SRC, dec, d)
        pre = '' if len(folders) == 1 else J.safe(os.path.basename(d))
        for rel in J.files_of(src):
            if os.path.basename(rel) == 'index.html':
                continue
            pub = published(dec, os.path.join(d, rel))
            if pub is None:
                left += 1
                continue
            out = os.path.join(dst, pre, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            if rel.endswith('.md'):
                shutil.copy2(pub, out)          # the scrubbed copy
            else:
                try:
                    os.link(os.path.join(src, rel), out)
                except OSError:
                    shutil.copy2(os.path.join(src, rel), out)
            kept.append(os.path.relpath(out, dst))
    os.makedirs(dst, exist_ok=True)
    open(os.path.join(dst, 'README.md'), 'w', encoding='utf-8').write(readme(title, kind, no, year, folders, sorted(kept)))
    return dst, len(kept), left


def sh(*a, **k):
    return subprocess.run(a, text=True, capture_output=True, **k)


def make_repo(repo, about):
    if sh('gh', 'repo', 'view', f'{OWNER}/{repo}').returncode:
        wait = 600
        while True:     # GitHub limits repo creation ("too many repositories, too quickly"): back off, never give up
            r = sh('gh', 'repo', 'create', f'{OWNER}/{repo}', '--public', '--description', about[:300])
            if not r.returncode or not sh('gh', 'repo', 'view', f'{OWNER}/{repo}').returncode:
                break
            print(f'  create {repo} failed ({r.stderr.strip()[:90]}); waiting {wait // 60} min', flush=True)
            time.sleep(wait)
            wait = min(wait * 2, 1800)
        time.sleep(90)
    clone = os.path.join(G, repo)
    if not os.path.isdir(os.path.join(clone, '.git')):
        os.makedirs(clone, exist_ok=True)
        sh('git', 'init', '-q', '-b', 'main', clone)
        sh('git', '-C', clone, 'remote', 'add', 'origin', f'https://github.com/{OWNER}/{repo}.git')
        r = sh('git', '-C', clone, 'fetch', '-q', '--filter=blob:none', 'origin')
        if not r.returncode and sh('git', '-C', clone, 'rev-parse', 'origin/main').returncode == 0:
            sh('git', '-C', clone, 'reset', '-q', 'origin/main')
            sh('git', '-C', clone, 'branch', '-u', 'origin/main')
    return clone


def load_state():
    try:
        return json.load(open(STATE))
    except OSError:
        return {}


def build(ps, dry):
    state = load_state()
    for p in ps:
        repo, kind, title, no, year, folders = p
        dst, n, left = stage(p)
        print(f'{repo}: {n} files ({left} not on the site, left out)', flush=True)
        if dry or not n:
            shutil.rmtree(dst, ignore_errors=True)
            continue
        clone = make_repo(repo, f'Ward-Beck Systems {kind} {"job " + no if no else "project"}: {title}')
        r = subprocess.run([sys.executable, os.path.join(TOP, 'tools', 'distribute_to_repo.py'), dst, clone,
                            '--message', f'{title}: photos, scans, PDFs, drawings and their notes'])
        shutil.rmtree(dst, ignore_errors=True)
        if r.returncode:
            print(f'FAIL {repo}', flush=True)
            continue
        sha = sh('git', '-C', clone, 'rev-parse', 'HEAD').stdout.strip()
        state[repo] = dict(kind=kind, title=title, job=no, year=year, folders=[f'{a}/{b}' for a, b in folders],
                           files=n, sha=sha)
        json.dump(state, open(STATE, 'w'), indent=1, sort_keys=True)


def index():
    """Console and Intercom: one submodule per project (gitlinks only), README + jobs.csv."""
    state = load_state()
    for kind, (name, full, title, about) in J.REPOS.items():
        repo = os.path.join(G, name)
        mine = {r: s for r, s in state.items() if s['kind'] == kind}
        keep = {'.git', '.gitmodules', '.gitignore', 'Microcom', 'Microcom-Simulator'}
        tracked = sh('git', '-C', repo, 'ls-files', '-z').stdout.split('\0')
        tops = {t.split('/')[0] for t in tracked if t} - keep
        if tops:
            sh('git', '-C', repo, 'rm', '-r', '-q', '--cached', '--', *sorted(tops))
            for t in tops:
                p = os.path.join(repo, t)
                shutil.rmtree(p) if os.path.isdir(p) else os.path.exists(p) and os.remove(p)
        gm = os.path.join(repo, '.gitmodules')
        for r, s in sorted(mine.items()):
            path = J.safe(s['title'])
            sh('git', '-C', repo, 'config', '-f', gm, f'submodule.{path}.path', path)
            sh('git', '-C', repo, 'config', '-f', gm, f'submodule.{path}.url', f'https://github.com/{OWNER}/{r}.git')
            sh('git', '-C', repo, 'update-index', '--add', '--cacheinfo', f'160000,{s["sha"]},{path}')
        rows = sorted(mine.items(), key=lambda x: (x[1]['job'] == '', x[1]['job'] or x[1]['title']))
        with open(os.path.join(repo, 'jobs.csv'), 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['job', 'year', 'name', 'repo', 'files', 'archive'])
            for r, s in rows:
                w.writerow([s['job'], s['year'], s['title'], f'{OWNER}/{r}', s['files'], ';'.join(s['folders'])])
        lines = [f'# {title}', '', about, '', 'Every project is its own repository, a submodule here '
                 '(`git clone --recurse-submodules`, or clone one project on its own). Built from '
                 '`WBSps.ca/2026/Consoles` by `tools/make_project_repos.py`; every project is also in `jobs.csv`.', '',
                 f'## {len(rows)} projects', '', '| Job | Year | Project | Files |', '|---|---|---|---|']
        lines += [f"| {s['job'] or '—'} | {J.yr(s['year']) if s['year'].isdigit() else s['year']} | "
                  f"[{s['title']}](https://github.com/{OWNER}/{r}) | {s['files']} |" for r, s in rows]
        lines += ['', '---', '© Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca) · archive by Anthony Peter Kuzub · '
                  '[WBSps.ca](https://WBSps.ca) · [WBSps.Kuzub.com](https://WBSps.Kuzub.com)', '']
        open(os.path.join(repo, 'README.md'), 'w', encoding='utf-8').write('\n'.join(lines))
        sh('git', '-C', repo, 'add', 'README.md', 'jobs.csv', '.gitmodules')
        r = sh('git', '-C', repo, 'commit', '-q', '-m',
               f'{name}: every project as its own repository ({len(rows)} submodules)' + TRAILER)
        print(name, r.stdout.strip() or r.stderr.strip()[:200])
        print(name, sh('git', '-C', repo, 'push', '-q', 'origin', 'HEAD').stderr.strip()[:300] or 'pushed')


def unpublished(dry):
    """Every file of 2026/Consoles that no public project repo takes (not on the site): one PRIVATE repo, same paths."""
    repo = 'CONSOLES.UNPUBLISHED'
    dst = os.path.join(STAGE, repo)
    shutil.rmtree(dst, ignore_errors=True)
    n = size = 0
    for root, dirs, files in os.walk(J.SRC):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f == 'index.html':
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, J.SRC)
            dec, _, inner = rel.partition(os.sep)
            if inner and published(dec, inner):
                continue
            n += 1
            size += os.path.getsize(full)
            if not dry:
                out = os.path.join(dst, rel)
                os.makedirs(os.path.dirname(out), exist_ok=True)
                try:
                    os.link(full, out)
                except OSError:
                    shutil.copy2(full, out)
    print(f'{repo}: {n} files, {size / 1e9:.2f} GB not on the site', flush=True)
    if dry or not n:
        return
    open(os.path.join(dst, 'README.md'), 'w').write(
        '# Consoles: unpublished\n\nThe files of WBSps.ca/2026/Consoles that are not on the published archive site '
        '(private, not yet reviewed, or left out), at their archive paths. Private.\n\n'
        '© Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca)\n')
    if sh('gh', 'repo', 'view', f'{OWNER}/{repo}').returncode:
        wait = 600
        while sh('gh', 'repo', 'create', f'{OWNER}/{repo}', '--private', '--description',
                 'Ward-Beck Systems console archive: files not on the published site (private)').returncode \
                and sh('gh', 'repo', 'view', f'{OWNER}/{repo}').returncode:
            time.sleep(wait)
            wait = min(wait * 2, 1800)
    clone = make_repo(repo, '')
    subprocess.run([sys.executable, os.path.join(TOP, 'tools', 'distribute_to_repo.py'), dst, clone, '--zip-big',
                    '--message', 'Consoles: the files not on the published site'])
    shutil.rmtree(dst, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--only', nargs='*')
    ap.add_argument('--index', action='store_true', help='only rebuild the Console/Intercom submodule indexes')
    ap.add_argument('--unpublished', action='store_true', help='the files not on the site -> private CONSOLES.UNPUBLISHED')
    a = ap.parse_args()
    if a.index:
        return index()
    if a.unpublished:
        return unpublished(a.dry_run)
    ps = projects()
    if a.only:
        ps = [p for p in ps if p[0] in a.only]
    done = load_state()
    if not a.dry_run:
        ps = [p for p in ps if p[0] not in done]
    print(f'{len(ps)} projects', flush=True)
    build(ps, a.dry_run)
    if not a.dry_run and not a.only:
        index()


if __name__ == '__main__':
    main()
