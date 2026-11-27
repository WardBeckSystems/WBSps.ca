#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Site audits: are the links and the sub-links of WBSps.ca working?

    python3 tools/audit_site.py [--out DIR] [--depth 2] [--pages 300] [--external 60] [--only a,b,...] [--seed N]

Audits (each one passes or fails, with every finding listed):

  doors     the front doors answer: wbsps.ca, www.wbsps.ca, WBSps.Kuzub.com, the GitHub Pages site,
            xtm.wbsps.ca, ward-beck.ca; and wbsps.ca keeps the path when it redirects (wbsps.ca/X -> Pages/X)
  build     the last GitHub Pages build succeeded and was built from what is on main now
  offline   every published page (git ls-files *.html) and every link in it, checked on disk, no network:
              missing      the target is not in the repo at all
              unpublished  the target is on disk but git does not publish it (ignored / untracked; Pages never sees it)
              case         the target exists only in another letter case (Pages is case-sensitive)
              anchor       #name points at no id / name on the target page
              submodule    the target is inside a submodule (served only if that repo is public), counted, not failed
  crawl     a live sample: from the home page, every internal link N levels deep (--depth, at most --pages pages),
            and every link, picture, script and stylesheet on those pages requested from the live site
  external  a live sample (--external) of the links that leave the site: GitHub repos, Google Drive, others

Out (default logs/site_audit/): audit.json (everything), report.html (the report), and a one-line summary per audit.
Exit status: 0 when every audit passes, 1 otherwise.
"""
import argparse
import html
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = 'https://wardbecksystems.github.io/WBSps.ca/'
REPO = 'WardBeckSystems/WBSps.ca'
DOORS = [
    ('https://wbsps.ca/', SITE),
    ('https://www.wbsps.ca/', SITE),
    ('https://WBSps.Kuzub.com/', None),
    (SITE, None),
    ('https://xtm.wbsps.ca/', None),
    ('https://ward-beck.ca/', None),
]
PATH_KEPT = ['PAGES/M450A.html', '2026/STATUS.html', '2026/Engineering/PINOUTS.html']
UA = 'Mozilla/5.0 (compatible; WBSps-site-audit/1.0)'
LINK_ATTRS = {('a', 'href'), ('link', 'href'), ('img', 'src'), ('script', 'src'), ('iframe', 'src'), ('source', 'src'),
              ('video', 'src'), ('audio', 'src'), ('embed', 'src'), ('object', 'data'), ('area', 'href')}


class Links(HTMLParser):
    """Every link of a page (tag, attribute, value) and every id / name it defines."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.ids, self.base = [], set(), None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k in ('id', 'name'):
            if a.get(k):
                self.ids.add(a[k])
        if tag == 'base' and a.get('href'):
            self.base = a['href']
        if tag == 'link' and (a.get('rel') or '').lower() in ('preconnect', 'dns-prefetch'):
            return   # a hint to the browser, not a link
        for (t, attr) in LINK_ATTRS:
            if tag == t and a.get(attr):
                self.links.append((tag, a[attr].strip()))
        if tag in ('img', 'source') and a.get('srcset'):
            for part in a['srcset'].split(','):
                if part.strip():
                    self.links.append((tag, part.strip().split()[0]))


def parse(text):
    p = Links()
    try:
        p.feed(text)
    except Exception:
        pass
    return p


def skip(url):
    return (not url or url.startswith(('mailto:', 'tel:', 'javascript:', 'data:', 'blob:', 'about:', '#!'))
            or '${' in url or '{{' in url or url.startswith('{'))


# ---- network ----

PACE = 0.25   # seconds between requests per worker: GitHub Pages answers 429 to a crawler in a hurry
_last = {}


def fetch(url, method='HEAD', timeout=20, body=False, tries=4):
    """(status, final url, text or None, error), politely: paced per host, a 429 waits (Retry-After) and tries again."""
    for k in range(tries):
        host = urlsplit(url).netloc.lower()
        wait = _last.get(host, 0) + PACE - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.time()
        r = _fetch(url, method, timeout, body)
        if r[0] != 429 or k == tries - 1:
            return r
        time.sleep(min(60, 5 * 2 ** k))
    return r


def _fetch(url, method='HEAD', timeout=20, body=False):
    """(status, final url, text or None, error). HEAD first; GET when HEAD is refused or the body is wanted."""
    req = urllib.request.Request(url, method='GET' if body else method, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = None
            if body and 'html' in (r.headers.get('Content-Type') or ''):
                text = r.read(3_000_000).decode('utf-8', 'replace')
            return r.status, r.geturl(), text, None
    except urllib.error.HTTPError as e:
        if not body and e.code in (403, 405, 501):   # HEAD refused: ask with GET
            return _fetch(url, timeout=timeout, body=True)[:2] + (None, None)
        return e.code, url, None, None
    except Exception as e:
        return None, url, None, f'{type(e).__name__}: {e}'[:200]


def audit_doors():
    findings = []
    for url, want in DOORS:
        st, final, _, err = fetch(url, body=True)
        ok = st == 200 and (want is None or final.rstrip('/').lower().startswith(want.rstrip('/').lower()))
        findings.append({'ok': ok, 'url': url, 'status': st, 'final': final, 'error': err,
                         'want': want and f'lands on {want}'})
    for p in PATH_KEPT:
        st, final, _, err = fetch('https://wbsps.ca/' + p)
        ok = st == 200 and final.endswith(p)
        findings.append({'ok': ok, 'url': 'https://wbsps.ca/' + p, 'status': st, 'final': final, 'error': err,
                         'want': 'keeps the path'})
    return findings


def audit_build():
    def gh(path):
        r = subprocess.run(['gh', 'api', path], capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout) if r.returncode == 0 else None
    builds = gh(f'repos/{REPO}/pages/builds') or []
    head = subprocess.run(['git', '-C', ROOT, 'rev-parse', 'origin/main'], capture_output=True, text=True).stdout.strip()
    done = [b for b in builds if b.get('status') in ('built', 'errored')]
    last_built = next((b for b in builds if b.get('status') == 'built'), None)
    running = [b for b in builds if b.get('status') in ('building', 'queued')]
    f = []
    if not builds:
        f.append({'ok': False, 'what': 'no Pages builds visible (gh api)'})
        return f
    f.append({'ok': bool(last_built), 'what': 'last successful build',
              'commit': (last_built or {}).get('commit', '')[:9], 'at': (last_built or {}).get('created_at')})
    f.append({'ok': bool(last_built) and last_built.get('commit') == head, 'what': 'serving origin/main',
              'commit': head[:9], 'note': 'a newer build is running' if running else ''})
    for b in done[:5]:
        if b.get('status') == 'errored':
            # A build GitHub cancelled for a newer push is not a failure of the site
            f.append({'ok': True, 'what': 'errored build (superseded by a newer push)' if b is not done[0] else 'errored build',
                      'commit': b.get('commit', '')[:9], 'at': b.get('created_at'),
                      'error': (b.get('error') or {}).get('message')})
    return f


# ---- offline ----

def published():
    out = subprocess.run(['git', '-C', ROOT, 'ls-files', '-s'], capture_output=True, text=True).stdout.splitlines()
    files, subs = set(), set()
    for ln in out:
        mode, _, rest = ln.partition(' ')
        path = rest.split('\t', 1)[1]
        (subs if mode == '160000' else files).add(path)
    return files, subs


def audit_offline(sample=None, seed=1):
    files, subs = published()
    lower = defaultdict(list)
    for f in files:
        lower[f.lower()].append(f)
    dirs = {os.path.dirname(f) for f in files}
    alldirs = set()
    for d in dirs:
        while d and d not in alldirs:
            alldirs.add(d)
            d = os.path.dirname(d)
    pages = sorted(f for f in files if f.lower().endswith(('.html', '.htm')))
    if sample and sample < len(pages):
        pages = sorted(random.Random(seed).sample(pages, sample))
    ids_cache = {}

    def ids_of(path):
        if path not in ids_cache:
            try:
                ids_cache[path] = parse(open(os.path.join(ROOT, path), encoding='utf-8', errors='replace').read()).ids
            except OSError:
                ids_cache[path] = set()
        return ids_cache[path]

    def in_sub(path):
        return next((s for s in subs if path == s or path.startswith(s + '/')), None)

    findings, counts, external = [], Counter(), []
    for page in pages:
        try:
            text = open(os.path.join(ROOT, page), encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        p = parse(text)
        ids_cache[page] = p.ids
        base = '/' + page
        for tag, url in p.links:
            if skip(url):
                continue
            counts['links'] += 1
            sp = urlsplit(url)
            if sp.scheme in ('http', 'https') or url.startswith('//'):
                full = url if sp.scheme else 'https:' + url
                if full.lower().startswith(SITE.lower()) or urlsplit(full).netloc.lower() in ('wbsps.ca', 'www.wbsps.ca'):
                    path = urlsplit(full).path
                    path = path[len('/WBSps.ca'):] if path.lower().startswith('/wbsps.ca') else path
                    url, sp = path + (('#' + urlsplit(full).fragment) if urlsplit(full).fragment else ''), urlsplit(path)
                else:
                    external.append({'page': page, 'tag': tag, 'url': full})
                    counts['external'] += 1
                    continue
            if sp.scheme:
                continue
            target = unquote(urljoin(base, sp.path)).lstrip('/') if sp.path else page
            target = os.path.normpath(target).replace(os.sep, '/') if target else ''
            if target in ('.', ''):
                target = 'index.html'
            frag = unquote(sp.fragment)
            kind = None
            if target in files:
                pass
            elif target in alldirs or target.endswith('/'):
                idx = target.rstrip('/') + '/index.html'
                if idx in files:
                    target = idx
                else:
                    kind = 'missing'   # a folder with no index.html: Pages answers 404
            elif in_sub(target):
                counts['submodule'] += 1
                continue
            elif target.lower() in lower:
                kind = 'case'
            elif os.path.exists(os.path.join(ROOT, target)):
                kind = 'unpublished'
            else:
                kind = 'missing'
            if not kind and frag and target.lower().endswith(('.html', '.htm')) and frag not in ids_of(target):
                if not re.match(r'^(top|/|!|$)', frag) and '=' not in frag:
                    kind = 'anchor'
            if kind:
                counts[kind] += 1
                findings.append({'kind': kind, 'page': page, 'tag': tag, 'link': url, 'target': target,
                                 'did_you_mean': lower.get(target.lower(), [None])[0] if kind == 'case' else None})
            else:
                counts['ok'] += 1
    counts['pages'] = len(pages)
    sections = Counter((x['kind'], section(x['page'])) for x in findings)
    counts['by_section'] = sorted(([k, s, n] for (k, s), n in sections.items()), key=lambda x: -x[2])
    return findings, counts, external


def section(page):
    """The part of the site a page belongs to: 2026/PAGES, Consoles/1980-1989, WEBSITE HISTORY ..."""
    parts = page.split('/')
    if parts[0] == '2026' and len(parts) > 2:
        return '/'.join(parts[:2]) if parts[1] not in ('Consoles', 'Modules', 'DOCUMENTS', 'PHOTOS') else '/'.join(parts[:3])[:40]
    return '/'.join(parts[:2])[:40] if len(parts) > 2 else parts[0] if len(parts) == 2 else '(top)'


# ---- live ----

def audit_crawl(depth, max_pages, workers=3):
    seen_pages, queue, checked, findings = set(), [(SITE, 0)], {}, []
    pages_meta = []
    pool = ThreadPoolExecutor(workers)
    while queue and len(seen_pages) < max_pages:
        batch = []
        while queue and len(batch) < workers and len(seen_pages) + len(batch) < max_pages:
            u, d = queue.pop(0)
            u = urlunsplit(urlsplit(u)._replace(fragment=''))
            if u in seen_pages:
                continue
            seen_pages.add(u)
            batch.append((u, d))
        for (u, d), (st, final, text, err) in zip(batch, pool.map(lambda x: fetch(x[0], body=True), batch)):
            checked[u] = (st, err)
            pages_meta.append({'url': u, 'depth': d, 'status': st})
            if st != 200 or not text:
                if st != 200:
                    findings.append({'kind': 'page', 'url': u, 'status': st, 'error': err, 'from': None})
                continue
            p = parse(text)
            for tag, link in p.links:
                if skip(link):
                    continue
                full = urlunsplit(urlsplit(urljoin(p.base and urljoin(final, p.base) or final, link))._replace(fragment=''))
                if not full.lower().startswith(SITE.lower()):
                    continue
                if full not in checked:
                    checked[full] = None
                    pages_meta.append({'url': full, 'from': u, 'tag': tag, 'depth': d + 1, 'status': None})
                if tag == 'a' and d + 1 <= depth and full.lower().endswith(('.html', '.htm', '/')) and full not in seen_pages:
                    queue.append((full, d + 1))
    todo = [m for m in pages_meta if m['status'] is None and checked.get(m['url']) is None]
    uniq = list({m['url']: m for m in todo}.values())
    for m, (st, final, _, err) in zip(uniq, pool.map(lambda m: fetch(m['url']), uniq)):
        checked[m['url']] = (st, err)
        if st != 200:
            findings.append({'kind': 'rate-limited' if st == 429 else 'link', 'url': m['url'], 'status': st, 'error': err,
                             'from': m.get('from'), 'tag': m.get('tag')})
    pool.shutdown()
    return findings, {'pages_crawled': len(seen_pages), 'urls_checked': len(checked),
                      'broken': sum(1 for f in findings if f['kind'] != 'rate-limited'),
                      'limited': sum(1 for f in findings if f['kind'] == 'rate-limited'), 'depth': depth}


def audit_external(external, n, seed=1, workers=8):
    uniq = list({e['url']: e for e in external}.values())
    by_host = defaultdict(list)
    for e in uniq:
        by_host[urlsplit(e['url']).netloc.lower()].append(e)
    rnd = random.Random(seed)
    # A spread: every host gets a turn before any host gets a second
    sample, hosts = [], sorted(by_host, key=lambda h: -len(by_host[h]))
    for h in hosts:
        rnd.shuffle(by_host[h])
    while len(sample) < n and any(by_host.values()):
        for h in hosts:
            if by_host[h] and len(sample) < n:
                sample.append(by_host[h].pop())
    findings = []
    with ThreadPoolExecutor(workers) as pool:
        for e, (st, final, _, err) in zip(sample, pool.map(lambda e: fetch(e['url']), sample)):
            if st is not None and st < 400:
                continue
            # 401 / 403 / 429: the site turns robots away; it may well work in a browser
            kind = 'refused' if st in (401, 403, 429) else 'dead host' if st is None else 'broken'
            findings.append({'kind': kind, **e, 'status': st, 'error': err})
    return findings, {'external_links': len(uniq), 'hosts': len(by_host), 'sampled': len(sample), 'broken': len(findings),
                      'top_hosts': Counter(urlsplit(e['url']).netloc.lower() for e in uniq).most_common(8)}


# ---- report ----

def report(out, res):
    e = lambda s: html.escape(str(s if s is not None else ''))
    rows = []
    for name, r in res['audits'].items():
        rows.append(f'<h2 class="{"ok" if r["pass"] else "bad"}">{e(name)}: {"PASS" if r["pass"] else "FAIL"}</h2>'
                    f'<p>{e(r["summary"])}</p>')
        if r.get('by_section'):
            rows.append('<table><tr><th>problem</th><th>part of the site</th><th>links</th></tr>' + ''.join(
                f'<tr class="b"><td>{e(k)}</td><td>{e(s)}</td><td>{n}</td></tr>' for k, s, n in r['by_section'][:30]) + '</table><p></p>')
        items = r.get('findings') or []
        if items:
            keys = [k for k in items[0].keys() if k != 'ok'][:7]
            rows.append('<table><tr>' + ''.join(f'<th>{e(k)}</th>' for k in keys) + '</tr>' + ''.join(
                '<tr class="' + ('' if it.get('ok', False) else 'b') + '">' + ''.join(f'<td>{e(it.get(k))}</td>' for k in keys) + '</tr>'
                for it in items[:400]) + '</table>' + (f'<p>… and {len(items) - 400} more in audit.json</p>' if len(items) > 400 else ''))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Site audit</title><style>
:root {{ --bg:#fbfaf4; --ink:#1f1e1c; --rule:#cfcabc; --ok:#15803d; --bad:#b91c1c; --hl:#fdecea; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1e1d1a; --ink:#e9e5d8; --rule:#4a473f; --ok:#4ade80; --bad:#f87171; --hl:#3b1f1f; }} }}
body {{ background:var(--bg); color:var(--ink); font:14px/1.5 ui-monospace,monospace; margin:0; padding:24px 16px; }}
main {{ max-width:1200px; margin:0 auto }} h1 {{ font-size:18px }} h2 {{ font-size:15px; margin-top:28px }}
h2.ok {{ color:var(--ok) }} h2.bad {{ color:var(--bad) }}
table {{ border-collapse:collapse; width:100%; display:block; overflow-x:auto; font-size:12px }}
th, td {{ border:1px solid var(--rule); padding:2px 6px; text-align:left; vertical-align:top; word-break:break-all }}
tr.b td {{ background:var(--hl) }}
</style></head><body><main><h1>WBSps.ca site audit · {e(res['at'])}</h1>
<p>{e(res['options'])}</p>{''.join(rows)}</main></body></html>"""
    with open(os.path.join(out, 'report.html'), 'w', encoding='utf-8') as fh:
        fh.write(page)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=os.path.join(ROOT, 'logs', 'site_audit'))
    ap.add_argument('--depth', type=int, default=2)
    ap.add_argument('--pages', type=int, default=300)
    ap.add_argument('--external', type=int, default=60)
    ap.add_argument('--offline-sample', type=int, default=0, help='check only N random pages offline (0: all)')
    ap.add_argument('--only', default='doors,build,offline,crawl,external')
    ap.add_argument('--seed', type=int, default=1)
    a = ap.parse_args()
    only = set(a.only.split(','))
    os.makedirs(a.out, exist_ok=True)
    res = {'at': time.strftime('%Y-%m-%d %H:%M'), 'options': vars(a), 'audits': {}}

    def put(name, ok, summary, findings):
        res['audits'][name] = {'pass': ok, 'summary': summary, 'findings': findings}
        print(f'{"PASS" if ok else "FAIL"}  {name:9} {summary}', flush=True)

    if 'doors' in only:
        f = audit_doors()
        put('doors', all(x['ok'] for x in f), f'{sum(x["ok"] for x in f)} of {len(f)} answer as they should', f)
    if 'build' in only:
        f = audit_build()
        put('build', all(x['ok'] for x in f), '; '.join(f'{x["what"]} {x.get("commit", "")}{" (" + x["note"] + ")" if x.get("note") else ""}'
                                                         for x in f if x['what'] in ('last successful build', 'serving origin/main')), f)
    external = []
    if only & {'offline', 'external'}:
        f, c, external = audit_offline(a.offline_sample or None, a.seed)
        if 'offline' in only:
            # an #anchor may be made by the page's script (the simulator): a warning, not a failure
            bad = sum(c[k] for k in ('missing', 'unpublished', 'case'))
            put('offline', bad == 0, f'{c["pages"]} pages, {c["links"]} links: {c["ok"]} ok, {c["missing"]} missing, '
                f'{c["unpublished"]} unpublished, {c["case"]} wrong case, {c["anchor"]} bad anchors, '
                f'{c["submodule"]} into submodules, {c["external"]} external', f)
            res['audits']['offline']['by_section'] = c['by_section']
    if 'crawl' in only:
        f, s = audit_crawl(a.depth, a.pages)
        put('crawl', not s['broken'], f'{s["pages_crawled"]} pages crawled to depth {s["depth"]}, {s["urls_checked"]} URLs checked, '
            f'{s["broken"]} broken' + (f', {s["limited"]} not checked (GitHub rate limit, run again later)' if s['limited'] else ''), f)
    if 'external' in only:
        f, s = audit_external(external, a.external, a.seed)
        k = Counter(x['kind'] for x in f)
        s['broken'] = f"{k['broken']} broken, {k['dead host']} dead hosts, {k['refused']} refused robots (check by hand)"
        put('external', not (k['broken'] or k['dead host']), f'{s["sampled"]} of {s["external_links"]} external links sampled across {s["hosts"]} hosts, '
            f'{s["broken"]}; most linked: ' + ', '.join(f'{h} ({n})' for h, n in s['top_hosts'][:5]), f)
    with open(os.path.join(a.out, 'audit.json'), 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    report(a.out, res)
    print(f'report: {os.path.join(a.out, "report.html")}')
    sys.exit(0 if all(r['pass'] for r in res['audits'].values()) else 1)


if __name__ == '__main__':
    main()
