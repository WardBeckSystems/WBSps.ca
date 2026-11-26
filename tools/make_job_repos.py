#!/usr/bin/env python3
"""Console and Intercom: every Ward-Beck job (project) in 2026/Consoles as a folder of its own repository, by job number.

  Console/   → WardBeckSystems/Console    the audio and radio console jobs (and the console folders with no job number)
  Intercom/  → WardBeckSystems/Intercom   the intercom jobs: MicroCOM, MiniCOM, intercom matrices, IFB

Jobs are named YY#### (two-digit year, four-digit number): 5-digit numbers as written in the 1970s and early 1990s
(73035, 94021) are padded (730035, 940021), and folders of the same job are merged. A job is an intercom when its name and
its drawings' names say so (INTERCOM, MicroCOM, MiniCOM, IFB, matrix, communications system, crosspoint...) more than
they say console; INTERCOM_JOBS / CONSOLE_JOBS below settle the rest by hand.

Media are hard links to the archive's own files (no copies, no extra disk) and stay offline (tools/module.gitignore).
Every file git would keep (the .md notes) is taken from the published site's copy (WBSps.ca/Consoles, made by
make_site.py: private and banned files left out, logins and e-mail addresses scrubbed); one not on the site is left out. Each job gets a README with its
files and a link to its page on the archive site; each repository a README and jobs.csv listing every job.

usage: python3 tools/make_job_repos.py        (rerun after the archive changes; the repositories' .git is kept)
"""
import csv, os, re, shutil, subprocess
from collections import defaultdict
from urllib.parse import quote

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(TOP, '2026', 'Consoles')
PUBLISHED = os.path.join(TOP, 'Consoles')   # the site's copy: what may be public
JOBS_CSV = os.path.join(TOP, '2026', 'timelines', 'data', 'jobs.csv')
SITE = 'https://wardbecksystems.github.io/WBSps.ca/2026/Consoles/'
GITIGNORE = os.path.join(TOP, 'tools', 'module.gitignore')
REPOS = {'console': ('Console', 'WardBeckSystems/Console', 'Ward-Beck Systems console jobs',
                     'The audio and radio console jobs of Ward-Beck Systems, one folder per job number (YY####).'),
         'intercom': ('Intercom', 'WardBeckSystems/Intercom', 'Ward-Beck Systems intercom jobs',
                      'The intercom jobs of Ward-Beck Systems (MicroCOM, MiniCOM, intercom matrices, IFB), one folder '
                      'per job number (YY####).')}
ICOM = re.compile(r'INTERCOM|MICRO ?COM|MINI ?COM|\bIFB\b|COMMUNICATIONS? SYSTEM|CROSSPOINT|TALKBACK|MATRIX|PARTY ?LINE|'
                  r'BELT ?PACK|KEY ?PANEL|\bSTATION', re.I)
CONS = re.compile(r'CONSOLE|MIXER|INPUT|FADER|\bR\d{3,4}\b|RENAISS|\bST\d|MONITOR|PROGRAM|\bPGM\b|TURRET|PREAMP', re.I)
INTERCOM_JOBS = set()
CONSOLE_JOBS = set()
JOB_DIR = re.compile(r'^(?:WBS)?(\d{5,6})(?: - (.*))?$')
SKIP_FILES = {'index.html'}   # the archive site's page for the folder: its links only work there


def job_no(n):
    return n if len(n) == 6 else n[:2] + '0' + n[2:]


def clean(name):
    """A folder's name, or '' when it is OCR noise ('_-_ _ - _._. _ _')."""
    name = (name or '').strip(' ,-')
    return name if len(re.findall(r'[A-Za-z]', name)) >= 3 else ''


def yr(y):
    """The archive's year format: YYYY|n, n = YYYY-1967."""
    return f'{y}\\|{int(y) - 1967}' if str(y).isdigit() else str(y)


def safe(s):
    return re.sub(r'[\\/:*?"<>|]', '-', s).strip()


def files_of(d):
    for root, dirs, files in os.walk(d):
        dirs[:] = sorted(x for x in dirs if not x.startswith('.'))
        for f in sorted(files):
            if f in SKIP_FILES and root == d:
                continue
            yield os.path.relpath(os.path.join(root, f), d)


def collect():
    years = {}
    try:
        for r in csv.DictReader(open(JOBS_CSV, encoding='utf-8')):
            years[job_no(r['job'])] = r.get('year') or ''
    except OSError:
        pass
    jobs, other = defaultdict(list), []
    for dec in sorted(os.listdir(SRC)):
        p = os.path.join(SRC, dec)
        if not os.path.isdir(p):
            continue
        for d in sorted(os.listdir(p)):
            if not os.path.isdir(os.path.join(p, d)) or d == dec:
                continue
            m = JOB_DIR.match(d)
            if m and dec[:2] in ('19', '20'):
                jobs[job_no(m.group(1))].append((dec, d, clean(m.group(2))))
            elif dec not in ('Binder spines',):
                other.append((dec, d))
    return jobs, other, years


def kind_of(no, folders):
    if no in INTERCOM_JOBS:
        return 'intercom'
    if no in CONSOLE_JOBS:
        return 'console'
    names = ' '.join(n for _, _, n in folders)
    text = ' '.join(f for dec, d, _ in folders for f in os.listdir(os.path.join(SRC, dec, d))
                    if not f.endswith(('.md', '.json', '.dxf', '.html')))
    i = 5 * len(ICOM.findall(names)) + len(ICOM.findall(text))
    c = 5 * len(CONS.findall(names)) + len(CONS.findall(text))
    return 'intercom' if i > c else 'console'


PENDING = []
ORIGIN = {}   # repo file -> its published copy


def publish_only(repo):
    """Each file git would keep: the published copy instead of the archive's, or nothing when the site has none."""
    if not os.path.isdir(os.path.join(repo, '.git')):
        subprocess.run(['git', 'init', '-q', '-b', 'main', repo], check=True)
    out = subprocess.run(['git', '-C', repo, 'ls-files', '-z', '-o', '-c', '--exclude-standard'], capture_output=True,
                         check=True).stdout.decode().split('\0')
    dropped = 0
    for rel in filter(None, out):
        dst = os.path.join(repo, rel)
        pub = ORIGIN.get(dst)
        if pub is None or not os.path.isfile(dst):
            continue      # the repo's own files: READMEs, jobs.csv, .gitignore
        os.remove(dst)
        if os.path.isfile(pub):
            shutil.copy2(pub, dst)
        else:
            dropped += 1
    return dropped


def link_into(src_dir, dst_dir, prefix=''):
    n = 0
    for rel in files_of(src_dir):
        dst = os.path.join(dst_dir, prefix, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.lexists(dst):
            os.remove(dst)
        ORIGIN[dst] = os.path.join(PUBLISHED, os.path.relpath(src_dir, SRC), rel)
        try:
            os.link(os.path.join(src_dir, rel), dst)
        except OSError:
            shutil.copy2(os.path.join(src_dir, rel), dst)
        n += 1
    return n


def page(dec, d):
    return SITE + quote(f'{dec}/{d}/index.html')


def job_readme(path, title, no, year, kind, folders, notes):
    lines = [f'# {title}', '', f'Ward-Beck Systems job **{no}**' + (f', {yr(year)}' if year else '') + f' ({kind}).', '',
             'In the archive: ' + ', '.join(f'[{dec}/{d}]({page(dec, d)})' for dec, d, _ in folders), '',
             'Scans, photos and PDFs stay offline; the notes (`.md`, the text read from each page) are here.', '']
    if notes:
        lines += ['## Files', ''] + [f'- [{n[:-3]}]({quote(n)})' for n in notes] + ['']
    lines += ['---', '© Ward-Beck Systems · archive by Anthony Peter Kuzub · [WBSps.ca](https://WBSps.ca)', '']
    open(os.path.join(path, 'README.md'), 'w', encoding='utf-8').write('\n'.join(lines))


def main():
    jobs, other, years = collect()
    rows = defaultdict(list)
    for name, *_ in REPOS.values():
        repo = os.path.join(TOP, name)
        os.makedirs(repo, exist_ok=True)
        for e in os.listdir(repo):    # rebuilt every run; the .git and the repo's own files stay
            if e not in ('.git', '.gitignore', '.gitmodules'):
                p = os.path.join(repo, e)
                shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
        shutil.copy(GITIGNORE, os.path.join(repo, '.gitignore'))
    for no in sorted(jobs):
        folders = jobs[no]
        kind = kind_of(no, folders)
        names = [n for _, _, n in folders if n]
        what = max(names, key=lambda s: (sum(ch.isupper() for ch in s), len(s))) if names else ''
        year = years.get(no) or ('19' if no[:2] > '30' else '20') + no[:2]
        title = f'{no} - {what}' if what else no
        dst = os.path.join(TOP, REPOS[kind][0], safe(title))
        os.makedirs(dst, exist_ok=True)
        count = 0
        for dec, d, _ in folders:
            count += link_into(os.path.join(SRC, dec, d), dst, '' if len(folders) == 1 else safe(d))
        PENDING.append((dst, title, no, year, kind, folders))
        rows[kind].append(dict(job=no, year=year, name=what, folder=safe(title), files=count,
                               archive=';'.join(f'{dec}/{d}' for dec, d, _ in folders)))
    for dec, d in other:     # console folders with no job number: drawings, models, manuals
        dst = os.path.join(TOP, REPOS['console'][0], '_other', safe(dec), safe(d))
        count = link_into(os.path.join(SRC, dec, d), dst)
        rows['other'].append(dict(job='', year=dec, name=d, folder=f'_other/{safe(dec)}/{safe(d)}', files=count,
                                  archive=f'{dec}/{d}'))
    for name, *_ in REPOS.values():
        print(name, 'left out (not on the site):', publish_only(os.path.join(TOP, name)))
    for dst, title, no, year, kind, folders in PENDING:
        notes = sorted(os.path.relpath(os.path.join(r, f), dst) for r, _, fs in os.walk(dst) for f in fs
                       if f.endswith('.md') and f != 'README.md' and os.path.isfile(ORIGIN.get(os.path.join(r, f), '')))
        job_readme(dst, title, no, year, kind, folders, notes)
    for kind, (name, full, title, about) in REPOS.items():
        repo = os.path.join(TOP, name)
        with open(os.path.join(repo, 'jobs.csv'), 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, ['job', 'year', 'name', 'folder', 'files', 'archive'])
            w.writeheader()
            w.writerows(rows[kind] + (rows['other'] if kind == 'console' else []))
        lines = [f'# {title}', '', about, '',
                 'Scans, photos and PDFs stay offline in the archive; the notes (`.md`, the text read from each page), '
                 'documents and drawings are here. Built from `WBSps.ca/2026/Consoles` by `tools/make_job_repos.py`; '
                 f'every job is also in `jobs.csv`.', '',
                 f'## {len(rows[kind])} jobs', '', '| Job | Year | Client / what | Files |', '|---|---|---|---|']
        lines += [f"| [{r['job']}]({quote(r['folder'])}/) | {yr(r['year'])} | {r['name']} | {r['files']} |" for r in rows[kind]]
        if kind == 'console' and rows['other']:
            lines += ['', '## Console folders with no job number', '', '| Folder | Files |', '|---|---|']
            lines += [f"| [{r['archive']}]({quote(r['folder'])}/) | {r['files']} |" for r in rows['other']]
        other_name, other_full = [(n, fu) for k, (n, fu, *_) in REPOS.items() if k != kind][0]
        lines += ['', f'The {other_name.lower()} jobs are in [{other_full}](https://github.com/{other_full}).', '',
                  '---', '© Ward-Beck Systems · archive by Anthony Peter Kuzub · [WBSps.ca](https://WBSps.ca) · '
                  '[WBSps.Kuzub.com](https://WBSps.Kuzub.com)', '']
        open(os.path.join(repo, 'README.md'), 'w', encoding='utf-8').write('\n'.join(lines))
        print(f'{name}: {len(rows[kind])} jobs' + (f' + {len(rows["other"])} folders' if kind == 'console' else ''))


if __name__ == '__main__':
    main()
