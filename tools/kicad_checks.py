#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""KiCad's own checks on every KiCad file of the archive: ERC on each schematic, DRC on each board (kicad-cli).

    python3 tools/kicad_checks.py [--jobs 8] [--only REPO ...] [--force]

Reads every .kicad_sch and .kicad_pcb committed in the public submodule clones (WBSps.ca/Github.WardBeckSystems/<repo>),
runs `kicad-cli sch erc` / `kicad-cli pcb drc` (all severities, JSON) on it, and writes what they found for the site:

    _catalog/kicad_checks/index.json     one row per file: repo, path, check, counts by severity, the commonest kinds
    _catalog/kicad_checks/<repo>.json    every violation of that repo's files (capped per file), with the items and where

viewer.html shows a schematic or board with KiCanvas and lists its violations beside it; PAGES/KiCad-Checks.html is the
index. A file is checked again only when its blob changes (the blob id is kept), unless --force.
"""
import json, os, re, subprocess, sys, tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = 'WBSps.ca/Github.WardBeckSystems'
OUT = os.path.join(TOP, '_catalog', 'kicad_checks')
CAP = 250            # violations kept per file (the counts are always whole)
SEV = ('error', 'warning', 'exclusion', 'info')


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def public_repos():
    """The registered submodules in HOME (the public ones: private repos are never registered)."""
    paths = re.findall(r'^\s*path = (.*)$', open(os.path.join(TOP, '.gitmodules')).read(), re.M)
    return sorted(p.strip()[len(HOME) + 1:] for p in paths if p.strip().startswith(HOME + '/'))


def files_of(repo):
    """[(path, blob)] of the KiCad schematics and boards committed in the repo."""
    d = os.path.join(TOP, HOME, repo)
    if not os.path.exists(os.path.join(d, '.git')):
        return []
    out = subprocess.run(['git', '-C', d, 'ls-files', '-s', '-z', '--', '*.kicad_sch', '*.kicad_pcb'], capture_output=True).stdout
    rows = []
    for line in out.decode(errors='replace').split('\0'):
        if line:
            meta, path = line.split('\t', 1)
            rows.append((path, meta.split()[1]))
    return rows


def run(repo, path):
    """kicad-cli on one file -> (check, report dict) or (check, {'failed': reason})."""
    src = os.path.join(TOP, HOME, repo, path)
    check = 'erc' if path.endswith('.kicad_sch') else 'drc'
    with tempfile.TemporaryDirectory() as tmp:
        rpt = os.path.join(tmp, 'r.json')
        cmd = ['kicad-cli', 'sch' if check == 'erc' else 'pcb', check, '--format', 'json', '--severity-all', '-o', rpt, src]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return check, {'failed': 'timed out'}
        if not os.path.exists(rpt):
            return check, {'failed': (r.stderr or r.stdout).strip().splitlines()[-1:] or ['no report']}
        return check, json.load(open(rpt))


def violations(check, rep):
    """Every violation of a report as [severity, type, description, [[item, x, y], …]]."""
    vs = rep.get('violations', []) + [v for s in rep.get('sheets', []) for v in s.get('violations', [])]
    if check == 'drc':
        vs += [dict(v, type=v.get('type', 'unconnected_items')) for v in rep.get('unconnected_items', [])]
        vs += [dict(v, type=v.get('type', 'schematic_parity')) for v in rep.get('schematic_parity', [])]
    out = []
    for v in vs:
        items = [[i.get('description', ''), round(i.get('pos', {}).get('x', 0), 3), round(i.get('pos', {}).get('y', 0), 3)]
                 for i in v.get('items', [])]
        out.append([v.get('severity', 'error'), v.get('type', ''), v.get('description', ''), items])
    return out


def main():
    jobs, force = arg('--jobs', 8), '--force' in sys.argv
    only = [a for i, a in enumerate(sys.argv) if i and sys.argv[i - 1] == '--only']
    os.makedirs(OUT, exist_ok=True)
    idx_path = os.path.join(OUT, 'index.json')
    old = {(r['repo'], r['path']): r for r in json.load(open(idx_path))['files']} if os.path.exists(idx_path) else {}
    repos = [r for r in public_repos() if not only or r in only]
    todo, keep = [], []
    for repo in repos:
        for path, blob in files_of(repo):
            o = old.get((repo, path))
            if o and o.get('blob') == blob and not force:
                keep.append(o)
            else:
                todo.append((repo, path, blob))
    print(f'{len(todo)} files to check, {len(keep)} unchanged', flush=True)

    def one(t):
        repo, path, blob = t
        check, rep = run(repo, path)
        return repo, path, blob, check, rep
    with ThreadPoolExecutor(jobs) as pool:
        done = list(pool.map(one, todo))

    per_repo = {}
    for repo in {t[0] for t in todo}:   # the repos checked now: their detail files are rebuilt from scratch
        p = os.path.join(OUT, repo + '.json')
        per_repo[repo] = json.load(open(p)) if os.path.exists(p) else {}
        for path in list(per_repo[repo]):
            if (repo, path) in {(r, p_) for r, p_, *_ in todo}:
                del per_repo[repo][path]
    rows = list(keep)
    for repo, path, blob, check, rep in done:
        row = {'repo': repo, 'path': path, 'blob': blob, 'check': check}
        if 'failed' in rep:
            row['failed'] = ' '.join(rep['failed']) if isinstance(rep['failed'], list) else rep['failed']
        else:
            vs = violations(check, rep)
            sev = Counter(v[0] for v in vs)
            row['n'] = {s: sev[s] for s in SEV if sev[s]}
            row['kinds'] = Counter(v[1] for v in vs).most_common(6)
            row['kicad'] = rep.get('kicad_version', '')
            per_repo[repo][path] = {'check': check, 'units': rep.get('coordinate_units', 'mm'), 'total': len(vs), 'v': vs[:CAP]}
        rows.append(row)
    for repo, d in per_repo.items():
        p = os.path.join(OUT, repo + '.json')
        if d:
            with open(p, 'w') as fh:
                json.dump(d, fh, separators=(',', ':'))
        elif os.path.exists(p):
            os.remove(p)
    present = {(r, p) for r in repos for p, _ in files_of(r)} if not only else None
    if present is not None:
        rows = [r for r in rows if (r['repo'], r['path']) in present]
    rows.sort(key=lambda r: (r['repo'], r['path']))
    tot = Counter()
    for r in rows:
        for s, n in r.get('n', {}).items():
            tot[r['check'] + ' ' + s] += n
    with open(idx_path, 'w') as fh:
        json.dump({'about': 'KiCad ERC (schematics) and DRC (boards) by kicad-cli, tools/kicad_checks.py', 'totals': dict(tot),
                   'files': rows}, fh, separators=(',', ':'))
    failed = [r for r in rows if 'failed' in r]
    print(f'{len(rows)} files: ' + ', '.join(f'{k} {v}' for k, v in sorted(tot.items())) + f'; {len(failed)} could not be checked')
    for r in failed[:10]:
        print('  FAILED', r['repo'], r['path'], r['failed'][:120])


if __name__ == '__main__':
    main()
