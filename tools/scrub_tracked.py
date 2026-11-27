#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Scrub the text files WBSps.ca tracks under 2026/ the way make_site.py scrubs the site copy: no e-mail
addresses, no logins / passwords; banned or private files are untracked (git rm --cached, the file stays).

    python3 tools/scrub_tracked.py [--dry-run]
"""
import os, subprocess, sys
TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dry = '--dry-run' in sys.argv
sys.argv = ['make_site.py', os.path.join(TOP, '2026'), os.path.join(TOP, 'site')]
sys.path.insert(0, os.path.join(TOP, '2026', 'timelines'))
import make_site as M  # noqa: E402  (its ban list and scrub())

files = subprocess.run(['git', '-C', TOP, 'ls-files', '-z', '--', '2026'], capture_output=True, text=True).stdout.split('\0')
changed, banned = [], []
for rel in filter(None, files):
    key = rel[len('2026/'):]
    p = os.path.join(TOP, rel)
    if not os.path.isfile(p):
        continue
    if M.is_banned(key) or M.PRIVATE_SRC.search(key):
        banned.append(rel)
        continue
    if os.path.splitext(rel)[1].lower() not in M.TEXT:
        continue
    t = open(p, encoding='utf-8', errors='surrogateescape').read()
    s = M.scrub(t)
    if s != t:
        changed.append(rel)
        if not dry:
            open(p, 'w', encoding='utf-8', errors='surrogateescape').write(s)
print(f'{len(changed)} files scrubbed, {len(banned)} banned/private files untracked' + (' (dry run)' if dry else ''))
for r in changed[:15]: print('  scrub', r)
for r in banned[:15]: print('  untrack', r)
if banned and not dry:
    subprocess.run(['git', '-C', TOP, 'rm', '-q', '--cached', '--', *banned])
    with open(os.path.join(TOP, '.gitignore'), 'a') as f:
        f.write('\n# banned / private (tools/scrub_tracked.py)\n' + ''.join('/' + r.replace(' ', '\\ ') + '\n' for r in banned))
