#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""The published site: WBSps.ca and every public submodule at its recorded commit, small files only.

    python3 tools/pages_build.py OUT [--max-bytes 2000000] [--jobs 8] [--only SUBMODULE-PATH ...]

GitHub Pages cannot take the whole archive (the module repos alone are 36 GB; a Pages site is ~1-10 GB), so the site
holds the pages and everything up to --max-bytes (pages, notes, SVG, traced JSON, KiCad, small pictures). A larger file
stays in its repository: 404.html sends a link to it on to the file on GitHub.

No submodule is checked out: each is fetched at its gitlink's commit with --filter=blob:limit (big blobs never
download), and its small blobs are written straight from git (cat-file --batch). Nested submodules and LFS pointers are
skipped, and so are DXF drawings and Rust build output (OFF_SITE). Runs in CI (.github/workflows/pages.yml) and locally.
"""
import os, re, shutil, subprocess, sys, tempfile, threading
from concurrent.futures import ThreadPoolExecutor

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_TOP = ('.github/', '.gitmodules', '.gitignore', '.gitattributes')
LFS = b'version https://git-lfs.github.com/spec/'
PAGE = re.compile(rb'\.(html?|js|css|webmanifest)$', re.I)   # the site's code: never capped (data and pictures are)
PAGE_LIMIT = 100_000_000   # GitHub's own file limit
# Not on the site (the 10 GB limit), opened from GitHub by 404.html: DXF drawings (3.6 GB, no viewer draws them) and
# Rust build output committed with the module plugins (SOFTWARE/plugin/target/, 0.9 GB).
OFF_SITE = re.compile(rb'(\.dxf$|(^|/)target/(release|debug)/)', re.I)


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def git(d, *a, inp=None):
    r = subprocess.run(['git', '-C', d, *a], capture_output=True, input=inp)
    if r.returncode:
        raise RuntimeError(f'git {" ".join(a)} in {d}: {r.stderr.decode(errors="replace").strip()}')
    return r.stdout


def small_blobs(repo, rev, limit):
    """[(path, sha, size)] of the files at rev no bigger than limit (gitlinks, symlinks and LFS pointers left out)."""
    out = []
    for line in git(repo, 'ls-tree', '-r', '-l', '-z', rev).split(b'\0'):
        if not line:
            continue
        meta, path = line.split(b'\t', 1)
        mode, kind, sha, size = meta.split()
        if kind != b'blob' or mode == b'120000' or size == b'-' or OFF_SITE.search(path):
            continue
        if int(size) > limit and not (PAGE.search(path) and int(size) <= PAGE_LIMIT):   # the site's own pages always go
            continue
        out.append((path.decode(), sha.decode(), int(size)))
    return out


def write_blobs(repo, blobs, dest):
    """Write blobs (cat-file --batch: one process for the whole repo)."""
    if not blobs:
        return 0, 0
    proc = subprocess.Popen(['git', '-C', repo, 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def feed():   # in its own thread: written all at once it deadlocks when cat-file's output pipe fills
        proc.stdin.write(''.join(f'{sha}\n' for _, sha, _ in blobs).encode())
        proc.stdin.close()
    threading.Thread(target=feed, daemon=True).start()
    n = total = 0
    for path, sha, size in blobs:
        head = proc.stdout.readline().split()
        if len(head) < 3 or head[1] == b'missing':
            continue
        data = proc.stdout.read(int(head[2]))
        proc.stdout.read(1)
        if data.startswith(LFS):
            continue
        p = os.path.join(dest, path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as fh:
            fh.write(data)
        n += 1
        total += size
    proc.wait()
    return n, total


def submodules():
    """[(path, url, sha)] for every gitlink of HEAD that .gitmodules names."""
    urls = dict(re.findall(r'^\s*path = (.*)\n\s*url = (.*)$', open(os.path.join(TOP, '.gitmodules')).read(), re.M))
    out = []
    for line in git(TOP, 'ls-tree', '-r', '-z', 'HEAD').split(b'\0'):
        if line.startswith(b'160000'):
            meta, path = line.split(b'\t', 1)
            path = path.decode()
            if path in urls:
                out.append((path, urls[path].strip(), meta.split()[2].decode()))
    return out


def fetch_one(sub, out, limit, work):
    path, url, sha = sub
    d = os.path.join(work, re.sub(r'[^A-Za-z0-9._-]', '_', path))
    try:
        if os.path.isdir(os.path.join(TOP, path, '.git')) or os.path.isfile(os.path.join(TOP, path, '.git')):
            src = os.path.join(TOP, path)   # a local clone has the commit: no network
            git(src, 'cat-file', '-e', sha + '^{commit}')
        else:
            os.makedirs(d, exist_ok=True)
            git(d, 'init', '-q')
            git(d, 'fetch', '-q', '--depth', '1', f'--filter=blob:limit={limit}', url, sha)
            src = d
        n, total = write_blobs(src, small_blobs(src, sha, limit), os.path.join(out, path))
        return path, n, total, None
    except Exception as e:   # a submodule that cannot be read is left out, the rest still publishes
        return path, 0, 0, str(e)[:200]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    out = os.path.abspath(sys.argv[1])
    limit = arg('--max-bytes', 2_000_000)
    jobs = arg('--jobs', 8)
    os.makedirs(out, exist_ok=True)
    blobs = [b for b in small_blobs(TOP, 'HEAD', limit) if not b[0].startswith(SKIP_TOP)]
    n, total = write_blobs(TOP, blobs, out)
    print(f'WBSps.ca: {n} files, {total / 1e6:.0f} MB')
    open(os.path.join(out, '.nojekyll'), 'w').close()
    subs = submodules()
    only = [a for i, a in enumerate(sys.argv) if i and sys.argv[i - 1] == '--only']   # testing: these submodules only
    if only:
        subs = [x for x in subs if any(x[0].startswith(o) for o in only)]
    with tempfile.TemporaryDirectory() as work, ThreadPoolExecutor(jobs) as pool:
        results = list(pool.map(lambda s: fetch_one(s, out, limit, work), subs))
    files = sum(r[1] for r in results) + n
    size = sum(r[2] for r in results) + total
    for path, _, _, err in results:
        if err:
            print(f'LEFT OUT {path}: {err}')
    print(f'{len(subs)} submodules; site: {files} files, {size / 1e9:.2f} GB (files over {limit / 1e6:.1f} MB stay in their repos)')


if __name__ == '__main__':
    main()
