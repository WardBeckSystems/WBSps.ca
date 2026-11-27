#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""No more PSDs: every .psd becomes a .jpg of its flattened image (quality 92), and the .psd is deleted.

    psd_to_jpg.py PATH... [--notes-root DIR]... [--git] [--dry-run]

X.psd -> X.jpg (X (from psd).jpg when an X.jpg is already there). The JPEG is checked (it opens, same size as the PSD)
before the PSD goes. Its note X.psd.md is renamed X.jpg.md (git mv when git tracks it) and its text points at the JPEG;
--notes-root also renames the note's copy in another tree with the same layout (the published site copy).
--git: in a git repo, stage the change (git rm the PSD, git add the JPEG); the caller commits.
"""
import argparse
import os
import subprocess
import sys

ENV = dict(os.environ, MAGICK_AREA_LIMIT='4GP', MAGICK_MEMORY_LIMIT='6GiB', MAGICK_MAP_LIMIT='12GiB',
           MAGICK_DISK_LIMIT='60GiB')


def size_of(path):
    r = subprocess.run(['identify', '-format', '%wx%h', f'{path}[0]'], capture_output=True, text=True, env=ENV)
    return r.stdout.strip() if not r.returncode else None


def tracked(path):
    d = os.path.dirname(path) or '.'
    return not subprocess.run(['git', '-C', d, 'ls-files', '--error-unmatch', '--', os.path.basename(path)],
                              capture_output=True).returncode


def rename_note(old, new):
    if not os.path.isfile(old):
        return
    if tracked(old):
        subprocess.run(['git', '-C', os.path.dirname(old), 'mv', '-k', os.path.basename(old), os.path.basename(new)])
    if os.path.isfile(old):
        os.rename(old, new)
    psd, jpg = os.path.basename(old)[:-3], os.path.basename(new)[:-3]
    t = open(new, encoding='utf-8', errors='surrogateescape').read()
    if psd in t:
        open(new, 'w', encoding='utf-8', errors='surrogateescape').write(
            t.replace(psd, jpg) + f'\n- **Converted:** from `{psd}` (PSD, flattened) to JPEG, 2026-11-26\n')
    if tracked(new):
        subprocess.run(['git', '-C', os.path.dirname(new), 'add', '--', os.path.basename(new)])


def convert(psd, a):
    base = psd[:-4]
    jpg = base + '.jpg'
    if os.path.exists(jpg):
        jpg = base + ' (from psd).jpg'
    dims = size_of(psd)
    if a.dry_run:
        print(f'would convert {psd} ({dims})')
        return True
    tmp = jpg + '.part'
    r = subprocess.run(['convert', f'{psd}[0]', '-quality', '92', f'jpg:{tmp}'], capture_output=True, text=True, env=ENV)
    if r.returncode or not os.path.isfile(tmp) or (dims and size_of(tmp) != dims):
        print(f'FAILED {psd}: {r.stderr.strip()[:200]}', file=sys.stderr)
        os.path.exists(tmp) and os.remove(tmp)
        return False
    os.rename(tmp, jpg)
    was_tracked = a.git and tracked(psd)
    if was_tracked:
        subprocess.run(['git', '-C', os.path.dirname(psd), 'rm', '-q', '--cached', '--', os.path.basename(psd)])
    os.remove(psd)
    if a.git and subprocess.run(['git', '-C', os.path.dirname(jpg), 'rev-parse'], capture_output=True).returncode == 0:
        subprocess.run(['git', '-C', os.path.dirname(jpg), 'add', '-f', '--', os.path.basename(jpg)])
    rename_note(psd + '.md', jpg + '.md')
    for root in a.notes_root:          # the note's copy at the same place under ROOT (the site copy of a PATH)
        for top in map(os.path.abspath, a.paths):
            if os.path.abspath(psd).startswith(top + os.sep):
                cand = os.path.join(root, os.path.relpath(os.path.abspath(psd), top)) + '.md'
                if os.path.isfile(cand):
                    rename_note(cand, os.path.join(root, os.path.relpath(os.path.abspath(jpg), top)) + '.md')
    print(f'{os.path.getsize(jpg) / 1e6:6.1f} MB  {jpg}', flush=True)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--notes-root', action='append', default=[])
    ap.add_argument('--git', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    ok = bad = 0
    for top in a.paths:
        for root, dirs, files in os.walk(top):
            dirs[:] = [d for d in dirs if d != '.git']
            for f in sorted(files):
                if f.lower().endswith('.psd'):
                    if convert(os.path.join(root, f), a):
                        ok += 1
                    else:
                        bad += 1
    print(f'converted {ok}, failed {bad}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
