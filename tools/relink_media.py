#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Point the site's broken links at where the files live now.

    python3 tools/relink_media.py [--dry-run] [--report OUT.json]

The media of WBSps.ca (photos, scans, drawings, PDFs, zips) was moved into the WardBeckSystems repos
(clones in WBSps.ca/Github.WardBeckSystems); the pages still link the old local paths, which GitHub Pages
does not have. For every published page (git ls-files *.html) and every link tools/audit_site.py finds broken:

  case         the file is published in another letter case      -> the published spelling (relative link)
  missing /    the file is in a public WardBeckSystems repo       -> that repo: pictures, scripts, styles and
  unpublished                                                        frames by raw.githubusercontent.com (Git LFS
                                                                     files by media.githubusercontent.com), links
                                                                     to the file's page on github.com
  _previews/<path>.jpg  a generated thumbnail of a moved picture  -> the picture itself, as above

A file is found in the repos by its name (exact, then any letter case) and then by the longest run of folder
names it shares with the old path; a tie between repos, or a match on the name alone when the name is common,
is left as it is and listed. Private repos are never linked (visitors would get a 404); those links are listed.
Run after the pages are made (2026/timelines/run_all.sh, after page_chrome.py); it changes only links that are
broken, so running it again changes nothing.
"""
import argparse
import fnmatch
import html
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CLONES = os.path.join(ROOT, 'WBSps.ca', 'Github.WardBeckSystems')
OWNER = 'WardBeckSystems'
sys.path.insert(0, HERE)
import audit_site  # noqa: E402
import wbs_home  # noqa: E402

SELF = {'wbsps.ca', 'site'}
EMBED = {'img', 'source', 'script', 'link', 'iframe', 'video', 'audio', 'embed', 'object'}


def git(repo, *args):
    return subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True).stdout


def visibility():
    r = subprocess.run(['gh', 'repo', 'list', OWNER, '-L', '1000', '--json', 'name,visibility'], capture_output=True, text=True)
    return {x['name']: x['visibility'] for x in json.loads(r.stdout or '[]')}


def lfs_patterns(clone):
    f = os.path.join(clone, '.gitattributes')
    if not os.path.exists(f):
        return []
    return [ln.split()[0] for ln in open(f, encoding='utf-8', errors='replace') if 'filter=lfs' in ln and ln.split()]


def index_repos(vis):
    """{basename: [(repo, path)]} of every file the public repos track (and the same, lower-cased)."""
    by_name, by_lower, lfs, private = defaultdict(list), defaultdict(list), {}, set()
    for d, clone in sorted(wbs_home.repos().items()):   # every clone, wherever its family folder is
        if not os.path.isdir(os.path.join(clone, '.git')) and not os.path.isfile(os.path.join(clone, '.git')):
            continue
        url = git(clone, 'remote', 'get-url', 'origin').strip()
        m = re.search(r'github\.com[:/]([^/]+)/(.+?)(\.git)?$', url)
        if not m or m.group(1) != OWNER:
            continue
        repo = m.group(2)
        if repo.lower() in SELF:
            continue   # an old clone of the site itself: its files are the site's, not a home for media
        branch = git(clone, 'rev-parse', '--abbrev-ref', 'origin/HEAD').strip().split('/')[-1] or 'main'
        if branch == 'HEAD':
            branch = 'main'
        public = vis.get(repo) == 'PUBLIC'
        if not public:
            private.add(repo)
        lfs[repo] = lfs_patterns(clone)
        # only what GitHub has (a clone may hold commits not pushed yet)
        for path in git(clone, 'ls-tree', '-r', '--name-only', '-z', f'origin/{branch}').split('\0'):
            if path:
                e = (repo, branch, path, public)
                by_name[os.path.basename(path)].append(e)
                by_lower[os.path.basename(path).lower()].append(e)
    return by_name, by_lower, lfs, private


def suffix_score(a, b):
    """How many trailing path components two paths share (any letter case)."""
    x, y = a.lower().split('/'), b.lower().split('/')
    n = 0
    while n < min(len(x), len(y)) and x[-1 - n] == y[-1 - n]:
        n += 1
    return n


def locate(target, by_name, by_lower):
    """(repo entry, why) for a lost file, or (None, why)."""
    t = target
    m = re.match(r'^(?:2026/)?_previews/(.+\.\w+)\.(jpg|png)$', t, re.I)   # a generated thumbnail: the picture itself
    if m:
        t = m.group(1)
    name = os.path.basename(t)
    cands = by_name.get(name) or by_lower.get(name.lower()) or []
    if not cands:
        return None, 'not in any repo'
    scored = sorted(((suffix_score(t, c[2]), c) for c in cands), key=lambda s: -s[0])
    best = scored[0][0]
    top = [c for s, c in scored if s == best]
    if len({(c[0], c[2]) for c in top}) > 1:
        # the same file twice in one repo (or in two): fine when they are the same bytes, else ambiguous
        repos = {c[0] for c in top}
        if len(repos) > 1:
            pub = [c for c in top if c[3]]
            if len({c[0] for c in pub}) == 1:
                top = pub
            else:
                return None, f'ambiguous: {len(top)} candidates in {", ".join(sorted(repos))[:120]}'
    if best < 2 and len(cands) > 1:
        return None, f'name only, {len(cands)} files share it'
    return top[0], f'matched {best} path parts'


def url_for(entry, tag, lfs):
    repo, branch, path, _ = entry
    q = quote(path)
    if tag in EMBED:
        if any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(os.path.basename(path), p) for p in lfs.get(repo, [])):
            return f'https://media.githubusercontent.com/media/{OWNER}/{repo}/{branch}/{q}'
        return f'https://raw.githubusercontent.com/{OWNER}/{repo}/{branch}/{q}'
    return f'https://github.com/{OWNER}/{repo}/blob/{branch}/{q}'


def rel_link(page, target, frag=''):
    r = os.path.relpath(target, os.path.dirname(page) or '.')
    return quote(r.replace(os.sep, '/')) + (('#' + frag) if frag else '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--report', default=None)
    a = ap.parse_args()
    findings, counts, _ = audit_site.audit_offline()
    files, _subs = audit_site.published()
    site_name = defaultdict(list)
    for f in files:
        site_name[os.path.basename(f).lower()].append(f)
    vis = visibility()
    by_name, by_lower, lfs, private = index_repos(vis)
    plan = defaultdict(dict)   # page -> {old link: new link}
    left, why = [], Counter()
    for f in findings:
        kind, page, link, target = f['kind'], f['page'], f['link'], f['target']
        if kind == 'anchor':
            continue
        frag = link.split('#', 1)[1] if '#' in link else ''
        if kind == 'case' and f.get('did_you_mean'):
            plan[page][link] = rel_link(page, f['did_you_mean'], frag)
            why['case'] += 1
            continue
        # The site publishes it under another path (a link with too many or too few ../): a relative link
        here = [s for s in site_name.get(os.path.basename(target).lower(), [])]
        if here:
            scored = sorted(((suffix_score(target, s), s) for s in here), reverse=True)
            if scored[0][0] >= 2 and (len(scored) == 1 or scored[1][0] < scored[0][0]):
                plan[page][link] = rel_link(page, scored[0][1], frag)
                why['site path'] += 1
                continue
        entry, reason = locate(target, by_name, by_lower)
        if entry and not entry[3]:
            left.append({**f, 'why': f'private repo {entry[0]}'})
            why[f'private repo'] += 1
            continue
        if not entry:
            left.append({**f, 'why': reason})
            why[reason.split(':')[0].split(',')[0]] += 1
            continue
        plan[page][link] = url_for(entry, f['tag'], lfs) + (('#' + frag) if frag and f['tag'] == 'a' else '')
        why['to repo'] += 1
    changed = 0
    for page, subs in plan.items():
        p = os.path.join(ROOT, page)
        text = open(p, encoding='utf-8', errors='replace').read()
        new = text
        for old, rep in subs.items():
            for form in {old, html.escape(old, quote=True), old.replace('&', '&amp;')}:
                new = new.replace(f'"{form}"', f'"{rep}"').replace(f"'{form}'", f"'{rep}'")
            # srcset entries are not whole attribute values
            new = re.sub(r'(srcset="[^"]*?)(?<![\w/.%-])' + re.escape(old) + r'(?=[\s,"])', lambda m: m.group(1) + rep, new)
        if new != text:
            changed += 1
            if not a.dry_run:
                with open(p, 'w', encoding='utf-8') as fh:
                    fh.write(new)
    print(f'{sum(len(v) for v in plan.values())} links fixed in {changed} pages ({dict(why)})')
    print(f'{len(left)} left as they are; private repos linked to: {len({l["why"] for l in left if l["why"].startswith("private")})}')
    if a.report:
        json.dump({'fixed': {k: v for k, v in plan.items()}, 'left': left, 'why': why, 'private_repos': sorted(private)},
                  open(a.report, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
