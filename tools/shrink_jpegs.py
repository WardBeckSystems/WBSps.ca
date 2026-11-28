#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""JPEGs that are too big (the user: "they should be 1 MB"): resized to at most 4000 px on the long side, the quality
chosen so the file is at most 1 MB (ImageMagick jpeg:extent). Then each repo is committed and pushed.

    python3 tools/shrink_jpegs.py LIST.txt [--no-push]       (one path per line)
"""
import os, subprocess, sys
from collections import defaultdict
LIMIT, SIDE = 1_000_000, 4000
sh = lambda *a, **k: subprocess.run(a, capture_output=True, text=True, **k)
paths = [l.strip() for l in open(sys.argv[1]) if l.strip()]
by_repo = defaultdict(list)
for p in paths:
    if not os.path.isfile(p) or os.path.getsize(p) <= LIMIT:
        continue
    tmp = p + '.shrink.jpg'
    r = sh('convert', p, '-resize', f'{SIDE}x{SIDE}>', '-strip', '-define', f'jpeg:extent={LIMIT // 1000}KB', tmp)
    if r.returncode or not os.path.exists(tmp) or os.path.getsize(tmp) > LIMIT * 1.05:
        print('FAILED', p, r.stderr[:200]); os.path.exists(tmp) and os.remove(tmp); continue
    before = os.path.getsize(p)
    os.replace(tmp, p)
    repo = sh('git', '-C', os.path.dirname(p), 'rev-parse', '--show-toplevel').stdout.strip()
    by_repo[repo].append((p, before))
for repo, files in by_repo.items():
    sh('git', '-C', repo, 'add', '--', *[os.path.relpath(p, repo) for p, _ in files])
    mb = sum(b for _, b in files) / 1e6
    c = sh('git', '-C', repo, 'commit', '-qm', f'{len(files)} drawings resized to 1 MB each (were {mb:.0f} MB in all; at most 4000 px)',
           '-m', 'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')
    if c.returncode == 0 and '--no-push' not in sys.argv:
        sh('git', '-C', repo, 'pull', '-q', '--rebase')
        if sh('git', '-C', repo, 'push', '-q').returncode:
            print('PUSH FAILED', repo)
    print(os.path.basename(repo), len(files), f'{mb:.0f} MB ->', f'{sum(os.path.getsize(p) for p, _ in files) / 1e6:.0f} MB')
