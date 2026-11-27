#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""What the WBSps.ca forum (Simple Machines, 2006|39 - 2014|47) said about each module, filed in the module's folder:

  <module>/FORUM.md              every topic that names the module: the posts, as quotes, oldest first
  <module>/PHOTOS/FORUM/<file>   the pictures and papers posted with them (only those not already in the archive)

Sources: the forum's database dumps in 2026/_private/wbsps - website ARCHIVE (tandapho_WBSPS004-complete_*.sql.gz,
newest first; an older dump adds the posts the newer one lost) and its attachments/ folders.

Only what the forum showed its readers is kept: subject, board, date, the poster's forum name and the post. E-mail
addresses, IPs and member records never leave the dump; e-mail addresses and phone numbers written in a post are
taken out. Quoted replies ([quote]) are dropped (the post they quote is there already).

Attachments: each is compared first (SHA-256) with every file the archive holds (wbs_timeline.db files / documents);
one the archive has already links to that copy. The rest are copied into the module's PHOTOS/FORUM/ and OCR'd
(2026/timelines/ocr_media.py, the archive's OCR, which reads each distinct file once); their text goes under the
picture in FORUM.md.

    python3 tools/forum_quotes.py [--no-ocr] [M470 ...]
"""
import datetime
import glob
import gzip
import hashlib
import html
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Y2026 = os.path.join(ROOT, '2026')
SRC = os.path.join(Y2026, '_private', 'wbsps - website ARCHIVE')
DB = os.path.join(Y2026, 'timelines', 'wbs_timeline.db')
OCR_PY = os.path.join(ROOT, 'public', 'extractors', 'ocr_tool', 'venv-gpu', 'bin', 'python')
OCR = os.path.join(Y2026, 'timelines', 'ocr_media.py')
OCR_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.pdf', '.tif', '.tiff', '.bmp'}
TABLES = ('smf_boards', 'smf_topics', 'smf_messages', 'smf_attachments')
ESC = {'n': '\n', 'r': '\r', 't': '\t', '0': ''}


# ---- the dump ------------------------------------------------------------------------------------------------------
def rows(sql, table):
    """Every row of INSERT INTO `table` (cols) VALUES (...), (...); as a dict."""
    out = []
    for m in re.finditer(r"INSERT INTO `%s`\s*\(([^)]*)\)\s*VALUES\s*" % table, sql):
        cols, i = re.findall(r'`([^`]+)`', m.group(1)), m.end()
        while True:
            while sql[i].isspace():
                i += 1
            if sql[i] != '(':
                break
            i, row = i + 1, []
            while True:
                while sql[i].isspace():
                    i += 1
                if sql[i] == "'":
                    i, buf = i + 1, []
                    while True:
                        c = sql[i]
                        if c == '\\':
                            buf.append(ESC.get(sql[i + 1], sql[i + 1]))
                            i += 2
                        elif c == "'" and sql[i + 1] == "'":
                            buf.append("'")
                            i += 2
                        elif c == "'":
                            i += 1
                            break
                        else:
                            buf.append(c)
                            i += 1
                    row.append(''.join(buf))
                else:
                    j = i
                    while sql[i] not in ',)':
                        i += 1
                    v = sql[j:i].strip()
                    row.append(None if v == 'NULL' else v)
                while sql[i].isspace():
                    i += 1
                i += 1
                if sql[i - 1] == ')':
                    break
            out.append(dict(zip(cols, row)))
            while sql[i].isspace():
                i += 1
            if sql[i] != ',':
                break
            i += 1
    return out


def load():
    """The forum: boards, topics, posts and attachments by id, the newest dump first, older ones filling gaps."""
    dumps = sorted(glob.glob(os.path.join(SRC, '**', 'tandapho_WBSPS*.sql.gz'), recursive=True), reverse=True)
    dumps.sort(key=lambda p: os.path.basename(p), reverse=True)
    key = {'smf_boards': 'ID_BOARD', 'smf_topics': 'ID_TOPIC', 'smf_messages': 'ID_MSG', 'smf_attachments': 'ID_ATTACH'}
    db = {t: {} for t in TABLES}
    for p in dumps:
        with gzip.open(p, 'rt', encoding='latin-1') as fh:
            sql = fh.read()
        for t in TABLES:
            for r in rows(sql, t):
                db[t].setdefault(r[key[t]], r)
    return db


def attachment_files():
    """ID_ATTACH -> the file on disk (SMF names them <id>_<hash>)."""
    on = {}
    for d in sorted(glob.glob(os.path.join(SRC, '**', 'attachments'), recursive=True)):
        for f in os.listdir(d):
            on.setdefault(f.split('_')[0], os.path.join(d, f))
    return on


# ---- a post as text ------------------------------------------------------------------------------------------------
EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
PHONE = re.compile(r'(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)')


def text_of(body):
    t = html.unescape(html.unescape(body or ''))
    try:   # UTF-8 stored in a latin-1 table
        t = t.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    for _ in range(4):   # nested quotes
        t = re.sub(r'\[quote[^\]]*\].*?\[/quote\]', ' ', t, flags=re.S | re.I)
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.I)
    t = re.sub(r'\[img[^\]]*\].*?\[/img\]', ' ', t, flags=re.S | re.I)
    t = re.sub(r'\[url=([^\]]+)\](.*?)\[/url\]', lambda m: m.group(2) if m.group(2).strip() else m.group(1), t, flags=re.S | re.I)
    t = re.sub(r'\[/?[a-z*][^\]]*\]', '', t, flags=re.I)
    t = re.sub(r'<[^>]+>', '', t)
    t = EMAIL.sub('(e-mail taken out)', t)
    t = PHONE.sub('(phone taken out)', t)
    t = re.sub(r'(?<=[.!:;,)\d])\?\?(?=\s|$)', '', t)   # the backup turned each non-breaking space into '??'
    t = t.replace('\xa0', ' ').replace('\r', '')
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n\s*\n+', '\n\n', t)
    return t.strip()


def when(ts):
    d = datetime.datetime.fromtimestamp(int(ts))
    return f'{d:%b} {d.day}, {d.year}|{d.year - 1967}'


# ---- modules -------------------------------------------------------------------------------------------------------
def module_dirs():
    out = {}
    for d in glob.glob(os.path.join(ROOT, 'Products', 'Modules', '*', '*')):
        if os.path.isdir(d) and re.match(r'R?M\d', os.path.basename(d)):
            out[os.path.basename(d)] = d
    return out


CODE = re.compile(r'(?<![A-Za-z0-9])(R?M) ?-?(\d{3,4})([A-Za-z]{0,3})(?![A-Za-z0-9])')


def codes_in(text, mods):
    found = set()
    for m in CODE.finditer(text):
        base, suf = m.group(1).upper() + m.group(2), m.group(3).upper()
        for k in range(len(suf), -1, -1):   # M470s, M470AS: the longest that is a module
            if base + suf[:k] in mods:
                found.add(base + suf[:k])
                break
    return found


# ---- attachments ---------------------------------------------------------------------------------------------------
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def archive_index():
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    have = {}
    for dest, s in con.execute('SELECT dest, sha256 FROM files'):
        have.setdefault(s, dest)
    return have


def ocr_text(paths):
    """OCR text by file (ocr_media.py's pages table), for the files given."""
    if not paths:
        return {}
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    out = {}
    for p in paths:
        r = con.execute('SELECT id FROM documents WHERE sha256=?', (sha(p),)).fetchone()
        if r:
            t = '\n'.join(x for (x,) in con.execute('SELECT text FROM pages WHERE doc_id=? ORDER BY page', r) if x)
            t = re.sub(r'[ \t]+', ' ', t).strip()
            if sum(c.isalnum() for c in t) >= 12:
                out[p] = t
    return out


def safe(name):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', '_', html.unescape(name)).strip() or 'attachment'


# ---- the pages -----------------------------------------------------------------------------------------------------
def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    mods, db, on = module_dirs(), load(), attachment_files()
    boards = {b['ID_BOARD']: html.unescape(b['name']).strip() for b in db['smf_boards'].values()}
    msgs = sorted(db['smf_messages'].values(), key=lambda m: (int(m['posterTime']), int(m['ID_MSG'])))
    by_topic = defaultdict(list)
    for m in msgs:
        by_topic[m['ID_TOPIC']].append(m)
    atts = defaultdict(list)
    for a in db['smf_attachments'].values():
        if a.get('attachmentType') == '0' and a.get('ID_MSG') not in (None, '0'):
            atts[a['ID_MSG']].append(a)
    # which topics speak of which module: the subject names it (the whole topic), or a post does (that post)
    want = defaultdict(lambda: defaultdict(set))   # code -> topic -> message ids
    for tid, ms in by_topic.items():
        subj = codes_in(html.unescape(ms[0]['subject']), mods)
        for c in subj:
            want[c][tid].update(m['ID_MSG'] for m in ms)
        for m in ms:
            for c in codes_in(html.unescape(m['subject']) + ' ' + text_of(m['body']), mods):
                want[c][tid].add(m['ID_MSG'])
    if args:
        want = {c: v for c, v in want.items() if c in args}
    have = archive_index()
    # attachments: compared first, copied where new
    placed = defaultdict(list)   # msg id -> [(label, link from the module folder, path for OCR or None, note)]
    copied = []
    for code, topics in sorted(want.items()):
        d = mods[code]
        for tid, ids in topics.items():
            for mid in ids:
                for a in atts.get(mid, []):
                    src = on.get(a['ID_ATTACH'])
                    label = safe(a['filename'])
                    if not src:
                        placed[(code, mid)].append((label, None, None, 'not kept: the file is not in the forum backups'))
                        continue
                    s = sha(src)
                    if s in have:
                        rel = os.path.relpath(os.path.join(Y2026, have[s]), d).replace(os.sep, '/')
                        placed[(code, mid)].append((label, rel, None, f'already in the archive: {have[s]}'))
                        continue
                    y = datetime.datetime.fromtimestamp(int(db['smf_messages'][mid]['posterTime'])).year
                    dst = os.path.join(d, 'PHOTOS', 'FORUM', f'{y} - forum {a["ID_ATTACH"]} - {label}')
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    if not os.path.exists(dst):
                        shutil.copy2(src, dst)
                    if os.path.splitext(dst)[1].lower() in OCR_EXT:
                        copied.append(dst)
                    placed[(code, mid)].append((label, os.path.relpath(dst, d).replace(os.sep, '/'), dst, ''))
    # OCR what was copied (after the comparison: only files the archive did not have)
    if copied and '--no-ocr' not in sys.argv:
        py = OCR_PY if os.path.exists(OCR_PY) else sys.executable
        dirs = sorted({os.path.dirname(p) for p in copied})
        env = dict(os.environ, OCR_GPU='1' if 'venv-gpu' in py else '0')
        subprocess.run([py, OCR, DB, '1', *dirs], cwd=os.path.dirname(OCR), env=env)
    texts = ocr_text(copied)
    n_quotes = 0
    for code, topics in sorted(want.items()):
        d = mods[code]
        name = ''
        try:
            name = dict(l.rstrip('\n').split('\t', 1) for l in open(os.path.join(ROOT, 'tools', 'module_names.tsv'), encoding='utf-8')
                        if '\t' in l and not l.startswith('#')).get(code, '')
        except OSError:
            pass
        order = sorted(topics, key=lambda t: int(by_topic[t][0]['posterTime']))
        first = min(int(by_topic[t][0]['posterTime']) for t in order)
        last = max(int(m['posterTime']) for t in order for m in by_topic[t])
        out = [f'# {code}{" — " + name if name else ""}: on the WBSps forum', '',
               f'What owners, technicians and Ward-Beck people said about the {code} on the WBSps.ca forum '
               f'(Simple Machines), {when(first).split(", ")[1]} to {when(last).split(", ")[1]}: '
               f'{len(order)} topic{"s" * (len(order) != 1)}, oldest first. Quoted as posted (contact details taken out). '
               f'Made by tools/forum_quotes.py from the forum\'s database backups.', '']
        for tid in order:
            ms = [m for m in by_topic[tid] if m['ID_MSG'] in topics[tid]]
            if not ms:
                continue
            subj = html.unescape(by_topic[tid][0]['subject']).strip()
            out += [f'## {subj}', '', f'_{boards.get(by_topic[tid][0]["ID_BOARD"], "")} · {when(by_topic[tid][0]["posterTime"])}_', '']
            for m in ms:
                t = text_of(m['body'])
                pics = placed.get((code, m['ID_MSG']), [])
                if not t and not pics:
                    continue
                n_quotes += 1
                if t:
                    out += ['> ' + l if l else '>' for l in t.split('\n')]
                    out.append('')
                out += [f'— **{html.unescape(m["posterName"]).strip()}**, {when(m["posterTime"])}', '']
                for label, link, path, note in pics:
                    if link and path and os.path.splitext(path)[1].lower() in ('.jpg', '.jpeg', '.png', '.gif'):
                        out.append(f'![{label}]({link.replace(" ", "%20")})')
                    elif link:
                        out.append(f'[{label}]({link.replace(" ", "%20")})')
                    else:
                        out.append(f'_{label}_')
                    if note:
                        out.append(f'_{note}_')
                    if path in texts:
                        out += ['', '<details><summary>Text in the picture (OCR)</summary>', '', '```', texts[path], '```',
                                '', '</details>']
                    out.append('')
        open(os.path.join(d, 'FORUM.md'), 'w', encoding='utf-8').write('\n'.join(out).rstrip() + '\n')
    print(f'{len(want)} modules, {n_quotes} quotes; {len(copied)} attachments new to the archive, {len(texts)} with OCR text')


if __name__ == '__main__':
    main()
