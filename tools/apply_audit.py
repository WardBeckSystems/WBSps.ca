#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Apply the picture audit (tools/audit_images.py): the highest resolution wins, then the sharpest.

    apply_audit.py AUDIT_DIR G_DIR [--repos NAME...] [--skip PREFIX...] [--dry-run]

From AUDIT_DIR/losers.tsv, for each loser inside a repo clone in G_DIR:
  winner in the same repo       the loser goes (git rm); its note goes too when the winner has one, else it becomes the
                                winner's note
  winner in another repo        exact copy: kept (each repo stays whole); thumbnail / same picture: upgraded, i.e.
                                replaced by the winner's file under the loser's name (the winner's extension), note kept
Losers outside the repos (2026/, hard drive recovery/, _stage/) are only reported. Files are unlinked before they are
replaced (many are hard links to the archive's own copy). Each repo is committed and pushed.
"""
import argparse
import csv
import os
import shutil
import subprocess
from collections import defaultdict

TRAILER = '\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'


def note_of(path):
    """The picture's note: <file>.md beside it, or <module>/OCR/<file>.md in a module repo."""
    beside = path + '.md'
    if os.path.isfile(beside):
        return beside
    parts = path.split(os.sep)
    for i in range(len(parts) - 1, 0, -1):
        if parts[i] in ('SCHEMATICS', 'MECHANICAL', 'PINOUTS', 'MANUALS', 'PHOTOS', 'SOFTWARE', 'KICAD'):
            ocr = os.path.join(os.sep.join(parts[:i]), 'OCR', parts[-1] + '.md')
            return ocr if os.path.isfile(ocr) else None
    return None


def repo_of(path, g):
    rel = os.path.relpath(path, g)
    return None if rel.startswith('..') else rel.split(os.sep)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('audit')
    ap.add_argument('g')
    ap.add_argument('--repos', nargs='*')
    ap.add_argument('--skip', nargs='*', default=[])
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    g = os.path.normpath(a.g)
    rows = list(csv.DictReader(open(os.path.join(a.audit, 'losers.tsv'), encoding='utf-8'), delimiter='\t'))
    plan = defaultdict(list)
    report = defaultdict(int)
    for r in rows:
        loser, winner, kind = os.path.normpath(r['loser']), os.path.normpath(r['winner']), r['kind']
        lr, wr = repo_of(loser, g), repo_of(winner, g)
        if lr is None or lr.startswith('_'):
            report['source (reported only)'] += 1
            continue
        if (a.repos and lr not in a.repos) or any(lr.startswith(s) for s in a.skip):
            report['repo busy, later'] += 1
            continue
        if not os.path.isfile(loser) or not os.path.isfile(winner):
            report['gone since the audit'] += 1
            continue
        if lr == wr:
            plan[lr].append(('drop', loser, winner, kind))
        elif kind == 'exact':
            report['exact copy in another repo (kept)'] += 1
        else:
            plan[lr].append(('upgrade', loser, winner, kind))
    for k, v in sorted(report.items()):
        print(f'{v:6d}  {k}')
    for act in ('drop', 'upgrade'):
        print(f'{sum(1 for ops in plan.values() for o in ops if o[0] == act):6d}  {act} ({len([r for r, ops in plan.items() if any(o[0] == act for o in ops)])} repos)')
    if a.dry_run:
        return
    for repo, ops in sorted(plan.items()):
        clone = os.path.join(g, repo)
        if subprocess.run(['git', '-C', clone, 'status', '--porcelain', '--untracked-files=no'],
                          capture_output=True, text=True).stdout.strip():
            print(f'skip {repo}: uncommitted changes')
            continue
        rm, add = set(), set()
        for act, loser, winner, kind in ops:
            if not os.path.isfile(loser) or not os.path.isfile(winner):
                continue        # moved or gone since the audit (the runs keep moving files): leave it for the next audit
            ln = note_of(loser)
            if act == 'drop':
                wn = note_of(winner)
                os.remove(loser)
                rm.add(loser)
                if ln:
                    if wn:
                        os.remove(ln)
                        rm.add(ln)
                    else:
                        new = os.path.join(os.path.dirname(ln), os.path.basename(winner) + '.md')
                        os.rename(ln, new)
                        rm.add(ln)
                        add.add(new)
            else:
                new = os.path.splitext(loser)[0] + os.path.splitext(winner)[1].lower()
                tmp = new + '.part'
                try:
                    shutil.copy2(winner, tmp)     # the winner first: nothing is removed if it cannot be copied
                except OSError as e:
                    print(f'  skip {loser}: {e}')
                    os.path.exists(tmp) and os.remove(tmp)
                    continue
                os.remove(loser)              # unlink: it may be a hard link to the archive's copy
                rm.add(loser)
                os.replace(tmp, new)
                add.add(new)
                rm.discard(new)
                if ln and new != loser:
                    nn = os.path.join(os.path.dirname(ln), os.path.basename(new) + '.md')
                    t = open(ln, encoding='utf-8', errors='surrogateescape').read()
                    os.remove(ln)
                    rm.add(ln)
                    open(nn, 'w', encoding='utf-8', errors='surrogateescape').write(
                        t + f'\n- **Upgraded:** replaced by the higher-resolution copy `{os.path.basename(winner)}` '
                            f'({repo_of(winner, g)}), 2026-11-26\n')
                    add.add(nn)
        rel = lambda p: os.path.relpath(p, clone)
        gone = [rel(p) for p in rm if not os.path.exists(p)]
        for i in range(0, len(gone), 400):
            subprocess.run(['git', '-C', clone, 'rm', '-q', '--cached', '--ignore-unmatch', '--', *gone[i:i + 400]])
        new = [rel(p) for p in add if os.path.exists(p)]
        for i in range(0, len(new), 400):
            subprocess.run(['git', '-C', clone, 'add', '-f', '--', *new[i:i + 400]])
        nd = sum(1 for o in ops if o[0] == 'drop')
        nu = len(ops) - nd
        r = subprocess.run(['git', '-C', clone, 'commit', '-q', '-m',
                            f'Pictures: the highest resolution wins ({nd} duplicates and thumbnails removed, '
                            f'{nu} upgraded to a better copy)' + TRAILER], capture_output=True, text=True)
        if r.returncode:
            print(f'{repo}: nothing to commit')
            continue
        p = subprocess.run(['git', '-C', clone, 'push', '-q', 'origin', 'HEAD'], capture_output=True, text=True)
        print(f'{repo}: -{nd} ~{nu}', 'pushed' if not p.returncode else f'PUSH FAILED {p.stderr.strip()[:200]}', flush=True)


if __name__ == '__main__':
    main()
