#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Move a local folder's files into its repo clone in WBSps.ca/Github.WardBeckSystems, commit, push, slim .git.

    distribute_to_repo.py SRC CLONE [--sub PATH] [--untracked-only] [--dry-run] [--no-slim]

SRC             the local folder whose files go to the repo (e.g. 2026/Modules/INPUT-PRE-AMPS/M460M)
CLONE           the repo clone (e.g. WBSps.ca/Github.WardBeckSystems/MODULES.INPUT-PRE-AMPS.M460M-Input-Module)
--sub PATH      put the files under PATH inside the clone (default: the clone's root)
--untracked-only  move only files SRC's own git doesn't track (SRC is a checkout of the same repo)

Files are MOVED (same disk, no extra space); a file already in the clone with the same size is just removed
from SRC. Media (PDFs, images, scans) is committed: the clone's media .gitignore is replaced by a junk-only one;
files over 100 MB go through Git LFS. Commits are cut at ~1.5 GB so each push stays under GitHub's 2 GB limit.
After a verified push the clone's .git is swapped for a blobless one (history stays on GitHub, files stay on
disk), because committed media would otherwise sit on the disk twice.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

JUNK_NAMES = {'Thumbs.db', '.DS_Store', 'desktop.ini', '__pycache__'}
# compiler / FPGA build output: regenerated, never archived
# (.tdf/.vhd/.v/.bsf/.lis are design sources and listings: kept)
JUNK_EXT = {'.pyc', '.o', '.obj', '.cdb', '.hdb', '.md5', '.qws', '.kpt', '.tmp', '.pdb', '.ilk', '.ncb', '.sbr',
            '.idb'}
GITIGNORE = """# Ward-Beck archive repo: every document, photo, scan and drawing is kept (PDFs and images included).
# Only OS clutter and build output are ignored.
Thumbs.db
.DS_Store
desktop.ini
__pycache__/
*.pyc
*.o
*.obj
*.tmp
"""
LFS_BYTES = 100 * 1024 * 1024
BATCH_BYTES = 1500 * 1024 * 1024
TRAILER = '\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'


def git(repo, *args, check=True, capture=True, env=None):
    r = subprocess.run(['git', '-C', repo, *args], text=True, env=env,
                       stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None)
    if check and r.returncode:
        raise SystemExit(f'git {" ".join(args)} in {repo} failed:\n{r.stderr}')
    return r.stdout if capture else ''


COMPRESSED = {'.zip', '.7z', '.rar', '.gz', '.tgz', '.bz2', '.xz', '.dmg', '.iso', '.jpg', '.jpeg', '.mp4', '.mov',
              '.mp3', '.png', '.pdf'}


def is_clutter(rel):
    return any(p in JUNK_NAMES or p == '.git' for p in rel.split('/')) or rel.endswith('.pyc')


def zip_big(src, rel):
    """A file over 100 MB that is not compressed already: replaced by <name>.zip (lossless) when that is smaller."""
    p = os.path.join(src, rel)
    if os.path.islink(p) or os.path.getsize(p) <= LFS_BYTES or os.path.splitext(rel)[1].lower() in COMPRESSED:
        return rel
    z = p + '.zip'
    r = subprocess.run(['zip', '-q', '-9', '-j', z, p])
    if r.returncode or not os.path.isfile(z) or os.path.getsize(z) >= os.path.getsize(p):
        os.path.exists(z) and os.remove(z)
        return rel
    print(f'  zipped {rel}: {os.path.getsize(p) / 1e6:.0f} -> {os.path.getsize(z) / 1e6:.0f} MB', flush=True)
    os.remove(p)
    return rel + '.zip'


def is_junk(rel):
    parts = rel.split('/')
    if any(p in JUNK_NAMES or p == '.git' for p in parts):
        return True
    return os.path.splitext(rel)[1].lower() in JUNK_EXT


def source_files(src, untracked_only):
    if untracked_only:
        out = subprocess.run(['git', '-C', src, 'ls-files', '-o', '-z'], stdout=subprocess.PIPE, check=True).stdout
        rels = [p.decode('utf-8', 'surrogateescape') for p in out.split(b'\0') if p]
    else:
        rels = []
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d != '.git']
            for f in files:
                rels.append(os.path.relpath(os.path.join(root, f), src))
    return [r for r in rels if not os.path.islink(os.path.join(src, r))]


def glob_escape(r):
    """A path as a literal .gitignore pattern: wildcards bracketed, a leading # or ! and trailing spaces escaped."""
    r = re.sub(r'([\[*?])', r'[\1]', r)
    r = re.sub(r'^([#!])', r'\\\1', r)
    return re.sub(r' $', '\\ ', r)


def prune_empty(top):
    for root, dirs, files in os.walk(top, topdown=False):
        if root != top and not os.listdir(root):
            os.rmdir(root)


def slim(clone):
    """Swap .git for a blobless clone of the pushed remote; working files stay, index is rebuilt from HEAD."""
    url = git(clone, 'remote', 'get-url', 'origin').strip()
    branch = git(clone, 'rev-parse', '--abbrev-ref', 'HEAD').strip()
    head = git(clone, 'rev-parse', 'HEAD').strip()
    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(clone))) as tmp:
        env = dict(os.environ, GIT_LFS_SKIP_SMUDGE='1')
        subprocess.run(['git', 'clone', '-q', '--filter=blob:none', '--no-checkout', '-b', branch, url, tmp + '/r'],
                       check=True, env=env)
        if git(tmp + '/r', 'rev-parse', 'HEAD').strip() != head:
            raise SystemExit(f'{clone}: remote HEAD differs from local, not slimming')
        shutil.rmtree(os.path.join(clone, '.git'))
        shutil.move(tmp + '/r/.git', os.path.join(clone, '.git'))
    git(clone, 'reset', '-q', env=dict(os.environ, GIT_LFS_SKIP_SMUDGE='1'))
    dirty = git(clone, 'status', '--porcelain', '--untracked-files=no')
    if dirty.strip():
        print(f'WARNING {clone}: dirty after slim:\n{dirty[:2000]}', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('clone')
    ap.add_argument('--sub', default='')
    ap.add_argument('--untracked-only', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--no-slim', action='store_true')
    ap.add_argument('--message', default='')
    ap.add_argument('--max-mb', type=float, default=0, help='leave files bigger than this in SRC (LFS quota)')
    ap.add_argument('--keep-junk', action='store_true', help='move and commit build output too (only OS clutter skipped)')
    ap.add_argument('--zip-big', action='store_true', help='zip (lossless) each file over 100 MB that is not already '
                    'compressed, so it fits GitHub without LFS; what is still over 100 MB goes through LFS')
    ap.add_argument('--local-only', action='append', default=[], help='substring of a path: moved, but gitignored '
                    '(third-party installers)')
    a = ap.parse_args()
    src, clone = a.src.rstrip('/'), a.clone.rstrip('/')
    if git(clone, 'status', '--porcelain').strip():
        raise SystemExit(f'{clone} has uncommitted changes; commit or clean it first')

    rels = source_files(src, a.untracked_only)
    if any(r.lower().endswith('.psd') for r in rels) and not a.dry_run:
        # no PSDs in the archive repos: each becomes a JPEG of its flattened image (tools/psd_to_jpg.py)
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'psd_to_jpg.py'), src])
        rels = source_files(src, a.untracked_only)
    if a.zip_big:
        rels = [zip_big(src, r) for r in rels]
    moves, dupes, conflicts, junk = [], 0, [], 0
    for rel in rels:
        if (is_clutter(rel) if a.keep_junk else is_junk(rel)):
            junk += 1
            continue
        s = os.path.join(src, rel)
        d = os.path.join(clone, a.sub, rel)
        if a.max_mb and os.path.getsize(s) > a.max_mb * 1e6:
            print(f'  too big, left in source: {rel} ({os.path.getsize(s) / 1e6:.0f} MB)')
            continue
        if os.path.lexists(d):
            if os.path.isfile(d) and os.path.getsize(d) == os.path.getsize(s):
                dupes += 1
                if not a.dry_run:
                    os.remove(s)
            else:
                conflicts.append(rel)
            continue
        moves.append((s, d, os.path.join(a.sub, rel)))
    total = sum(os.path.getsize(s) for s, _, _ in moves)
    print(f'{src} -> {clone}: move {len(moves)} ({total / 1e6:.1f} MB), already there {dupes}, '
          f'junk skipped {junk}, conflicts {len(conflicts)}')
    for c in conflicts[:20]:
        print('  conflict (kept in source):', c)
    if a.dry_run:
        return

    gi = os.path.join(clone, '.gitignore')
    local = [r for _, _, r in moves if any(x in r for x in a.local_only)]
    prev = open(gi).read() if os.path.isfile(gi) else ''
    keep_local = [l for l in prev.splitlines() if l.startswith('/') and 'local only' not in l]
    with open(gi, 'w') as f:
        f.write(GITIGNORE.replace('*.o\n*.obj\n', '') if a.keep_junk else GITIGNORE)
        lines = keep_local + ['/' + glob_escape(r) for r in local]
        if lines:
            f.write('# kept on disk only (third-party software, not ours to publish)\n' + '\n'.join(dict.fromkeys(lines)) + '\n')
    moves_local = set(local)
    for s, d, _ in moves:
        os.makedirs(os.path.dirname(d), exist_ok=True)
        os.rename(s, d)
    prune_empty(src)

    big = [r for _, d, r in moves if os.path.getsize(d) > LFS_BYTES and r not in moves_local]
    if big:
        git(clone, 'lfs', 'install', '--local')
        with open(os.path.join(clone, '.gitattributes'), 'a') as f:
            for r in big:
                pat = r.replace('\\', '\\\\').replace(' ', '[[:space:]]').replace('#', '\\#')
                f.write(f'{pat} filter=lfs diff=lfs merge=lfs -text\n')

    msg = a.message or f'Archive: every photo, scan, PDF and drawing of {os.path.basename(clone)}'
    # the .gitignore/.gitattributes first, then the files in pushes under GitHub's 2 GB limit
    git(clone, 'add', '-f', '--', '.gitignore', *(['.gitattributes'] if big else []))
    batch, size, n = [], 0, 0
    def flush():
        nonlocal batch, size, n
        if not batch and n:
            return
        for i in range(0, len(batch), 500):
            git(clone, 'add', '-f', '--', *batch[i:i + 500])
        n += 1
        git(clone, 'commit', '-q', '-m', f'{msg}' + (f' (part {n})' if total > BATCH_BYTES else '') + TRAILER)
        git(clone, 'push', '-q', 'origin', 'HEAD', capture=False)
        batch, size = [], 0
        if total > BATCH_BYTES and not a.no_slim:
            slim(clone)   # drop the pushed blobs now, or a big repo piles its whole size up in .git
    def wait_for_disk():
        import time
        while shutil.disk_usage(clone).free < 3 * 1024 ** 3:
            print(f'  {clone}: under 3 GB free, waiting', flush=True)
            time.sleep(60)
    for _, d, r in moves:
        if r in moves_local:
            continue
        batch.append(r)
        size += os.path.getsize(d)
        if size >= BATCH_BYTES:
            wait_for_disk()
            flush()
    flush()
    left = git(clone, 'status', '--porcelain')
    if left.strip():
        print(f'NOTE {clone}: not committed (ignored/unchanged?):\n{left[:1000]}')
    if not a.no_slim:
        slim(clone)
    print(f'done {clone}: {git(clone, "rev-parse", "--short", "HEAD").strip()}, .git '
          f'{subprocess.run(["du", "-sh", os.path.join(clone, ".git")], stdout=subprocess.PIPE, text=True).stdout.split()[0]}')


if __name__ == '__main__':
    main()
